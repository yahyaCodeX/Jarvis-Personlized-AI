"""
audio_gate.py — barge-in: let the user interrupt Jarvis while it is talking.

The problem: if the mic is open while Jarvis speaks through laptop speakers, the
mic hears Jarvis's own voice and Gemini interrupts itself. The old fix was to
mute the mic completely while Jarvis talked, so the user could never cut in.

BargeInGate keeps the mic muted for echo but opens it for the user:
  * While Jarvis speaks, it tracks how loud the echo of Jarvis's voice is
    (a slowly decaying peak of the mic level).
  * If the mic gets clearly louder than that echo (ratio x) for a few chunks in
    a row, that is the user talking over Jarvis. The gate opens and forwards the
    audio, including a short pre-roll so the start of the sentence is not lost.
    Gemini's own voice detection then interrupts Jarvis.
  * When Jarvis stops speaking, the gate resets and everything is forwarded as usual.

Barge-in is disabled while a sensitive action waits for "confirm", so Jarvis's own
echoed voice can never reach the confirmation transcript.

Tune in .env:
  JARVIS_BARGE_IN=0                 turn it off (mic muted while Jarvis talks, the old behaviour)
  JARVIS_BARGE_IN_RATIO=3.0         how much louder than the echo you must be (raise if Jarvis interrupts itself)
  JARVIS_BARGE_IN_MIN_LEVEL=0.03    minimum mic level (0-1 RMS) that can count as speech
With headphones there is no echo, so barge-in works at normal speaking volume.
"""

from __future__ import annotations

import math
import os
from array import array
from collections import deque


def pcm_rms(pcm: bytes) -> float:
    """RMS of 16-bit little-endian mono PCM, 0.0 - 1.0."""
    samples = array("h")
    samples.frombytes(pcm[: len(pcm) - len(pcm) % 2])
    if not samples:
        return 0.0
    return math.sqrt(sum(s * s for s in samples) / len(samples)) / 32768.0


def _env_float(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, default))
    except ValueError:
        return default


class BargeInGate:
    def __init__(self, enabled: bool | None = None, ratio: float | None = None,
                 min_level: float | None = None, trigger_chunks: int = 3,
                 preroll_chunks: int = 6, warmup_chunks: int = 8, echo_decay: float = 0.97,
                 max_open_chunks: int = 40):
        self.enabled = (os.getenv("JARVIS_BARGE_IN", "1").strip() != "0") if enabled is None else enabled
        self.ratio = _env_float("JARVIS_BARGE_IN_RATIO", 3.0) if ratio is None else ratio
        self.min_level = _env_float("JARVIS_BARGE_IN_MIN_LEVEL", 0.03) if min_level is None else min_level
        self.trigger_chunks = trigger_chunks   # 3 x 64 ms ≈ 0.2 s of sustained speech
        self.warmup_chunks = warmup_chunks     # first ~0.5 s of each reply: only learn the echo level
        self.echo_decay = echo_decay
        self.max_open_chunks = max_open_chunks  # ~2.5 s open while Jarvis keeps talking = false alarm
        self._preroll: deque[bytes] = deque(maxlen=preroll_chunks)
        self.triggered_count = 0
        self._reset()

    def _reset(self) -> None:
        self._echo = 0.0
        self._loud = 0
        self._seen = 0
        self._open = False
        self._open_chunks = 0
        self._streak: list[float] = []
        self._open_peak = 0.0
        self._preroll.clear()

    @property
    def is_open(self) -> bool:
        return self._open

    def threshold(self) -> float:
        return max(self.min_level, self._echo * self.ratio)

    def process(self, pcm: bytes, jarvis_speaking: bool, allow: bool = True) -> list[bytes]:
        """Return the chunks to send to Gemini for this mic chunk (possibly none)."""
        if not jarvis_speaking:
            if self._seen:
                self._reset()
            return [pcm]
        if not self.enabled or not allow:
            self._reset()
            return []
        level = pcm_rms(pcm)
        if self._open:
            self._open_chunks += 1
            self._open_peak = max(self._open_peak, level)
            if self._open_chunks < self.max_open_chunks:
                return [pcm]
            # Gemini never interrupted, so that was Jarvis's own echo: close and raise the bar
            self._echo = max(self._echo, self._open_peak)
            self._open, self._open_chunks, self._open_peak = False, 0, 0.0
            self._loud, self._streak = 0, []
            return []

        self._seen += 1
        self._preroll.append(pcm)

        if self._seen <= self.warmup_chunks or level <= self.threshold():
            # Echo of Jarvis's own voice (or silence): remember how loud it gets.
            # A loud burst too short to be speech was an echo peak, so learn it too.
            self._echo = max([level, self._echo * self.echo_decay] + self._streak)
            self._loud, self._streak = 0, []
            return []

        self._loud += 1
        self._streak.append(level)
        if self._loud < self.trigger_chunks:
            return []

        self._open = True
        self._open_peak = max(self._streak)
        self._streak = []
        self.triggered_count += 1
        chunks = list(self._preroll)
        self._preroll.clear()
        return chunks
