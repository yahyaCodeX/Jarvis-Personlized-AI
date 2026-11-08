import math
import struct
import unittest

from audio_gate import BargeInGate, pcm_rms


def tone(level: float, n: int = 1024) -> bytes:
    """A 16-bit mono sine chunk with the given RMS level (0-1)."""
    amp = level * math.sqrt(2) * 32767
    return struct.pack(f"<{n}h", *(int(amp * math.sin(i / 5)) for i in range(n)))


class TestBargeIn(unittest.TestCase):

    def setUp(self):
        self.gate = BargeInGate(enabled=True, ratio=3.0, min_level=0.03)

    def feed(self, level, count, speaking=True, allow=True):
        out = []
        for _ in range(count):
            out += self.gate.process(tone(level), speaking, allow)
        return out

    def test_rms(self):
        self.assertAlmostEqual(pcm_rms(tone(0.1)), 0.1, delta=0.01)
        self.assertEqual(pcm_rms(b""), 0.0)

    def test_everything_passes_when_jarvis_is_quiet(self):
        self.assertEqual(len(self.feed(0.001, 5, speaking=False)), 5)

    def test_echo_of_jarvis_is_blocked(self):
        self.assertEqual(self.feed(0.05, 60), [])       # steady echo, never forwarded
        self.assertFalse(self.gate.is_open)

    def test_user_talking_over_jarvis_opens_gate_with_preroll(self):
        self.feed(0.05, 20)                                # learn the echo level
        out = self.feed(0.4, 3)                            # user speaks 8x louder
        self.assertTrue(self.gate.is_open)
        self.assertGreaterEqual(len(out), 3)               # pre-roll keeps the start of the sentence
        self.assertEqual(len(self.feed(0.4, 2)), 2)        # then streams live
        self.assertEqual(self.gate.triggered_count, 1)

    def test_short_loud_burst_is_learned_as_echo(self):
        self.feed(0.05, 20)
        self.feed(0.4, 2)                                  # only 2 loud chunks: not speech
        self.feed(0.05, 1)
        self.assertFalse(self.gate.is_open)
        self.assertGreater(self.gate.threshold(), 0.4 * 0.9)

    def test_false_alarm_closes_and_raises_threshold(self):
        self.feed(0.05, 20)
        self.feed(0.3, 3)
        self.assertTrue(self.gate.is_open)
        self.feed(0.3, self.gate.max_open_chunks)          # Gemini never interrupted → echo
        self.assertFalse(self.gate.is_open)
        self.assertEqual(self.feed(0.3, 10), [])           # same level no longer triggers

    def test_reset_when_jarvis_stops(self):
        self.feed(0.05, 20)
        self.feed(0.4, 3)
        self.feed(0.001, 1, speaking=False)
        self.assertFalse(self.gate.is_open)
        self.assertEqual(self.gate.threshold(), 0.03)

    def test_disabled_while_confirmation_pending(self):
        self.feed(0.05, 20, allow=False)
        self.assertEqual(self.feed(0.5, 10, allow=False), [])

    def test_can_be_turned_off(self):
        gate = BargeInGate(enabled=False)
        self.assertEqual(gate.process(tone(0.6), True), [])
        self.assertEqual(len(gate.process(tone(0.6), False)), 1)


if __name__ == "__main__":
    unittest.main()
