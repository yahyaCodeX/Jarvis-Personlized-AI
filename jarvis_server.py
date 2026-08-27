"""
J.A.R.V.I.S Core Daemon — Threaded Audio Architecture
======================================================
Audio capture runs in a dedicated background thread that never touches the
asyncio event loop directly.  PCM chunks are passed to the async world via a
thread-safe queue.  mic_worker() does nothing but dequeue and forward bytes to
Gemini; all blocking work stays off the event loop so WebSocket keepalive pings
are always answered on time.
"""

import asyncio
import json
import math
import os
import psutil
import pyaudio
import pythoncom
import queue as thread_queue
import struct
import threading
import time
import traceback
import websockets
import win32com.client
from dotenv import load_dotenv
from google import genai
from google.genai import types

from auth.voice_auth import VoiceAuthenticator
from commands import (
    fetch_ug_attendance,
    youtube_control,
    web_search_and_navigate,
    browser_viewport_control,
    create_folder,
    assistive_shopping_agent,
    open_application,
    close_application,
    system_control,
    generate_assignment,
    ask_local_qwen,
    open_website,
    play_on_youtube,
    search_google,
    browser_tab_control,
    page_scroll,
    site_interaction,
    search_maps,
    remember_fact,
    get_all_memories,
)

load_dotenv()

# ============================================================
#  Audio constants
# ============================================================
AUDIO_FORMAT       = pyaudio.paInt16
INPUT_SAMPLE_RATE  = 16000
OUTPUT_SAMPLE_RATE = 24000
CHUNK_SIZE         = 1024          # samples per read
MIC_CHANNELS       = 4            # Realtek 4-ch WASAPI array
MIC_DEVICE_INDEX   = 1            # Microphone Array (3- Realtek(R))

print()
print("=" * 60)
print("  J.A.R.V.I.S — THREADED AUDIO ARCHITECTURE")
print(f"  Mic: device {MIC_DEVICE_INDEX}  (4-ch 16kHz WASAPI)")
print("=" * 60)
print()

# ============================================================
#  Global state
# ============================================================
tools_map = {
    "check_attendance":         fetch_ug_attendance,
    "youtube_control":          youtube_control,
    "web_search_and_navigate":   web_search_and_navigate,
    "browser_viewport_control": browser_viewport_control,
    "create_folder":            create_folder,
    "assistive_shopping_agent": assistive_shopping_agent,
    "open_application":         open_application,
    "close_application":        close_application,
    "system_control":           system_control,
    "generate_assignment":      generate_assignment,
    "ask_local_qwen":           ask_local_qwen,
    "open_website":             open_website,
    "play_on_youtube":          play_on_youtube,
    "search_google":            search_google,
    "browser_tab_control":      browser_tab_control,
    "page_scroll":              page_scroll,
    "site_interaction":         site_interaction,
    "search_maps":              search_maps,
    "remember_fact":            remember_fact,
}

connected_clients:  set            = set()
session_running:    bool           = False
is_jarvis_speaking: bool           = False
audio_out_queue:    asyncio.Queue  = None   # type: ignore

# Global mic-thread lifecycle — tracked here so each new session can kill any
# zombie thread left over from a previous crashed session before starting fresh.
_active_mic_stop_event: threading.Event = None  # type: ignore
_active_mic_thread:     threading.Thread = None  # type: ignore

_tool_lock             = asyncio.Lock()
_last_tool_timestamps: dict = {}


# ============================================================
#  Utilities
# ============================================================

def _rms(pcm: bytes) -> float:
    n = len(pcm) // 2
    if n == 0:
        return 0.0
    shorts = struct.unpack(f"<{n}h", pcm)
    return min(1.0, math.sqrt(sum(s * s for s in shorts) / n) / 32768.0 * 5.0)


def speak_tts(text: str) -> None:
    """Blocking Windows SAPI5 TTS — always call via asyncio.to_thread()."""
    try:
        pythoncom.CoInitialize()
        win32com.client.Dispatch("SAPI.SpVoice").Speak(text)
    except Exception as exc:
        print(f"[TTS ERROR] {exc}")
    finally:
        pythoncom.CoUninitialize()


async def broadcast(event_type: str, data: dict) -> None:
    if not connected_clients:
        return
    msg = json.dumps({"type": event_type, **data})
    await asyncio.gather(*[c.send(msg) for c in connected_clients],
                         return_exceptions=True)


async def execute_tool_safely(name: str, args: dict) -> str:
    now = time.time()
    if now - _last_tool_timestamps.get(name, 0) < 8.0:
        print(f"[TOOL DEBOUNCE] Skipped duplicate '{name}'")
        return f"'{name}' already running, sir."
    _last_tool_timestamps[name] = now
    async with _tool_lock:
        fn = tools_map.get(name)
        if fn is None:
            return f"Tool '{name}' not recognised."
        try:
            return str(await asyncio.to_thread(fn, **args))
        except Exception as exc:
            print(f"[TOOL ERROR] {name}: {exc}")
            return f"Error in {name}: {exc}"


# ============================================================
#  System telemetry
# ============================================================

async def telemetry_loop() -> None:
    while True:
        if connected_clients:
            await broadcast("telemetry", {
                "cpu":     psutil.cpu_percent(),
                "ram":     psutil.virtual_memory().percent,
                "gpu":     78.0,
                "latency": 12,
            })
        await asyncio.sleep(1.0)


# ============================================================
#  Background microphone capture thread
# ============================================================

def _mic_capture_thread(
    loop: asyncio.AbstractEventLoop,
    mic_queue: asyncio.Queue,
    stop_event: threading.Event,
) -> None:
    """
    Runs entirely outside the asyncio event loop.

    Reads 4-channel 16kHz PCM from the WASAPI mic, downmixes to mono,
    and posts each chunk to mic_queue using loop.call_soon_threadsafe so the
    async world can consume it without any synchronous delay.

    This thread does ALL the blocking work (stream.read + struct math) so the
    event loop is 100% free to handle WebSocket keepalive pings at all times.
    """
    pa = pyaudio.PyAudio()

    try:
        # Default microphone 1-channel 16kHz capture — Windows WASAPI automatically
        # handles array downmixing, beamforming, and gain amplification.
        stream = pa.open(
            format=pyaudio.paInt16,
            channels=1,
            rate=INPUT_SAMPLE_RATE,
            input=True,
            frames_per_buffer=CHUNK_SIZE,
        )
        print("[MIC THREAD] 1-channel 16kHz default mic stream open.")
    except Exception as exc:
        print(f"[MIC THREAD] Default mic open failed ({exc}), retrying on device 1...")
        stream = pa.open(
            format=pyaudio.paInt16,
            channels=1,
            rate=INPUT_SAMPLE_RATE,
            input=True,
            input_device_index=MIC_DEVICE_INDEX,
            frames_per_buffer=CHUNK_SIZE,
        )

    frame_n    = 0
    last_log   = time.time()

    try:
        while not stop_event.is_set():
            # ── Blocking read (safe here — we're in a thread) ────────────────
            pcm = stream.read(CHUNK_SIZE, exception_on_overflow=False)
            frame_n += 1

            # ── Periodic telemetry print (in thread — no async needed) ───────
            now = time.time()
            if now - last_log >= 2.0:
                n       = len(pcm) // 2
                raw_rms = (math.sqrt(sum(s * s for s in struct.unpack(f"<{n}h", pcm)) / n)
                           / 32768.0) if n else 0.0
                print(
                    f"[MIC THREAD] raw_rms={raw_rms:.4f}"
                    f"  frames={frame_n}"
                    f"  jarvis_speaking={is_jarvis_speaking}"
                )
                last_log = now

            # ── Prevent CPU spin-lock on tiny read bursts ────────────────────
            # If PyAudio returns an unexpectedly small chunk (< 128 frames =
            # 256 bytes), sleep briefly to keep the thread from burning a full
            # CPU core at 100% utilisation.
            if len(pcm) < 256:
                time.sleep(0.005)

            # ── Skip sending while Jarvis is outputting speech ───────────────
            if is_jarvis_speaking:
                continue

            # ── Hand chunk to the async world — zero event-loop blocking ─────
            loop.call_soon_threadsafe(mic_queue.put_nowait, pcm)

    except Exception as exc:
        print(f"[MIC THREAD CRASH] {exc}")
        traceback.print_exc()
    finally:
        stream.stop_stream()
        stream.close()
        pa.terminate()
        print("[MIC THREAD] Stopped.")


# ============================================================
#  Gemini Live Engine
# ============================================================

async def run_gemini_live() -> None:
    global session_running, audio_out_queue, is_jarvis_speaking

    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        msg = "GEMINI_API_KEY not found in .env!"
        print(f"[CRITICAL] {msg}")
        await broadcast("status", {"state": "alert", "message": msg})
        session_running = False
        return

    client   = genai.Client(api_key=api_key, http_options={"api_version": "v1alpha"})
    model_id = "gemini-2.0-flash-exp"

    memories      = get_all_memories()
    system_prompt = (
        "You are J.A.R.V.I.S, an advanced AI operating system.\n"
        "You were created by Muhammad Yahya Siddiqui, a Computer Systems Engineering "
        "student at MUET and a backend software developer. He is your creator and primary user.\n"
        "When asked to remember something, use the `remember_fact` tool.\n"
        f"Memories from previous sessions:\n{memories}"
    )

    # ─────────────────────────────────────────────────────────────────────────
    # Gemini Live config — native server-side VAD is intentionally left active.
    # We stream continuous raw PCM and let Gemini decide turn boundaries.
    # ─────────────────────────────────────────────────────────────────────────
    config = types.LiveConnectConfig(
        response_modalities=["AUDIO"],
        speech_config=types.SpeechConfig(
            voice_config=types.VoiceConfig(
                prebuilt_voice_config=types.PrebuiltVoiceConfig(voice_name="Fenrir")
            )
        ),
        system_instruction=types.Content(
            parts=[types.Part.from_text(text=system_prompt)]
        ),
        tools=[{
            "function_declarations": [
                {
                    "name": "youtube_control",
                    "description": "Manages YouTube: 'search' (opens YouTube search results), 'select_video' (selects video 1, 2, 3, etc. from search results via Tab/Enter), or 'play_direct' (plays directly via pywhatkit). Use 'search' when the user wants to search/browse, and 'select_video' when user asks to click/open a specific video rank.",
                    "parameters": {
                        "type": "OBJECT",
                        "properties": {
                            "action":      {"type": "STRING", "description": "'search', 'select_video', or 'play_direct'"},
                            "query":       {"type": "STRING", "description": "Search query or video title"},
                            "video_index": {"type": "INTEGER", "description": "1-based video index when action is 'select_video'"},
                        },
                        "required": ["action"],
                    },
                },
                {
                    "name": "web_search_and_navigate",
                    "description": "Performs Google search or opens search results immediately: 'google_search' (opens Google search results page) or 'open_result' (opens top Google result or result N).",
                    "parameters": {
                        "type": "OBJECT",
                        "properties": {
                            "action":       {"type": "STRING", "description": "'google_search' or 'open_result'"},
                            "query":        {"type": "STRING", "description": "Search query or topic"},
                            "result_index": {"type": "INTEGER", "description": "1-based result index when action is 'open_result'"},
                        },
                        "required": ["action"],
                    },
                },
                {
                    "name": "browser_viewport_control",
                    "description": "Controls active browser scrolling and tab management: 'scroll_down', 'scroll_up', 'next_tab', 'prev_tab', 'close_tab', or 'select_tab'.",
                    "parameters": {
                        "type": "OBJECT",
                        "properties": {
                            "action": {"type": "STRING", "description": "'scroll_down', 'scroll_up', 'next_tab', 'prev_tab', 'close_tab', or 'select_tab'"},
                            "value":  {"type": "INTEGER", "description": "Scroll pixels (e.g. 500) or tab number (1-9) for 'select_tab'"},
                        },
                        "required": ["action"],
                    },
                },
                {
                    "name": "assistive_shopping_agent",
                    "description": "Assistive E-Commerce Agent (SDG 10 accessibility for visually impaired users). Autonomously searches e-commerce stores using Playwright to extract product titles and prices to read aloud ('search_product'), or fills out checkout shipping forms and Cash on Delivery choices using user details ('checkout_product').",
                    "parameters": {
                        "type": "OBJECT",
                        "properties": {
                            "action": {"type": "STRING", "description": "'search_product' or 'checkout_product'"},
                            "query":  {"type": "STRING", "description": "Product name or search topic"},
                        },
                        "required": ["action"],
                    },
                },
                {
                    "name": "create_folder",
                    "description": "Creates a directory on Desktop, Downloads, Documents, Projects (D:\\Development), or a custom directory path.",
                    "parameters": {
                        "type": "OBJECT",
                        "properties": {
                            "folder_name": {"type": "STRING", "description": "Name of the folder to create"},
                            "location":    {"type": "STRING", "description": "'Desktop', 'Downloads', 'Documents', 'Projects', or absolute path"},
                        },
                        "required": ["folder_name"],
                    },
                },
                {
                    "name": "play_on_youtube",
                    "description": "Searches for and plays any song, music, or video on YouTube.",
                    "parameters": {
                        "type": "OBJECT",
                        "properties": {"query": {"type": "STRING"}},
                        "required": ["query"],
                    },
                },
                {
                    "name": "search_google",
                    "description": "Performs a Google search for any topic.",
                    "parameters": {
                        "type": "OBJECT",
                        "properties": {"query": {"type": "STRING"}},
                        "required": ["query"],
                    },
                },
                {
                    "name": "check_attendance",
                    "description": "Loads MIS university attendance.",
                    "parameters": {"type": "OBJECT", "properties": {}},
                },
                {
                    "name": "open_application",
                    "description": "Opens an application by name.",
                    "parameters": {
                        "type": "OBJECT",
                        "properties": {"app_name": {"type": "STRING"}},
                        "required": ["app_name"],
                    },
                },
                {
                    "name": "close_application",
                    "description": "Safely closes a running application.",
                    "parameters": {
                        "type": "OBJECT",
                        "properties": {"app_name": {"type": "STRING"}},
                        "required": ["app_name"],
                    },
                },
                {
                    "name": "system_control",
                    "description": "Controls system parameters: volume, brightness, lock.",
                    "parameters": {
                        "type": "OBJECT",
                        "properties": {"action": {"type": "STRING"}},
                        "required": ["action"],
                    },
                },
                {
                    "name": "open_website",
                    "description": "Opens a website URL or search in the browser.",
                    "parameters": {
                        "type": "OBJECT",
                        "properties": {"url_or_query": {"type": "STRING"}},
                        "required": ["url_or_query"],
                    },
                },
                {
                    "name": "browser_tab_control",
                    "description": "Manages browser tabs: next_tab, prev_tab, close_tab, select_tab.",
                    "parameters": {
                        "type": "OBJECT",
                        "properties": {
                            "action":    {"type": "STRING"},
                            "tab_index": {"type": "INTEGER"},
                        },
                        "required": ["action"],
                    },
                },
                {
                    "name": "page_scroll",
                    "description": "Scrolls the active browser page or window up or down.",
                    "parameters": {
                        "type": "OBJECT",
                        "properties": {
                            "direction": {"type": "STRING"},
                            "amount":    {"type": "INTEGER"},
                        },
                        "required": ["direction"],
                    },
                },
                {
                    "name": "site_interaction",
                    "description": "Interacts with webpage elements: youtube_search, youtube_select_video, page_search.",
                    "parameters": {
                        "type": "OBJECT",
                        "properties": {
                            "action": {"type": "STRING"},
                            "query":  {"type": "STRING"},
                        },
                        "required": ["action"],
                    },
                },
                {
                    "name": "search_maps",
                    "description": "Launches Google Maps for a location or place search.",
                    "parameters": {
                        "type": "OBJECT",
                        "properties": {"query": {"type": "STRING"}},
                        "required": ["query"],
                    },
                },
                {
                    "name": "remember_fact",
                    "description": "Saves a fact or preference permanently to long-term memory.",
                    "parameters": {
                        "type": "OBJECT",
                        "properties": {"fact": {"type": "STRING"}},
                        "required": ["fact"],
                    },
                },
            ]
        }],
    )

    audio_out_queue = asyncio.Queue()

    # ── Kill any zombie mic thread from a previous crashed session ───────────
    global _active_mic_stop_event, _active_mic_thread
    if _active_mic_stop_event is not None and not _active_mic_stop_event.is_set():
        print("[MIC THREAD] WARNING: Previous mic thread still alive — killing it now.")
        _active_mic_stop_event.set()
    if _active_mic_thread is not None and _active_mic_thread.is_alive():
        _active_mic_thread.join(timeout=3.0)
        print("[MIC THREAD] Previous zombie thread joined.")

    # ── Shared objects for the mic thread ────────────────────────────────────
    mic_queue  = asyncio.Queue()          # PCM chunks produced by the thread
    stop_event = threading.Event()        # signals the thread to exit
    loop       = asyncio.get_running_loop()

    # Register globally so the next session can kill this thread if needed
    _active_mic_stop_event = stop_event

    # Launch the dedicated capture thread
    mic_thread = threading.Thread(
        target=_mic_capture_thread,
        args=(loop, mic_queue, stop_event),
        daemon=True,
        name="jarvis-mic-thread",
    )
    mic_thread.start()
    _active_mic_thread = mic_thread
    print("[MIC THREAD] Background capture thread started.")

    await broadcast("status", {
        "state":   "listening",
        "message": "JARVIS Duplex Engine Online. Listening...",
    })

    # ── mic_worker ───────────────────────────────────────────────────────────
    # Enforces an 8192-byte send threshold (~0.256 s at 16kHz 16-bit mono)
    # to minimize WebSocket frame overhead.  Wrapped in try/except so if the
    # socket closes, it returns cleanly without throwing a fatal traceback.
    # ─────────────────────────────────────────────────────────────────────────
    SEND_THRESHOLD = 8192  # bytes ≈ 0.256 s at 16kHz 16-bit mono

    async def mic_worker(session) -> None:
        audio_buffer  = bytearray()
        sends         = 0
        last_send_log = time.time()

        try:
            while session_running:
                pcm = await mic_queue.get()
                audio_buffer.extend(pcm)
                mic_queue.task_done()

                # Drain in 8192-byte slices (0.256s chunks to minimize network overhead)
                while len(audio_buffer) >= SEND_THRESHOLD:
                    chunk_to_send = bytes(audio_buffer[:SEND_THRESHOLD])
                    del audio_buffer[:SEND_THRESHOLD]
                    try:
                        await session.send_realtime_input(
                            audio=types.Blob(data=chunk_to_send, mime_type="audio/pcm;rate=16000")
                        )
                        sends += 1
                    except Exception as exc:
                        print(f"[MIC WORKER] Connection dropped by server: {exc}")
                        return  # Exit worker cleanly so outer reconnect loop takes over

                    now = time.time()
                    if now - last_send_log >= 10.0:
                        print(f"[MIC WORKER] {sends} payloads sent in last 10s  "
                              f"queue_size={mic_queue.qsize()}  "
                              f"buf_remaining={len(audio_buffer)}B")
                        sends         = 0
                        last_send_log = now

                await asyncio.sleep(0.001)

        except Exception as exc:
            print(f"[MIC WORKER EXITED] {exc}")

    # ── speaker_worker ───────────────────────────────────────────────────────
    async def speaker_worker() -> None:
        global is_jarvis_speaking
        pa_out = pyaudio.PyAudio()
        spk    = pa_out.open(
            format=AUDIO_FORMAT,
            channels=1,
            rate=OUTPUT_SAMPLE_RATE,
            output=True,
        )
        try:
            while session_running:
                pcm = await audio_out_queue.get()
                if pcm is None:
                    audio_out_queue.task_done()
                    continue

                is_jarvis_speaking = True
                await broadcast("status", {
                    "state":       "speaking",
                    "audio_level": _rms(pcm),
                    "message":     "JARVIS Speaking...",
                })

                # Non-blocking write — stays off the event loop
                await asyncio.to_thread(spk.write, pcm)
                audio_out_queue.task_done()

                # Hysteresis: hold speaking flag until queue truly drains
                if audio_out_queue.empty():
                    await asyncio.sleep(0.4)
                    if audio_out_queue.empty():
                        is_jarvis_speaking = False
                        await broadcast("status", {
                            "state":   "listening",
                            "message": "Listening for your next command...",
                        })
        except Exception as exc:
            print(f"[SPEAKER ERROR] {exc}")
        finally:
            is_jarvis_speaking = False
            spk.stop_stream()
            spk.close()
            pa_out.terminate()

    # ── receiver_worker ──────────────────────────────────────────────────────
    async def receiver_worker(session) -> None:
        global is_jarvis_speaking
        recv_n        = 0
        last_recv_log = time.time()
        print("[RECEIVER] Worker started — waiting for Gemini responses...")

        while session_running:
            try:
                async for resp in session.receive():
                    recv_n += 1

                    # Heartbeat: warn if nothing received for >15 seconds
                    now = time.time()
                    if now - last_recv_log >= 15.0:
                        print(f"[RECEIVER] Heartbeat: {recv_n} total responses received so far.")
                        last_recv_log = now

                    # Debug summary line
                    tags: list[str] = []
                    sc = resp.server_content
                    if sc:
                        if sc.interrupted:   tags.append("INTERRUPTED")
                        if sc.turn_complete: tags.append("TURN_COMPLETE")
                        if sc.model_turn:
                            for p in sc.model_turn.parts:
                                if p.inline_data: tags.append(f"audio({len(p.inline_data.data)}B)")
                                if p.text:        tags.append(f"text='{p.text[:50]}'")
                    if resp.tool_call:
                        tags.append(f"tool_call({len(resp.tool_call.function_calls)})")
                    print(f"[RECV #{recv_n}] {', '.join(tags) or 'empty'}")
                    last_recv_log = time.time()

                    # Interruption → drain queue immediately
                    if sc and sc.interrupted:
                        is_jarvis_speaking = False
                        while not audio_out_queue.empty():
                            try:
                                audio_out_queue.get_nowait()
                                audio_out_queue.task_done()
                            except asyncio.QueueEmpty:
                                break
                        await broadcast("status", {"state": "listening", "message": "Interrupted."})

                    # Audio chunks → speaker queue
                    if sc and sc.model_turn:
                        for p in sc.model_turn.parts:
                            if p.inline_data:
                                await audio_out_queue.put(p.inline_data.data)
                            if p.text:
                                await broadcast("status", {"state": "speaking", "message": p.text})

                    # Turn complete → back to listening HUD state
                    if sc and sc.turn_complete:
                        await broadcast("status", {"state": "listening", "message": "Listening..."})

                    # Tool calls
                    if resp.tool_call:
                        for call in resp.tool_call.function_calls:
                            fn_name = call.name
                            fn_id   = call.id
                            fn_args = call.args if hasattr(call, "args") and call.args else {}
                            print(f"[TOOL] '{fn_name}' args={fn_args}")
                            await broadcast("status", {
                                "state":   "processing",
                                "message": f"Executing: {fn_name}",
                            })
                            result = await execute_tool_safely(fn_name, fn_args)
                            print(f"[TOOL RESULT] '{fn_name}' → {result}")
                            await session.send_tool_response(
                                function_responses=[
                                    types.FunctionResponse(
                                        name=fn_name, id=fn_id, response={"result": result}
                                    )
                                ]
                            )

            except Exception as exc:
                print(f"[RECEIVER CLOSED] Connection closed: {exc}")
                return

    # ── Auto-Reconnect Connection Loop ───────────────────────────────────────
    models_to_try = [
        "gemini-2.0-flash-exp",
        "gemini-3.1-flash-live-preview",
    ]
    model_idx = 0

    try:
        while session_running:
            current_model = models_to_try[model_idx % len(models_to_try)]
            print(f"[GEMINI] Connecting to {current_model}...")

            try:
                async with client.aio.live.connect(model=current_model, config=config) as session:
                    print(f"[GEMINI] Connected to {current_model} successfully!")

                    # ── Trigger initial session greeting via send_client_content ──────
                    try:
                        print("[GEMINI] Triggering opening spoken greeting...")
                        await session.send_client_content(
                            turns=[
                                types.Content(
                                    role="user",
                                    parts=[
                                        types.Part.from_text(
                                            text="Greetings Jarvis! Say: J.A.R.V.I.S duplex engine is online and ready, sir."
                                        )
                                    ],
                                )
                            ],
                            turn_complete=True,
                        )
                    except Exception as greeting_err:
                        print(f"[GEMINI] Initial greeting warning: {greeting_err}")

                    results = await asyncio.gather(
                        mic_worker(session),
                        speaker_worker(),
                        receiver_worker(session),
                        return_exceptions=True,
                    )

                    for wname, result in zip(
                        ["mic_worker", "speaker_worker", "receiver_worker"], results
                    ):
                        if isinstance(result, Exception):
                            print(f"[WORKER EXIT] {wname}: {result}")

            except Exception as exc:
                err_str = str(exc)
                print(f"[GEMINI SESSION DISCONNECTED] {exc}")
                if "1008" in err_str or "not found" in err_str.lower():
                    model_idx += 1
                    print(f"[GEMINI] Fallback switching to model: {models_to_try[model_idx % len(models_to_try)]}")

            if session_running:
                print("[GEMINI] Reconnecting in 2 seconds...")
                await broadcast("status", {"state": "idle", "message": "Reconnecting to Gemini Live..."})
                await asyncio.sleep(2.0)

    finally:
        # Signal the background thread to stop
        stop_event.set()
        session_running    = False
        is_jarvis_speaking = False
        mic_thread.join(timeout=3.0)
        print("[MIC THREAD] Joined.")


# ============================================================
#  WebSocket handler (Flutter ↔ Python bridge)
# ============================================================

async def handler(websocket) -> None:
    global session_running
    connected_clients.add(websocket)
    print(f"[WS] Flutter connected: {websocket.remote_address}")

    await websocket.send(json.dumps({
        "type":    "status",
        "state":   "idle",
        "message": "Connected to J.A.R.V.I.S Core Daemon (port 8765)",
    }))

    try:
        async for raw in websocket:
            payload = json.loads(raw)
            cmd     = payload.get("command")

            if cmd == "initialize" and not session_running:
                session_running = True
                await broadcast("status", {
                    "state":   "face_scanning",
                    "user":    "TAB & TECH",
                    "message": "Initializing J.A.R.V.I.S OS...",
                })
                await asyncio.to_thread(
                    speak_tts,
                    "Greetings, sir. J.A.R.V.I.S Duplex Engine is online and ready.",
                )
                await broadcast("status", {
                    "state":   "listening",
                    "user":    "TAB & TECH",
                    "message": "Launching Gemini Live Duplex...",
                })

                task = asyncio.create_task(run_gemini_live())
                task.add_done_callback(
                    lambda t: (
                        print(f"[TASK ERROR] run_gemini_live: {t.exception()}")
                        if not t.cancelled() and t.exception()
                        else None
                    )
                )

            elif cmd == "stop":
                session_running = False
                await broadcast("status", {"state": "idle", "message": "Session terminated."})
                await asyncio.to_thread(speak_tts, "Session terminated.")

    except websockets.ConnectionClosed:
        pass
    except Exception as exc:
        print(f"[WS ERROR] {exc}")
    finally:
        connected_clients.discard(websocket)
        print(f"[WS] Flutter disconnected: {websocket.remote_address}")


# ============================================================
#  Entry point
# ============================================================

async def main() -> None:
    asyncio.create_task(telemetry_loop())
    async with websockets.serve(handler, "localhost", 8765, ping_interval=None):
        print()
        print("=" * 60)
        print("  J.A.R.V.I.S CORE DAEMON — RUNNING")
        print("  WebSocket: ws://localhost:8765")
        print("=" * 60)
        print()
        await asyncio.Future()


if __name__ == "__main__":
    asyncio.run(main())
