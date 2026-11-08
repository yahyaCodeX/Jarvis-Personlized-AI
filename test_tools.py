import os
import tempfile
import unittest
from unittest.mock import MagicMock, patch

import requests

import tools
from tools import academic, apps, browser, files, info, registry, web


class TestRegistry(unittest.TestCase):
    """Gemini declarations are generated from the function signatures."""

    def test_types_required_and_enums_come_from_signature(self):
        decl = tools.TOOLS["system_control"].declaration()
        props = decl["parameters"]["properties"]
        self.assertEqual(props["action"]["type"], "STRING")
        self.assertEqual(props["value"]["type"], "INTEGER")          # int | None → INTEGER
        self.assertIn("brightness_set", props["action"]["enum"])
        self.assertEqual(decl["parameters"]["required"], ["action"])  # value has a default

    def test_tool_without_params_has_no_required_list(self):
        decl = tools.TOOLS["get_time_and_date"].declaration()
        self.assertEqual(decl["parameters"], {"type": "OBJECT", "properties": {}})

    def test_every_tool_is_documented(self):
        for name, t in tools.TOOLS.items():
            self.assertTrue(t.description.strip(), name)
            for pname in t.declaration()["parameters"]["properties"]:
                self.assertIn(pname, t.params, f"{name}.{pname} has no description for Gemini")

    def test_documenting_a_missing_param_fails_fast(self):
        with self.assertRaises(TypeError):
            registry.tool("x", params={"nope": "..."})(lambda a: a)

    def test_sensitive_tools_are_marked(self):
        sensitive = {n for n, t in tools.TOOLS.items() if t.confirm}
        self.assertEqual(sensitive, {"write_local_file", "close_application", "assistive_checkout"})

    def test_clean_args_drops_invented_arguments(self):
        def fn(a: str, b: int = 1) -> str:
            return a
        self.assertEqual(registry.clean_args(fn, {"a": "x", "zzz": 1}), {"a": "x"})
        self.assertEqual(registry.clean_args(lambda **kw: kw, {"q": 1}), {"q": 1})


class TestInfo(unittest.TestCase):

    def _at(self, hour, minute):
        now = MagicMock(hour=hour, minute=minute)
        return patch("tools.info.datetime", **{"datetime.now.return_value": now})

    def test_get_time(self):
        for (h, m), expected in {(10, 15): "It's 10:15 AM, sir.", (15, 45): "It's 3:45 PM, sir.",
                                 (0, 5): "It's 12:05 AM, sir.", (12, 0): "It's 12:00 PM, sir."}.items():
            with self._at(h, m):
                self.assertEqual(info.get_time(), expected)

    @patch("tools.info.datetime")
    def test_get_date(self, mock_dt):
        mock_dt.datetime.now.return_value.strftime.return_value = "Wednesday, August 12, 2026"
        self.assertEqual(info.get_date(), "Today is Wednesday, August 12, 2026.")

    @patch("tools.info.requests.get")
    def test_get_weather_success(self, mock_get):
        mock_get.return_value = MagicMock(status_code=200, text="Clear, +35°C, feels like +38°C, humidity 60%")
        with patch("tools.info.WEATHER_CITY", "Testville, Sindh"):
            res = info.get_weather()
        self.assertEqual(res, "Testville right now: Clear, +35 degrees Celsius, feels like "
                              "+38 degrees Celsius, humidity 60%, sir.")

    @patch("tools.info.requests.get")
    def test_get_weather_other_city(self, mock_get):
        mock_get.return_value = MagicMock(status_code=200, text="Sunny, +30°C")
        self.assertTrue(info.get_weather("Karachi").startswith("Karachi right now"))
        self.assertIn("wttr.in/Karachi", mock_get.call_args[0][0])

    @patch("tools.info.requests.get", side_effect=requests.Timeout("slow"))
    def test_get_weather_timeout(self, _):
        self.assertEqual(info.get_weather(), "Weather request timed out. Try again in a moment, sir.")

    @patch("tools.info.requests.get", side_effect=Exception("down"))
    def test_get_weather_failure(self, _):
        self.assertEqual(info.get_weather(), "Weather service is unreachable right now, sir.")


class TestWeb(unittest.TestCase):

    def test_play_on_youtube(self):
        fake = MagicMock()
        with patch.dict("sys.modules", {"pywhatkit": fake}):
            self.assertEqual(web.play_on_youtube("logic"), "Playing 'logic' on YouTube now, sir.")
        fake.playonyt.assert_called_once_with("logic")

    @patch("tools.web.force_open_browser")
    def test_play_on_youtube_fallback(self, mock_open):
        fake = MagicMock()
        fake.playonyt.side_effect = Exception("no network")
        with patch.dict("sys.modules", {"pywhatkit": fake}):
            self.assertEqual(web.play_on_youtube("logic"), "Searching YouTube for logic, sir.")
        mock_open.assert_called_once_with("https://www.youtube.com/results?search_query=logic")

    @patch("tools.web.force_open_browser")
    def test_open_website_domain_and_search(self, mock_open):
        web.open_website("github.com")
        mock_open.assert_called_with("https://github.com")
        web.open_website("python tutorials")
        mock_open.assert_called_with("https://www.google.com/search?q=python%20tutorials")


class TestApps(unittest.TestCase):

    @patch("tools.apps.subprocess.run")
    def test_brightness_set_clamps_and_uses_arg_list(self, mock_run):
        mock_run.return_value = MagicMock(returncode=0)
        self.assertEqual(apps.system_control("brightness_set", 150), "Brightness set to 100 percent, sir.")
        cmd = mock_run.call_args[0][0]
        self.assertIsInstance(cmd, list)
        self.assertIn("Brightness=100", cmd[-1])
        self.assertNotIn("shell", mock_run.call_args[1])

    @patch("tools.apps.set_brightness", return_value="ok")
    @patch("tools.apps._get_brightness", return_value=50)
    def test_brightness_up_down(self, _get, mock_set):
        apps.system_control("brightness_up")
        mock_set.assert_called_with(70)
        apps.system_control("brightness_down", 10)
        mock_set.assert_called_with(40)

    @patch("tools.apps._get_brightness", return_value=None)
    def test_brightness_unsupported_display(self, _):
        self.assertIn("doesn't support", apps.system_control("brightness_up"))

    @patch("tools.apps._press_media_key")
    def test_media_control(self, mock_key):
        apps.media_control("play_pause")
        mock_key.assert_called_once_with(0xB3)
        self.assertIn("Unknown", apps.media_control("rewind"))

    @patch("tools.apps.os.system")
    def test_open_known_app(self, mock_system):
        self.assertEqual(apps.open_application("notepad"), "Opening notepad for you, sir.")
        mock_system.assert_called_once_with("notepad")


class TestFolders(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.env = patch.dict(os.environ, {"JARVIS_ALLOWED_DIRS": self.tmp.name})
        self.env.start()

    def tearDown(self):
        self.env.stop()
        self.tmp.cleanup()

    def test_create_folder_inside_sandbox(self):
        res = files.create_folder("NewProject", self.tmp.name)
        self.assertIn("created", res)
        self.assertTrue(os.path.isdir(os.path.join(self.tmp.name, "NewProject")))

    def test_create_folder_outside_sandbox_refused(self):
        self.assertIn("outside", files.create_folder("evil", r"C:\Windows"))
        self.assertFalse(os.path.exists(r"C:\Windows\evil"))

    def test_create_folder_rejects_traversal(self):
        self.assertIn("valid folder name", files.create_folder("..\\..\\x", self.tmp.name))

    @patch("tools.files.os.startfile")
    def test_open_local_folder_never_creates_or_runs_files(self, mock_startfile):
        missing = os.path.join(self.tmp.name, "does_not_exist")
        self.assertIn("couldn't find", files.open_local_folder(missing))
        self.assertFalse(os.path.exists(missing))
        exe = os.path.join(self.tmp.name, "app.exe")
        open(exe, "w").close()
        self.assertIn("couldn't find", files.open_local_folder(exe))
        mock_startfile.assert_not_called()


class TestAcademic(unittest.TestCase):

    def setUp(self):
        academic._last_attendance_time = 0
        academic._attendance_cache_result = None
        academic._attendance_cache_timestamp = 0

    @patch("tools.academic.speak")
    @patch("tools.academic.requests.post")
    @patch("docx.Document")
    def test_generate_assignment_uses_profile_header(self, mock_doc_class, mock_post, mock_speak):
        mock_post.return_value.iter_lines.return_value = [
            b'{"response": "Introduction", "done": false}',
            b'{"response": " body", "done": true}',
        ]
        doc = mock_doc_class.return_value
        profile = {"name": "Test Student", "roll_no": "00XX000", "department": "Testing Dept"}
        with patch("tools.academic.load_profile", return_value=profile), \
                patch.dict(os.environ, {"OLLAMA_MODEL": "test-model"}):
            academic.generate_assignment_thread("Artificial Intelligence", "Computer Science")

        self.assertEqual(mock_post.call_args[1]["json"]["model"], "test-model")
        self.assertIn("Artificial Intelligence", mock_post.call_args[1]["json"]["prompt"])
        doc.add_paragraph.assert_any_call("Name: Test Student\nRoll No: 00XX000\nDepartment: Testing Dept")
        doc.add_heading.assert_called_once_with("Artificial Intelligence", level=0)
        self.assertTrue(doc.save.call_args[0][0].endswith("Artificial_Intelligence_Assignment.docx"))
        self.assertIn("saved to your desktop", mock_speak.call_args[0][0])

    @patch("tools.academic.threading.Thread")
    def test_generate_assignment_runs_in_background(self, mock_thread):
        res = academic.generate_assignment("AI", "CS")
        mock_thread.return_value.start.assert_called_once()
        self.assertIn("background", res)

    @patch("tools.academic.os.startfile")
    def test_open_last_assignment(self, mock_startfile):
        with tempfile.NamedTemporaryFile(suffix="_Assignment.docx", delete=False) as f:
            path = f.name
        try:
            academic.last_generated_doc = path
            self.assertIn("Opening", academic.open_last_assignment())
            mock_startfile.assert_called_once_with(path)
        finally:
            os.remove(path)

    def test_attendance_needs_credentials(self):
        with patch.dict(os.environ, {"MIS_CNIC": "", "MIS_PASSWORD": ""}):
            self.assertIn("missing", academic.check_attendance())

    def test_attendance_logs_in_and_selects_class(self):
        page = MagicMock()
        select = MagicMock()
        select.locator.return_value.all_inner_texts.return_value = ["--", "Class 99XX-I - Semester 3"]
        page.locator.return_value.nth.return_value = select
        page.locator.return_value.count.return_value = 2
        profile = {"mis": {"department": "Testing", "class": "Semester 3"}}
        select.locator.return_value.all_inner_texts.side_effect = [["Dept of Testing"], ["Class 99XX-I - Semester 3"]]

        with patch.dict(os.environ, {"MIS_CNIC": "11111-1111111-1", "MIS_PASSWORD": "pw"}), \
                patch("tools.browser.get_active_page", return_value=page), \
                patch("tools.academic.load_profile", return_value=profile):
            res = academic.check_attendance()

        page.goto.assert_called_once_with(academic.MIS_LOGIN_URL, timeout=20000)
        page.locator.return_value.press_sequentially.assert_called_once_with("11111-1111111-1", delay=30)
        select.select_option.assert_any_call(label="Class 99XX-I - Semester 3")
        self.assertIn("Semester 3", res)
        # second call within 15 minutes is served from cache, no new login
        self.assertEqual(academic.check_attendance(), res)
        page.goto.assert_called_once()

    def test_attendance_failure_is_reported(self):
        page = MagicMock()
        page.goto.side_effect = Exception("timeout")
        with patch.dict(os.environ, {"MIS_CNIC": "1", "MIS_PASSWORD": "pw"}), \
                patch("tools.browser.get_active_page", return_value=page):
            self.assertIn("problem navigating the MIS portal", academic.check_attendance())

    @patch("tools.academic.requests.post")
    def test_ask_local_qwen(self, mock_post):
        mock_post.return_value.json.return_value = {"response": " 42 "}
        self.assertEqual(academic.ask_local_qwen("meaning of life?"), "42")


class TestCheckoutSummary(unittest.TestCase):

    def test_summary_only_reveals_last_four_digits(self):
        with patch.dict(browser.USER_PROFILES, {"default_phone": "03001234567"}):
            s = browser._summarize_checkout({"address_choice": "home"})
        self.assertIn("home address", s)
        self.assertIn("4567", s)
        self.assertNotIn("0300123", s)


if __name__ == "__main__":
    unittest.main()
