# commands.py — Instant local skills for Jarvis (zero AI latency)
# These commands are handled locally — no Ollama call, no wait time.

import datetime
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

# Global state for multi-turn assignment generation
assignment_state = {
    "is_active": False,
    "step": 0,
    "topic": "",
    "subject": ""
}

# Global tracking variable for the last generated assignment document path
last_generated_doc = None

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
def play_on_youtube(query):
    encoded_query = urllib.parse.quote(query)
    webbrowser.open(f"https://www.youtube.com/results?search_query={encoded_query}")
    return f"Searching YouTube for {query}."

def search_google(query):
    encoded_query = urllib.parse.quote(query)
    webbrowser.open(f"https://www.google.com/search?q={encoded_query}")
    return f"Searching Google for {query}."

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
def check_attendance_thread():
    from selenium import webdriver
    from selenium.webdriver.common.by import By
    from selenium.webdriver.support.ui import WebDriverWait
    from selenium.webdriver.support import expected_conditions as EC
    
    try:
        options = webdriver.EdgeOptions()
        options.add_experimental_option("detach", True)
        options.add_argument("--disable-gpu")
        options.add_argument("--log-level=3")
        options.add_argument("--silent")
        
        driver = webdriver.Edge(options=options)
        driver.get("http://misportal.muet.edu.pk/mis/login.php")
        
        wait = WebDriverWait(driver, 10)
        cnic_input = wait.until(EC.presence_of_element_located((By.ID, "inputStudentCNIC")))
        password_input = driver.find_element(By.ID, "inputStudentPassword")
        submit_btn = driver.find_element(By.ID, "studentLogin")
        
        cnic_input.clear()
        cnic_input.send_keys("43304-7952345-7")
        password_input.clear()
        password_input.send_keys("yahyamis@01")
        submit_btn.click()
    except Exception as e:
        try:
            from brain import speak
            speak(f"Sir, I encountered an issue logging into the attendance portal: {e}")
        except Exception:
            pass


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
    elif "attendance" in text_clean or "attendence" in text_clean:
        threading.Thread(target=check_attendance_thread, daemon=True).start()
        return "Opening the Mehran University attendance portal and logging you in now, sir."

    # Returning None tells brain.py to forward the prompt to Qwen/Ollama
    return None
