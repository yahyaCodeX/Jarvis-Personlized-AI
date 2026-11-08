import pyaudio, struct, math, time

pa = pyaudio.PyAudio()
info = pa.get_default_input_device_info()
print(f"Device: {info['name']}")
print(f"Native sample rate: {info['defaultSampleRate']}")
print(f"Max input channels: {info['maxInputChannels']}")
print()
print("Recording 3 seconds at 16kHz... SPEAK NOW!")
print()

mic = pa.open(format=pyaudio.paInt16, channels=1, rate=16000,
              input=True, frames_per_buffer=1024)

max_rms = 0.0
for i in range(48):  # ~3 seconds
    data = mic.read(1024, exception_on_overflow=False)
    n = len(data) // 2
    shorts = struct.unpack(f"{n}h", data)
    rms_val = math.sqrt(sum(s * s for s in shorts) / n) / 32768.0
    if rms_val > max_rms:
        max_rms = rms_val
    bar = "#" * int(rms_val * 200)
    print(f"  Frame {i:3d} | RMS={rms_val:.6f} | {bar}")

mic.close()
pa.terminate()
print()
print(f"Peak RMS over 3 seconds: {max_rms:.6f}")
if max_rms < 0.005:
    print("RESULT: Mic is SILENT. Check Windows mic permissions or default device.")
elif max_rms < 0.04:
    print("RESULT: Mic level is very LOW. Gemini VAD will NOT trigger.")
else:
    print("RESULT: Mic is capturing audio at usable levels.")
