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


def get_secret(name: str, default: str = "") -> str:
    """Read a secret from the environment (.env). Never hardcode secrets."""
    return os.getenv(name, default)


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
