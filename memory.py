# memory.py — Persistent memory for Jarvis

import json
import os
import tempfile
import shutil
from datetime import datetime

MEMORY_FILE = os.path.join(os.path.dirname(__file__), "memory.json")

# ── TUNED FOR SPEED ──────────────────────────────────────────
# 8 messages = ~400 tokens of context sent to the AI.
# This is the single biggest lever for reducing "thinking time".
# 20 messages (old) → ~1000 tokens → slow first response.
# 8 messages (new)  → ~400 tokens  → ~2.5x faster first token.
MAX_CONTEXT_MESSAGES = 8

MAX_STORED_MESSAGES  = 120   # Hard cap on disk


def load_memory():
    """Load all past conversations from disk."""
    if os.path.exists(MEMORY_FILE):
        try:
            with open(MEMORY_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                return data.get("conversations", [])
        except (json.JSONDecodeError, KeyError):
            return []
    return []


def save_memory(conversations):
    """
    Atomic save — writes temp file then renames.
    Guarantees no corruption if Jarvis crashes mid-write.
    """
    data = {
        "last_updated":   datetime.now().isoformat(),
        "total_messages": len(conversations),
        "conversations":  conversations
    }
    dir_name = os.path.dirname(MEMORY_FILE) or "."
    try:
        fd, tmp_path = tempfile.mkstemp(dir=dir_name, suffix=".tmp")
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        shutil.move(tmp_path, MEMORY_FILE)
    except Exception as e:
        print(f"⚠️  Memory save error: {e}")
        with open(MEMORY_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)


def add_message(conversations, role, content):
    conversations.append({
        "role":      role,
        "content":   content,
        "timestamp": datetime.now().isoformat()
    })
    if len(conversations) > MAX_STORED_MESSAGES:
        conversations = conversations[-MAX_STORED_MESSAGES:]
    return conversations


def get_context_messages(conversations):
    """Return last MAX_CONTEXT_MESSAGES in Ollama format (no timestamps)."""
    recent = conversations[-MAX_CONTEXT_MESSAGES:]
    return [{"role": m["role"], "content": m["content"]} for m in recent]


def clear_memory():
    save_memory([])
    return []


def get_stats(conversations):
    return f"I have {len(conversations)} messages in memory, sir."
