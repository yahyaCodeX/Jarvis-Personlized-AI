"""
config.py — Central place for secrets and personal data.

Secrets live in `.env` (gitignored). Personal profile data (address, phone,
email) lives in `profile.json` (gitignored). Copy `profile.example.json` to
`profile.json` and fill in your own details.
"""

import json
import os

from dotenv import load_dotenv

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

load_dotenv(os.path.join(BASE_DIR, ".env"))

PROFILE_PATH = os.path.join(BASE_DIR, "profile.json")

_EMPTY_PROFILE = {
    "name": "",
    "first_name": "",
    "last_name": "",
    "default_phone": "",
    "email": "",
    "weather_city": "",
    "addresses": {},
}


def setup_logging() -> None:
    """
    Console + rotating file (logs/jarvis.log, 3 x 1 MB).
    Level from JARVIS_LOG_LEVEL in .env (DEBUG shows every Gemini packet & mic level).
    """
    import logging
    from logging.handlers import RotatingFileHandler

    level = getattr(logging, os.getenv("JARVIS_LOG_LEVEL", "INFO").upper(), logging.INFO)
    fmt = logging.Formatter("%(asctime)s %(levelname)-7s %(message)s", datefmt="%H:%M:%S")

    root = logging.getLogger("jarvis")
    root.setLevel(level)
    root.handlers.clear()

    import sys
    try:  # Windows consoles default to cp1252/cp437 and mangle "—", "→", etc.
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass
    console = logging.StreamHandler()
    console.setFormatter(fmt)
    root.addHandler(console)

    log_dir = os.path.join(BASE_DIR, "logs")
    os.makedirs(log_dir, exist_ok=True)
    file_handler = RotatingFileHandler(os.path.join(log_dir, "jarvis.log"),
                                       maxBytes=1_000_000, backupCount=3, encoding="utf-8")
    file_handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)-7s %(name)s %(message)s"))
    root.addHandler(file_handler)


def get_secret(name: str, default: str = "") -> str:
    """Read a secret from the environment (.env). Never hardcode secrets."""
    return os.getenv(name, default)


def _model_list(env_name: str, default: str) -> list[str]:
    raw = os.getenv(env_name, "") or default
    return [m.strip() for m in raw.split(",") if m.strip()]


# ── Gemini models (override in .env as comma-separated lists, first = preferred) ──
# Realtime voice models (must support the Live / bidiGenerateContent API)
LIVE_MODELS = _model_list(
    "JARVIS_LIVE_MODELS",
    # Verified 2026-11-08 against this project's full tool config.
    "gemini-3.8-live,gemini-3.1-flash-live-preview,gemini-2.5-flash-native-audio-latest",
)
# Fast text + vision models (screen reading, Ghost Coder, checkout field mapping)
VISION_MODELS = _model_list(
    "JARVIS_VISION_MODELS",
    "gemini-3.8-flash,gemini-3.6-flash,gemini-flash-latest",
)


def load_profile() -> dict:
    """Load the user's personal profile from profile.json (empty profile if missing)."""
    try:
        with open(PROFILE_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
        return {**_EMPTY_PROFILE, **data}
    except FileNotFoundError:
        print(f"[CONFIG] {PROFILE_PATH} not found — copy profile.example.json to profile.json.")
    except json.JSONDecodeError as e:
        print(f"[CONFIG] profile.json is not valid JSON: {e}")
    return dict(_EMPTY_PROFILE)
