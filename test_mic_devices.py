import pyaudio, struct, math

pa = pyaudio.PyAudio()

print("=" * 60)
print("ALL AUDIO INPUT DEVICES:")
print("=" * 60)
for i in range(pa.get_device_count()):
    info = pa.get_device_info_by_index(i)
    if info["maxInputChannels"] > 0:
        print(f"  [{i}] {info['name']}")
        print(f"      Channels: {info['maxInputChannels']}, Rate: {info['defaultSampleRate']}")
        print()

default = pa.get_default_input_device_info()
print(f"Default input: [{default['index']}] {default['name']}")
print(f"  Native rate: {default['defaultSampleRate']}")
print()

# Test 1: Try at native 44100Hz
print("=" * 60)
print("TEST 1: Recording at NATIVE 44100Hz for 2 seconds... SPEAK!")
print("=" * 60)
try:
    mic = pa.open(format=pyaudio.paInt16, channels=1, rate=44100,
                  input=True, frames_per_buffer=4410)
    max_rms = 0.0
    for i in range(20):  # ~2 seconds
        data = mic.read(4410, exception_on_overflow=False)
        n = len(data) // 2
        shorts = struct.unpack(f"{n}h", data)
        rms_val = math.sqrt(sum(s * s for s in shorts) / n) / 32768.0
        if rms_val > max_rms:
            max_rms = rms_val
        bar = "#" * int(rms_val * 200)
        print(f"  Frame {i:3d} | RMS={rms_val:.6f} | {bar}")
    mic.close()
    print(f"  Peak RMS at 44100Hz: {max_rms:.6f}")
    if max_rms < 0.005:
        print("  -> STILL SILENT at native rate!")
    else:
        print("  -> WORKS at 44100Hz! The 16kHz resampling was the issue.")
except Exception as e:
    print(f"  ERROR at 44100Hz: {e}")

print()

# Test 2: Try with 2 channels (stereo mic array)
print("=" * 60)
print("TEST 2: Recording at 16kHz with 2 channels... SPEAK!")
print("=" * 60)
try:
    mic = pa.open(format=pyaudio.paInt16, channels=2, rate=16000,
                  input=True, frames_per_buffer=1024)
    max_rms = 0.0
    for i in range(24):
        data = mic.read(1024, exception_on_overflow=False)
        n = len(data) // 2
        shorts = struct.unpack(f"{n}h", data)
        rms_val = math.sqrt(sum(s * s for s in shorts) / n) / 32768.0
        if rms_val > max_rms:
            max_rms = rms_val
        bar = "#" * int(rms_val * 200)
        print(f"  Frame {i:3d} | RMS={rms_val:.6f} | {bar}")
    mic.close()
    print(f"  Peak RMS at 16kHz/2ch: {max_rms:.6f}")
except Exception as e:
    print(f"  ERROR at 16kHz/2ch: {e}")

print()

# Test 3: Try each input device individually at 16kHz mono
print("=" * 60)
print("TEST 3: Trying each input device at 16kHz/1ch...")
print("=" * 60)
for i in range(pa.get_device_count()):
    info = pa.get_device_info_by_index(i)
    if info["maxInputChannels"] > 0:
        try:
            mic = pa.open(format=pyaudio.paInt16, channels=1, rate=16000,
                          input=True, input_device_index=i, frames_per_buffer=1024)
            data = mic.read(1024, exception_on_overflow=False)
            n = len(data) // 2
            shorts = struct.unpack(f"{n}h", data)
            rms_val = math.sqrt(sum(s * s for s in shorts) / n) / 32768.0
            mic.close()
            status = "SIGNAL" if rms_val > 0.001 else "silent"
            print(f"  [{i}] {info['name']}: RMS={rms_val:.6f} ({status})")
        except Exception as e:
            print(f"  [{i}] {info['name']}: FAILED ({e})")

pa.terminate()
print()
print("DONE. Check which device/rate combination produces signal.")
