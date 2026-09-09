# commands.py — Instant local skills for Jarvis (zero AI latency)
# These commands are handled locally — no Ollama call, no wait time.

import datetime
import json
import requests
import os
import re
import math as _math
import subprocess
import webbrowser
import urllib.parse
import ctypes
import psutil
import pyautogui
import pyperclip
import threading
import win32com.client
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import Select
from webdriver_manager.chrome import ChromeDriverManager
from playwright.sync_api import sync_playwright
import time
import io
from PIL import ImageGrab, Image

# Global state for multi-turn assignment generation
assignment_state = {
    "is_active": False,
    "step": 0,
    "topic": "",
    "subject": ""
}

# Global tracking variable for the last generated assignment document path
last_generated_doc = None

# Global tracking variable for the last opened directory folder path
last_opened_folder = None

# ─── Config ──────────────────────────────────────────────────
WEATHER_CITY = "Jamshoro, Sindh"

# ─── Time & Date ─────────────────────────────────────────────
def get_time():
    now = datetime.datetime.now()
    h = now.hour % 12 or 12
    m = now.minute
    period = "AM" if now.hour < 12 else "PM"
    return f"It's {h}:{m:02d} {period}, sir."

def get_date():
    now = datetime.datetime.now()
    return f"Today is {now.strftime('%A, %B %d, %Y')}."

# ─── Weather (free, no API key) ───────────────────────────────
def get_weather():
    try:
        city = WEATHER_CITY.replace(" ", "+").replace(",", "")
        url = f"https://wttr.in/{city}?format=%C,+%t,+feels+like+%f,+humidity+%h"
        r = requests.get(url, timeout=6, headers={"User-Agent": "curl/7.68.0"})
        if r.status_code == 200 and r.text.strip():
            weather_text = r.text.strip()
            # Clean up Unicode degree symbol to avoid console encoding crashes
            # and make SAPI speech engine read it correctly.
            weather_text = weather_text.replace("°C", " degrees Celsius")
            weather_text = weather_text.replace("°F", " degrees Fahrenheit")
            weather_text = weather_text.replace("°", " degrees")
            return f"Shikarpur right now: {weather_text}, sir."
        return "Couldn't get the weather for Shikarpur right now, sir."
    except requests.Timeout:
        return "Weather request timed out. Try again in a moment, sir."
    except Exception:
        return "Weather service is unreachable right now, sir."

# ─── App Launcher ────────────────────────────────────────────
_APPS = {
    "notepad":       "notepad",
    "calculator":    "calc",
    "calc":          "calc",
    "paint":         "mspaint",
    "chrome":        "start chrome",
    "browser":       "start chrome",
    "google":        "start chrome",
    "explorer":      "explorer",
    "file explorer": "explorer",
    "files":         "explorer",
    "task manager":  "taskmgr",
    "vs code":       "code .",
    "vscode":        "code .",
    "spotify":       "start spotify",
    "word":          "start winword",
    "excel":         "start excel",
    "powerpoint":    "start powerpnt",
    "ppt":           "start powerpnt",
    "cmd":           "start cmd",
    "command prompt":"start cmd",
    "terminal":      "start cmd",
}

def open_app(text):
    for app_key, cmd in _APPS.items():
        if app_key in text:
            try:
                os.system(cmd)
                return f"Opening {app_key} for you, sir."
            except Exception:
                return f"Couldn't open {app_key}, sir."
    return None

# ─── Math ────────────────────────────────────────────────────
_SAFE_MATH = {k: getattr(_math, k) for k in dir(_math) if not k.startswith('_')}
_SAFE_MATH.update({'abs': abs, 'round': round})

def calculate(text):
    expr = text.lower()
    expr = re.sub(r'\btimes\b',         '*',  expr)
    expr = re.sub(r'\bmultiplied by\b', '*',  expr)
    expr = re.sub(r'\bdivided by\b',    '/',  expr)
    expr = re.sub(r'\bover\b',          '/',  expr)
    expr = re.sub(r'\bplus\b',          '+',  expr)
    expr = re.sub(r'\bminus\b',         '-',  expr)
    expr = re.sub(r'\bsquared\b',       '**2',expr)
    expr = re.sub(r'\bto the power of\b','**',expr)

    # Extract a math-looking substring
    match = re.search(r'(\d[\d\s\+\-\*\/\.\(\)\*\^%]+\d)', expr)
    if not match:
        return None

    math_str = match.group(1).strip().replace('^', '**')
    try:
        result = eval(math_str, {"__builtins__": {}}, _SAFE_MATH)
        if isinstance(result, float) and result.is_integer():
            result = int(result)
        return f"That's {result}, sir."
    except Exception:
        return None

# ─── Trigger word lists ───────────────────────────────────────
_TIME_WORDS    = ["what time", "what's the time", "current time", "time is it"]
_DATE_WORDS    = ["what date", "what's the date", "today's date", "what day", "what is today", "day is it"]
_WEATHER_WORDS = ["weather", "temperature", "how hot", "how cold", "forecast", "raining", "sunny", "cloudy"]
_OPEN_WORDS    = ["open ", "launch ", "start "]
_MATH_WORDS    = [" plus ", " minus ", " times ", "divided", "multiplied", "squared",
                  "calculate ", "what is ", "what's "]
_CLEAR_WORDS   = ["clear memory", "forget everything", "reset memory", "wipe memory",
                  "clear your memory", "forget all"]

# ─── Main Router ─────────────────────────────────────────────
def handle_command(text):
    """
    Returns a response string if this is a local command, else returns None.
    Special return '__CLEAR_MEMORY__' signals brain.py to wipe memory.
    """
    t = text.lower().strip()

    if any(p in t for p in _TIME_WORDS):
        return get_time()

    if any(p in t for p in _DATE_WORDS):
        return get_date()

    if any(p in t for p in _WEATHER_WORDS):
        return get_weather()

    if any(p in t or ("please " + p) in t for p in _OPEN_WORDS):
        result = open_app(t)
        if result:
            return result

    if any(trig in t for trig in _MATH_WORDS):
        result = calculate(t)
        if result:
            return result

    if any(p in t for p in _CLEAR_WORDS):
        return "__CLEAR_MEMORY__"

    # ─── Instant Local screen brightness adjustments ─────────────
    if "brightness" in t or "dim " in t or "brighten" in t:
        res = adjust_brightness_local(t)
        if res:
            return res

    # ─── Instant Local screen lock ──────────────────────────────
    if any(p in t for p in ["lock screen", "lock my pc", "lock the pc", "lock computer", "lock the computer"]):
        return lock_screen_local()

    # ─── Process Fast Commands ──────────────────────────────────
    fast_res = process_fast_command(text)
    if fast_res is not None:
        return fast_res

    return None


def adjust_brightness_local(text):
    """Adjusts screen brightness using native Windows WMI via PowerShell."""
    import subprocess
    t = text.lower().strip()

    # Check direction
    is_increase = "increase" in t or "brighten" in t or "up" in t or "raise" in t
    is_decrease = "decrease" in t or "dim" in t or "down" in t or "lower" in t

    # Find level in text
    match = re.search(r'\d+', t)
    
    current = 50  # Fallback current level
    try:
        # Get current brightness level
        cmd_get = 'powershell -Command "(Get-WmiObject -Namespace root/WMI -Class WmiMonitorBrightness).CurrentBrightness"'
        res = subprocess.run(cmd_get, capture_output=True, text=True, shell=True)
        if res.stdout.strip():
            current = int(res.stdout.strip())
    except Exception:
        pass

    if match:
        level = int(match.group(0))
        level = max(0, min(100, level))  # Clamp between 0 and 100
    elif is_increase:
        level = min(100, current + 20)
    elif is_decrease:
        level = max(0, current - 20)
    else:
        return None

    try:
        # Set WMI Brightness
        cmd_set = f'powershell -Command "(Get-WmiObject -Namespace root/WMI -Class WmiMonitorBrightnessMethods).WmiSetBrightness(1, {level})"'
        subprocess.run(cmd_set, shell=True)
        return f"Brightness set to {level} percent, sir."
    except Exception as e:
        return f"Could not change brightness: {e}"


def lock_screen_local():
    """Instantly locks Windows session using the Win32 user32.dll API."""
    import ctypes
    try:
        ctypes.windll.user32.LockWorkStation()
        return "Locking the screen now, sir."
    except Exception as e:
        return f"Could not lock the screen: {e}"

# --- WORKSPACE PRESETS ---
def launch_workspace(preset_name):
    preset_name = preset_name.lower()
    try:
        if "dev" in preset_name or "code" in preset_name:
            subprocess.Popen(["code", "D:\\Development"], shell=True)
            webbrowser.open("http://localhost:3000")
            return "Development workspace launched, sir."
        elif "study" in preset_name:
            webbrowser.open("https://scholar.google.com")
            subprocess.Popen(["notepad.exe"])
            return "Study environment ready."
    except Exception as e:
        return f"Failed to launch workspace: {e}"
    return "Workspace preset not found."

# --- HARDWARE HEALTH & DISK CHECK ---
def get_detailed_system_health():
    c_drive = psutil.disk_usage('C:')
    d_drive = psutil.disk_usage('D:')
    c_free_gb = round(c_drive.free / (1024**3), 1)
    d_free_gb = round(d_drive.free / (1024**3), 1)
    
    battery = psutil.sensors_battery()
    battery_status = f"{battery.percent}%" if battery else "Desktop (AC Power)"
    
    return f"Drive C has {c_free_gb} GB free. Drive D has {d_free_gb} GB free. Battery is at {battery_status}."

# --- WEB & YOUTUBE ---
def focus_browser_and_page():
    """Brings Chrome or default browser window to the foreground and positions cursor over the webpage."""
    try:
        import win32gui
        import win32con
        import win32api
        import pyautogui
        
        pyautogui.FAILSAFE = False
        
        def enum_cb(hwnd, extra):
            if win32gui.IsWindowVisible(hwnd):
                title = win32gui.GetWindowText(hwnd).lower()
                if any(b in title for b in ["chrome", "edge", "firefox", "brave", "opera", "youtube", "google maps"]) or (" - " in title and any(t in title for t in [".com", ".org", "http", "search", "google"])):
                    extra.append(hwnd)
        
        hwnds = []
        win32gui.EnumWindows(enum_cb, hwnds)
        
        if hwnds:
            hwnd = hwnds[0]
            win32api.keybd_event(0x12, 0, 0, 0)
            win32gui.ShowWindow(hwnd, win32con.SW_RESTORE)
            win32gui.SetForegroundWindow(hwnd)
            win32api.keybd_event(0x12, 0, win32con.KEYEVENTF_KEYUP, 0)
            time.sleep(0.15)
            
        sw, sh = pyautogui.size()
        pyautogui.moveTo(sw // 2, sh // 2)
    except Exception as e:
        print(f"[FOCUS BROWSER WARNING] {e}")


def force_open_browser(url: str) -> bool:
    """Forces opening a URL on Windows using multiple robust fallback methods."""
    opened = False
    try:
        subprocess.Popen(f'start "" "{url}"', shell=True)
        opened = True
    except Exception:
        pass
    if not opened:
        try:
            chrome_paths = [
                r"C:\Program Files\Google\Chrome\Application\chrome.exe",
                r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
                os.path.expanduser(r"~\AppData\Local\Google\Chrome\Application\chrome.exe"),
            ]
            for cp in chrome_paths:
                if os.path.exists(cp):
                    subprocess.Popen([cp, url])
                    opened = True
                    break
        except Exception:
            pass
    if not opened:
        try:
            webbrowser.open(url)
            opened = True
        except Exception:
            pass
            
    if opened:
        time.sleep(0.5)
        focus_browser_and_page()
    return opened

def play_on_youtube(query):
    try:
        import pywhatkit
        pywhatkit.playonyt(query)
        return f"Playing '{query}' on YouTube now, sir."
    except Exception:
        encoded_query = urllib.parse.quote(query)
        target = f"https://www.youtube.com/results?search_query={encoded_query}"
        force_open_browser(target)
        return f"Searching YouTube for {query}, sir."

def search_google(query):
    encoded_query = urllib.parse.quote(query)
    target = f"https://www.google.com/search?q={encoded_query}"
    force_open_browser(target)
    return f"Searching Google for {query}, sir."

def open_in_new_tab(query_or_url):
    query_or_url = query_or_url.strip()
    if re.match(r'^(https?://)?[a-zA-Z0-9-]+\.[a-zA-Z]{2,}', query_or_url):
        url = query_or_url if query_or_url.startswith("http") else f"https://{query_or_url}"
        webbrowser.open_new_tab(url)
        return f"Opening {query_or_url} in a new tab, sir."
    else:
        encoded = urllib.parse.quote(query_or_url)
        webbrowser.open_new_tab(f"https://www.google.com/search?q={encoded}")
        return f"Searching Google for {query_or_url} in a new tab, sir."

def search_specific_site(query, site_name):
    site_urls = {
        "netflix": "https://www.netflix.com/search?q=",
        "youtube": "https://www.youtube.com/results?search_query=",
        "github": "https://github.com/search?q=",
        "amazon": "https://www.amazon.com/s?k=",
        "daraz": "https://www.daraz.pk/catalog/?q="
    }
    encoded_query = urllib.parse.quote(query)
    site_lower = site_name.lower()
    
    for key, url in site_urls.items():
        if key in site_lower:
            webbrowser.open_new_tab(url + encoded_query)
            return f"Searching for {query} on {site_name}."
            
    webbrowser.open_new_tab(f"https://www.google.com/search?q=site:{site_name}+{encoded_query}")
    return f"Searching for {query} on {site_name}."


# --- ACADEMIC & ASSIGNMENT GENERATION ---
def generate_assignment_thread(topic, subject):
    from docx import Document
    import json
    from brain import speak
    
    desktop_path = os.path.join(os.path.expanduser("~"), "Desktop")
    ollama_url = "http://localhost:11434/api/generate"
    prompt = f"Write a detailed, academic university assignment on the topic: {topic} for the subject: {subject}."
    
    payload = {
        "model": "qwen2.5:7b",
        "prompt": prompt,
        "stream": True,
        "options": {
            "num_predict": 800,  # Longer is fine since it runs in the background
            "temperature": 0.5,
            "num_ctx": 2048
        }
    }
    
    generated_text = ""
    try:
        response = requests.post(ollama_url, json=payload, stream=True, timeout=180)
        response.raise_for_status()
        
        for line in response.iter_lines():
            if line:
                chunk = json.loads(line.decode('utf-8'))
                token = chunk.get("response", "")
                generated_text += token
                if chunk.get("done", False):
                    break
        generated_text = generated_text.strip()
    except Exception as e:
        speak(f"Sir, I failed to generate the assignment content due to an error: {e}")
        return

    if not generated_text:
        speak("Sir, Ollama returned an empty response, so I could not create the assignment document.")
        return

    try:
        doc = Document()
        
        # Academic Header
        header_text = (
            "Name: M. Yahya Siddiqui\n"
            "Roll No: 22CS001\n"
            "Department: Computer Systems Engineering, MUET Jamshoro"
        )
        doc.add_paragraph(header_text)
        doc.add_paragraph(f"Subject: {subject}")
        
        # Title Heading
        doc.add_heading(topic, level=0)
        
        # Add generated content
        for p_text in generated_text.split("\n"):
            p_clean = p_text.strip()
            if p_clean:
                doc.add_paragraph(p_clean)
                
        # Save to Desktop
        filename = f"{topic.replace(' ', '_')}_Assignment.docx"
        file_path = os.path.join(desktop_path, filename)
        doc.save(file_path)
        
        global last_generated_doc
        last_generated_doc = file_path
        
        # Spoken confirmation using centralized SAPI queue
        speak(f"Sir, your university assignment on {topic} for the subject {subject} has been successfully generated and saved to your desktop.")
    except Exception as e:
        speak(f"Sir, I encountered an error while saving the Word document: {e}")


# --- UTILITY & NOTES ---
def handle_clipboard(action):
    if "read" in action:
        text = pyperclip.paste()
        return f"On your clipboard: {text[:150]}" if text else "Your clipboard is empty."
    return "Unknown clipboard action."

def take_quick_note(note_text):
    timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with open("quick_notes.txt", "a", encoding="utf-8") as f:
        f.write(f"[{timestamp}] {note_text}\n")
    return "Note saved successfully."

def take_screenshot():
    filename = f"screenshot_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.png"
    pyautogui.screenshot(filename)
    return f"Screenshot saved as {filename}."

def empty_recycle_bin():
    try:
        ctypes.windll.shell32.SHEmptyRecycleBinW(None, None, 7)
        return "Recycle Bin emptied."
    except Exception:
        return "Failed to empty Recycle Bin."


# --- BROWSER AUTOMATION FOR MUET PORTAL ---
_last_attendance_time = 0
_attendance_cache_result = None
_attendance_cache_timestamp = 0

def fetch_ug_attendance():
    global _last_attendance_time, _attendance_cache_result, _attendance_cache_timestamp
    now = time.time()

    # 15-minute (900 seconds) in-memory cache check for millisecond response time
    if _attendance_cache_result and (now - _attendance_cache_timestamp < 900):
        print("[ATTENDANCE CACHE HIT] Returning cached MIS attendance in milliseconds.")
        return _attendance_cache_result

    if now - _last_attendance_time < 15.0:
        return "I am already logging into the MIS portal for your attendance, sir."
    _last_attendance_time = now

    try:
        options = webdriver.ChromeOptions()
        options.add_experimental_option("detach", True)
        options.add_argument("--disable-gpu")
        options.add_argument("--log-level=3")
        options.add_argument("--silent")
        
        driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=options)
        driver.get("http://misportal.muet.edu.pk/mis/login.php")
        
        wait = WebDriverWait(driver, 15)
        
        # a) Login logic
        cnic_input = wait.until(EC.presence_of_element_located((By.ID, "inputStudentCNIC")))
        password_input = driver.find_element(By.ID, "inputStudentPassword")
        submit_btn = driver.find_element(By.ID, "studentLogin")
        
        cnic_input.clear()
        cnic_input.send_keys("43304-7952345-7")
        password_input.clear()
        password_input.send_keys("yahyamis@01")
        submit_btn.click()
        
        # b) Locate the sidebar menu item "Provisional Report" and click it
        provisional_report_link = wait.until(
            EC.element_to_be_clickable((By.XPATH, "//a[contains(., 'Provisional Report')]"))
        )
        provisional_report_link.click()
        
        # c) Locate the submenu item "1. Under Graduate" and click it
        under_graduate_link = wait.until(
            EC.element_to_be_clickable((By.XPATH, "//a[contains(., '1. Under Graduate')]"))
        )
        under_graduate_link.click()
        
        # d) Locate first dropdown (Department) using tag name, wrap in Select() and select
        select_elements = wait.until(
            EC.presence_of_all_elements_located((By.TAG_NAME, "select"))
        )
        if len(select_elements) >= 1:
            dept_select = Select(select_elements[0])
            try:
                dept_select.select_by_visible_text("Computer Systems Engineering")
            except:
                driver.execute_script("""
                    var sel = arguments[0];
                    for(var i=0; i<sel.options.length; i++){
                        if(sel.options[i].text.includes('Computer Systems Engineering')){
                            sel.value = sel.options[i].value;
                            break;
                        }
                    }
                    sel.dispatchEvent(new Event('input', { bubbles: true }));
                    sel.dispatchEvent(new Event('change', { bubbles: true }));
                    if (typeof jQuery !== 'undefined') { jQuery(sel).trigger('change'); }
                """, select_elements[0])
        
        # e) AJAX delay
        time.sleep(2)
        
        # f) Locate second dropdown (Semester), wrap in Select() and select
        select_elements = driver.find_elements(By.TAG_NAME, "select")
        if len(select_elements) >= 2:
            sem_select = Select(select_elements[1])
            try:
                sem_select.select_by_visible_text("Class 22CS-I - Semester 8")
            except:
                driver.execute_script("""
                    var sel = arguments[0];
                    for(var i=0; i<sel.options.length; i++){
                        if(sel.options[i].text.includes('Semester 8')){
                            sel.value = sel.options[i].value;
                            break;
                        }
                    }
                    sel.dispatchEvent(new Event('input', { bubbles: true }));
                    sel.dispatchEvent(new Event('change', { bubbles: true }));
                    if (typeof jQuery !== 'undefined') { jQuery(sel).trigger('change'); }
                """, select_elements[1])
                
        result_msg = "I have successfully logged into the MIS portal and loaded your 8th-semester attendance, sir."
        _attendance_cache_result = result_msg
        _attendance_cache_timestamp = now
        return result_msg
    except Exception as e:
        print(f"--- SELENIUM ERROR ---\n{str(e)}\n-----------------------")
        return "I encountered an error navigating the MIS portal."


# ─── REFINED AUTOMATION & SYSTEM TOOLS ───────────────────────

def youtube_control(action: str, query: str = None, video_index: int = 1) -> str:
    """Manages YouTube search, video selection, and direct playback."""
    action = (action or "search").lower().strip()
    
    if action == "search":
        if not query:
            return "Please specify a search query for YouTube, sir."
        encoded = urllib.parse.quote(query)
        webbrowser.open(f"https://www.youtube.com/results?search_query={encoded}")
        return f"Searching YouTube for '{query}', sir."
        
    elif action == "select_video":
        tab_count = 4 + max(0, (video_index - 1))
        time.sleep(0.5)
        for _ in range(tab_count):
            pyautogui.press('tab')
            time.sleep(0.08)
        pyautogui.press('enter')
        return f"Selected video #{video_index} on YouTube, sir."
        
    elif action == "play_direct":
        if not query:
            return "Please specify a video or song to play, sir."
        try:
            import pywhatkit
            pywhatkit.playonyt(query)
        except Exception:
            encoded = urllib.parse.quote(query)
            webbrowser.open(f"https://www.youtube.com/results?search_query={encoded}")
        return f"Playing '{query}' on YouTube, sir."
        
    else:
        return f"Unknown YouTube action '{action}', sir."


def web_search_and_navigate(action: str, query: str = None, result_index: int = 1) -> str:
    """Performs Google search or opens specific search results immediately."""
    action = (action or "google_search").lower().strip()
    
    if action == "google_search":
        if not query:
            return "Please specify a search query, sir."
        encoded = urllib.parse.quote(query)
        webbrowser.open(f"https://www.google.com/search?q={encoded}")
        return f"Searching Google for '{query}', sir."
        
    elif action == "open_result":
        if not query:
            time.sleep(0.5)
            tab_count = 14 + max(0, (result_index - 1) * 2)
            for _ in range(tab_count):
                pyautogui.press('tab')
                time.sleep(0.08)
            pyautogui.press('enter')
            return f"Opened search result #{result_index}, sir."
        else:
            encoded = urllib.parse.quote(query)
            webbrowser.open(f"https://www.google.com/search?q={encoded}&btnI=1")
            return f"Opened top search result for '{query}', sir."
            
    else:
        return f"Unknown search action '{action}', sir."


def browser_viewport_control(action: str, value: int = 500) -> str:
    """Controls browser scrolling and tab management."""
    action = (action or "").lower().strip()
    try:
        val = int(value) if value is not None else 500
    except (ValueError, TypeError):
        val = 500
    
    # Disable PyAutoGUI failsafe and click center of screen to focus active window before scrolling
    try:
        pyautogui.FAILSAFE = False
        screenWidth, screenHeight = pyautogui.size()
        pyautogui.click(screenWidth / 2, screenHeight / 2)
    except Exception:
        pass

    if action == "scroll_down":
        pyautogui.scroll(-val)
        return f"Scrolled down by {val} units, sir."
    elif action == "scroll_up":
        pyautogui.scroll(val)
        return f"Scrolled up by {val} units, sir."
    elif action == "next_tab":
        pyautogui.hotkey('ctrl', 'tab')
        return "Switched to next tab, sir."
    elif action == "prev_tab":
        pyautogui.hotkey('ctrl', 'shift', 'tab')
        return "Switched to previous tab, sir."
    elif action == "close_tab":
        pyautogui.hotkey('ctrl', 'w')
        return "Closed active tab, sir."
    elif action == "select_tab":
        tab_num = min(9, max(1, val))
        pyautogui.hotkey('ctrl', str(tab_num))
        return f"Selected tab #{tab_num}, sir."
    else:
        return f"Unknown viewport action '{action}', sir."


def create_folder(folder_name: str, location: str = "Desktop") -> str:
    """Creates a directory at Desktop, Downloads, Documents, Projects (D:\\Development), or a custom path."""
    if not folder_name:
        return "Folder name is required, sir."
        
    user_home = os.path.expanduser("~")
    location_clean = (location or "Desktop").strip()
    loc_lower = location_clean.lower()
    
    if loc_lower == "desktop":
        base_dir = os.path.join(user_home, "Desktop")
    elif loc_lower == "downloads":
        base_dir = os.path.join(user_home, "Downloads")
    elif loc_lower == "documents":
        base_dir = os.path.join(user_home, "Documents")
    elif loc_lower in ["projects", "development", "dev"]:
        base_dir = r"D:\Development" if os.path.exists(r"D:\Development") else os.path.join(user_home, "Projects")
    elif os.path.isabs(location_clean):
        base_dir = location_clean
    else:
        base_dir = os.path.join(user_home, location_clean)
        
    target_path = os.path.join(base_dir, folder_name)
    try:
        os.makedirs(target_path, exist_ok=True)
        return f"Folder '{folder_name}' created successfully at {target_path}, sir."
    except Exception as e:
        return f"Failed to create folder '{folder_name}': {e}"


# ─── PERSISTENT SINGLETON PLAYWRIGHT BROWSER (SDG 10) ───────────────
_playwright_context = None
_browser = None
_active_page = None
_playwright_thread_id = None


def stealth_sync(page):
    """Applies Playwright stealth evasions to hide automation flags."""
    try:
        from playwright_stealth import stealth_sync as _ss
        _ss(page)
    except ImportError:
        try:
            from playwright_stealth.stealth import Stealth
            Stealth().apply_stealth_sync(page)
        except Exception as err:
            print(f"[STEALTH WARNING] Could not apply stealth evasions: {err}")


def get_active_page():
    """
    Returns the active singleton Playwright browser page instance with stealth anti-bot protection.
    Auto-heals if the user closed the window, or if invoked from a different thread (greenlet thread boundary).
    ALWAYS tracks the most recently opened tab/popup so target=_blank links never lose focus.
    """
    global _playwright_context, _browser, _active_page, _playwright_thread_id
    current_thread = threading.get_ident()

    try:
        if (
            _browser is None
            or not _browser.is_connected()
            or _playwright_context is None
            or _playwright_thread_id != current_thread
        ):
            from playwright.sync_api import sync_playwright
            if _playwright_context:
                try:
                    _playwright_context.stop()
                except Exception:
                    pass
            _playwright_context = sync_playwright().start()
            _browser = _playwright_context.chromium.launch(
                headless=False,
                slow_mo=100,
                args=["--disable-blink-features=AutomationControlled", "--start-maximized"]
            )
            _active_page = _browser.new_page(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            )
            _playwright_thread_id = current_thread
            try:
                stealth_sync(_active_page)
            except Exception as stealth_err:
                print(f"[STEALTH WARNING] {stealth_err}")

        # ALWAYS track the most recently opened tab or popup (handles target="_blank" links)
        try:
            if _browser.contexts:
                pages = _browser.contexts[0].pages
                if pages:
                    _active_page = pages[-1]
                    try:
                        _active_page.bring_to_front()
                    except Exception:
                        pass
        except Exception as tab_err:
            print(f"[TAB TRACKER] Could not update active tab: {tab_err}")

        # Final guard: if _active_page is somehow still None or closed, open a fresh page
        if _active_page is None or _active_page.is_closed():
            _active_page = _browser.new_page(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            )

    except Exception as e:
        print(f"[PLAYWRIGHT ENGINE] Re-initializing browser session on thread {current_thread} due to: {e}")
        from playwright.sync_api import sync_playwright
        _playwright_context = sync_playwright().start()
        _browser = _playwright_context.chromium.launch(
            headless=False,
            slow_mo=100,
            args=["--disable-blink-features=AutomationControlled", "--start-maximized"]
        )
        _active_page = _browser.new_page(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        )
        _playwright_thread_id = current_thread
        try:
            stealth_sync(_active_page)
        except Exception:
            pass

    return _active_page


def resolve_brand_url(target_name: str) -> str:
    """
    Resolves a brand or search term to its official direct URL using DuckDuckGo HTML link extraction.
    Bypasses DuckDuckGo/Google redirect traps and CAPTCHAs.
    """
    try:
        ddg_html_url = f"https://html.duckduckgo.com/html/?q={urllib.parse.quote(target_name)}"
        resp = requests.get(ddg_html_url, headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}, timeout=8)
        if resp.status_code == 200:
            from bs4 import BeautifulSoup
            soup = BeautifulSoup(resp.text, "html.parser")
            first_link = soup.select_one("a.result__url")
            if first_link and first_link.get("href"):
                href = first_link.get("href")
                parsed = urllib.parse.parse_qs(urllib.parse.urlparse(href).query)
                real_url = parsed.get("uddg", [None])[0]
                if real_url:
                    return real_url
    except Exception as err:
        print(f"[URL RESOLVER WARNING] {err}")
    return None


def safe_goto(url, timeout=15000):
    """
    Safely navigates to a URL using get_active_page().
    Auto-heals if the target page, context, or browser was closed.
    """
    global _active_page
    try:
        page = get_active_page()
        page.goto(url, timeout=timeout)
        return page
    except Exception as err:
        err_str = str(err).lower()
        if any(k in err_str for k in ["closed", "target", "greenlet", "context", "destroyed"]):
            print(f"[PLAYWRIGHT AUTO-HEAL] Re-creating browser page due to closed target: {err}")
            _active_page = None
            page = get_active_page()
            page.goto(url, timeout=timeout)
            return page
        else:
            raise err


def assistive_web_action(action: str, target: str = None) -> str:
    """
    Universal Smart Navigation Tool for SDG 10 visually impaired accessibility.
    Actions:
    - 'search': Searches DuckDuckGo for target query.
    - 'open_url': Opens specific site directly or uses DuckDuckGo !ducky bang auto-redirect.
    - 'click_result': Clicks search result by number (1-based index).
    - 'scroll_down': Injects JS DOM scroll down by 800px.
    - 'scroll_up': Injects JS DOM scroll up by 800px.
    - 'click_text': Intelligently finds and clicks element with target text.
    """
    act = (action or "search").lower().strip()
    target_clean = (target or "").strip()

    # 1. Fix Variable Scope: Define page at the absolute top of the function
    page = get_active_page()

    try:
        if act == "open_url":
            if not target_clean:
                return "Please provide a URL to open, sir."

            target_nav = target_clean
            if not target_nav.startswith("http"):
                # Safely encode the auto-redirect command
                encoded_query = urllib.parse.quote(f"!ducky {target_nav}")
                target_nav = f"https://duckduckgo.com/?q={encoded_query}"

            try:
                print(f"[ASSISTIVE WEB] Navigating to target: {target_nav}...")
                page.goto(target_nav, timeout=15000)
                try:
                    page.wait_for_timeout(2000)
                except Exception:
                    pass
                page_title = page.title() or target_clean
                return f"Opened website '{page_title}' on screen, sir."
            except Exception as e:
                return f"Failed to load page: {e}"

        elif act == "search":
            if not target_clean:
                return "Please specify what to search for, sir."
            encoded_query = urllib.parse.quote(target_clean)
            search_url = f"https://duckduckgo.com/?q={encoded_query}"
            print(f"[ASSISTIVE WEB] Searching DuckDuckGo for '{target_clean}'...")
            try:
                page.goto(search_url, timeout=15000)
                page_title = page.title() or target_clean
                return f"Searched and opened '{page_title}' on screen, sir."
            except Exception as e:
                return f"Failed to perform search: {e}"

        elif act in ["click_result", "open_result"] or (act in ["click_text", "click"] and (re.search(r'\b(1st|first|top|1|2nd|second|2|3rd|third|3|4th|fourth|4)\b', target_clean, re.IGNORECASE) or "result" in target_clean.lower() or "site" in target_clean.lower() or "link" in target_clean.lower())):
            try:
                # Convert target (e.g., "1") or ordinal to a zero-based index
                index = 0
                ord_match = re.search(r'\b(1st|first|top|1|2nd|second|2|3rd|third|3|4th|fourth|4)\b', target_clean, re.IGNORECASE)
                if ord_match:
                    w = ord_match.group(1).lower()
                    if w in ["2nd", "second", "2"]:
                        index = 1
                    elif w in ["3rd", "third", "3"]:
                        index = 2
                    elif w in ["4th", "fourth", "4"]:
                        index = 3
                elif target_clean.isdigit():
                    index = int(target_clean) - 1

                print(f"[ASSISTIVE WEB] Clicking search result index #{index + 1}...")
                # Locate the search result link and click it
                page.locator('h3, a[data-testid="result-title-a"], article h2 a, .result__title a').nth(index).click(timeout=5000)
                # Wait for the new page to load
                try:
                    page.wait_for_load_state("domcontentloaded", timeout=5000)
                except Exception:
                    pass
                page_title = page.title() or f"result #{index + 1}"
                return f"Successfully clicked search result number {index + 1} ('{page_title}')."
            except Exception as e:
                return f"Failed to click search result {target_clean}. Error: {e}"

        elif act == "scroll_down":
            print("[ASSISTIVE WEB] Injecting JS scrollBy(0, 800)...")
            page.evaluate("window.scrollBy(0, 800)")
            return "Scrolled down the page, sir."

        elif act == "scroll_up":
            print("[ASSISTIVE WEB] Injecting JS scrollBy(0, -800)...")
            page.evaluate("window.scrollBy(0, -800)")
            return "Scrolled up the page, sir."

        elif act in ["click_text", "click"]:
            if not target_clean:
                return "Please specify text to click on the page, sir."
            print(f"[ASSISTIVE WEB] Clicking element with text: '{target_clean}'...")
            try:
                # Tier 1: Native Playwright text locator — works on any element type (spans, divs, anchors)
                # This is the most reliable for e-commerce product grids where text is inside nested divs
                try:
                    page.locator(f"text={target_clean}").first.click(timeout=4000)
                    page.wait_for_load_state("domcontentloaded", timeout=5000)
                    return f"Successfully clicked on '{target_clean}'."
                except Exception:
                    pass

                # Tier 2: Partial text match on clickable elements (links, buttons, headings)
                try:
                    page.locator(
                        f"a:has-text('{target_clean}'), button:has-text('{target_clean}'), "
                        f"h1:has-text('{target_clean}'), h2:has-text('{target_clean}'), "
                        f"h3:has-text('{target_clean}'), span:has-text('{target_clean}')"
                    ).first.click(timeout=4000)
                    page.wait_for_load_state("domcontentloaded", timeout=5000)
                    return f"Successfully clicked on '{target_clean}'."
                except Exception:
                    pass

                # Tier 3: First keyword of the phrase (handles truncated product titles in grids)
                first_word = target_clean.split()[0] if target_clean.split() else target_clean
                if len(first_word) > 3:
                    try:
                        page.locator(
                            f"a:has-text('{first_word}'), h3:has-text('{first_word}'), "
                            f"span:has-text('{first_word}'), div:has-text('{first_word}')"
                        ).first.click(timeout=4000)
                        page.wait_for_load_state("domcontentloaded", timeout=5000)
                        return f"Clicked item containing '{first_word}' on page, sir."
                    except Exception:
                        pass

                # Tier 4: get_by_text fallback (broader match, lower precision)
                try:
                    page.get_by_text(target_clean, exact=False).first.click(timeout=3000)
                    return f"Clicked '{target_clean}' on page, sir."
                except Exception:
                    pass

                return f"Could not find '{target_clean}' on screen. Try scrolling down and asking again, sir."

            except Exception as click_err:
                print(f"[ASSISTIVE WEB] Text click error: {click_err}")
                return f"Failed to click '{target_clean}'. It might not be visible on screen. Error: {click_err}"

        elif act == "play_youtube":
            if not target_clean:
                return "Please specify what to play on YouTube, sir."
            encoded = urllib.parse.quote(target_clean)
            print(f"[ASSISTIVE WEB] Searching YouTube for '{target_clean}'...")
            try:
                page.goto(f"https://www.youtube.com/results?search_query={encoded}", timeout=15000)
                page.locator('a#video-title').first.click(timeout=5000)
                page_title = page.title() or target_clean
                return f"Playing '{target_clean}' on YouTube, sir."
            except Exception as e:
                return f"Failed to play YouTube video: {e}"

        elif act == "new_tab":
            global _active_page, _browser
            try:
                _active_page = _browser.new_page(
                    user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
                )
                _playwright_thread_id = threading.get_ident()
                return "Opened a new browser tab, sir."
            except Exception as e:
                return f"Failed to open new tab: {e}"

        elif act == "close_tab":
            try:
                page.close()
                pages = _browser.contexts[0].pages if _browser.contexts else []
                if pages:
                    _active_page = pages[-1]
                    _active_page.bring_to_front()
                else:
                    _active_page = _browser.new_page(
                        user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
                    )
                return "Closed current tab, sir."
            except Exception as e:
                return f"Failed to close tab: {e}"

        elif act == "switch_tab":
            try:
                pages = _browser.contexts[0].pages if _browser.contexts else []
                if pages:
                    current_idx = pages.index(_active_page) if _active_page in pages else 0
                    _active_page = pages[(current_idx + 1) % len(pages)]
                    _active_page.bring_to_front()
                    page_title = _active_page.title() or "new tab"
                    return f"Switched to tab: '{page_title}', sir."
                return "No other tabs open, sir."
            except Exception as e:
                return f"Failed to switch tab: {e}"

        else:
            return f"Unknown web action '{action}', sir."

    except Exception as e:
        print(f"[ASSISTIVE WEB ERROR] {e}")
        return f"Encountered an issue executing '{action}': {e}"


# ─── SINGLE-WINDOW FILE EXPLORER NAVIGATION ─────────────────────────
def open_local_folder(target_path: str) -> str:
    """
    Navigates an existing Windows Explorer window to a folder,
    or opens a new one if none is open. Avoids spawning duplicate windows.
    """
    target_path = os.path.abspath(target_path)
    os.makedirs(target_path, exist_ok=True)
    try:
        shell = win32com.client.Dispatch("Shell.Application")
        for window in shell.Windows():
            try:
                if window.Name in ["File Explorer", "Windows Explorer"]:
                    window.Navigate(target_path)
                    return f"Navigated existing Explorer to {target_path}"
            except Exception:
                continue
        # Fallback: open a new window if none is open
        os.startfile(target_path)
        return f"Opened new Explorer window at {target_path}"
    except Exception as e:
        return f"Failed to open folder: {e}"


# ─── USER PROFILES FOR ASSISTIVE E-COMMERCE (SDG 10) ───────────────
USER_PROFILES = {
    "name": "Muhammad Yahya Siddiqui",
    "first_name": "Muhammad Yahya",
    "last_name": "Siddiqui",
    "default_phone": "03163434749",
    "email": "siddiquiyahya796@gmail.com",
    "addresses": {
        "home": {
            "address": "Siddiqui street boot bazar shikarpur sindh",
            "city": "Shikarpur",
            "province": "Sindh",
        },
        "hostel": {
            "address": "AQ boys hostel muet jamshoro",
            "city": "Jamshoro",
            "province": "Sindh",
        },
    },
}


def assistive_checkout(address_choice: str = "home", custom_phone: str = None) -> str:
    """
    Contextual Checkout Tool for SDG 10 visually impaired accessibility.
    Dynamically extracts visible form fields from ANY e-commerce checkout page,
    uses Gemini LLM to map user profile data to the form inputs, and fills them via Playwright.
    """
    addr_type = (address_choice or "home").lower().strip()
    if addr_type not in ["home", "hostel"]:
        addr_type = "home"

    target_profile = USER_PROFILES["addresses"][addr_type]
    target_address = target_profile["address"]
    city_name = "Jamshoro" if addr_type == "hostel" else "Shikarpur"
    phone_val = custom_phone.strip() if custom_phone and custom_phone.strip() else USER_PROFILES["default_phone"]
    selected_email = USER_PROFILES["email"]

    user_data = {
        "name": USER_PROFILES["name"],
        "first_name": USER_PROFILES["first_name"],
        "last_name": USER_PROFILES["last_name"],
        "email": selected_email,
        "phone": phone_val,
        "address": target_address,
        "city": city_name,
        "province": "Sindh"
    }

    try:
        page = get_active_page()
        print(f"[ASSISTIVE CHECKOUT] Extracting visible form fields from active page ({addr_type} profile)...")

        # 1. Dynamic Field Extraction via JS DOM evaluate
        extracted_fields = page.evaluate("""
            () => {
                const fields = [];
                const elements = document.querySelectorAll('input, textarea, select');
                elements.forEach(el => {
                    const style = window.getComputedStyle(el);
                    if (style.display !== 'none' && style.visibility !== 'hidden' && el.type !== 'hidden' && el.type !== 'submit' && el.type !== 'button') {
                        const rect = el.getBoundingClientRect();
                        if (rect.width > 0 && rect.height > 0) {
                            fields.push({
                                id: el.id || '',
                                name: el.name || '',
                                type: el.type || 'text',
                                placeholder: el.placeholder || '',
                                aria_label: el.getAttribute('aria-label') || '',
                                autocomplete: el.getAttribute('autocomplete') || ''
                            });
                        }
                    }
                });
                return fields;
            }
        """)

        print(f"[ASSISTIVE CHECKOUT] Extracted {len(extracted_fields)} visible form input fields.")

        # 2. LLM-Powered Mapping using Gemini Client
        dynamic_mapping = {}
        api_key = os.getenv("GEMINI_API_KEY")

        if api_key and extracted_fields:
            try:
                from google import genai
                client = genai.Client(api_key=api_key)

                prompt = f"""You are an AI web automation assistant. Map the user's profile data to the correct HTML 'name' or 'id' attributes from this list of input fields. Return ONLY a valid JSON object where keys are the field 'name' or 'id', and values are the user's exact data to be typed.

User Profile Data:
{json.dumps(user_data, indent=2)}

List of Input Fields:
{json.dumps(extracted_fields, indent=2)}

Rules:
- Output MUST be a valid JSON object where key is the field 'name' or 'id' (prefer 'name', fallback to 'id'), and value is the exact string from User Profile Data.
- Do NOT output extra text or explanations outside JSON.
"""
                models_to_try = ["gemini-2.5-flash", "gemini-flash-latest", "gemini-3.6-flash"]
                raw_response = ""

                for model_name in models_to_try:
                    try:
                        resp = client.models.generate_content(model=model_name, contents=prompt)
                        if resp and resp.text:
                            raw_response = resp.text.strip()
                            print(f"[ASSISTIVE CHECKOUT] LLM Mapping succeeded via {model_name}.")
                            break
                    except Exception as m_err:
                        print(f"[ASSISTIVE CHECKOUT LLM WARNING] Model {model_name} error: {m_err}")

                if raw_response:
                    clean_json = raw_response
                    if "```json" in clean_json:
                        clean_json = clean_json.split("```json")[1].split("```")[0].strip()
                    elif "```" in clean_json:
                        clean_json = clean_json.split("```")[1].split("```")[0].strip()
                    dynamic_mapping = json.loads(clean_json)

            except Exception as llm_err:
                print(f"[ASSISTIVE CHECKOUT LLM ERROR] {llm_err}")

        # 3. Dynamic Injection based on Gemini LLM mapping
        if dynamic_mapping:
            print(f"[ASSISTIVE CHECKOUT] Injecting LLM-mapped fields: {dynamic_mapping}")
            for field_identifier, user_value in dynamic_mapping.items():
                if not field_identifier or user_value is None:
                    continue
                try:
                    page.locator(f"[name='{field_identifier}'], [id='{field_identifier}']").first.fill(str(user_value), timeout=2000)
                    print(f"[ASSISTIVE CHECKOUT] Filled '{field_identifier}' -> '{user_value}'")
                except Exception as fill_err:
                    print(f"[ASSISTIVE CHECKOUT WARNING] Could not fill '{field_identifier}': {fill_err}")

        else:
            # Fallback heuristic form filling if LLM mapping was unavailable
            print("[ASSISTIVE CHECKOUT] Using heuristic fallback form filling...")
            try:
                page.locator('input[name="checkout[email_or_phone]"], input[name="checkout[email]"], input[type="email"], input[id="checkout_email_or_phone"]').first.fill(selected_email, timeout=2000)
            except Exception: pass
            try:
                page.locator('input[placeholder*="First name" i], input[name="checkout[shipping_address][first_name]"]').first.fill(USER_PROFILES["first_name"], timeout=2000)
            except Exception: pass
            try:
                page.locator('input[placeholder*="Last name" i], input[name="checkout[shipping_address][last_name]"]').first.fill(USER_PROFILES["last_name"], timeout=2000)
            except Exception: pass
            try:
                page.locator('input[placeholder*="Address" i], input[name="checkout[shipping_address][address1]"]').first.fill(target_address, timeout=2000)
            except Exception: pass
            try:
                page.locator('input[placeholder*="City" i], input[name="checkout[shipping_address][city]"]').first.fill(city_name, timeout=2000)
            except Exception: pass
            try:
                page.locator('input[name="checkout[shipping_address][phone]"], input[name="phone"], input[placeholder*="Phone" i]').last.fill(phone_val, timeout=2000)
            except Exception: pass

        # 4. Universal Cash on Delivery Selection
        try:
            page.wait_for_timeout(1000)
            page.locator('label:has-text("Cash on Delivery"), label:has-text("COD")').first.click(timeout=3000)
            print("[ASSISTIVE CHECKOUT] Clicked Cash on Delivery (COD) payment option.")
        except Exception:
            print("[Playwright] COD option not found, might require navigating to the next page first.")

        # Freeze browser for visual inspection
        print("[ASSISTIVE CHECKOUT] Freezing browser for visual verification...")
        page.wait_for_timeout(15000)
        return "Checkout details injected successfully using dynamic LLM form mapping. Please verify the screen."

    except Exception as e:
        print(f"[ASSISTIVE CHECKOUT ERROR] {e}")
        return f"Checkout details injected. Please verify the screen. Error: {e}"


def analyze_active_screen(query: str = None) -> str:
    """
    Screen Vision Tool for SDG 10 visually impaired accessibility.
    Captures the active desktop screen and uses Gemini Vision to find product prices or UI text.
    """
    query_str = (query or "the product price").strip()
    image_bytes = None
    try:
        try:
            img = ImageGrab.grab()
            img_byte_arr = io.BytesIO()
            img.save(img_byte_arr, format='PNG')
            image_bytes = img_byte_arr.getvalue()
        except Exception:
            try:
                img = pyautogui.screenshot()
                img_byte_arr = io.BytesIO()
                img.save(img_byte_arr, format='PNG')
                image_bytes = img_byte_arr.getvalue()
            except Exception as capture_err:
                print(f"[SCREEN CAPTURE WARNING] {capture_err}")

        if not image_bytes:
            print("[SCREEN VISION] Desktop capture unavailable — searching page text...")
            return assistive_web_action("search", query_str)

        api_key = os.getenv("GEMINI_API_KEY")
        if not api_key:
            return "Gemini API key is missing, sir."

        from google import genai
        from google.genai import types

        client = genai.Client(api_key=api_key)
        prompt = (
            f"You are an assistive screen reader for a visually impaired user. "
            f"Look at this screen capture and find the requested item/price for: '{query_str}'. "
            f"Return the exact product name, variant, and price in PKR clearly."
        )

        response = None
        vision_models = ["gemini-3.6-flash", "gemini-flash-latest"]
        for vmodel in vision_models:
            try:
                response = client.models.generate_content(
                    model=vmodel,
                    contents=[
                        types.Part.from_bytes(data=image_bytes, mime_type="image/png"),
                        prompt
                    ]
                )
                if response and response.text:
                    print(f"[SCREEN VISION] Success using model {vmodel}")
                    break
            except Exception as m_err:
                print(f"[SCREEN VISION] Model {vmodel} failed ({m_err}), trying fallback...")

        if response and response.text:
            return response.text.strip()
        else:
            return f"Screen captured, but I could not find clear pricing details for '{query_str}', sir."

    except Exception as e:
        print(f"[SCREEN VISION ERROR] {e}")
        return assistive_web_action("search", query_str)


# ─── GHOST CODER — Screen Debugger (SDG 10 & Developer Productivity) ─
def debug_active_screen_code(issue_hint: str = None) -> str:
    """
    Ghost Coder: captures the active screen (IDE / terminal / browser) and sends
    it to Gemini as a Senior Software Engineer to diagnose and fix code errors.
    """
    image_bytes = None
    try:
        # Capture screen — JPEG at 95% quality keeps code crisp while staying fast
        try:
            img = ImageGrab.grab()
            img_byte_arr = io.BytesIO()
            img.save(img_byte_arr, format='JPEG', quality=95)
            image_bytes = img_byte_arr.getvalue()
            mime_type = "image/jpeg"
        except Exception:
            try:
                img = pyautogui.screenshot()
                img_byte_arr = io.BytesIO()
                img.save(img_byte_arr, format='JPEG', quality=95)
                image_bytes = img_byte_arr.getvalue()
                mime_type = "image/jpeg"
            except Exception as cap_err:
                print(f"[GHOST CODER] Screen capture failed: {cap_err}")

        if not image_bytes:
            return "Could not capture the screen for debugging, sir."

        api_key = os.getenv("GEMINI_API_KEY")
        if not api_key:
            return "Gemini API key is missing, sir."

        from google import genai
        from google.genai import types

        client = genai.Client(api_key=api_key)

        hint_text = f" The user specifically mentioned: '{issue_hint}'." if issue_hint else ""
        prompt = (
            "You are a Senior Software Engineer and Ghost Coder acting as a voice assistant's debugging module."
            f"{hint_text} "
            "Analyze this screenshot of the developer's screen or IDE carefully. "
            "1. Identify the programming language and framework. "
            "2. Locate any visible syntax errors, runtime exceptions, missing imports, "
            "missing annotations (e.g. @Autowired, @Override), type mismatches, or logical bugs. "
            "3. Explain the root cause concisely. "
            "4. Provide the exact fix or corrected code snippet. "
            "Keep your response clear and actionable — the user will hear it as speech."
        )

        # Try vision-capable Gemini models in order of preference
        vision_models = ["gemini-3.6-flash", "gemini-flash-latest"]
        for vmodel in vision_models:
            try:
                response = client.models.generate_content(
                    model=vmodel,
                    contents=[
                        types.Part.from_bytes(data=image_bytes, mime_type=mime_type),
                        prompt
                    ]
                )
                if response and response.text:
                    print(f"[GHOST CODER] Diagnosis complete using {vmodel}.")
                    return response.text.strip()
            except Exception as m_err:
                print(f"[GHOST CODER] Model {vmodel} failed ({m_err}), trying fallback...")

        return "I analyzed the screen but could not produce a diagnosis. Please try again, sir."

    except Exception as e:
        print(f"[GHOST CODER ERROR] {e}")
        return f"Failed to analyze the code on screen. Error: {e}"




# ─── AUTONOMOUS DEVELOPER — File I/O Tools ──────────────────────────
def read_local_file(filepath: str) -> str:
    """
    Reads the full text/code of a local file on the user's machine.
    Returns the raw content prefixed with the resolved absolute path.
    Handles large files gracefully — no size limit imposed by Jarvis.
    """
    filepath = os.path.abspath(filepath)
    print(f"[FILE I/O] Reading: {filepath}")
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            content = f.read()
        lines = content.count('\n') + 1
        print(f"[FILE I/O] Read {lines} lines from {filepath}.")
        return f"--- FILE: {filepath} ({lines} lines) ---\n{content}"
    except UnicodeDecodeError:
        # Fallback for files with mixed encodings (e.g. legacy Windows source)
        try:
            with open(filepath, 'r', encoding='latin-1') as f:
                content = f.read()
            return f"--- FILE (latin-1): {filepath} ---\n{content}"
        except Exception as enc_err:
            return f"Failed to decode file (tried utf-8 and latin-1): {enc_err}"
    except FileNotFoundError:
        return f"File not found: {filepath}"
    except Exception as e:
        return f"Failed to read file: {e}"


def write_local_file(filepath: str, new_content: str) -> str:
    """
    Overwrites a local file with completely new content.
    Creates parent directories if they do not exist.
    Always writes the ENTIRE file — never partial snippets.
    """
    filepath = os.path.abspath(filepath)
    print(f"[FILE I/O] Writing: {filepath}")
    try:
        os.makedirs(os.path.dirname(filepath), exist_ok=True)
        # Atomic-safe write: write to a temp file first, then replace
        tmp_path = filepath + ".jarvis_tmp"
        with open(tmp_path, 'w', encoding='utf-8') as f:
            f.write(new_content)
        os.replace(tmp_path, filepath)
        lines = new_content.count('\n') + 1
        print(f"[FILE I/O] Successfully wrote {lines} lines to {filepath}.")
        return f"Successfully updated and saved {lines} lines of code to {filepath}."
    except Exception as e:
        # Clean up temp file if it exists
        try:
            if os.path.exists(filepath + ".jarvis_tmp"):
                os.remove(filepath + ".jarvis_tmp")
        except Exception:
            pass
        return f"Failed to write to file: {e}"


def find_local_file(filename: str, root_dir: str = None) -> str:
    import os
    matches = []
    target = filename.lower()
    
    # Start in the project folder, fallback to the entire User directory (C:\Users\...)
    search_dirs = [os.getcwd()] if root_dir is None else [root_dir]
    if root_dir is None:
        search_dirs.append(os.path.expanduser("~"))

    try:
        for search_dir in search_dirs:
            for root, _, files in os.walk(search_dir):
                for file in files:
                    if target in file.lower():
                        matches.append(os.path.abspath(os.path.join(root, file)))
            
            # If found in the first directory (project), stop searching to save time
            if matches:
                break
                    
        if not matches:
            return f"Could not find '{filename}' anywhere in {search_dirs}."
            
        result_str = f"Found {len(matches)} matching files:\n"
        for match in set(matches): # Use set to remove duplicates
            result_str += f"- {match}\n"
        return result_str
    except Exception as e:
        return f"Error searching for file: {e}"


browser_viewport_control = lambda action, value=500: assistive_web_action(action, str(value))
assistive_shopping_checkout = lambda address_type="home", custom_phone=None, custom_email=None: assistive_checkout(address_type, custom_phone)
assistive_shopping_agent = lambda action="search", query=None: assistive_web_action("search" if "search" in action else "open_url", query)
search_and_inspect_product = lambda query, store_name=None: assistive_web_action("search", f"{query} {store_name}" if store_name else query)


def process_fast_command(text):
    global assignment_state
    if not text:
        return None
        
    text_clean = text.lower().strip()
    
    # ─── Multi-turn Assignment State Machine ─────────────────────
    if assignment_state["is_active"]:
        if "cancel" in text_clean or "stop" in text_clean:
            assignment_state = {"is_active": False, "step": 0, "topic": "", "subject": ""}
            return "Assignment creation cancelled."
            
        if assignment_state["step"] == 1:
            assignment_state["topic"] = text.strip()
            assignment_state["step"] = 2
            return "And what is the subject name?"
            
        if assignment_state["step"] == 2:
            assignment_state["subject"] = text.strip()
            topic = assignment_state["topic"]
            subject = assignment_state["subject"]
            
            # Reset state immediately
            assignment_state = {"is_active": False, "step": 0, "topic": "", "subject": ""}
            
            # Launch background thread
            threading.Thread(
                target=generate_assignment_thread,
                args=(topic, subject),
                daemon=True
            ).start()
            
            return f"Understood. I am now generating the assignment on {topic} for {subject} in the background. I am listening for your next command, sir."
    
    # 1. Workspaces
    if "launch dev" in text_clean or "start coding" in text_clean:
        return launch_workspace("dev")
    elif "launch study" in text_clean:
        return launch_workspace("study")
        
    # 2. Hardware & Health
    elif "disk space" in text_clean or "storage" in text_clean or "battery" in text_clean or "system health" in text_clean:
        return get_detailed_system_health()
        
    # 3. Web & YouTube Search
    elif "play" in text_clean and "on youtube" in text_clean:
        query = text_clean.replace("play", "").replace("on youtube", "").strip()
        return play_on_youtube(query)
    elif "new tab" in text_clean or "open tab" in text_clean:
        query = text_clean
        for phrase in ["open a new tab for", "open in new tab", "open in a new tab", "open new tab", "open tab", "new tab"]:
            query = query.replace(phrase, "")
        query = query.strip()
        if not query:
            webbrowser.open_new_tab("https://www.google.com")
            return "Opening a new tab, sir."
        return open_in_new_tab(query)
    elif (match := re.search(r'\bsearch\s+(?:for\s+)?(.+?)\s+on\s+(.+)', text_clean)):
        query = match.group(1).strip()
        site_name = match.group(2).strip()
        return search_specific_site(query, site_name)
    elif (match := re.search(r'\b(?:open|go\s+to)\s+(.+?)\s+(?:and\s+search|to\s+search)\s+(?:for\s+)?(.+)', text_clean)):
        site_name = match.group(1).strip()
        query = match.group(2).strip()
        site_clean = re.sub(r'\.(com|org|pk|net|edu|gov|co|in|us)\b', '', site_name).strip()
        return search_specific_site(query, site_clean)
    elif "search for" in text_clean:
        query = text_clean.replace("search for", "").strip()
        return search_google(query)
    elif not assignment_state["is_active"] and ("create assignment" in text_clean or "generate university assignment" in text_clean):
        assignment_state["is_active"] = True
        assignment_state["step"] = 1
        return "What topic are you working on for your assignment, sir?"
    elif "open" in text_clean and ("assignment" in text_clean or "doc" in text_clean or "document" in text_clean):
        global last_generated_doc
        if last_generated_doc and os.path.exists(last_generated_doc):
            os.startfile(last_generated_doc)
            return "Opening your assignment document now, sir."
        else:
            # Fallback check for any recent .docx on Desktop
            desktop = os.path.join(os.path.expanduser("~"), "Desktop")
            if os.path.exists(desktop):
                docx_files = [os.path.join(desktop, f) for f in os.listdir(desktop) if f.endswith("_Assignment.docx")]
                if docx_files:
                    latest_file = max(docx_files, key=os.path.getctime)
                    os.startfile(latest_file)
                    return "Opening your most recent assignment from the desktop, sir."
            return "I could not find any recently generated assignments on your desktop, sir."
        
    # 4. Notes, Clipboard & Utility
    elif "take a note" in text_clean or "write note" in text_clean:
        note = text_clean.replace("take a note", "").replace("write note", "").strip()
        return take_quick_note(note)
    elif "read clipboard" in text_clean or "what's on my clipboard" in text_clean:
        return handle_clipboard("read")
    elif "take screenshot" in text_clean or "capture screen" in text_clean:
        return take_screenshot()
    elif "empty recycle bin" in text_clean:
        return empty_recycle_bin()
    elif any(p in text_clean for p in ["check my attendance", "show my attendance", "open mis portal", "attendance", "attendence"]):
        return fetch_ug_attendance()

    # Returning None tells brain.py to forward the prompt to Qwen/Ollama
    return None


# ─── Gemini Live Assistant Tools ─────────────────────────────

def check_attendance() -> str:
    """Checks and displays university class attendance from the MIS portal using Selenium."""
    return fetch_ug_attendance()


def generate_assignment(topic: str, subject: str) -> str:
    """Generates an academic university assignment Word document on a background thread using local Ollama."""
    threading.Thread(
        target=generate_assignment_thread,
        args=(topic, subject),
        daemon=True
    ).start()
    return f"I am now generating the assignment on {topic} for the subject {subject} in the background, sir."


def open_last_assignment() -> str:
    """Opens the last generated assignment document in Microsoft Word."""
    global last_generated_doc
    if last_generated_doc and os.path.exists(last_generated_doc):
        try:
            os.startfile(last_generated_doc)
            return "Opening your assignment document now, sir."
        except Exception as e:
            return f"Failed to open the document: {e}"
    else:
        # Fallback check for any recent .docx on Desktop
        desktop = os.path.join(os.path.expanduser("~"), "Desktop")
        if os.path.exists(desktop):
            docx_files = [os.path.join(desktop, f) for f in os.listdir(desktop) if f.endswith("_Assignment.docx")]
            if docx_files:
                latest_file = max(docx_files, key=os.path.getctime)
                try:
                    os.startfile(latest_file)
                    last_generated_doc = latest_file
                    return "Opening your most recent assignment from the desktop, sir."
                except Exception as e:
                    return f"Failed to open the document: {e}"
        return "I could not find any recently generated assignment document, sir."


def ask_local_qwen(prompt: str) -> str:
    """Queries the local Ollama Qwen model synchronously and returns the response."""
    import json
    ollama_url = "http://localhost:11434/api/generate"
    payload = {
        "model": "qwen",
        "prompt": prompt,
        "stream": False
    }
    try:
        response = requests.post(ollama_url, json=payload, timeout=60)
        response.raise_for_status()
        res_json = response.json()
        return res_json.get("response", "").strip()
    except Exception as e:
        return f"Error contacting local Qwen model: {e}"


def open_application(app_name: str) -> str:
    """Opens a common application (notepad, calculator, chrome, explorer, cmd) or a custom URL/path."""
    global last_opened_folder
    
    # Clean the path from surrounding quotes
    path_clean = app_name.strip(' "\'')
    
    # Normalize drive letters (e.g., "e:" -> "E:\", "E:" -> "E:\")
    if len(path_clean) == 2 and path_clean[1] == ":":
        path_clean = path_clean.upper() + "\\"
        
    name_clean = path_clean.lower()
    
    # Resolve common folder aliases
    common_folders = {
        "pictures": os.path.join(os.path.expanduser("~"), "Pictures"),
        "downloads": os.path.join(os.path.expanduser("~"), "Downloads"),
        "documents": os.path.join(os.path.expanduser("~"), "Documents"),
        "desktop": os.path.join(os.path.expanduser("~"), "Desktop"),
        "videos": os.path.join(os.path.expanduser("~"), "Videos"),
        "music": os.path.join(os.path.expanduser("~"), "Music")
    }
    
    for alias, folder_path in common_folders.items():
        if name_clean == alias or name_clean == f"{alias} folder":
            path_clean = folder_path
            name_clean = folder_path.lower()
            last_opened_folder = folder_path
            break

    # Track directory paths if opening a folder
    if os.path.isdir(path_clean):
        last_opened_folder = os.path.abspath(path_clean)
    
    # Check if it's a URL
    if name_clean.startswith("http://") or name_clean.startswith("https://") or re.match(r'^[a-zA-Z0-9-]+\.[a-zA-Z]{2,}', name_clean):
        url = name_clean if name_clean.startswith("http") else f"https://{name_clean}"
        webbrowser.open(url)
        return f"Opening URL: {url}, sir."
        
    # Check in _APPS dict
    for app_key, cmd in _APPS.items():
        if app_key in name_clean:
            try:
                # If opening file explorer via alias, we can track default explorer directory
                if app_key == "explorer":
                    last_opened_folder = os.path.expanduser("~")
                os.system(cmd)
                return f"Opening {app_key} for you, sir."
            except Exception as e:
                return f"Failed to open {app_key}: {e}"
                
    # Fallback to direct start
    try:
        os.startfile(path_clean)
        return f"Opening {path_clean}, sir."
    except Exception:
        try:
            subprocess.Popen([path_clean], shell=True)
            return f"Launching {path_clean}, sir."
        except Exception as e2:
            return f"Could not launch or find application '{app_name}': {e2}"


def close_application(app_name: str) -> str:
    """Safely closes a running application or process."""
    name_clean = app_name.lower().strip()
    
    # Strict blocklist to protect critical Windows system processes
    blocklist = ['explorer.exe', 'csrss.exe', 'svchost.exe', 'winlogon.exe']
    
    # Map common keys to process names
    app_mapping = {
        "chrome": "chrome.exe",
        "browser": "chrome.exe",
        "notepad": "notepad.exe",
        "calculator": "CalculatorApp.exe",
        "calc": "CalculatorApp.exe",
        "paint": "mspaint.exe",
        "vs code": "Code.exe",
        "vscode": "Code.exe",
        "explorer": "explorer.exe",
        "file explorer": "explorer.exe",
        "cmd": "cmd.exe",
        "terminal": "cmd.exe",
        "spotify": "Spotify.exe",
        "word": "WINWORD.EXE",
        "excel": "EXCEL.EXE",
        "powerpoint": "POWERPNT.EXE",
        "ppt": "POWERPNT.EXE"
    }
    
    exe_name = app_mapping.get(name_clean, app_name)
    if not exe_name.endswith(".exe") and not exe_name.endswith(".EXE"):
        exe_name += ".exe"
        
    # Check if the process matches any critical blocklist item
    if exe_name.lower() in blocklist:
        if exe_name.lower() == "explorer.exe":
            # Gracefully close File Explorer windows instead of killing explorer.exe
            try:
                import win32com.client
                shell = win32com.client.Dispatch("Shell.Application")
                windows = shell.Windows()
                closed_count = 0
                for window in list(windows):
                    if "explorer.exe" in getattr(window, "FullName", "").lower():
                        window.Quit()
                        closed_count += 1
                if closed_count > 0:
                    return f"Gracefully closed {closed_count} File Explorer window(s), preserving the system shell, sir."
                else:
                    return "No File Explorer windows were open to close, sir."
            except Exception as e:
                return f"Failed to gracefully close File Explorer windows: {e}"
        else:
            return f"[WARNING] Terminating critical system process '{exe_name}' is blocked to protect system stability, sir."
            
    try:
        result = subprocess.run(f"taskkill /f /im {exe_name}", capture_output=True, text=True, shell=True)
        if result.returncode == 0:
            return f"Closed {app_name} successfully, sir."
        else:
            return f"Could not close {app_name}. (taskkill message: {result.stderr.strip()})"
    except Exception as e:
        return f"Failed to close application {app_name}: {e}"


def system_control(action: str) -> str:
    """Controls OS features like volume, lock screen, or taking screenshots."""
    act_clean = action.lower().strip()
    
    if "volume_up" in act_clean:
        try:
            # VK_VOLUME_UP (0xAF) code sent 5 times
            for _ in range(5):
                ctypes.windll.user32.keybd_event(0xAF, 0, 0, 0)
                ctypes.windll.user32.keybd_event(0xAF, 0, 2, 0)
            return "Volume increased, sir."
        except Exception as e:
            return f"Failed to increase volume: {e}"
            
    elif "volume_down" in act_clean:
        try:
            # VK_VOLUME_DOWN (0xAE) code sent 5 times
            for _ in range(5):
                ctypes.windll.user32.keybd_event(0xAE, 0, 0, 0)
                ctypes.windll.user32.keybd_event(0xAE, 0, 2, 0)
            return "Volume decreased, sir."
        except Exception as e:
            return f"Failed to decrease volume: {e}"
            
    elif "mute" in act_clean:
        try:
            # VK_VOLUME_MUTE (0xAD) code
            ctypes.windll.user32.keybd_event(0xAD, 0, 0, 0)
            ctypes.windll.user32.keybd_event(0xAD, 0, 2, 0)
            return "Volume mute state toggled, sir."
        except Exception as e:
            return f"Failed to toggle mute state: {e}"
            
    elif "screenshot" in act_clean:
        return take_screenshot()
        
    elif "lock" in act_clean:
        return lock_screen_local()
        
    else:
        return f"Unknown system control action '{action}', sir."


def open_website(url_or_query: str) -> str:
    """Opens any website, URL, or search query directly in the default browser."""
    target = url_or_query.strip()
    
    # Custom alias mapping to bypass voice/safety blocks
    aliases = {
        "p-hub": "pornhub.com",
        "phub": "pornhub.com",
        "the hub": "pornhub.com",
        "adult site": "pornhub.com",
        "xv": "xvideos.com",
        "x-videos": "xvideos.com",
        "xn": "xnxx.com"
    }
    
    target_lower = target.lower()
    for alias, actual in aliases.items():
        if alias in target_lower:
            target = actual
            break
            
    if not target.startswith("http://") and not target.startswith("https://"):
        if "." in target and " " not in target:
            target = "https://" + target
        else:
            import urllib.parse
            target = f"https://www.google.com/search?q={urllib.parse.quote(target)}"
    force_open_browser(target)
    return f"Opened {target} in browser, sir."


def write_to_notepad_async(content: str, title: str = "notes.txt") -> str:
    """Launches Notepad in a background thread and writes content without blocking."""
    def _worker():
        filepath = os.path.join(os.getcwd(), title)
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(content)
        subprocess.Popen(["notepad.exe", filepath])
    
    thread = threading.Thread(target=_worker, daemon=True)
    thread.start()
    return f"Opened Notepad and wrote {len(content)} characters to {title} in the background."


def shutdown_assistant() -> str:
    """Terminates the Jarvis assistant application cleanly."""
    print("\n👋 Shutting down Jarvis... Goodbye, sir.")
    try:
        import win32com.client
        speaker = win32com.client.Dispatch("SAPI.SpVoice")
        speaker.Speak("Goodbye, sir. Shutting down now.")
    except Exception:
        pass
    os._exit(0)


def page_scroll(direction: str, amount: int = 500) -> str:
    """Scrolls the active window or browser page up or down using native Windows mouse wheel events."""
    dir_clean = direction.lower().strip()
    try:
        import pyautogui
        import win32api
        import win32con
        import time
        
        pyautogui.FAILSAFE = False
        
        # 1. Bring browser window to front and position mouse at screen center (no click)
        focus_browser_and_page()
        time.sleep(0.1)
        
        amt = abs(int(amount)) if amount else 500
        notches = max(1, min(20, amt // 100))
        
        if "up" in dir_clean:
            wheel_delta = 120 * notches
            # Native Windows mouse wheel event
            win32api.mouse_event(win32con.MOUSEEVENTF_WHEEL, 0, 0, wheel_delta, 0)
            # PyAutoGUI wheel event
            pyautogui.scroll(amt)
            # Keyboard PageUp fallback
            pyautogui.press("pageup")
            return f"Scrolled up by {amt} units, sir."
        elif "down" in dir_clean:
            wheel_delta = -120 * notches
            # Native Windows mouse wheel event
            win32api.mouse_event(win32con.MOUSEEVENTF_WHEEL, 0, 0, wheel_delta, 0)
            # PyAutoGUI wheel event
            pyautogui.scroll(-amt)
            # Keyboard PageDown fallback
            pyautogui.press("pagedown")
            return f"Scrolled down by {amt} units, sir."
        else:
            return f"Unknown scroll direction '{direction}', sir."
    except Exception as e:
        return f"Failed to scroll page: {e}"



def type_and_search(text: str) -> str:
    """Types text on the active input field and presses enter to execute a search."""
    try:
        import pyautogui
        import time
        pyautogui.write(text)
        time.sleep(0.2)
        pyautogui.press("enter")
        return f"Typed '{text}' and executed search, sir."
    except Exception as e:
        return f"Failed to type and search: {e}"


# Stateful YouTube automation variables
youtube_driver = None
latest_youtube_results = []


def search_youtube(query: str) -> str:
    """Searches YouTube using Selenium and stores the video results for playback."""
    global youtube_driver, latest_youtube_results
    try:
        # Close any existing driver if active
        if youtube_driver is not None:
            try:
                youtube_driver.quit()
            except Exception:
                pass
            youtube_driver = None
            
        latest_youtube_results = []
        
        # Initialize Selenium Chrome driver
        options = webdriver.ChromeOptions()
        options.add_experimental_option("detach", True)
        options.add_argument("--disable-gpu")
        options.add_argument("--log-level=3")
        options.add_argument("--silent")
        
        # Launch browser
        youtube_driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=options)
        url = f"https://www.youtube.com/results?search_query={urllib.parse.quote(query)}"
        youtube_driver.get(url)
        
        # Wait for video renderer elements to load
        wait = WebDriverWait(youtube_driver, 15)
        video_elements = wait.until(
            EC.presence_of_all_elements_located((By.XPATH, "//a[@id='video-title']"))
        )
        
        # Store elements and titles
        latest_youtube_results = []
        titles_preview = []
        for index, elem in enumerate(video_elements):
            title = elem.get_attribute("title")
            href = elem.get_attribute("href")
            # Filter out non-video or empty elements
            if title and href and "/watch" in href:
                latest_youtube_results.append({
                    "element": elem,
                    "title": title,
                    "href": href
                })
                if len(latest_youtube_results) <= 5:
                    titles_preview.append(f"#{len(latest_youtube_results)}: {title}")
                if len(latest_youtube_results) >= 10:
                    break
                    
        preview_str = "\n".join(titles_preview)
        print(f"[YOUTUBE SEARCH] Top Results:\n{preview_str}")
        return "Search complete. Ready to play."
    except Exception as e:
        # Fallback to web browser search if Selenium fails
        try:
            url = f"https://www.youtube.com/results?search_query={urllib.parse.quote(query)}"
            webbrowser.open(url)
            return f"Opened YouTube search for '{query}' in default browser due to automation error: {e}"
        except Exception as e2:
            return f"Failed to search YouTube: {e} | {e2}"


def play_youtube_video(index: int = 1) -> str:
    """Plays a YouTube video by 1-based index from the latest search results."""
    global youtube_driver, latest_youtube_results
    if not youtube_driver:
        return "No active YouTube search session found. Please search first, sir."
        
    if not latest_youtube_results:
        return "No YouTube search results available to play, sir."
        
    # Adjust 1-based index to 0-based index
    actual_index = index - 1 if index > 0 else 0
    
    if actual_index < 0 or actual_index >= len(latest_youtube_results):
        return f"Index {index} is out of range. I found {len(latest_youtube_results)} videos, sir."
        
    video = latest_youtube_results[actual_index]
    video_title = video["title"]
    video_href = video["href"]
    
    try:
        # Navigate the active driver directly to the video URL for instant playback
        youtube_driver.get(video_href)
        return f"Playing video: '{video_title}', sir."
    except Exception as e:
        # Fallback to default browser
        try:
            webbrowser.open(video_href)
            return f"Playing '{video_title}' in default browser due to automation error: {e}"
        except Exception as e2:
            return f"Failed to play video: {e} | {e2}"


def open_file_by_name(filename: str, parent_dir: str = "") -> str:
    """Locates and opens a file (image, video, document) by name in the specified or last opened folder."""
    global last_opened_folder
    
    file_clean = filename.lower().strip()
    
    # 1. Determine directories to scan
    search_dirs = []
    if parent_dir and os.path.isdir(parent_dir):
        search_dirs.append(os.path.abspath(parent_dir))
    
    if last_opened_folder and os.path.isdir(last_opened_folder):
        search_dirs.append(last_opened_folder)
        
    # Standard user folders fallback
    home_dir = os.path.expanduser("~")
    common_dirs = [
        os.path.join(home_dir, "Desktop"),
        os.path.join(home_dir, "Downloads"),
        os.path.join(home_dir, "Documents"),
        os.path.join(home_dir, "Pictures"),
        os.path.join(home_dir, "Videos")
    ]
    for d in common_dirs:
        if os.path.isdir(d) and d not in search_dirs:
            search_dirs.append(d)
            
    # 2. Search for the file in the designated directories (and their immediate subdirectories)
    matched_file = None
    for directory in search_dirs:
        try:
            # First, check files in the main directory
            for item in os.listdir(directory):
                item_path = os.path.join(directory, item)
                if os.path.isfile(item_path):
                    item_name_lower = item.lower()
                    if file_clean in item_name_lower:
                        matched_file = item_path
                        break
            if matched_file:
                break
                
            # Second, check files in immediate subdirectories (1 level deep)
            for item in os.listdir(directory):
                sub_path = os.path.join(directory, item)
                if os.path.isdir(sub_path):
                    try:
                        for sub_item in os.listdir(sub_path):
                            file_path = os.path.join(sub_path, sub_item)
                            if os.path.isfile(file_path):
                                if file_clean in sub_item.lower():
                                    matched_file = file_path
                                    break
                    except Exception:
                        continue
                if matched_file:
                    break
        except Exception:
            continue
        if matched_file:
            break
            
    # 3. Open the file if found
    if matched_file:
        try:
            os.startfile(matched_file)
            return f"Opening '{os.path.basename(matched_file)}' from '{os.path.dirname(matched_file)}', sir."
        except Exception as e:
            return f"Found file at '{matched_file}' but failed to open it: {e}"
            
    return f"Could not find any file matching '{filename}' in the recently opened folder or system folders, sir."


def change_brightness(action: str, value: int = 10) -> str:
    """Natively gets or sets screen brightness using PowerShell/WMI queries."""
    act_clean = action.lower().strip()
    try:
        if act_clean in ["increase", "up", "raise"]:
            # Query current brightness
            cmd_get = 'powershell -Command "(Get-CimInstance -Namespace root/WMI -ClassName WmiMonitorBrightness).CurrentBrightness"'
            res_get = subprocess.run(cmd_get, capture_output=True, text=True, shell=True)
            curr = 50
            if res_get.returncode == 0 and res_get.stdout.strip():
                curr = int(res_get.stdout.strip())
            new_val = min(100, curr + value)
            cmd_set = f'powershell -Command "Get-CimInstance -Namespace root/WMI -ClassName WmiMonitorBrightnessMethods | Invoke-CimMethod -MethodName WmiSetBrightness -Arguments @{{ Timeout = 0; Brightness = {new_val} }}"'
            subprocess.run(cmd_set, shell=True)
            return f"Increased brightness from {curr}% to {new_val}%, sir."
            
        elif act_clean in ["decrease", "down", "lower"]:
            # Query current brightness
            cmd_get = 'powershell -Command "(Get-CimInstance -Namespace root/WMI -ClassName WmiMonitorBrightness).CurrentBrightness"'
            res_get = subprocess.run(cmd_get, capture_output=True, text=True, shell=True)
            curr = 50
            if res_get.returncode == 0 and res_get.stdout.strip():
                curr = int(res_get.stdout.strip())
            new_val = max(0, curr - value)
            cmd_set = f'powershell -Command "Get-CimInstance -Namespace root/WMI -ClassName WmiMonitorBrightnessMethods | Invoke-CimMethod -MethodName WmiSetBrightness -Arguments @{{ Timeout = 0; Brightness = {new_val} }}"'
            subprocess.run(cmd_set, shell=True)
            return f"Decreased brightness from {curr}% to {new_val}%, sir."
            
        elif act_clean in ["set", "to"]:
            val_clean = min(100, max(0, value))
            cmd_set = f'powershell -Command "Get-CimInstance -Namespace root/WMI -ClassName WmiMonitorBrightnessMethods | Invoke-CimMethod -MethodName WmiSetBrightness -Arguments @{{ Timeout = 0; Brightness = {val_clean} }}"'
            subprocess.run(cmd_set, shell=True)
            return f"Set screen brightness to {val_clean}%, sir."
            
        else:
            return f"Unknown brightness action '{action}', sir."
    except Exception as e:
        return f"Failed to adjust screen brightness: {e}"


def media_control(action: str) -> str:
    """Controls system-wide media playback (play, pause, next, previous, stop)."""
    act_clean = action.lower().strip()
    try:
        import win32api
        import win32con
        
        # Virtual key code mapping
        key_mapping = {
            "play": win32con.VK_MEDIA_PLAY_PAUSE,
            "pause": win32con.VK_MEDIA_PLAY_PAUSE,
            "playpause": win32con.VK_MEDIA_PLAY_PAUSE,
            "next": win32con.VK_MEDIA_NEXT_TRACK,
            "prev": win32con.VK_MEDIA_PREV_TRACK,
            "previous": win32con.VK_MEDIA_PREV_TRACK,
            "stop": win32con.VK_MEDIA_STOP
        }
        
        if act_clean in key_mapping:
            vk_code = key_mapping[act_clean]
            # Send key down
            win32api.keybd_event(vk_code, 0, 0, 0)
            # Send key up
            win32api.keybd_event(vk_code, 0, win32con.KEYEVENTF_KEYUP, 0)
            return f"Executed media {action} command, sir."
        else:
            # Fallback to space key if it's browser-focused play/pause
            if act_clean in ["play", "pause", "playpause"]:
                import pyautogui
                pyautogui.press("space")
                return "Pressed Spacebar for play/pause, sir."
            return f"Unknown media action '{action}', sir."
    except Exception as e:
        return f"Failed to execute media control: {e}"


def switch_browser_tab(direction_or_index: str) -> str:
    """Switches browser tabs using Ctrl+Tab, Ctrl+Shift+Tab, or Ctrl+Number."""
    val_clean = direction_or_index.lower().strip()
    try:
        import pyautogui
        if "next" in val_clean or "forward" in val_clean:
            pyautogui.hotkey("ctrl", "tab")
            return "Switched to the next tab, sir."
        elif "prev" in val_clean or "back" in val_clean or "previous" in val_clean:
            pyautogui.hotkey("ctrl", "shift", "tab")
            return "Switched to the previous tab, sir."
        else:
            # Check if it's a number (tab index)
            digits = re.findall(r"\d+", val_clean)
            if digits:
                idx = int(digits[0])
                if 1 <= idx <= 9:
                    pyautogui.hotkey("ctrl", str(idx))
                    return f"Switched to tab index {idx}, sir."
            return f"Could not determine tab direction or index from '{direction_or_index}', sir."
    except Exception as e:
        return f"Failed to switch browser tab: {e}"


def click_screen(x: int = -1, y: int = -1, click_type: str = "single") -> str:
    """Clicks the mouse on the screen at specified coordinates or current position."""
    try:
        import pyautogui
        pyautogui.FAILSAFE = False
        
        click_clean = click_type.lower().strip()
        
        # Resolve target position
        if x >= 0 and y >= 0:
            pyautogui.moveTo(x, y, duration=0.2)
            pos_str = f"at coordinates ({x}, {y})"
        else:
            pos_str = "at the current mouse position"
            
        # Execute click type
        if "double" in click_clean:
            pyautogui.doubleClick()
            return f"Double-clicked {pos_str}, sir."
        elif "right" in click_clean:
            pyautogui.rightClick()
            return f"Right-clicked {pos_str}, sir."
        else:
            pyautogui.click()
            return f"Clicked {pos_str}, sir."
    except Exception as e:
        return f"Failed to click screen: {e}"


def browser_tab_control(action: str, tab_index: int = None) -> str:
    """Manages browser tabs using pyautogui hotkeys."""
    act_clean = action.lower().strip()
    try:
        import pyautogui
        import time
        
        focus_browser_and_page()
        time.sleep(0.15)
        
        if act_clean in ["next_tab", "next"]:
            pyautogui.hotkey("ctrl", "tab")
            return "Switched to the next tab, sir."
        elif act_clean in ["prev_tab", "prev", "previous_tab", "previous"]:
            pyautogui.hotkey("ctrl", "shift", "tab")
            return "Switched to the previous tab, sir."
        elif act_clean in ["close_tab", "close"]:
            pyautogui.hotkey("ctrl", "w")
            return "Closed current tab, sir."
        elif act_clean in ["select_tab", "select"] and tab_index is not None:
            pyautogui.hotkey("ctrl", str(tab_index))
            return f"Switched to tab index {tab_index}, sir."
        else:
            return f"Unknown or incomplete browser tab action '{action}', sir."
    except Exception as e:
        return f"Failed to control browser tab: {e}"


def site_interaction(action: str, query: str = None) -> str:
    """Interacts with current web page using keyboard shortcuts via pyautogui."""
    act_clean = action.lower().strip()
    try:
        import pyautogui
        import time
        
        focus_browser_and_page()
        time.sleep(0.15)
        
        if act_clean == "youtube_search":
            pyautogui.press("/")
            time.sleep(0.5)
            if query:
                pyautogui.hotkey("ctrl", "a")
                pyautogui.write(query)
                pyautogui.press("enter")
                return f"Searched YouTube for '{query}', sir."
            return "Activated YouTube search box, sir."
        elif act_clean == "youtube_select_video":
            count = 1
            if query:
                try:
                    count = int(query)
                except ValueError:
                    digits = re.findall(r"\d+", query)
                    if digits:
                        count = int(digits[0])
            for _ in range(count):
                pyautogui.press("tab")
                time.sleep(0.1)
            pyautogui.press("enter")
            return f"Selected YouTube video #{count}, sir."
        elif act_clean == "page_search":
            pyautogui.hotkey("ctrl", "f")
            time.sleep(0.3)
            if query:
                pyautogui.write(query)
                pyautogui.press("enter")
                return f"Searched page for '{query}', sir."
            return "Opened page search box, sir."
        else:
            return f"Unknown site interaction action '{action}', sir."
    except Exception as e:
        return f"Failed to perform site interaction: {e}"


def search_maps(query: str) -> str:
    """Launches Google Maps search in the default browser."""
    try:
        encoded_query = urllib.parse.quote(query)
        url = f"https://www.google.com/maps/search/?api=1&query={encoded_query}"
        force_open_browser(url)
        return f"Opened Google Maps search for '{query}', sir."
    except Exception as e:
        return f"Failed to search Google Maps: {e}"


# ─── MEMORY & IDENTITY ────────────────────────────────────────
MEMORY_FILE = "jarvis_memory.json"


def remember_fact(fact: str) -> str:
    """Appends a new fact to the permanent JSON memory file."""
    fact_clean = fact.strip()
    if not fact_clean:
        return "Fact cannot be empty, sir."
        
    memories = []
    if os.path.exists(MEMORY_FILE):
        try:
            with open(MEMORY_FILE, "r", encoding="utf-8") as f:
                memories = json.load(f)
                if not isinstance(memories, list):
                    memories = []
        except Exception:
            memories = []
            
    memories.append(fact_clean)
    
    try:
        with open(MEMORY_FILE, "w", encoding="utf-8") as f:
            json.dump(memories, f, indent=2)
        return f"Remembered: '{fact_clean}', sir."
    except Exception as e:
        return f"Failed to save memory: {e}"


def get_all_memories() -> str:
    """Reads saved facts from the permanent JSON memory file and returns them formatted."""
    if not os.path.exists(MEMORY_FILE):
        return "No previous memories."
        
    try:
        with open(MEMORY_FILE, "r", encoding="utf-8") as f:
            memories = json.load(f)
            if isinstance(memories, list) and memories:
                formatted = "\n".join([f"- {m}" for m in memories])
                return formatted
            return "No previous memories."
    except Exception:
        return "No previous memories."



