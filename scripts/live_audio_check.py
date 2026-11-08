"""
End-to-end test: Mic (device 4) -> Gemini Live -> Speaker
Speak into your mic when you see LISTENING.
"""
import asyncio
import math
import os
import struct
import pyaudio
from dotenv import load_dotenv
from google import genai
from google.genai import types

load_dotenv()

MIC_DEVICE = 4  # "Primary Sound Capture Driver" - the one that works
RATE_IN = 16000
RATE_OUT = 24000
CHUNK = 1024


def rms(data):
    n = len(data) // 2
    if n == 0:
        return 0.0
    shorts = struct.unpack(f"{n}h", data)
    return math.sqrt(sum(s * s for s in shorts) / n) / 32768.0


async def main():
    api_key = os.getenv("GEMINI_API_KEY")
    client = genai.Client(api_key=api_key, http_options={"api_version": "v1alpha"})

    config = types.LiveConnectConfig(
        response_modalities=["AUDIO"],
        speech_config=types.SpeechConfig(
            voice_config=types.VoiceConfig(
                prebuilt_voice_config=types.PrebuiltVoiceConfig(voice_name="Fenrir")
            )
        ),
    )

    pa = pyaudio.PyAudio()
    mic = pa.open(format=pyaudio.paInt16, channels=1, rate=RATE_IN,
                  input=True, input_device_index=MIC_DEVICE,
                  frames_per_buffer=CHUNK)
    spk = pa.open(format=pyaudio.paInt16, channels=1, rate=RATE_OUT, output=True)

    print("Connecting to Gemini Live...")
    async with client.aio.live.connect(
        model="gemini-3.1-flash-live-preview", config=config
    ) as session:
        audio_q = asyncio.Queue()
        speaking = False

        async def send_mic():
            nonlocal speaking
            user_talking = False
            quiet_frames = 0

            while True:
                data = await asyncio.to_thread(mic.read, CHUNK, False)
                level = rms(data)

                if speaking:
                    await asyncio.sleep(0.005)
                    continue

                await session.send_realtime_input(
                    audio=types.Blob(data=data, mime_type="audio/pcm;rate=16000")
                )

                if level > 0.04:
                    if not user_talking:
                        user_talking = True
                        print(f"[VAD] START speaking (level={level:.4f})")
                        await session.send_realtime_input(
                            activity_start=types.ActivityStart()
                        )
                    quiet_frames = 0
                else:
                    if user_talking:
                        quiet_frames += 1
                        if quiet_frames > 12:
                            user_talking = False
                            quiet_frames = 0
                            print("[VAD] END speaking -> waiting for Gemini response...")
                            await session.send_realtime_input(
                                activity_end=types.ActivityEnd()
                            )

                await asyncio.sleep(0.005)

        async def play_audio():
            nonlocal speaking
            while True:
                pcm = await audio_q.get()
                speaking = True
                await asyncio.to_thread(spk.write, pcm)
                audio_q.task_done()
                if audio_q.empty():
                    speaking = False

        async def recv():
            async for resp in session.receive():
                sc = resp.server_content
                if sc:
                    if sc.interrupted:
                        print("[GEMINI] Interrupted")
                    if sc.model_turn:
                        for part in sc.model_turn.parts:
                            if part.inline_data:
                                n = len(part.inline_data.data)
                                print(f"[GEMINI] Audio chunk: {n} bytes")
                                await audio_q.put(part.inline_data.data)
                    if sc.turn_complete:
                        print("[GEMINI] Turn complete!")

        print("=" * 50)
        print("LISTENING on device [4]... SPEAK NOW!")
        print("=" * 50)
        await asyncio.gather(send_mic(), play_audio(), recv())


if __name__ == "__main__":
    asyncio.run(main())
