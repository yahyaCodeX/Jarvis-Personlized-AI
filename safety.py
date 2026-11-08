"""
safety.py — Guard rails for tools that touch the file system or need user consent.

Two protections:

1. Path sandbox
   File tools may only read/write inside JARVIS_ALLOWED_DIRS (semicolon-separated
   in .env). Secrets (.env, profile.json, voiceprint, .git internals, SSH keys)
   are always blocked, even inside an allowed folder.

2. Spoken confirmation
   Sensitive tools (writing files, killing apps, filling checkout forms) are not
   executed directly. Instead a pending action is created and Jarvis must ask the
   user. The action only runs if the user's OWN microphone transcript — not the
   model's text, not a web page, not a screenshot — contains an affirmative word
   ("confirm", "yes", ...) after the request was made. A prompt-injected model
   therefore cannot approve its own actions.
"""

import os
import re
import secrets
import threading
import time

from config import BASE_DIR, get_secret

# ─────────────────────────────────────────────────────────────────────────────
#  1. PATH SANDBOX
# ─────────────────────────────────────────────────────────────────────────────

def _default_allowed_dirs() -> list[str]:
    home = os.path.expanduser("~")
    return [
        r"D:\Development",
        os.path.join(home, "Desktop"),
        os.path.join(home, "Documents"),
        os.path.join(home, "Downloads"),
    ]


def allowed_dirs() -> list[str]:
    raw = get_secret("JARVIS_ALLOWED_DIRS", "")
    dirs = [d.strip() for d in raw.split(";") if d.strip()] or _default_allowed_dirs()
    return [os.path.normcase(os.path.realpath(os.path.expanduser(d))) for d in dirs]


# File names / path parts that must never be read or written by the AI.
_BLOCKED_NAMES = {
    ".env", "profile.json", "owner_voice.wav", "id_rsa", "id_ed25519",
    "credentials.json", "token.json", "jarvis_memory.json", "contacts.json",
}
_BLOCKED_PARTS = {".git", ".ssh", ".aws", ".gnupg"}
_BLOCKED_PREFIXES = (".env.",)


def check_path(path: str) -> tuple[bool, str]:
    """
    Resolve `path` (following symlinks and '..') and check it is allowed.
    Returns (True, absolute_path) or (False, reason).
    """
    if not path or not str(path).strip():
        return False, "No file path given."

    expanded = os.path.expanduser(str(path).strip().strip('"\''))
    if not os.path.isabs(expanded):
        expanded = os.path.join(BASE_DIR, expanded)
    real = os.path.realpath(expanded)
    real_cmp = os.path.normcase(real)

    parts = {p.lower() for p in re.split(r"[\\/]+", real_cmp) if p}
    name = os.path.basename(real_cmp).lower()
    if (name in _BLOCKED_NAMES
            or name.startswith(_BLOCKED_PREFIXES)
            or parts & _BLOCKED_PARTS):
        return False, f"Access to '{os.path.basename(real)}' is blocked for security reasons."

    for root in allowed_dirs():
        try:
            if os.path.commonpath([real_cmp, root]) == root:
                return True, real
        except ValueError:
            continue  # different drives
    return False, (
        f"'{real}' is outside the folders Jarvis may access. "
        f"Allowed: {', '.join(allowed_dirs())} (change JARVIS_ALLOWED_DIRS in .env)."
    )


# ─────────────────────────────────────────────────────────────────────────────
#  2. SPOKEN CONFIRMATION GATE
# ─────────────────────────────────────────────────────────────────────────────

CONFIRM_TIMEOUT_S = 90

_AFFIRMATIVE = re.compile(
    r"\b(confirm(ed)?|yes|yeah|yep|go ahead|do it|proceed|approved?|haan|ji haan|theek hai)\b",
    re.IGNORECASE,
)
_NEGATIVE = re.compile(
    r"\b(no|nope|cancel|stop|don'?t|do not|abort|nahi|mat)\b",
    re.IGNORECASE,
)


def confirmation_required() -> bool:
    return get_secret("JARVIS_REQUIRE_CONFIRMATION", "1").strip() != "0"


class ConfirmationGate:
    """Holds pending sensitive actions until the human approves them by voice."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._pending: dict[str, dict] = {}
        self._speech: list[tuple[float, str]] = []   # (timestamp, user transcript chunk)
        self._ui_approvals: dict[str, float] = {}    # token -> time approved from the HUD

    # ── Inputs from the outside world ────────────────────────────────────────
    def record_user_speech(self, text: str) -> None:
        """Feed the transcription of the USER's microphone audio (never model text)."""
        if not text or not text.strip():
            return
        with self._lock:
            self._speech.append((time.time(), text))
            self._speech = self._speech[-50:]

    def approve_latest_from_ui(self) -> str | None:
        """Approve the newest pending action from a trusted UI button (Flutter HUD)."""
        with self._lock:
            self._expire()
            if not self._pending:
                return None
            token = max(self._pending, key=lambda t: self._pending[t]["created"])
            self._ui_approvals[token] = time.time()
            return token

    # ── Tool-side API ────────────────────────────────────────────────────────
    def request(self, name: str, args: dict, summary: str) -> str:
        token = secrets.token_hex(3)
        with self._lock:
            self._expire()
            self._pending[token] = {
                "name": name, "args": args, "summary": summary, "created": time.time(),
            }
        return token

    def resolve(self, token: str) -> tuple[bool, dict | str]:
        """
        Returns (True, pending_entry) if the user approved since the request,
        otherwise (False, reason). A refusal or approval consumes the token.
        """
        token = (token or "").strip()
        with self._lock:
            self._expire()
            entry = self._pending.get(token)
            if entry is None:
                return False, "No pending action with that token (it may have expired). Ask the user again."

            if token in self._ui_approvals:
                self._pending.pop(token)
                self._ui_approvals.pop(token, None)
                return True, entry

            heard = " ".join(t for ts, t in self._speech if ts >= entry["created"])
            # Any negative word wins ("don't do it" must never count as approval).
            if _NEGATIVE.search(heard):
                self._pending.pop(token)
                return False, "The user declined. The action was cancelled."
            if _AFFIRMATIVE.search(heard):
                self._pending.pop(token)
                return True, entry

            return False, (
                "The user has not said 'confirm' yet. Wait for them to answer out loud, "
                "then call confirm_action again. Do not assume consent."
            )

    def _expire(self) -> None:
        now = time.time()
        for tok in [t for t, e in self._pending.items() if now - e["created"] > CONFIRM_TIMEOUT_S]:
            self._pending.pop(tok, None)
            self._ui_approvals.pop(tok, None)


gate = ConfirmationGate()
