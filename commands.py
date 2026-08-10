# commands.py — Instant local skills for Jarvis (zero AI latency)
# These commands are handled locally — no Ollama call, no wait time.

import datetime
import requests
import os
import re
import math as _math

# ─── Config ──────────────────────────────────────────────────
WEATHER_CITY = "Shikarpur, Sindh"

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

