import os
import speech_recognition as sr

def enroll():
    print("\n--- VOICEPRINT ENROLLMENT ---")
    
    # Ensure auth directory exists
    auth_dir = os.path.join(os.path.dirname(__file__), "auth")
    os.makedirs(auth_dir, exist_ok=True)
    
    recognizer = sr.Recognizer()
    
    # Try using MIC_DEVICE_INDEX 1 (as configured in brain.py), fallback to default if it fails
    mic_index = 1
    try:
        source = sr.Microphone(device_index=mic_index)
    except Exception:
        source = sr.Microphone()
        
    print("\nPreparing microphone (please remain quiet for 1.5 seconds)...")
    with source as s:
        recognizer.adjust_for_ambient_noise(s, duration=1.5)
        print("\n[READY] Please speak naturally to generate your biometric voiceprint...")
        audio_data = recognizer.listen(s, timeout=8, phrase_time_limit=6)
        
    wav_path = os.path.join(auth_dir, "owner_voice.wav")
    with open(wav_path, "wb") as f:
        f.write(audio_data.get_wav_data())
        
    print("\nVoiceprint successfully enrolled and secured.")
    print(f"Saved to: {wav_path}")

if __name__ == "__main__":
    enroll()
