import unittest
from unittest.mock import patch, MagicMock
import datetime
import requests

# Import the module under test
import commands

class TestCommands(unittest.TestCase):

    # ─── Time & Date Tests ──────────────────────────────────────────
    @patch('commands.datetime')
    def test_get_time_am(self, mock_datetime):
        # Test morning time (10:15 AM)
        mock_now = MagicMock()
        mock_now.hour = 10
        mock_now.minute = 15
        mock_datetime.datetime.now.return_value = mock_now
        
        self.assertEqual(commands.get_time(), "It's 10:15 AM, sir.")

    @patch('commands.datetime')
    def test_get_time_pm(self, mock_datetime):
        # Test afternoon time (3:45 PM)
        mock_now = MagicMock()
        mock_now.hour = 15
        mock_now.minute = 45
        mock_datetime.datetime.now.return_value = mock_now
        
        self.assertEqual(commands.get_time(), "It's 3:45 PM, sir.")

    @patch('commands.datetime')
    def test_get_time_midnight(self, mock_datetime):
        # Test midnight (12:05 AM)
        mock_now = MagicMock()
        mock_now.hour = 0
        mock_now.minute = 5
        mock_datetime.datetime.now.return_value = mock_now
        
        self.assertEqual(commands.get_time(), "It's 12:05 AM, sir.")

    @patch('commands.datetime')
    def test_get_time_noon(self, mock_datetime):
        # Test noon (12:00 PM)
        mock_now = MagicMock()
        mock_now.hour = 12
        mock_now.minute = 0
        mock_datetime.datetime.now.return_value = mock_now
        
        self.assertEqual(commands.get_time(), "It's 12:00 PM, sir.")

    @patch('commands.datetime')
    def test_get_date(self, mock_datetime):
        # Test date format formatting
        mock_now = MagicMock()
        mock_now.strftime.return_value = "Wednesday, August 12, 2026"
        mock_datetime.datetime.now.return_value = mock_now
        
        self.assertEqual(commands.get_date(), "Today is Wednesday, August 12, 2026.")
        mock_now.strftime.assert_called_once_with('%A, %B %d, %Y')


    # ─── Weather Tests ──────────────────────────────────────────────
    @patch('commands.requests.get')
    def test_get_weather_success(self, mock_get):
        # Test successful response and degree clean-up
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.text = "Clear, +35°C, feels like +38°C, humidity 60%"
        mock_get.return_value = mock_response

        res = commands.get_weather()
        expected = "Shikarpur right now: Clear, +35 degrees Celsius, feels like +38 degrees Celsius, humidity 60%, sir."
        self.assertEqual(res, expected)

    @patch('commands.requests.get')
    def test_get_weather_timeout(self, mock_get):
        # Test timeout handling
        mock_get.side_effect = requests.Timeout("Timeout occurred")
        res = commands.get_weather()
        self.assertEqual(res, "Weather request timed out. Try again in a moment, sir.")

    @patch('commands.requests.get')
    def test_get_weather_failure(self, mock_get):
        # Test network/service failure handling
        mock_get.side_effect = Exception("Service unavailable")
        res = commands.get_weather()
        self.assertEqual(res, "Weather service is unreachable right now, sir.")


    # ─── App Launcher Tests ─────────────────────────────────────────
    @patch('commands.os.system')
    def test_open_app_success(self, mock_system):
        # Test launcher for valid command
        res = commands.open_app("please open notepad for me")
        self.assertEqual(res, "Opening notepad for you, sir.")
        mock_system.assert_called_with("notepad")

    @patch('commands.os.system')
    def test_open_app_failure(self, mock_system):
        # Test when system command raises exception
        mock_system.side_effect = Exception("Command failed")
        res = commands.open_app("open calculator")
        self.assertEqual(res, "Couldn't open calculator, sir.")

    @patch('commands.os.system')
    def test_open_app_loose_match_bug(self, mock_system):
        # BUG DEMONSTRATION: Loose substring matching causes incorrect apps to open.
        # "open safari browser" contains "browser", which maps to "start chrome" in _APPS.
        # So Chrome is opened instead of returning None or handled correctly.
        res = commands.open_app("open safari browser")
        self.assertEqual(res, "Opening browser for you, sir.")
        mock_system.assert_called_with("start chrome")

    def test_open_app_no_match(self):
        # Test when input does not match any registered apps
        res = commands.open_app("open hyperdrive")
        self.assertIsNone(res)


    # ─── Math Tests (demonstrating current capabilities & limitations) ──
    def test_calculate_valid_basic(self):
        # Basic calculations that work correctly
        self.assertEqual(commands.calculate("what is 5 plus 10"), "That's 15, sir.")
        self.assertEqual(commands.calculate("calculate 10 divided by 2"), "That's 5, sir.")
        self.assertEqual(commands.calculate("100 minus 30"), "That's 70, sir.")
        self.assertEqual(commands.calculate("5 times 6"), "That's 30, sir.")
        self.assertEqual(commands.calculate("3 squared"), "That's 9, sir.")
        self.assertEqual(commands.calculate("2 to the power of 3"), "That's 8, sir.")

    def test_calculate_single_digit_bug(self):
        # BUG DEMONSTRATION: Single numbers are not recognized by regex (requires \d...\d)
        # "what is 5" -> returns None instead of "That's 5, sir."
        self.assertIsNone(commands.calculate("what is 5"))

    def test_calculate_math_functions_bug(self):
        # BUG DEMONSTRATION: Functions like sqrt, sin, cos are not in regex charset,
        # so they are stripped out or partial strings are evaluated incorrectly.
        
        # "calculate sqrt of 16 plus 9" -> matches "16 + 9" directly, returning 25 instead of 5 or 13.
        self.assertEqual(commands.calculate("calculate sqrt of 16 plus 9"), "That's 25, sir.")
        
        # "calculate sin(0.5)" -> matches "0.5" and returns 0.5, completely ignoring sin(...)
        self.assertEqual(commands.calculate("calculate sin(0.5)"), "That's 0.5, sir.")


    # ─── Screen Brightness Tests ────────────────────────────────────
    @patch('subprocess.run')
    def test_adjust_brightness_absolute(self, mock_run):
        # Test setting absolute brightness level
        mock_get_res = MagicMock()
        mock_get_res.stdout = "50\n"
        mock_run.return_value = mock_get_res

        res = commands.adjust_brightness_local("set screen brightness to 80")
        self.assertEqual(res, "Brightness set to 80 percent, sir.")
        mock_run.assert_any_call(
            'powershell -Command "(Get-WmiObject -Namespace root/WMI -Class WmiMonitorBrightnessMethods).WmiSetBrightness(1, 80)"',
            shell=True
        )

    @patch('subprocess.run')
    def test_adjust_brightness_increase_no_number(self, mock_run):
        # Test increasing brightness by default amount (20%)
        mock_get_res = MagicMock()
        mock_get_res.stdout = "40\n"
        mock_run.return_value = mock_get_res

        res = commands.adjust_brightness_local("brighten screen please")
        self.assertEqual(res, "Brightness set to 60 percent, sir.")
        mock_run.assert_any_call(
            'powershell -Command "(Get-WmiObject -Namespace root/WMI -Class WmiMonitorBrightnessMethods).WmiSetBrightness(1, 60)"',
            shell=True
        )

    @patch('subprocess.run')
    def test_adjust_brightness_decrease_no_number(self, mock_run):
        # Test decreasing brightness by default amount (20%)
        mock_get_res = MagicMock()
        mock_get_res.stdout = "40\n"
        mock_run.return_value = mock_get_res

        res = commands.adjust_brightness_local("dim screen")
        self.assertEqual(res, "Brightness set to 20 percent, sir.")

    @patch('subprocess.run')
    def test_adjust_brightness_relative_bug_with_number(self, mock_run):
        # BUG DEMONSTRATION: Relative commands with numbers are treated as absolute values
        # "brighten screen by 10 percent" (expected: 40 + 10 = 50) -> sets it to 10% absolute
        mock_get_res = MagicMock()
        mock_get_res.stdout = "40\n"
        mock_run.return_value = mock_get_res

        res = commands.adjust_brightness_local("brighten screen by 10 percent")
        self.assertEqual(res, "Brightness set to 10 percent, sir.")


    # ─── Lock Screen Tests ──────────────────────────────────────────
    @patch('ctypes.windll')
    def test_lock_screen_success(self, mock_windll):
        # Test calling native Windows LockWorkStation API
        res = commands.lock_screen_local()
        self.assertEqual(res, "Locking the screen now, sir.")
        mock_windll.user32.LockWorkStation.assert_called_once()

    @patch('ctypes.windll')
    def test_lock_screen_failure(self, mock_windll):
        # Test lock screen exception safety
        mock_windll.user32.LockWorkStation.side_effect = Exception("API error")
        res = commands.lock_screen_local()
        self.assertTrue(res.startswith("Could not lock the screen:"))


    # ─── Main Router (handle_command) Tests ─────────────────────────
    @patch('commands.get_time')
    def test_handle_command_time_routing(self, mock_get_time):
        mock_get_time.return_value = "It's 10:15 AM, sir."
        res = commands.handle_command("what is the current time?")
        self.assertEqual(res, "It's 10:15 AM, sir.")
        mock_get_time.assert_called_once()

    def test_handle_command_clear_memory_routing(self):
        res = commands.handle_command("please reset memory")
        self.assertEqual(res, "__CLEAR_MEMORY__")

    def test_handle_command_unhandled(self):
        # Test fallback to AI/None when not a local command
        res = commands.handle_command("what is the distance to Mars?")
        self.assertIsNone(res)

    # ─── Fast Commands Router Tests ─────────────────────────────
    @patch('commands.subprocess.Popen')
    @patch('commands.webbrowser.open')
    def test_launch_workspace_dev(self, mock_web_open, mock_popen):
        res = commands.handle_command("launch dev workspace")
        self.assertEqual(res, "Development workspace launched, sir.")
        mock_popen.assert_called_once_with(["code", "D:\\Development"], shell=True)
        mock_web_open.assert_called_once_with("http://localhost:3000")

    @patch('commands.psutil.disk_usage')
    @patch('commands.psutil.sensors_battery')
    def test_get_detailed_system_health(self, mock_battery, mock_disk):
        mock_battery.return_value = MagicMock(percent=85)
        
        c_mock = MagicMock()
        c_mock.free = 50 * (1024**3)
        d_mock = MagicMock()
        d_mock.free = 150 * (1024**3)
        mock_disk.side_effect = lambda path: c_mock if path == 'C:' else d_mock

        res = commands.handle_command("check my system health and storage")
        self.assertIn("Drive C has 50.0 GB free", res)
        self.assertIn("Drive D has 150.0 GB free", res)
        self.assertIn("Battery is at 85%", res)

    @patch('commands.webbrowser.open')
    def test_play_on_youtube(self, mock_web_open):
        res = commands.handle_command("play logic on youtube")
        self.assertEqual(res, "Searching YouTube for logic.")
        mock_web_open.assert_called_once_with("https://www.youtube.com/results?search_query=logic")

    @patch('commands.pyperclip.paste')
    def test_read_clipboard(self, mock_paste):
        mock_paste.return_value = "hello clipboard"
        res = commands.handle_command("read clipboard")
        self.assertEqual(res, "On your clipboard: hello clipboard")

    @patch('commands.webbrowser.open_new_tab')
    def test_open_new_tab_url(self, mock_open_new_tab):
        res = commands.handle_command("open tab github.com")
        self.assertEqual(res, "Opening github.com in a new tab, sir.")
        mock_open_new_tab.assert_called_once_with("https://github.com")

    @patch('commands.webbrowser.open_new_tab')
    def test_open_new_tab_query(self, mock_open_new_tab):
        res = commands.handle_command("new tab python programming")
        self.assertEqual(res, "Searching Google for python programming in a new tab, sir.")
        mock_open_new_tab.assert_called_once_with("https://www.google.com/search?q=python%20programming")

    @patch('commands.webbrowser.open_new_tab')
    def test_search_specific_site_known(self, mock_open_new_tab):
        res = commands.handle_command("search inception on netflix")
        self.assertEqual(res, "Searching for inception on netflix.")
        mock_open_new_tab.assert_called_once_with("https://www.netflix.com/search?q=inception")

    @patch('commands.webbrowser.open_new_tab')
    def test_search_specific_site_unknown(self, mock_open_new_tab):
        res = commands.handle_command("search for Interstellar on stackoverflow")
        self.assertEqual(res, "Searching for interstellar on stackoverflow.")
        mock_open_new_tab.assert_called_once_with("https://www.google.com/search?q=site:stackoverflow+interstellar")

    @patch('commands.requests.post')
    @patch('docx.Document')
    @patch('commands.threading.Thread')
    @patch('brain.speak')
    def test_generate_university_assignment_success(self, mock_speak, mock_thread, mock_doc_class, mock_post):
        # Mock Ollama API response to yield bytes chunks via iter_lines
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.iter_lines.return_value = [
            b'{"response": "Introduction\\n", "done": false}',
            b'{"response": "This is a test assignment body.\\n", "done": false}',
            b'{"response": "Conclusion", "done": true}'
        ]
        mock_post.return_value = mock_response
        
        # Mock Document instance
        mock_doc_instance = MagicMock()
        mock_doc_class.return_value = mock_doc_instance
        
        # Mock Thread to run target synchronously when start() is called
        def mock_start():
            target = mock_thread.call_args[1].get('target')
            args = mock_thread.call_args[1].get('args', ())
            target(*args)
            
        mock_thread_instance = MagicMock()
        mock_thread_instance.start = mock_start
        mock_thread.return_value = mock_thread_instance
        
        # Reset state to clean
        commands.assignment_state = {"is_active": False, "step": 0, "topic": "", "subject": ""}
        
        # Turn 1: Trigger the machine
        res1 = commands.handle_command("create assignment")
        self.assertEqual(res1, "What topic are you working on for your assignment, sir?")
        self.assertTrue(commands.assignment_state["is_active"])
        self.assertEqual(commands.assignment_state["step"], 1)
        
        # Turn 2: Provide the topic
        res2 = commands.handle_command("Artificial Intelligence")
        self.assertEqual(res2, "And what is the subject name?")
        self.assertEqual(commands.assignment_state["topic"], "Artificial Intelligence")
        self.assertEqual(commands.assignment_state["step"], 2)
        
        # Turn 3: Provide the subject (which triggers background thread and returns confirmation)
        res3 = commands.handle_command("Computer Science")
        expected_msg = "Understood. I am now generating the assignment on Artificial Intelligence for Computer Science in the background. I am listening for your next command, sir."
        self.assertEqual(res3, expected_msg)
        
        # Verify Ollama was called correctly
        mock_post.assert_called_once()
        args, kwargs = mock_post.call_args
        self.assertEqual(args[0], "http://localhost:11434/api/generate")
        self.assertIn("Artificial Intelligence", kwargs["json"]["prompt"])
        self.assertIn("Computer Science", kwargs["json"]["prompt"])
        
        # Verify document methods were called
        mock_doc_class.assert_called_once()
        mock_doc_instance.add_paragraph.assert_any_call(
            "Name: M. Yahya Siddiqui\n"
            "Roll No: 22CS001\n"
            "Department: Computer Systems Engineering, MUET Jamshoro"
        )
        mock_doc_instance.add_heading.assert_called_once_with("Artificial Intelligence", level=0)
        mock_doc_instance.save.assert_called_once()

    def test_generate_university_assignment_cancel(self):
        # Reset state to clean
        commands.assignment_state = {"is_active": False, "step": 0, "topic": "", "subject": ""}
        
        # Turn 1: Trigger the machine
        res1 = commands.handle_command("create assignment")
        self.assertEqual(res1, "What topic are you working on for your assignment, sir?")
        self.assertTrue(commands.assignment_state["is_active"])
        self.assertEqual(commands.assignment_state["step"], 1)
        
        # Turn 2: Cancel the flow
        res2 = commands.handle_command("cancel please")
        self.assertEqual(res2, "Assignment creation cancelled.")
        self.assertFalse(commands.assignment_state["is_active"])
        self.assertEqual(commands.assignment_state["step"], 0)

    @patch('commands.os.startfile')
    @patch('commands.os.path.exists')
    def test_open_assignment_tracked(self, mock_exists, mock_startfile):
        mock_exists.return_value = True
        commands.last_generated_doc = "C:\\Users\\Test\\Desktop\\AI_Assignment.docx"
        
        res = commands.handle_command("open assignment")
        self.assertEqual(res, "Opening your assignment document now, sir.")
        mock_startfile.assert_called_once_with("C:\\Users\\Test\\Desktop\\AI_Assignment.docx")

    @patch('commands.os.startfile')
    @patch('commands.os.path.exists')
    @patch('commands.os.listdir')
    def test_open_assignment_fallback(self, mock_listdir, mock_exists, mock_startfile):
        commands.last_generated_doc = None
        
        # Mock Desktop listdir and path exists
        mock_exists.side_effect = lambda path: True
        mock_listdir.return_value = ["Maths_Assignment.docx", "Notes.txt"]
        
        with patch('commands.os.path.getctime') as mock_getctime:
            mock_getctime.return_value = 1000
            res = commands.handle_command("open the document")
            self.assertEqual(res, "Opening your most recent assignment from the desktop, sir.")
            mock_startfile.assert_called_once()

    @patch('commands.webbrowser.open_new_tab')
    def test_open_and_search_catcher(self, mock_open_new_tab):
        res = commands.handle_command("open daraz.com and search kumar perfume")
        self.assertEqual(res, "Searching for kumar perfume on daraz.")
        mock_open_new_tab.assert_called_once_with("https://www.daraz.pk/catalog/?q=kumar%20perfume")

    @patch('commands.webbrowser.open_new_tab')
    def test_go_to_and_search_catcher(self, mock_open_new_tab):
        res = commands.handle_command("go to amazon and search for mechanical keyboard")
        self.assertEqual(res, "Searching for mechanical keyboard on amazon.")
        mock_open_new_tab.assert_called_once_with("https://www.amazon.com/s?k=mechanical%20keyboard")

    @patch('commands.webdriver.Chrome')
    @patch('commands.Service')
    @patch('commands.ChromeDriverManager')
    def test_check_attendance_trigger_success(self, mock_manager, mock_service, mock_chrome):
        mock_driver = MagicMock()
        mock_chrome.return_value = mock_driver
        
        with patch('commands.WebDriverWait') as mock_wait_cls, \
             patch('commands.Select') as mock_select_cls, \
             patch('commands.time.sleep') as mock_sleep:
            
            mock_wait = MagicMock()
            mock_wait_cls.return_value = mock_wait
            
            # Create mocks for elements
            mock_cnic = MagicMock()
            mock_prov_report = MagicMock()
            mock_ug = MagicMock()
            mock_selects = [MagicMock(), MagicMock()]
            
            # Each wait.until() call will return these in sequence
            mock_wait.until.side_effect = [
                mock_cnic,
                mock_prov_report,
                mock_ug,
                mock_selects
            ]
            
            # find_elements for select tags
            mock_driver.find_elements.return_value = mock_selects
            
            # find_element for inputStudentPassword and studentLogin
            mock_password = MagicMock()
            mock_submit = MagicMock()
            mock_driver.find_element.side_effect = [
                mock_password,
                mock_submit
            ]
            
            res = commands.handle_command("check my attendance")
            
            self.assertEqual(res, "I have successfully logged into the MIS portal and loaded your 8th-semester attendance, sir.")
            mock_chrome.assert_called_once()
            mock_driver.get.assert_called_once_with("http://misportal.muet.edu.pk/mis/login.php")
            mock_cnic.clear.assert_called_once()
            mock_cnic.send_keys.assert_called_once_with("43304-7952345-7")
            mock_password.clear.assert_called_once()
            mock_password.send_keys.assert_called_once_with("yahyamis@01")
            mock_submit.click.assert_called_once()
            mock_prov_report.click.assert_called_once()
            mock_ug.click.assert_called_once()

    @patch('commands.webdriver.Chrome')
    @patch('commands.Service')
    @patch('commands.ChromeDriverManager')
    def test_check_attendance_trigger_failure(self, mock_manager, mock_service, mock_chrome):
        mock_chrome.side_effect = Exception("Browser failed to start")
        
        res = commands.handle_command("check my attendance")
        self.assertEqual(res, "I encountered an error navigating the MIS portal.")

if __name__ == '__main__':
    unittest.main()
