"""Applications and Windows system controls (volume, brightness, media, lock, screenshot)."""

from __future__ import annotations

import ctypes
import datetime
import logging
import os
import re
import subprocess
import webbrowser

from .registry import tool

log = logging.getLogger("jarvis.tools")

# Friendly name → command for os.system (fixed strings only, never user text)
_APPS = {
    "notepad":        "notepad",
    "calculator":     "calc",
    "calc":           "calc",
    "paint":          "mspaint",
    "chrome":         "start chrome",
    "browser":        "start chrome",
    "google":         "start chrome",
    "explorer":       "explorer",
    "file explorer":  "explorer",
    "files":          "explorer",
    "task manager":   "taskmgr",
    "vs code":        "code .",
    "vscode":         "code .",
    "spotify":        "start spotify",
    "word":           "start winword",
    "excel":          "start excel",
    "powerpoint":     "start powerpnt",
    "ppt":            "start powerpnt",
    "cmd":            "start cmd",
    "command prompt": "start cmd",
    "terminal":       "start cmd",
    "portfolio site": "start https://yahyasiddiqui.me",
}

_SCRIPT_EXTS = {".bat", ".cmd", ".ps1", ".vbs", ".vbe", ".js", ".jse", ".wsf", ".wsh",
                ".hta", ".scr", ".msi", ".com", ".pif", ".reg", ".lnk"}

_COMMON_FOLDERS = ("pictures", "downloads", "documents", "desktop", "videos", "music")


def _is_trusted_exe_location(path: str) -> bool:
    real = os.path.normcase(os.path.realpath(path))
    trusted = [
        os.environ.get("ProgramFiles", r"C:\Program Files"),
        os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)"),
        os.environ.get("SystemRoot", r"C:\Windows"),
        os.path.join(os.path.expanduser("~"), "AppData", "Local", "Programs"),
    ]
    for root in trusted:
        root = os.path.normcase(os.path.realpath(root))
        try:
            if os.path.commonpath([real, root]) == root:
                return True
        except ValueError:
            continue
    return False


@tool("Opens an application (notepad, calculator, chrome, VS Code, Spotify, Word...), a common folder, "
      "an installed program by name, or a file path.",
      params={"app_name": "App name like 'spotify', a folder like 'downloads', or a full path"})
def open_application(app_name: str) -> str:
    path_clean = (app_name or "").strip(' "\'')
    if len(path_clean) == 2 and path_clean[1] == ":":      # "e:" → "E:\"
        path_clean = path_clean.upper() + "\\"
    name_clean = path_clean.lower()

    folder_key = name_clean.removesuffix(" folder")
    if folder_key in _COMMON_FOLDERS:
        path_clean = os.path.join(os.path.expanduser("~"), folder_key.capitalize())
        name_clean = path_clean.lower()

    # URL / bare domain → browser
    looks_like_domain = (re.match(r"^[a-zA-Z0-9-]+\.[a-zA-Z]{2,}", name_clean)
                         and not re.search(r"\.(exe|bat|cmd|lnk|msc|txt|pdf|docx?|py)$", name_clean))
    if name_clean.startswith(("http://", "https://")) or looks_like_domain:
        url = name_clean if name_clean.startswith("http") else f"https://{name_clean}"
        webbrowser.open(url)
        return f"Opening URL: {url}, sir."

    for app_key, cmd in _APPS.items():
        if app_key in name_clean:
            try:
                os.system(cmd)
                return f"Opening {app_key} for you, sir."
            except Exception as e:
                return f"Failed to open {app_key}: {e}"

    # An existing folder or file
    if os.path.exists(path_clean):
        ext = os.path.splitext(path_clean)[1].lower()
        if ext in _SCRIPT_EXTS:
            return f"For safety I won't run script files ({ext}) by voice, sir. Open it manually."
        if ext == ".exe" and not _is_trusted_exe_location(path_clean):
            return "For safety I only launch programs installed in Program Files or Windows, sir."
        try:
            os.startfile(path_clean)
            return f"Opening {path_clean}, sir."
        except Exception as e:
            return f"Could not open '{path_clean}': {e}"

    # A plain installed-app name (e.g. "obs64"). Strict whitelist: nothing reaches cmd.exe unescaped.
    if re.fullmatch(r"[A-Za-z0-9 ._-]{1,60}", path_clean):
        try:
            subprocess.Popen(["cmd", "/c", "start", "", path_clean])
            return f"Launching {path_clean}, sir."
        except Exception as e:
            return f"Could not launch or find application '{app_name}': {e}"
    return f"I couldn't find an application called '{app_name}', sir."


_PROTECTED = {"explorer.exe", "csrss.exe", "svchost.exe", "winlogon.exe", "lsass.exe",
              "services.exe", "smss.exe", "wininit.exe", "dwm.exe", "msmpeng.exe",
              "python.exe", "pythonw.exe", "py.exe"}   # python = Jarvis itself

_PROCESS_NAMES = {
    "chrome": "chrome.exe", "browser": "chrome.exe", "notepad": "notepad.exe",
    "calculator": "CalculatorApp.exe", "calc": "CalculatorApp.exe", "paint": "mspaint.exe",
    "vs code": "Code.exe", "vscode": "Code.exe", "explorer": "explorer.exe",
    "file explorer": "explorer.exe", "cmd": "cmd.exe", "terminal": "cmd.exe",
    "spotify": "Spotify.exe", "word": "WINWORD.EXE", "excel": "EXCEL.EXE",
    "powerpoint": "POWERPNT.EXE", "ppt": "POWERPNT.EXE",
}


def _summarize_close(args: dict) -> str:
    return f"force-close {args.get('app_name', 'an application')} (unsaved work will be lost)"


@tool("Force-closes a running application (unsaved work is lost). The user must confirm out loud first.",
      params={"app_name": "App name like 'chrome' or 'spotify', or a process name like 'obs64.exe'"},
      confirm=_summarize_close)
def close_application(app_name: str) -> str:
    name_clean = (app_name or "").lower().strip()
    exe_name = _PROCESS_NAMES.get(name_clean, (app_name or "").strip())
    if not exe_name.lower().endswith(".exe"):
        exe_name += ".exe"

    if exe_name.lower() in _PROTECTED:
        if exe_name.lower() != "explorer.exe":
            return f"Terminating the system process '{exe_name}' is blocked to protect system stability, sir."
        # Close Explorer *windows* without killing the Windows shell
        try:
            import win32com.client
            closed = 0
            for window in list(win32com.client.Dispatch("Shell.Application").Windows()):
                if "explorer.exe" in getattr(window, "FullName", "").lower():
                    window.Quit()
                    closed += 1
            if closed:
                return f"Closed {closed} File Explorer window(s), sir."
            return "No File Explorer windows were open, sir."
        except Exception as e:
            return f"Failed to close File Explorer windows: {e}"

    # Process names only: letters, digits, space, dot, dash, underscore — no shell metacharacters
    if not re.fullmatch(r"[A-Za-z0-9 ._-]{1,64}\.exe", exe_name, re.IGNORECASE):
        return f"'{app_name}' doesn't look like a valid application name, sir."
    try:
        result = subprocess.run(["taskkill", "/f", "/im", exe_name], capture_output=True, text=True)
        if result.returncode == 0:
            return f"Closed {app_name} successfully, sir."
        return f"Could not close {app_name}. (taskkill: {result.stderr.strip()})"
    except Exception as e:
        return f"Failed to close application {app_name}: {e}"


# ─── System controls ──────────────────────────────────────────────────

def lock_screen_local() -> str:
    try:
        ctypes.windll.user32.LockWorkStation()
        return "Locking the screen now, sir."
    except Exception as e:
        return f"Could not lock the screen: {e}"


def take_screenshot() -> str:
    folder = os.path.join(os.path.expanduser("~"), "Pictures", "Screenshots")
    os.makedirs(folder, exist_ok=True)
    path = os.path.join(folder, f"jarvis_{datetime.datetime.now():%Y%m%d_%H%M%S}.png")
    import pyautogui
    pyautogui.screenshot(path)
    return f"Screenshot saved to {path}, sir."


def _press_media_key(vk: int, times: int = 1) -> None:
    for _ in range(times):
        ctypes.windll.user32.keybd_event(vk, 0, 0, 0)
        ctypes.windll.user32.keybd_event(vk, 0, 2, 0)   # KEYEVENTF_KEYUP


_PS = ["powershell", "-NoProfile", "-NonInteractive", "-Command"]


def _get_brightness() -> int | None:
    try:
        res = subprocess.run(
            _PS + ["(Get-CimInstance -Namespace root/WMI -ClassName WmiMonitorBrightness).CurrentBrightness"],
            capture_output=True, text=True, timeout=10,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        return int(res.stdout.split()[0]) if res.returncode == 0 and res.stdout.strip() else None
    except Exception:
        return None


def set_brightness(level: int) -> str:
    level = max(0, min(100, int(level)))   # int() → nothing but digits reaches PowerShell
    try:
        res = subprocess.run(
            _PS + ["Get-CimInstance -Namespace root/WMI -ClassName WmiMonitorBrightnessMethods | "
                   f"Invoke-CimMethod -MethodName WmiSetBrightness -Arguments @{{Timeout=0; Brightness={level}}}"],
            capture_output=True, text=True, timeout=10,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        if res.returncode != 0:
            return "This display doesn't support brightness control from Windows, sir."
        return f"Brightness set to {level} percent, sir."
    except Exception as e:
        return f"Could not change brightness: {e}"


@tool("Controls the PC: volume up/down/mute, screen brightness up/down/set, lock the screen, take a screenshot.",
      params={"action": "What to do",
              "value": "Brightness percent for 'brightness_set' (0-100), or the step size for brightness_up/down (default 20)"},
      enums={"action": ["volume_up", "volume_down", "mute", "brightness_up", "brightness_down",
                        "brightness_set", "lock", "screenshot"]})
def system_control(action: str, value: int | None = None) -> str:
    act = (action or "").lower().strip()
    try:
        if "volume_up" in act:
            _press_media_key(0xAF, 5)
            return "Volume increased, sir."
        if "volume_down" in act:
            _press_media_key(0xAE, 5)
            return "Volume decreased, sir."
        if "mute" in act:
            _press_media_key(0xAD)
            return "Mute toggled, sir."
        if "brightness" in act:
            if act == "brightness_set":
                if value is None:
                    return "Tell me the brightness level in percent, sir."
                return set_brightness(value)
            step = int(value) if value else 20
            current = _get_brightness()
            if current is None:
                return "This display doesn't support brightness control from Windows, sir."
            return set_brightness(current + step if "up" in act else current - step)
        if "screenshot" in act:
            return take_screenshot()
        if "lock" in act:
            return lock_screen_local()
    except Exception as e:
        return f"Failed to run '{action}': {e}"
    return f"Unknown system control action '{action}', sir."


@tool("Controls whatever media is playing on the PC (Spotify, YouTube, etc.).",
      params={"action": "Media key to press"},
      enums={"action": ["play_pause", "next", "previous", "stop"]})
def media_control(action: str) -> str:
    keys = {"play_pause": 0xB3, "play": 0xB3, "pause": 0xB3, "playpause": 0xB3,
            "next": 0xB0, "previous": 0xB1, "prev": 0xB1, "stop": 0xB2}
    vk = keys.get((action or "").lower().strip())
    if vk is None:
        return f"Unknown media action '{action}', sir."
    try:
        _press_media_key(vk)
        return f"Media {action.replace('_', '/')} done, sir."
    except Exception as e:
        return f"Failed to control media: {e}"
