import asyncio
import os
import sys
import pyaudio
import win32com.client
from dotenv import load_dotenv
from google import genai
from google.genai import types
import speech_recognition as sr
from auth.voice_auth import VoiceAuthenticator

# Import existing local automation tools from commands.py
from commands import (
    check_attendance,
    generate_assignment,
    open_last_assignment,
    ask_local_qwen,
    open_application,
    close_application,
    system_control,
    open_website,
    write_to_notepad_async,
    shutdown_assistant,
    page_scroll,
    type_and_search,
    search_youtube,
    play_youtube_video,
    open_file_by_name,
    change_brightness,
    media_control,
    switch_browser_tab,
    click_screen
)

# Load environment variables
load_dotenv()

# Audio Configuration
AUDIO_FORMAT = pyaudio.paInt16
CHANNELS = 1
INPUT_SAMPLE_RATE = 16000     
OUTPUT_SAMPLE_RATE = 24000    
CHUNK_SIZE = 1024

p = pyaudio.PyAudio()

# Global state to track model speaking and prevent acoustic echo feedback interruptions
is_model_speaking = False

# Map Gemini tools to the imported commands.py functions
tools_map = {
    "check_attendance": check_attendance,
    "generate_assignment": generate_assignment,
    "open_last_assignment": open_last_assignment,
    "ask_local_qwen": ask_local_qwen,
    "open_application": open_application,
    "close_application": close_application,
    "system_control": system_control,
    "open_website": open_website,
    "write_to_notepad_async": write_to_notepad_async,
    "shutdown_assistant": shutdown_assistant,
    "page_scroll": page_scroll,
    "type_and_search": type_and_search,
    "search_youtube": search_youtube,
    "play_youtube_video": play_youtube_video,
    "open_file_by_name": open_file_by_name,
    "change_brightness": change_brightness,
    "media_control": media_control,
    "switch_browser_tab": switch_browser_tab,
    "click_screen": click_screen
}


async def main():
    # --- 1. Voice Authentication Security Gate ---
    print("\n🔐 [SECURITY GATE] Performing voice biometric validation...")
    recognizer = sr.Recognizer()
    
    def get_microphone():
        # Try using MIC_DEVICE_INDEX 1 (active system mic), fallback to default if it fails
        try:
            return sr.Microphone(device_index=1)
        except Exception:
            return sr.Microphone()
            
    # Calibrate ambient noise once at start while the user remains silent
    with get_microphone() as source:
        print("Calibrating microphone for ambient noise (please remain quiet for 1.5 seconds)...")
        recognizer.adjust_for_ambient_noise(source, duration=1.5)
        
    authenticator = VoiceAuthenticator()
    authenticated = False
    max_attempts = 3

    for attempt in range(1, max_attempts + 1):
        print(f"\n[Attempt {attempt} of {max_attempts}] Please speak a command to authenticate...")
        with get_microphone() as source:
            print("[READY] Say something now...")
            try:
                # Wait for user speech and capture the audio dynamically
                audio = recognizer.listen(source, timeout=8, phrase_time_limit=6)
                temp_path = "temp_speech.wav"
                with open(temp_path, "wb") as f:
                    f.write(audio.get_wav_data())
                    
                if authenticator.verify(temp_path):
                    print("✅ Biometric fingerprint verified. Access granted.\n")
                    authenticated = True
                    break
                else:
                    print("❌ Voice signature mismatch.")
            except sr.WaitTimeoutError:
                print("⚠️ Silence detected. No speech captured.")
            except Exception as auth_err:
                print(f"⚠️ Error capturing audio: {auth_err}")

    if not authenticated:
        # Rejection message verbatim
        rejection_msg = "Acoustic fingerprint mismatch. Biometric security protocols engaged. Unauthorized input discarded."
        print(f"\n❌ {rejection_msg}")
        try:
            speaker = win32com.client.Dispatch("SAPI.SpVoice")
            speaker.Speak(rejection_msg)
        except Exception as speak_err:
            print(f"Failed to play SAPI rejection: {speak_err}")
        sys.exit(1)

    # --- 2. Live API Connection Setup ---
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        print("[ERROR] GEMINI_API_KEY missing in .env file.")
        return

    client = genai.Client(api_key=api_key)
    model_id = "gemini-3.1-flash-live-preview"

    # Define tool function declarations for Gemini
    tools_config = [{"function_declarations": [
        {
            "name": "check_attendance",
            "description": "Opens the university MIS portal using Selenium Chrome automation, logs in, and loads the 8th-semester provisional attendance page.",
            "parameters": {"type": "OBJECT", "properties": {}}
        },
        {
            "name": "generate_assignment",
            "description": "Generates a detailed academic university assignment Word document (.docx) on a background thread using the local Ollama LLM.",
            "parameters": {
                "type": "OBJECT",
                "properties": {
                    "topic": {"type": "STRING", "description": "The academic topic of the assignment."},
                    "subject": {"type": "STRING", "description": "The course subject name."}
                },
                "required": ["topic", "subject"]
            }
        },
        {
            "name": "open_last_assignment",
            "description": "Opens the most recently generated assignment document (.docx) in Microsoft Word on the desktop.",
            "parameters": {"type": "OBJECT", "properties": {}}
        },
        {
            "name": "ask_local_qwen",
            "description": "Sends a private query to the local Ollama model (Qwen) for local computation and returns the generated text response.",
            "parameters": {
                "type": "OBJECT",
                "properties": {
                    "prompt": {"type": "STRING", "description": "The query/prompt to send to the local Qwen model."}
                },
                "required": ["prompt"]
            }
        },
        {
            "name": "open_application",
            "description": "Opens a common application (notepad, calculator, chrome, explorer, cmd) or a custom URL/path on the Windows system.",
            "parameters": {
                "type": "OBJECT",
                "properties": {
                    "app_name": {"type": "STRING", "description": "The name, path, or URL of the application to open."}
                },
                "required": ["app_name"]
            }
        },
        {
            "name": "close_application",
            "description": "Force closes a running application or process on Windows.",
            "parameters": {
                "type": "OBJECT",
                "properties": {
                    "app_name": {"type": "STRING", "description": "The name of the application process to terminate."}
                },
                "required": ["app_name"]
            }
        },
        {
            "name": "system_control",
            "description": "Controls OS level functionality (volume_up, volume_down, mute, screenshot, lock).",
            "parameters": {
                "type": "OBJECT",
                "properties": {
                    "action": {
                        "type": "STRING", 
                        "description": "The control action to execute.",
                        "enum": ["volume_up", "volume_down", "mute", "screenshot", "lock"]
                    }
                },
                "required": ["action"]
            }
        },
        {
            "name": "open_website",
            "description": "Opens any website, domain, URL, or web query in the user's default browser.",
            "parameters": {
                "type": "OBJECT",
                "properties": {
                    "url_or_query": {
                        "type": "STRING",
                        "description": "The exact URL, website name (e.g. 'youtube.com', 'github.com', 'reddit.com'), or search topic to open."
                    }
                },
                "required": ["url_or_query"]
            }
        },
        {
            "name": "write_to_notepad_async",
            "description": "Launches Notepad in a background thread and writes content without blocking.",
            "parameters": {
                "type": "OBJECT",
                "properties": {
                    "content": {
                        "type": "STRING",
                        "description": "The text content to write into Notepad."
                    },
                    "title": {
                        "type": "STRING",
                        "description": "The filename to save the note to (default: notes.txt)."
                    }
                },
                "required": ["content"]
            }
        },
        {
            "name": "shutdown_assistant",
            "description": "Terminates the Jarvis assistant application cleanly.",
            "parameters": {"type": "OBJECT", "properties": {}}
        },
        {
            "name": "page_scroll",
            "description": "Scrolls the active window or browser page up or down.",
            "parameters": {
                "type": "OBJECT",
                "properties": {
                    "direction": {
                        "type": "STRING",
                        "description": "The scroll direction: 'up' or 'down'."
                    }
                },
                "required": ["direction"]
            }
        },
        {
            "name": "type_and_search",
            "description": "Types text on the active input field (like search boxes) and presses enter to execute.",
            "parameters": {
                "type": "OBJECT",
                "properties": {
                    "text": {
                        "type": "STRING",
                        "description": "The text search query or input text to write."
                    }
                },
                "required": ["text"]
            }
        },
        {
            "name": "search_youtube",
            "description": "Searches YouTube using Selenium and stores results.",
            "parameters": {
                "type": "OBJECT",
                "properties": {
                    "query": {
                        "type": "STRING",
                        "description": "The video search term or topic to query on YouTube."
                    }
                },
                "required": ["query"]
            }
        },
        {
            "name": "play_youtube_video",
            "description": "Plays a video from the last YouTube search results using index (1-based index).",
            "parameters": {
                "type": "OBJECT",
                "properties": {
                    "index": {
                        "type": "INTEGER",
                        "description": "The 1-based index of the video to play (e.g. 1 for the first result, 2 for the second)."
                    }
                },
                "required": ["index"]
            }
        },
        {
            "name": "open_file_by_name",
            "description": "Locates and opens a file (image, video, document) by name in the specified or last opened folder.",
            "parameters": {
                "type": "OBJECT",
                "properties": {
                    "filename": {
                        "type": "STRING",
                        "description": "The exact or partial file name to open."
                    },
                    "parent_dir": {
                        "type": "STRING",
                        "description": "Optional parent directory path to scan first."
                    }
                },
                "required": ["filename"]
            }
        },
        {
            "name": "change_brightness",
            "description": "Natively gets or sets screen brightness using WMI/PowerShell.",
            "parameters": {
                "type": "OBJECT",
                "properties": {
                    "action": {
                        "type": "STRING",
                        "description": "The action: 'increase', 'decrease', or 'set'."
                    },
                    "value": {
                        "type": "INTEGER",
                        "description": "The brightness amount/percentage (e.g., 10 for adjustment, or 0-100 for set)."
                    }
                },
                "required": ["action"]
            }
        },
        {
            "name": "media_control",
            "description": "Controls system-wide media playback (play, pause, next, previous, stop).",
            "parameters": {
                "type": "OBJECT",
                "properties": {
                    "action": {
                        "type": "STRING",
                        "description": "The media action: 'play', 'pause', 'playpause', 'next', 'previous', 'stop'."
                    }
                },
                "required": ["action"]
            }
        },
        {
            "name": "switch_browser_tab",
            "description": "Switches browser tabs using Ctrl+Tab or Ctrl+Number.",
            "parameters": {
                "type": "OBJECT",
                "properties": {
                    "direction_or_index": {
                        "type": "STRING",
                        "description": "The tab switch direction ('next', 'previous') or specific tab number index ('1', '2', etc.)."
                    }
                },
                "required": ["direction_or_index"]
            }
        },
        {
            "name": "click_screen",
            "description": "Clicks the mouse on the screen at specified coordinates or current position.",
            "parameters": {
                "type": "OBJECT",
                "properties": {
                    "x": {
                        "type": "INTEGER",
                        "description": "Optional X coordinate on the screen."
                    },
                    "y": {
                        "type": "INTEGER",
                        "description": "Optional Y coordinate on the screen."
                    },
                    "click_type": {
                        "type": "STRING",
                        "description": "The click action: 'single', 'double', or 'right'."
                    }
                },
                "required": []
            }
        }
    ]}]

    config = types.LiveConnectConfig(
        response_modalities=["AUDIO"],
        speech_config=types.SpeechConfig(
            voice_config=types.VoiceConfig(
                prebuilt_voice_config=types.PrebuiltVoiceConfig(voice_name="Fenrir")
            )
        ),
        system_instruction=types.Content(
            parts=[types.Part.from_text(
                text=(
                    "You are Jarvis, a personalized AI operating system created by Muhammad Yahya Siddiqui. "
                    "Muhammad Yahya Siddiqui is your creator, engineer, and boss. If asked who created you, always state that you were built and customized by Muhammad Yahya Siddiqui. "
                    "You have direct control over his local workstation via function tools. "
                    "Whenever the user asks to open ANY website, platform, video, or link, ALWAYS call the `open_website` tool immediately. "
                    "If the user asks you to shutdown, exit, turn off, say goodbye, or close down, ALWAYS call the `shutdown_assistant` tool immediately. "
                    "When asked to scroll, search, or type on the page, use the `page_scroll` or `type_and_search` tools immediately. "
                    "When the user asks to search for videos, songs, or topics on YouTube, use the `search_youtube` tool. "
                    "When the user selects a specific result (e.g. 'play the first one', 'play number two'), use the `play_youtube_video` tool with the corresponding 1-based index. "
                    "When the user asks to open a specific image, video, file, or photo, use the `open_file_by_name` tool with the file name. "
                    "When the user asks to increase, decrease, or set screen/system brightness, use the `change_brightness` tool. "
                    "When the user asks to pause, play, stop, next, or skip media (videos, YouTube, music, etc.), use the `media_control` tool. "
                    "When the user asks to switch tabs in the browser, use the `switch_browser_tab` tool. "
                    "When the user asks to click somewhere on the screen (single, double, or right click), use the `click_screen` tool. "
                    "Keep verbal responses crisp, candor-driven, and focused on executing instructions."
                )
            )]
        ),
        tools=tools_config
    )

    audio_out_queue = asyncio.Queue()

    # --- 3. Parallel Audio Streaming Tasks ---
    
    async def send_mic_audio(session):
        """Continuously streams captured microphone audio (16kHz PCM) to Gemini."""
        # Open PyAudio stream. Try device_index 1 first (active system mic), fallback to default if it fails
        try:
            audio_stream = p.open(
                format=AUDIO_FORMAT,
                channels=CHANNELS,
                rate=INPUT_SAMPLE_RATE,
                input=True,
                input_device_index=1,
                frames_per_buffer=CHUNK_SIZE
            )
        except Exception:
            audio_stream = p.open(
                format=AUDIO_FORMAT,
                channels=CHANNELS,
                rate=INPUT_SAMPLE_RATE,
                input=True,
                frames_per_buffer=CHUNK_SIZE
            )
        print("🎙️  Live duplex connection active. Start speaking...")
        
        global is_model_speaking
        import numpy as np
        
        try:
            while True:
                data = await asyncio.to_thread(audio_stream.read, CHUNK_SIZE, exception_on_overflow=False)
                
                if is_model_speaking:
                    # When model is speaking, apply noise gate to filter out speaker feedback echo
                    samples = np.frombuffer(data, dtype=np.int16)
                    rms = np.sqrt(np.mean(samples.astype(np.float32)**2)) if len(samples) > 0 else 0
                    
                    if rms >= 3000:
                        # Allow loud barge-in
                        await session.send_realtime_input(
                            audio=types.Blob(data=data, mime_type="audio/pcm;rate=16000")
                        )
                    else:
                        # Stream silence to prevent echo feedback triggering interruption
                        silent_data = b'\x00' * len(data)
                        await session.send_realtime_input(
                            audio=types.Blob(data=silent_data, mime_type="audio/pcm;rate=16000")
                        )
                else:
                    # When model is idle/listening, stream raw microphone input directly (normal sensitivity)
                    await session.send_realtime_input(
                        audio=types.Blob(data=data, mime_type="audio/pcm;rate=16000")
                    )
        except asyncio.CancelledError:
            pass
        finally:
            audio_stream.stop_stream()
            audio_stream.close()

    async def play_audio_stream():
        """Reads audio chunks from the queue and writes them to the speaker (24kHz PCM)."""
        global is_model_speaking
        speaker_stream = p.open(
            format=AUDIO_FORMAT,
            channels=CHANNELS,
            rate=OUTPUT_SAMPLE_RATE,
            output=True
        )
        try:
            while True:
                pcm_data = await audio_out_queue.get()
                if pcm_data is None:  
                    continue
                is_model_speaking = True
                await asyncio.to_thread(speaker_stream.write, pcm_data)
                audio_out_queue.task_done()
                
                # Turn off model speaking flag if queue is empty
                if audio_out_queue.empty():
                    is_model_speaking = False
        except asyncio.CancelledError:
            pass
        finally:
            is_model_speaking = False
            speaker_stream.stop_stream()
            speaker_stream.close()

    async def receive_from_gemini(session):
        """Processes responses from the Gemini Live stream, handling barge-in and tool calls."""
        global is_model_speaking
        while True:
            async for response in session.receive():
                server_content = response.server_content

                if server_content is not None:
                    # Handle Barge-In Interruption: user spoke while model was speaking
                    if server_content.interrupted:
                        is_model_speaking = False
                        while not audio_out_queue.empty():
                            try:
                                audio_out_queue.get_nowait()
                                audio_out_queue.task_done()
                            except asyncio.QueueEmpty:
                                break
                        print("\n[Interrupted by user]")

                    # Play incoming synthesized audio chunks
                    if server_content.model_turn is not None:
                        for part in server_content.model_turn.parts:
                            if part.inline_data:
                                await audio_out_queue.put(part.inline_data.data)

                # Handle Tool/Function Calls
                tool_call = response.tool_call
                if tool_call is not None:
                    for call in tool_call.function_calls:
                        name = call.name
                        call_id = call.id
                        args = call.args
                        # Non-blocking tool execution
                        if name in tools_map:
                            func = tools_map[name]
                            # Extract arguments if present
                            args = call.args if hasattr(call, 'args') and call.args else {}
                            
                            print(f"\n[TOOL CALLED] Running {name} asynchronously...")
                            # Execute synchronously in a background thread
                            result_str = await asyncio.to_thread(func, **args)
                            print(f"[TOOL RESULT] {result_str}")
                            
                            # Return the response back to Gemini using types.LiveClientToolResponse
                            await session.send(input=types.LiveClientToolResponse(
                                function_responses=[types.FunctionResponse(
                                    name=name,
                                    id=call_id,
                                    response={"result": str(result_str)}
                                )]
                            ))

    # Connect to the Live Session
    async with client.aio.live.connect(model=model_id, config=config) as session:
        mic_task = asyncio.create_task(send_mic_audio(session))
        speaker_task = asyncio.create_task(play_audio_stream())
        receiver_task = asyncio.create_task(receive_from_gemini(session))

        # Monitor tasks concurrently. If any task raises an exception or fails,
        # FIRST_EXCEPTION triggers immediately to prevent main thread lockups/hangs.
        done, pending = await asyncio.wait(
            [mic_task, speaker_task, receiver_task],
            return_when=asyncio.FIRST_EXCEPTION
        )
        
        # Clean up any remaining tasks to prevent dangling background loops
        for task in pending:
            task.cancel()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nTerminated.")
        p.terminate()
