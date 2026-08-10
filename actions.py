# ╔══════════════════════════════════════════════════════════════╗
# ║  JARVIS — actions.py                                         ║
# ║                                                              ║
# ║  Real system-action whitelist.                               ║
# ║  Every function:                                             ║
# ║    • Returns "✅ ..." on success or "❌ ..." on failure       ║
# ║    • Is wrapped in try/except — one broken action never      ║
# ║      crashes the assistant                                    ║
# ║    • Logs timestamp + action + result to action_log.txt      ║
# ║                                                              ║
# ║  To add a new app: just add a key/value to APP_MAP below.   ║
# ╚══════════════════════════════════════════════════════════════╝

import os
import subprocess
import webbrowser
import ctypes
import shutil
import datetime
import re
import json
from urllib.parse import quote_plus

# ═══════════════════════════════════════════════════════════════
#  AUDIT LOG
# ═══════════════════════════════════════════════════════════════
_LOG_FILE = os.path.join(os.path.dirname(__file__), "action_log.txt")

def _log(action: str, result: str) -> None:
    """Append a timestamped line to action_log.txt for auditing."""
    timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with open(_LOG_FILE, "a", encoding="utf-8") as f:
        f.write(f"[{timestamp}] {action} → {result}\n")


# ═══════════════════════════════════════════════════════════════
#  APP MAP  ← Add new apps here!
#  Format: "friendly name": "path or command"
#  Use shutil.which() fallbacks for portability.
# ═══════════════════════════════════════════════════════════════
def _build_app_map() -> dict:
    """
    Build the app name → executable path dictionary.
    Tries multiple common install locations automatically so it
    works on most Windows machines without manual path editing.
    """

    def _find(*candidates) -> str | None:
        """Return the first existing path from a list of candidates."""
        for c in candidates:
            expanded = os.path.expandvars(c)
            if os.path.exists(expanded):
                return expanded
            found = shutil.which(c)        # also check PATH
            if found:
                return found
        return None

    user_profile = os.environ.get("USERPROFILE", "C:\\Users\\Default")

    return {
        # ── Browsers ──────────────────────────────────────────────
        "chrome": _find(
            r"%PROGRAMFILES%\Google\Chrome\Application\chrome.exe",
            r"%PROGRAMFILES(X86)%\Google\Chrome\Application\chrome.exe",
            r"%LOCALAPPDATA%\Google\Chrome\Application\chrome.exe",
            "chrome",
        ),
        "firefox": _find(
            r"%PROGRAMFILES%\Mozilla Firefox\firefox.exe",
            r"%PROGRAMFILES(X86)%\Mozilla Firefox\firefox.exe",
            "firefox",
        ),
        "edge": _find(
            r"%PROGRAMFILES(X86)%\Microsoft\Edge\Application\msedge.exe",
            r"%PROGRAMFILES%\Microsoft\Edge\Application\msedge.exe",
            "msedge",
        ),

        # ── Code editors ──────────────────────────────────────────
        "vscode": _find(
            r"%LOCALAPPDATA%\Programs\Microsoft VS Code\Code.exe",
            r"%PROGRAMFILES%\Microsoft VS Code\Code.exe",
            "code",
        ),
        "vs code": _find(
            r"%LOCALAPPDATA%\Programs\Microsoft VS Code\Code.exe",
            r"%PROGRAMFILES%\Microsoft VS Code\Code.exe",
            "code",
        ),
        "notepad": "notepad.exe",
        "notepad++": _find(
            r"%PROGRAMFILES%\Notepad++\notepad++.exe",
            r"%PROGRAMFILES(X86)%\Notepad++\notepad++.exe",
            "notepad++",
        ),

        # ── System apps ───────────────────────────────────────────
        "explorer":         "explorer.exe",
        "file explorer":    "explorer.exe",
        "files":            "explorer.exe",
        "calculator":       "calc.exe",
        "calc":             "calc.exe",
        "task manager":     "taskmgr.exe",
        "control panel":    "control.exe",
        "settings":         "ms-settings:",      # Opens with os.startfile
        "paint":            "mspaint.exe",
        "wordpad":          "wordpad.exe",
        "cmd":              "cmd.exe",
        "terminal":         _find("wt.exe", "cmd.exe"),   # Windows Terminal or CMD
        "powershell":       "powershell.exe",

        # ── Media & Entertainment ─────────────────────────────────
        "spotify": _find(
            rf"{user_profile}\AppData\Roaming\Spotify\Spotify.exe",
            r"%APPDATA%\Spotify\Spotify.exe",
            "spotify",
        ),
        "vlc": _find(
            r"%PROGRAMFILES%\VideoLAN\VLC\vlc.exe",
            r"%PROGRAMFILES(X86)%\VideoLAN\VLC\vlc.exe",
            "vlc",
        ),
        "discord": _find(
            rf"{user_profile}\AppData\Local\Discord\Update.exe",
            r"%LOCALAPPDATA%\Discord\Update.exe",
            "discord",
        ),

        # ── Microsoft Office ──────────────────────────────────────
        "word":       _find(r"%PROGRAMFILES%\Microsoft Office\root\Office16\WINWORD.EXE",
                             r"%PROGRAMFILES(X86)%\Microsoft Office\root\Office16\WINWORD.EXE",
                             "winword.exe"),
        "excel":      _find(r"%PROGRAMFILES%\Microsoft Office\root\Office16\EXCEL.EXE",
                             r"%PROGRAMFILES(X86)%\Microsoft Office\root\Office16\EXCEL.EXE",
                             "excel.exe"),
        "powerpoint": _find(r"%PROGRAMFILES%\Microsoft Office\root\Office16\POWERPNT.EXE",
                             r"%PROGRAMFILES(X86)%\Microsoft Office\root\Office16\POWERPNT.EXE",
                             "powerpnt.exe"),
    }


# Build once at import time
APP_MAP: dict = _build_app_map()


# ═══════════════════════════════════════════════════════════════
#  ACTION: open_app
# ═══════════════════════════════════════════════════════════════
# Chrome profile to always use for all browser/search actions.
# Found by running: chrome --profile-directory=... or checking
# %LOCALAPPDATA%\Google\Chrome\User Data\<dir>\Preferences -> profile.name
# Profile 2 = YAHYA SIDDIQUI (yahyasid45@gmail.com)
CHROME_PROFILE = "Profile 2"

def open_app(app_name: str) -> str:
    """
    Opens a whitelisted application by its friendly name.
    Looks up the exe path in APP_MAP, then launches it.
    For Chrome specifically, always opens with CHROME_PROFILE so the
    profile picker never blocks Jarvis.
    Falls back to os.startfile for protocol URLs like ms-settings:.
    """
    key = app_name.lower().strip()
    path = APP_MAP.get(key)

    if not path:
        # One more attempt: try running the name directly (it might be in PATH)
        found = shutil.which(key)
        if found:
            path = found

    if not path:
        result = f"❌ App not found in whitelist: '{app_name}'. Add it to APP_MAP in actions.py."
        _log(f"open_app({app_name})", result)
        return result

    try:
        if path.startswith("ms-"):
            # Handle ms-settings: and other URI protocols
            os.startfile(path)
        elif key == "chrome" and path:
            # Always open Chrome with the designated profile -- skips the picker
            subprocess.Popen([path, f"--profile-directory={CHROME_PROFILE}"], shell=False)
        else:
            subprocess.Popen([path], shell=False)
        result = f"✅ Opened {app_name.title()}."
    except Exception as e:
        result = f"❌ Failed to open {app_name}: {e}"

    _log(f"open_app({app_name})", result)
    return result


# ═══════════════════════════════════════════════════════════════
#  ACTION: open_website
# ═══════════════════════════════════════════════════════════════
# Regex: matches real domains like "youtube.com", "github.com/user"
_DOMAIN_RE = re.compile(
    r"^(https?://)?"                          # optional scheme
    r"([a-zA-Z0-9-]+\.)"                      # subdomain or domain
    r"[a-zA-Z]{2,}"                           # TLD
    r"(/[^\s]*)?$"                            # optional path
)

def open_website(query: str) -> str:
    """
    Opens a URL or search query always in Chrome using the YAHYA SIDDIQUI
    profile (CHROME_PROFILE) -- bypasses the profile picker completely.

    If `query` looks like a real domain -> opens it directly in Chrome.
    Otherwise -> builds a properly URL-encoded Google search URL.
    Falls back to webbrowser.open() if Chrome exe is not found.
    """
    q = query.strip()

    # Resolve Chrome path from APP_MAP (built at import time)
    chrome_path = APP_MAP.get("chrome")

    try:
        if _DOMAIN_RE.match(q):
            # Looks like a real domain -- add https:// if missing
            url   = q if q.startswith("http") else f"https://{q}"
            label = f"Opened {url}"
        else:
            # Search query -- properly encode every special character
            encoded = quote_plus(q)
            url     = f"https://www.google.com/search?q={encoded}"
            label   = f"Searching Google for '{q}'"

        if chrome_path:
            # Launch Chrome directly with the pinned profile -- no picker shown
            subprocess.Popen(
                [chrome_path, f"--profile-directory={CHROME_PROFILE}", url],
                shell=False
            )
            result = f"✅ {label} (YAHYA SIDDIQUI profile)."
        else:
            # Fallback: Chrome not found, use system default browser
            webbrowser.open(url)
            result = f"✅ {label} in your default browser."

    except Exception as e:
        result = f"❌ Could not open browser: {e}"

    _log(f"open_website({query})", result)
    return result


# ═══════════════════════════════════════════════════════════════
#  ACTION: lock_screen
# ═══════════════════════════════════════════════════════════════
def lock_screen() -> str:
    """Locks the Windows session using the Win32 API."""
    try:
        ctypes.windll.user32.LockWorkStation()
        result = "✅ Screen locked."
    except Exception as e:
        result = f"❌ Could not lock screen: {e}"

    _log("lock_screen()", result)
    return result


# ═══════════════════════════════════════════════════════════════
#  ACTION: set_volume
# ═══════════════════════════════════════════════════════════════
def set_volume(level: int | str) -> str:
    """
    Sets the Windows master volume to `level` (0–100).
    Uses pycaw (Windows Core Audio API wrapper) for reliable control.
    Falls back to nircmd if pycaw is unavailable.
    """
    try:
        level = int(level)
        level = max(0, min(100, level))   # Clamp to 0–100
    except (ValueError, TypeError):
        result = f"❌ Invalid volume level: '{level}'. Use a number between 0 and 100."
        _log(f"set_volume({level})", result)
        return result

    try:
        from pycaw.pycaw import AudioUtilities, IAudioEndpointVolume
        from comtypes import CLSCTX_ALL
        from ctypes import cast, POINTER

        devices  = AudioUtilities.GetSpeakers()
        interface = devices.Activate(IAudioEndpointVolume._iid_, CLSCTX_ALL, None)
        volume    = cast(interface, POINTER(IAudioEndpointVolume))

        # pycaw uses scalar 0.0–1.0
        volume.SetMasterVolumeLevelScalar(level / 100.0, None)
        result = f"✅ Volume set to {level}%."

    except ImportError:
        # pycaw not installed — try nircmd as fallback
        try:
            nircmd = shutil.which("nircmd") or shutil.which("nircmdc")
            if nircmd:
                # nircmd uses 0–65535 scale
                nircmd_level = int(level / 100 * 65535)
                subprocess.run([nircmd, "setsysvolume", str(nircmd_level)], check=True)
                result = f"✅ Volume set to {level}% (via nircmd)."
            else:
                result = "❌ Volume control unavailable. Run: pip install pycaw"
        except Exception as e:
            result = f"❌ Volume control failed: {e}"

    except Exception as e:
        result = f"❌ Could not set volume: {e}"

    _log(f"set_volume({level})", result)
    return result


# ═══════════════════════════════════════════════════════════════
#  ACTION: take_screenshot
# ═══════════════════════════════════════════════════════════════
_SCREENSHOT_DIR = os.path.join(
    os.path.expanduser("~"), "Pictures", "Jarvis Screenshots"
)

def take_screenshot() -> str:
    """
    Captures a full-screen screenshot using PIL.ImageGrab.
    Saves to ~/Pictures/Jarvis Screenshots/ with a timestamp filename.
    Falls back to pyautogui if PIL is unavailable.
    """
    os.makedirs(_SCREENSHOT_DIR, exist_ok=True)
    timestamp = datetime.datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    filepath  = os.path.join(_SCREENSHOT_DIR, f"screenshot_{timestamp}.png")

    try:
        from PIL import ImageGrab
        img = ImageGrab.grab()
        img.save(filepath)
        result = f"✅ Screenshot saved to {filepath}"

    except ImportError:
        try:
            import pyautogui
            pyautogui.screenshot(filepath)
            result = f"✅ Screenshot saved to {filepath}"
        except ImportError:
            result = "❌ Screenshot failed. Run: pip install pillow"
        except Exception as e:
            result = f"❌ Screenshot failed: {e}"

    except Exception as e:
        result = f"❌ Screenshot failed: {e}"

    _log("take_screenshot()", result)
    return result


# ═══════════════════════════════════════════════════════════════
#  ACTION: close_app
# ═══════════════════════════════════════════════════════════════
# Maps friendly names → process executable names
_PROCESS_MAP = {
    "chrome":       "chrome.exe",
    "firefox":      "firefox.exe",
    "edge":         "msedge.exe",
    "spotify":      "Spotify.exe",
    "vlc":          "vlc.exe",
    "discord":      "Discord.exe",
    "vscode":       "Code.exe",
    "vs code":      "Code.exe",
    "notepad":      "notepad.exe",
    "notepad++":    "notepad++.exe",
    "explorer":     "explorer.exe",
    "file explorer":"explorer.exe",
    "calculator":   "CalculatorApp.exe",
    "word":         "WINWORD.EXE",
    "excel":        "EXCEL.EXE",
    "powerpoint":   "POWERPNT.EXE",
    "task manager": "Taskmgr.exe",
    "powershell":   "powershell.exe",
    "cmd":          "cmd.exe",
    "terminal":     "WindowsTerminal.exe",
}

def close_app(app_name: str) -> str:
    """
    Terminates a running application by its process name.
    Uses psutil for a clean kill; falls back to taskkill if unavailable.
    """
    key         = app_name.lower().strip()
    process_name = _PROCESS_MAP.get(key, key + ".exe")   # fallback: treat as exe name

    try:
        import psutil
        killed = 0
        for proc in psutil.process_iter(["name"]):
            if proc.info["name"] and proc.info["name"].lower() == process_name.lower():
                proc.kill()
                killed += 1

        if killed > 0:
            result = f"✅ Closed {app_name.title()} ({killed} process{'es' if killed > 1 else ''} terminated)."
        else:
            result = f"❌ {app_name.title()} is not running."

    except ImportError:
        # Fall back to Windows taskkill
        try:
            subprocess.run(
                ["taskkill", "/F", "/IM", process_name],
                check=True, capture_output=True
            )
            result = f"✅ Closed {app_name.title()} (via taskkill)."
        except subprocess.CalledProcessError:
            result = f"❌ {app_name.title()} is not running (taskkill found nothing)."
        except Exception as e:
            result = f"❌ Could not close {app_name}: {e}"

    except Exception as e:
        result = f"❌ Could not close {app_name}: {e}"

    _log(f"close_app({app_name})", result)
    return result


# ═══════════════════════════════════════════════════════════════
#  ACTION: send_whatsapp_message
# ═══════════════════════════════════════════════════════════════
_CONTACTS_FILE = os.path.join(os.path.dirname(__file__), "contacts.json")

def _load_contacts() -> dict:
    """Load contacts.json. Returns empty dict if file missing or malformed."""
    try:
        with open(_CONTACTS_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        # Strip the _comment key if present, normalise keys to lowercase
        return {k.lower(): v for k, v in data.items() if not k.startswith("_")}
    except FileNotFoundError:
        return {}
    except Exception as e:
        return {}

def send_whatsapp_message(contact_name: str, message: str) -> str:
    """
    Sends a WhatsApp message via the WhatsApp Desktop app.

    How it works:
      1. Builds a  whatsapp://send/?phone=...&text=...  URI.
      2. os.startfile() hands it to Windows, which opens WhatsApp Desktop
         and pre-fills the chat with the contact + message text.
      3. pyautogui waits 4 seconds (for WA Desktop to open the chat)
         then presses Enter to actually send the message.

    Requirements: WhatsApp Desktop installed and logged in. No browser needed.
    """
    name     = contact_name.strip().lower()
    contacts = _load_contacts()

    if not contacts:
        result = "❌ contacts.json is missing or empty. Add contacts first, sir."
        _log(f"send_whatsapp({contact_name})", result)
        return result

    phone = contacts.get(name)
    if not phone:
        result = f"❌ I don't have a saved number for '{contact_name}', sir. Add them to contacts.json."
        _log(f"send_whatsapp({contact_name})", result)
        return result

    if not message.strip():
        result = "❌ No message content provided."
        _log(f"send_whatsapp({contact_name})", result)
        return result

    try:
        import time
        import pyautogui
        from urllib.parse import quote

        # Build the whatsapp:// deep link.
        # Windows passes this URI to WhatsApp Desktop, which opens
        # the chat pre-filled with the contact and message text.
        encoded_msg = quote(message)
        uri = "whatsapp://send/?phone=" + phone + "&text=" + encoded_msg

        # Open WhatsApp Desktop with the pre-filled chat
        os.startfile(uri)

        # Wait for WhatsApp Desktop to open and load the conversation.
        # Increase this value on slower machines if the message doesn't send.
        time.sleep(4)

        # Press Enter to send the pre-filled message
        pyautogui.press("enter")

        result = f"✅ WhatsApp message sent to {contact_name.title()}."

    except FileNotFoundError:
        result = "❌ WhatsApp Desktop is not installed or not registered as a URI handler."
    except Exception as e:
        result = f"❌ Failed to send WhatsApp message: {e}"

    _log(f"send_whatsapp({contact_name}, msg='{message[:30]}...')", result)
    return result


# ═══════════════════════════════════════════════════════════════
#  ACTION: run_cmd_command
# ═══════════════════════════════════════════════════════════════
def run_cmd_command(command: str) -> str:
    """
    Executes a shell command in a new visible Command Prompt window.
    Allows user to inspect results interactively.
    """
    if not command.strip():
        result = "❌ No command specified."
        _log("run_cmd_command()", result)
        return result

    try:
        # /k runs the command and keeps the CMD window open for review
        subprocess.Popen(f'start cmd /k "{command}"', shell=True)
        result = f"✅ Executed command on CMD: {command}"
    except Exception as e:
        result = f"❌ Failed to run command on CMD: {e}"

    _log(f"run_cmd_command('{command}')", result)
    return result


# ═══════════════════════════════════════════════════════════════
#  CENTRAL DISPATCHER
# ═══════════════════════════════════════════════════════════════
# Only actions listed here can be called — the LLM cannot reach
# anything outside this explicit whitelist.
_WHITELIST = {
    "open_app":               lambda p: open_app(p.get("app_name", "")),
    "open_website":           lambda p: open_website(p.get("query", p.get("url", ""))),
    "lock_screen":            lambda p: lock_screen(),
    "set_volume":             lambda p: set_volume(p.get("level", 50)),
    "take_screenshot":        lambda p: take_screenshot(),
    "close_app":              lambda p: close_app(p.get("app_name", "")),
    "send_whatsapp_message":  lambda p: send_whatsapp_message(
                                            p.get("contact_name", ""),
                                            p.get("message", "")
                                        ),
    "run_cmd_command":        lambda p: run_cmd_command(p.get("command", "")),
}

def dispatch_action(action_name: str, params: dict) -> str:
    """
    The only entry point from brain.py into the action system.
    Looks up `action_name` in the whitelist and calls the handler.
    Returns a result string for Jarvis to speak.
    If the action is not whitelisted, returns a safe refusal message.
    """
    handler = _WHITELIST.get(action_name)
    if handler is None:
        result = f"I don't have permission to do that yet, sir. Action '{action_name}' is not in my whitelist."
        _log(f"dispatch({action_name})", "BLOCKED — not in whitelist")
        return result

    return handler(params)
