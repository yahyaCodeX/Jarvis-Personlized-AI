import asyncio
import os
import tempfile
import unittest
from unittest.mock import patch

import jarvis_server as js
from safety import ConfirmationGate


class TestServerConfirmationFlow(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.target = os.path.join(self.tmp.name, "app.py")
        self.calls = []
        self.patches = [
            patch.dict(os.environ, {"JARVIS_ALLOWED_DIRS": self.tmp.name,
                                    "JARVIS_REQUIRE_CONFIRMATION": "1"}),
            patch.object(js, "gate", ConfirmationGate()),
            patch.dict(js.tools_map, {"write_local_file": lambda **kw: self.calls.append(kw) or "written"}),
        ]
        for p in self.patches:
            p.start()
        js._last_tool_timestamps.clear()

    def tearDown(self):
        for p in reversed(self.patches):
            p.stop()
        self.tmp.cleanup()

    def run_tool(self, name, args):
        return asyncio.run(js.execute_tool_safely(name, args))

    def _request_write(self):
        res = self.run_tool("write_local_file", {"filepath": self.target, "new_content": "print(1)\n"})
        self.assertIn("CONFIRMATION REQUIRED", res)
        self.assertEqual(self.calls, [], "tool must not run before confirmation")
        return res.split("token='")[1].split("'")[0]

    def test_model_cannot_self_confirm(self):
        token = self._request_write()
        res = self.run_tool("confirm_action", {"token": token})
        self.assertIn("not said", res)
        self.assertEqual(self.calls, [])

    def test_user_voice_confirm_executes(self):
        token = self._request_write()
        js.gate.record_user_speech("yes, confirm")
        self.assertEqual(self.run_tool("confirm_action", {"token": token}), "written")
        self.assertEqual(len(self.calls), 1)

    def test_blocked_path_skips_confirmation_and_is_refused(self):
        # A path outside the sandbox is refused by the tool itself (real function)
        with patch.dict(js.tools_map, {"write_local_file": js.TOOLS["write_local_file"].fn}):
            res = self.run_tool("write_local_file", {"filepath": r"C:\Windows\x.py", "new_content": "x"})
        self.assertIn("outside", res)


class TestHudButtons(TestServerConfirmationFlow):
    """HUD Confirm/Cancel run (or drop) the pending action and tell Gemini."""

    def setUp(self):
        super().setUp()
        self.notes = []
        notes = self.notes

        class FakeSession:
            async def send_client_content(self, turns, turn_complete):
                notes.append(turns[0].parts[0].text)

        p = patch.object(js, "_live_session", FakeSession())
        p.start()
        self.patches.append(p)

    def test_hud_confirm_runs_action_and_notifies_model(self):
        token = self._request_write()
        asyncio.run(js._resolve_from_hud(approved=True))
        self.assertEqual(len(self.calls), 1)
        self.assertFalse(js.gate.is_pending(token))
        self.assertIn("pressed Confirm", self.notes[0])
        self.assertIn("written", self.notes[0])

    def test_hud_cancel_drops_action(self):
        token = self._request_write()
        asyncio.run(js._resolve_from_hud(approved=False))
        self.assertEqual(self.calls, [])
        self.assertFalse(js.gate.is_pending(token))
        self.assertIn("pressed Cancel", self.notes[0])

    def test_hud_confirm_with_nothing_pending_is_harmless(self):
        asyncio.run(js._resolve_from_hud(approved=True))
        self.assertEqual(self.calls, [])
        self.assertEqual(self.notes, [])


if __name__ == "__main__":
    unittest.main()
