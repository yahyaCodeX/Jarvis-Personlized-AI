import os
import tempfile
import time
import unittest
from unittest.mock import patch

import safety
import commands


class TestPathSandbox(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = self.tmp.name
        self.env = patch.dict(os.environ, {"JARVIS_ALLOWED_DIRS": self.root})
        self.env.start()

    def tearDown(self):
        self.env.stop()
        self.tmp.cleanup()

    def test_inside_allowed_dir_ok(self):
        ok, path = safety.check_path(os.path.join(self.root, "a.py"))
        self.assertTrue(ok)
        self.assertTrue(path.endswith("a.py"))

    def test_outside_allowed_dir_blocked(self):
        ok, reason = safety.check_path(r"C:\Windows\System32\drivers\etc\hosts")
        self.assertFalse(ok)
        self.assertIn("outside", reason)

    def test_dotdot_escape_blocked(self):
        ok, _ = safety.check_path(os.path.join(self.root, "..", "..", "evil.txt"))
        self.assertFalse(ok)

    def test_secret_files_blocked_even_inside_allowed_dir(self):
        for name in [".env", ".env.local", "profile.json", "owner_voice.wav", os.path.join(".git", "config")]:
            ok, reason = safety.check_path(os.path.join(self.root, name))
            self.assertFalse(ok, name)
            self.assertIn("blocked", reason)

    def test_write_local_file_respects_sandbox_and_makes_backup(self):
        target = os.path.join(self.root, "code.py")
        with open(target, "w", encoding="utf-8") as f:
            f.write("old\n")
        res = commands.write_local_file(target, "new\n")
        self.assertIn("Successfully", res)
        with open(target + ".bak", encoding="utf-8") as f:
            self.assertEqual(f.read(), "old\n")

        res = commands.write_local_file(r"C:\Windows\evil.py", "x")
        self.assertIn("outside", res)
        self.assertFalse(os.path.exists(r"C:\Windows\evil.py"))

    def test_read_local_file_blocks_env(self):
        res = commands.read_local_file(os.path.join(self.root, ".env"))
        self.assertIn("blocked", res)


class TestConfirmationGate(unittest.TestCase):

    def setUp(self):
        self.gate = safety.ConfirmationGate()

    def test_no_speech_means_not_confirmed(self):
        tok = self.gate.request("write_local_file", {}, "overwrite x")
        ok, reason = self.gate.resolve(tok)
        self.assertFalse(ok)
        self.assertIn("not said", reason)

    def test_speech_before_request_does_not_count(self):
        self.gate.record_user_speech("yes")
        time.sleep(0.01)
        tok = self.gate.request("write_local_file", {}, "overwrite x")
        ok, _ = self.gate.resolve(tok)
        self.assertFalse(ok)

    def test_spoken_confirm_approves(self):
        tok = self.gate.request("close_application", {"app_name": "chrome"}, "close chrome")
        self.gate.record_user_speech("yes confirm")
        ok, entry = self.gate.resolve(tok)
        self.assertTrue(ok)
        self.assertEqual(entry["args"], {"app_name": "chrome"})
        # Token is single-use
        self.assertFalse(self.gate.resolve(tok)[0])

    def test_negative_wins_over_affirmative(self):
        tok = self.gate.request("write_local_file", {}, "overwrite x")
        self.gate.record_user_speech("no don't do it")
        ok, reason = self.gate.resolve(tok)
        self.assertFalse(ok)
        self.assertIn("declined", reason)

    def test_wrong_token_rejected(self):
        self.gate.request("write_local_file", {}, "overwrite x")
        self.gate.record_user_speech("confirm")
        self.assertFalse(self.gate.resolve("bogus")[0])

    def test_pop_latest_for_hud_buttons(self):
        self.gate.request("write_local_file", {}, "older")
        time.sleep(0.01)
        tok = self.gate.request("assistive_checkout", {"address_choice": "home"}, "newest")
        popped_tok, entry = self.gate.pop_latest()
        self.assertEqual(popped_tok, tok)
        self.assertEqual(entry["summary"], "newest")
        self.assertFalse(self.gate.is_pending(tok))
        self.assertEqual(self.gate.pop_latest()[1]["summary"], "older")
        self.assertIsNone(self.gate.pop_latest())

    def test_expired_request(self):
        tok = self.gate.request("write_local_file", {}, "overwrite x")
        self.gate._pending[tok]["created"] -= safety.CONFIRM_TIMEOUT_S + 1
        self.gate.record_user_speech("confirm")
        self.assertFalse(self.gate.resolve(tok)[0])


class TestShellInjection(unittest.TestCase):

    @patch("commands.subprocess.run")
    def test_close_application_rejects_metacharacters(self, mock_run):
        res = commands.close_application("chrome & del C:\\important")
        self.assertIn("valid application name", res)
        mock_run.assert_not_called()

    @patch("commands.subprocess.run")
    def test_close_application_uses_arg_list(self, mock_run):
        mock_run.return_value.returncode = 0
        commands.close_application("notepad")
        args, kwargs = mock_run.call_args
        self.assertEqual(args[0], ["taskkill", "/f", "/im", "notepad.exe"])
        self.assertNotIn("shell", kwargs)

    def test_close_application_protects_jarvis_itself(self):
        self.assertIn("blocked", commands.close_application("python"))

    @patch("commands.os.system")
    @patch("commands.subprocess.Popen")
    @patch("commands.os.startfile")
    def test_open_application_rejects_injection(self, mock_startfile, mock_popen, mock_system):
        res = commands.open_application('foo" & evil.exe & "')
        self.assertIn("couldn't find", res)
        mock_popen.assert_not_called()
        mock_system.assert_not_called()

    @patch("commands.os.startfile")
    def test_open_application_refuses_scripts(self, mock_startfile):
        with tempfile.NamedTemporaryFile(suffix=".bat", delete=False) as f:
            path = f.name
        try:
            res = commands.open_application(path)
            self.assertIn("won't run script", res)
            mock_startfile.assert_not_called()
        finally:
            os.remove(path)

    @patch("commands.os.startfile")
    def test_force_open_browser_rejects_non_http(self, mock_startfile):
        self.assertFalse(commands.force_open_browser('" & calc & "'))
        mock_startfile.assert_not_called()


if __name__ == "__main__":
    unittest.main()
