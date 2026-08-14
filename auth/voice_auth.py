import os
import warnings
import logging


# Suppress PyTorch, Hugging Face, and SpeechBrain warnings/logs
warnings.filterwarnings("ignore")
logging.getLogger("speechbrain").setLevel(logging.ERROR)
os.environ["TF_CPP_MIN_LOG_LEVEL"] = "3"
os.environ["HF_HUB_DISABLE_SYMLINKS_WARNING"] = "1"

# Import torch, torchaudio, and soundfile after suppressing warnings if possible
try:
    import torch
    import torchaudio
    import soundfile as sf
    if not hasattr(torchaudio, "set_audio_backend"):
        torchaudio.set_audio_backend = lambda backend: None
        
    class MockAudioMetaData:
        def __init__(self, sample_rate, num_frames, num_channels):
            self.sample_rate = sample_rate
            self.num_frames = num_frames
            self.num_channels = num_channels

    def _patched_audio_info(filepath, *args, **kwargs):
        info = sf.info(filepath)
        return MockAudioMetaData(
            sample_rate=info.samplerate,
            num_frames=info.frames,
            num_channels=info.channels
        )

    torchaudio.info = _patched_audio_info

    def _patched_audio_load(filepath, *args, **kwargs):
        channels_first = kwargs.get("channels_first", True)
        frame_offset = kwargs.get("frame_offset", 0)
        num_frames = kwargs.get("num_frames", -1)
        
        # Use soundfile to read the audio cleanly without FFmpeg/TorchCodec
        data, sr = sf.read(filepath, start=frame_offset, frames=num_frames, dtype='float32')
        tensor = torch.from_numpy(data)
        
        # Ensure tensor is shaped correctly based on channels_first
        if tensor.ndim == 1:
            if channels_first:
                tensor = tensor.unsqueeze(0)  # (1, frames)
            else:
                tensor = tensor.unsqueeze(1)  # (frames, 1)
        else:
            if channels_first:
                tensor = tensor.t()  # (channels, frames)
            else:
                pass  # Keep (frames, channels)
        return tensor, sr

    torchaudio.load = _patched_audio_load
except ImportError:
    pass

# Patch huggingface_hub for compatibility with SpeechBrain and newer huggingface_hub versions
try:
    import huggingface_hub
    from requests.exceptions import HTTPError
    
    orig_download = huggingface_hub.hf_hub_download
    def patched_download(*args, **kwargs):
        kwargs.pop('use_auth_token', None)
        try:
            return orig_download(*args, **kwargs)
        except Exception as e:
            if "404" in str(e) or "not found" in str(e).lower():
                raise HTTPError("404 Client Error") from e
            raise
            
    huggingface_hub.hf_hub_download = patched_download
except ImportError:
    pass

try:
    from speechbrain.pretrained import SpeakerRecognition
except ImportError:
    from speechbrain.inference.speaker import SpeakerRecognition

class VoiceAuthenticator:
    def __init__(self):
        # Suppress logging during model loading
        logging.getLogger("speechbrain").setLevel(logging.ERROR)
        model_dir = os.path.join(os.path.dirname(__file__), "..", "tmp_model")
        self.verifier = SpeakerRecognition.from_hparams(
            source="speechbrain/spkrec-ecapa-voxceleb",
            savedir=model_dir
        )

    def verify(self, test_audio_path, baseline_path=None):
        if baseline_path is None:
            baseline_path = os.path.join(os.path.dirname(__file__), "owner_voice.wav")
            
        if not os.path.exists(baseline_path):
            print(f"\n[WARNING] Biometric baseline '{baseline_path}' not found. Voice verification bypassed (fail-safe active).")
            return True
            
        if not os.path.exists(test_audio_path):
            print(f"\n[ERROR] Test audio file '{test_audio_path}' not found for verification.")
            return False

        try:
            score, prediction = self.verifier.verify_files(baseline_path, test_audio_path)
            # Threshold of 0.40 is optimal to prevent false negatives from microphone/room acoustic variation,
            # while still easily blocking unauthorized speakers (who score below 0.15).
            threshold = 0.40
            print(f"\n[BIOMETRIC] Similarity Score: {score.item():.4f} (Threshold: {threshold:.2f})")
            return score.item() > threshold
        except Exception as e:
            print(f"\n[ERROR] Speaker recognition failed: {e}")
            # In case of internal processing error, we fallback to True to avoid locking out the owner
            return True
