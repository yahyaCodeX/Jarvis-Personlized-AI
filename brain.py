# ╔══════════════════════════════════════════════════════════════╗
# ║  JARVIS — Personal AI Voice Assistant for Muhammad Yahya    ║
# ║                                                              ║
# ║  TTS Engine : Windows SAPI via win32com (never hangs)       ║
# ║  Speech     : Parallel streaming — speaks while thinking    ║
# ║  Mode       : Always-listen (no wake word)                  ║
# ║  Speed      : Reduced context window for fast first token   ║
# ╚══════════════════════════════════════════════════════════════╝

import sys
import io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

import speech_recognition as sr
import requests
import os
import json
import threading
import queue
import time
from colorama import init as colorama_init, Fore, Style
from memory import (load_memory, save_memory, add_message,
                    get_context_messages, clear_memory, get_stats)
from commands import handle_command
from actions import dispatch_action
from auth.voice_auth import VoiceAuthenticator

colorama_init(autoreset=True)

# ═══════════════════════════════════════════════════════════════
#  CONSTANTS
# ═══════════════════════════════════════════════════════════════
MODEL      = "qwen2.5:7b"
OLLAMA_URL = "http://localhost:11434/api/chat"

EXIT_COMMANDS = [
    "goodbye", "bye jarvis", "stop jarvis", "exit jarvis", "shut down",
    "go to sleep", "quit jarvis", "jarvis exit", "turn off", "see you"
]

# ═══════════════════════════════════════════════════════════════
#  TTS — Windows SAPI via win32com (the reliable approach)
# ═══════════════════════════════════════════════════════════════
#
#  WHY win32com instead of pyttsx3?
#  ─────────────────────────────────
#  pyttsx3 wraps SAPI but its runAndWait() can HANG permanently
#  when called from a background thread on Windows. This is a
#  known Windows COM threading bug. win32com bypasses pyttsx3
#  and calls SAPI directly with proper COM initialization
#  (CoInitialize), which fixes the hang completely.
#
#  win32com.Speak() is blocking but NEVER hangs — it always
#  returns when speech is done, making it perfect for our
#  sentence-by-sentence queuing approach.
# ───────────────────────────────────────────────────────────────
_tts_queue     = queue.Queue()
_tts_ready     = threading.Event()
_tts_interrupt = threading.Event()
_tts_thread    = None          # Keep reference for watchdog checks


def _tts_worker():
    """
    Runs on its own dedicated thread.
    Uses Windows SAPI directly via win32com — no hangs, no crashes.
    COM must be initialized per-thread on Windows (CoInitialize).
    """
    import pythoncom
    import win32com.client

    # Required: initialize COM for this thread's apartment
    pythoncom.CoInitialize()

    speaker = win32com.client.Dispatch("SAPI.SpVoice")

    # Set voice — try to find a female English voice (Zira/Hazel)
    voices = speaker.GetVoices()
    for i in range(voices.Count):
        v = voices.Item(i)
        name = v.GetDescription().lower()
        if "zira" in name or "hazel" in name:
            speaker.Voice = v
            break

    # Rate: -10 (slowest) to 10 (fastest). 2-3 = fast but clear.
    speaker.Rate   = 2
    speaker.Volume = 100

    _tts_ready.set()   # Signal that TTS is ready

    while True:
        try:
            text = _tts_queue.get(timeout=1)
        except queue.Empty:
            continue

        if text is None:           # Shutdown signal
            _tts_queue.task_done()
            pythoncom.CoUninitialize()
            break

        if not _tts_interrupt.is_set() and text.strip():
            try:
                speaker.Speak(text)   # Blocking but never hangs
            except Exception as e:
                print(f"\n{Fore.RED}⚠️  TTS error: {e}. Reinitializing speaker...")
                try:
                    speaker = win32com.client.Dispatch("SAPI.SpVoice")
                    speaker.Rate   = 2
                    speaker.Volume = 100
                    speaker.Speak(text)   # Retry once with fresh speaker
                except Exception as e2:
                    print(f"{Fore.RED}⚠️  TTS retry failed: {e2}")

        _tts_queue.task_done()


def _ensure_tts_alive():
    """Restart TTS thread if it crashed."""
    global _tts_thread
    if _tts_thread is None or not _tts_thread.is_alive():
        print(f"\n{Fore.YELLOW}⚠️  Restarting TTS thread...")
        _tts_ready.clear()
        _tts_thread = threading.Thread(target=_tts_worker, daemon=True, name="TTS")
        _tts_thread.start()
        _tts_ready.wait(timeout=8)
        print(f"{Fore.GREEN}✅  TTS thread restarted.")


def speak(text, wait=False):
    """
    Print and queue text for speech. Non-blocking by default.
    Set wait=True to block until the text has been spoken.
    """
    print(f"{Fore.CYAN}🤖  Jarvis: {Style.RESET_ALL}{text}")
    _ensure_tts_alive()
    _tts_queue.put(text)
    if wait:
        _tts_queue.join()


def flush_speech():
    """Cancel all speech waiting in the queue (e.g., when user interrupts)."""
    _tts_interrupt.set()
    while not _tts_queue.empty():
        try:
            _tts_queue.get_nowait()
            _tts_queue.task_done()
        except queue.Empty:
            break
    _tts_interrupt.clear()


def wait_for_speech():
    """Block until every queued sentence has been spoken."""
    _tts_queue.join()


# ═══════════════════════════════════════════════════════════════
#  MICROPHONE SETUP
# ═══════════════════════════════════════════════════════════════
# Device 1 = Microphone Array (Realtek) — built-in laptop mic
# Set to None to use Windows default if you change hardware
MIC_DEVICE_INDEX = 1

recognizer = sr.Recognizer()

recognizer.energy_threshold         = 300
recognizer.dynamic_energy_threshold = False
recognizer.pause_threshold          = 2.0
recognizer.operation_timeout        = None

# Minimum silence duration (seconds) that counts as non-speech at all.
# Raised from 0.3 to 0.5 so brief breath pauses inside a sentence don't
# accidentally trigger an early end-of-phrase detection.
recognizer.non_speaking_duration    = 0.5

# ═══════════════════════════════════════════════════════════════
#  LOAD PERSONALITY & MEMORY
# ═══════════════════════════════════════════════════════════════
_personality_path = os.path.join(os.path.dirname(__file__), "personality.txt")
with open(_personality_path, "r", encoding="utf-8") as f:
    SYSTEM_PROMPT = f.read()

conversation_history = load_memory()


# ═══════════════════════════════════════════════════════════════
#  STARTUP
# ═══════════════════════════════════════════════════════════════
def startup():
    global _tts_thread

    print(f"\n{Fore.MAGENTA}{'═'*55}")
    print(f"  🤖  JARVIS — Initializing...")
    print(f"{'═'*55}{Style.RESET_ALL}\n")

    # ── TTS thread ───────────────────────────────────────────────
    print(f"{Fore.YELLOW}  ⏳  Starting TTS engine (Windows SAPI)...", end="", flush=True)
    _tts_thread = threading.Thread(target=_tts_worker, daemon=True, name="TTS")
    _tts_thread.start()
    ok = _tts_ready.wait(timeout=10)
    print(f"\r{Fore.GREEN}  ✅  TTS engine ready {'(SAPI)' if ok else '— WARNING: may have failed'}.")

    # ── Mic calibration (once at startup) ────────────────────────
    print(f"{Fore.YELLOW}  Calibrating microphone...", end="", flush=True)
    with sr.Microphone(device_index=MIC_DEVICE_INDEX) as source:
        recognizer.adjust_for_ambient_noise(source, duration=2)
    # Prevent near-zero calibration — enforce a minimum floor
    if recognizer.energy_threshold < 300:
        recognizer.energy_threshold = 300
    print(f"\r{Fore.GREEN}  Microphone listener calibrated (Pause threshold: 2.0s).")

    # ── Warm up Ollama ────────────────────────────────────────────
    print(f"{Fore.YELLOW}  ⏳  Warming up AI model ({MODEL})...", end="", flush=True)
    try:
        r = requests.post(OLLAMA_URL, json={
            "model":      MODEL,
            "messages":   [{"role": "user", "content": "hi"}],
            "stream":     False,
            "keep_alive": -1,   # Keep model in VRAM permanently
            "options":    {"num_predict": 1}
        }, timeout=45)
        r.raise_for_status()
        print(f"\r{Fore.GREEN}  ✅  AI model loaded and ready.          ")
    except Exception:
        print(f"\r{Fore.RED}  ⚠️  Couldn't warm up model — first response may be slow.")

    print(f"{Fore.BLUE}  📚  Loaded {len(conversation_history)} messages from memory.")

    print(f"\n{Fore.MAGENTA}{'═'*55}")
    print(f"  🤖  JARVIS ONLINE — Always-Listening Mode")
    print(f"  Just talk. Say 'Goodbye' to exit.")
    print(f"{'═'*55}{Style.RESET_ALL}\n")

    speak("Jarvis online. I'm listening, sir.", wait=True)


# ═══════════════════════════════════════════════════════════════
#  THINKING ANIMATION — Shows while waiting for first AI token
# ═══════════════════════════════════════════════════════════════
_thinking = False

def _thinking_animation():
    """Spins a dot animation in the terminal while Ollama thinks."""
    frames = ["🧠  Thinking   ", "🧠  Thinking.  ", "🧠  Thinking.. ", "🧠  Thinking..."]
    i = 0
    while _thinking:
        print(f"\r{Fore.YELLOW}{frames[i % len(frames)]}", end="", flush=True)
        i += 1
        time.sleep(0.35)
    print(f"\r{' '*20}\r", end="", flush=True)


# ═══════════════════════════════════════════════════════════════
#  ASK JARVIS — Streaming: speaks each sentence the moment it's ready
# ═══════════════════════════════════════════════════════════════
def ask_jarvis(user_input):
    """
    Speed strategy:
      1. Reduced context (8 msgs) -> ~2.5x faster first-token time
      2. Reduced num_ctx (1024)   -> less memory = faster processing
      3. Reduced num_predict (80) -> shorter, faster answers
      4. Sentence streaming       -> speak sentence 1 while generating 2
      5. TTS queued non-blocking  -> AI + TTS run in parallel

    Action detection:
      - If the first token starts with '{', we are likely receiving a JSON
        action object. We switch to silent buffering mode (no streaming speak)
        and collect the full response before parsing.
      - If JSON parses and has an 'action' key -> dispatch to actions.py.
      - Otherwise -> treat as normal chat and speak the buffered text.
    """
    global conversation_history, _thinking

    conversation_history = add_message(conversation_history, "user", user_input)

    messages = [{"role": "system", "content": SYSTEM_PROMPT}]
    messages.extend(get_context_messages(conversation_history))

    payload = {
        "model":      MODEL,
        "messages":   messages,
        "stream":     True,
        "keep_alive": -1,   # Keep model in VRAM permanently
        "options":    {
            "num_predict":    128,   # Caps token length for faster generation
            "num_ctx":        2048,  # Reduces prompt evaluation latency
            "temperature":    0.5,   # Focused generation temperature
            "top_p":          0.9,
            "repeat_penalty": 1.1,
        }
    }

    try:
        # Start thinking animation
        _thinking = True
        anim_thread = threading.Thread(target=_thinking_animation, daemon=True)
        anim_thread.start()

        response = requests.post(OLLAMA_URL, json=payload, stream=True, timeout=90)
        response.raise_for_status()

        full_response   = ""
        sentence_buffer = ""
        first_token     = True
        maybe_action    = False   # Flips True when first token looks like JSON

        for line in response.iter_lines():
            if line:
                chunk = json.loads(line)

                if "message" in chunk and "content" in chunk["message"]:
                    token = chunk["message"]["content"]

                    if first_token:
                        _thinking = False
                        anim_thread.join(timeout=1)
                        first_token  = False
                        # Detect action mode: JSON starts with '{'
                        maybe_action = token.lstrip().startswith("{")

                    full_response   += token
                    sentence_buffer += token

                    # ── Normal chat: stream-speak sentence by sentence ────────
                    # Skip this path when we think it's a JSON action response
                    if not maybe_action:
                        if sentence_buffer.rstrip().endswith(('.', '!', '?', '\n')):
                            clean = sentence_buffer.strip()
                            if clean:
                                speak(clean)   # Non-blocking: queued to TTS
                            sentence_buffer = ""

                if chunk.get("done", False):
                    _thinking = False
                    break

        _thinking = False

        # ── Decide: action dispatch or normal chat ────────────────────────────
        trimmed = full_response.strip()

        # Strip markdown code fences the LLM might wrap JSON in
        if trimmed.startswith("```"):
            lines = trimmed.splitlines()
            trimmed = "\n".join(
                l for l in lines if not l.startswith("```")
            ).strip()

        action_dispatched = False
        if maybe_action:
            try:
                parsed = json.loads(trimmed)
                if isinstance(parsed, dict) and "action" in parsed:
                    action_name = parsed["action"]
                    params      = parsed.get("params", {})
                    # Log the dispatch cleanly -- never print raw JSON to console
                    print(f"{Fore.MAGENTA}[ACTION] {action_name}{Style.RESET_ALL}")
                    result = dispatch_action(action_name, params)
                    # Speak the REAL result string from actions.py, not the JSON
                    speak(result, wait=True)
                    action_dispatched = True
                    # Memory stores the spoken result, not raw JSON
                    full_response = result
            except json.JSONDecodeError:
                # Looked like JSON but wasn't -- fall through to normal chat
                pass

        if not action_dispatched:
            # Normal chat: speak any remaining buffered text
            if sentence_buffer.strip():
                speak(sentence_buffer.strip())
            wait_for_speech()

        conversation_history = add_message(conversation_history, "assistant", full_response)
        save_memory(conversation_history)

    except requests.ConnectionError:
        _thinking = False
        speak("I can't reach Ollama, sir. Make sure it's running.", wait=True)
    except requests.Timeout:
        _thinking = False
        speak("The AI is taking too long. Try again, sir.", wait=True)
    except Exception as e:
        _thinking = False
        speak(f"Something went wrong: {str(e)[:60]}", wait=True)


# ═══════════════════════════════════════════════════════════════
#  MAIN LOOP — Always-listen, no wake word
# ═══════════════════════════════════════════════════════════════
if __name__ == "__main__":
    startup()
    
    authenticator = VoiceAuthenticator()

    while True:
        with sr.Microphone(device_index=MIC_DEVICE_INDEX) as source:
            print(f"{Fore.GREEN}Listening...{Style.RESET_ALL}", end="", flush=True)
            try:
                audio_data = recognizer.listen(source, timeout=8, phrase_time_limit=20)
            except sr.WaitTimeoutError:
                # No speech detected within the timeout window
                print(f"\r{' '*25}\r", end="", flush=True)
                continue

        # Immediately save and verify biometric
        with open("temp_speech.wav", "wb") as f:
            f.write(audio_data.get_wav_data())

        if not authenticator.verify("temp_speech.wav"):
            speak("Acoustic fingerprint mismatch. Biometric security protocols engaged. Unauthorized input discarded.", wait=True)
            continue

        # Perform STT
        try:
            text = recognizer.recognize_google(audio_data)
            print(f"\r{Fore.WHITE}👂  You: {Fore.YELLOW}{text}{Style.RESET_ALL}   ")
            heard = text.lower()
        except sr.UnknownValueError:
            print(f"\r{Fore.YELLOW}🔁  Didn't catch that...{Style.RESET_ALL}   ")
            speak("Sorry, I didn't catch that — could you repeat?", wait=True)
            continue
        except sr.RequestError:
            print(f"\n{Fore.RED}🌐  Google Speech API unavailable. Check internet.")
            continue

        # Exit
        if any(cmd in heard for cmd in EXIT_COMMANDS):
            speak("Goodbye sir. Shutting down.", wait=True)
            save_memory(conversation_history)
            break

        # ── Local commands (instant — zero Ollama latency) ────────
        local_response = handle_command(heard)

        if local_response == "__CLEAR_MEMORY__":
            conversation_history = clear_memory()
            speak("Memory wiped. Starting fresh, sir.", wait=True)
            continue

        if local_response == "__STATS__":
            speak(get_stats(conversation_history), wait=True)
            continue

        if local_response:
            speak(local_response, wait=True)
            continue

        # ── AI response ───────────────────────────────────────────
        ask_jarvis(heard)
