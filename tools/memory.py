"""Long-term memory: facts the user asked Jarvis to remember (jarvis_memory.json)."""

from __future__ import annotations

import json
import os

from config import BASE_DIR
from .registry import tool

MEMORY_FILE = os.path.join(BASE_DIR, "jarvis_memory.json")
MAX_MEMORIES = 200


def _load_memories() -> list:
    try:
        with open(MEMORY_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, list) else []
    except (FileNotFoundError, json.JSONDecodeError):
        return []


@tool("Saves a fact or preference about the user permanently, so you remember it in future sessions.",
      params={"fact": "The fact in one short sentence, e.g. 'User prefers dark mode'"})
def remember_fact(fact: str) -> str:
    fact_clean = (fact or "").strip()
    if not fact_clean:
        return "Fact cannot be empty, sir."

    memories = _load_memories()
    if any(m.lower() == fact_clean.lower() for m in memories):
        return f"I already know that, sir: '{fact_clean}'."
    memories.append(fact_clean)
    memories = memories[-MAX_MEMORIES:]

    tmp_path = MEMORY_FILE + ".tmp"
    try:
        with open(tmp_path, "w", encoding="utf-8") as f:
            json.dump(memories, f, indent=2, ensure_ascii=False)
        os.replace(tmp_path, MEMORY_FILE)   # atomic: never leaves a half-written file
        return f"Remembered: '{fact_clean}', sir."
    except Exception as e:
        return f"Failed to save memory: {e}"


def get_all_memories() -> str:
    """Saved facts as a bullet list (goes into the system prompt)."""
    memories = _load_memories()
    if not memories:
        return "No previous memories."
    return "\n".join(f"- {m}" for m in memories)
