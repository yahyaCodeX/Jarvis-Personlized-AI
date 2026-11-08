"""Helpers shared by several tool modules (not tools themselves)."""

from __future__ import annotations

import io
import logging
import os
import re
import subprocess
import time
import webbrowser

log = logging.getLogger("jarvis.tools")


def speak(text: str) -> None:
    """Blocking Windows SAPI announcement for background jobs (call from a worker thread)."""
    log.info(f"[SPEAK] {text}")
    try:
        import pythoncom
        import win32com.client
        pythoncom.CoInitialize()
        try:
            win32com.client.Dispatch("SAPI.SpVoice").Speak(text)
        finally:
            pythoncom.CoUninitialize()
    except Exception as e:
        log.warning(f"[SPEAK] TTS failed: {e}")


def focus_browser_and_page() -> None:
    """Bring the browser window to the foreground and park the mouse over the page."""
    try:
        import pyautogui
        import win32api
        import win32con
        import win32gui

        pyautogui.FAILSAFE = False

        def enum_cb(hwnd, extra):
            if win32gui.IsWindowVisible(hwnd):
                title = win32gui.GetWindowText(hwnd).lower()
                if any(b in title for b in ["chrome", "edge", "firefox", "brave", "opera", "youtube", "google maps"]) or (
                        " - " in title and any(t in title for t in [".com", ".org", "http", "search", "google"])):
                    extra.append(hwnd)

        hwnds: list = []
        win32gui.EnumWindows(enum_cb, hwnds)
        if hwnds:
            hwnd = hwnds[0]
            win32api.keybd_event(0x12, 0, 0, 0)          # Alt: lets SetForegroundWindow succeed
            win32gui.ShowWindow(hwnd, win32con.SW_RESTORE)
            win32gui.SetForegroundWindow(hwnd)
            win32api.keybd_event(0x12, 0, win32con.KEYEVENTF_KEYUP, 0)
            time.sleep(0.15)

        sw, sh = pyautogui.size()
        pyautogui.moveTo(sw // 2, sh // 2)
    except Exception as e:
        log.warning(f"[FOCUS BROWSER WARNING] {e}")


def force_open_browser(url: str) -> bool:
    """Open an http(s) URL in the default browser (falls back to Chrome, then webbrowser)."""
    if not re.match(r"^https?://", url or "", re.IGNORECASE):
        log.warning(f"[BROWSER] Refusing non-http URL: {url!r}")
        return False
    opened = False
    try:
        os.startfile(url)  # default browser, no shell involved
        opened = True
    except Exception:
        pass
    if not opened:
        for cp in (r"C:\Program Files\Google\Chrome\Application\chrome.exe",
                   r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
                   os.path.expanduser(r"~\AppData\Local\Google\Chrome\Application\chrome.exe")):
            if os.path.exists(cp):
                try:
                    subprocess.Popen([cp, url])
                    opened = True
                    break
                except Exception:
                    pass
    if not opened:
        try:
            opened = bool(webbrowser.open(url))
        except Exception:
            pass
    if opened:
        time.sleep(0.5)
        focus_browser_and_page()
    return opened


def capture_screen(fmt: str = "PNG", quality: int = 95) -> bytes | None:
    """Screenshot of the whole desktop as image bytes (None if capture failed)."""
    for grab in (_grab_pil, _grab_pyautogui):
        try:
            img = grab()
            buf = io.BytesIO()
            if fmt.upper() == "JPEG":
                img.convert("RGB").save(buf, format="JPEG", quality=quality)
            else:
                img.save(buf, format=fmt)
            return buf.getvalue()
        except Exception as err:
            log.debug(f"[SCREEN CAPTURE] {grab.__name__} failed: {err}")
    log.warning("[SCREEN CAPTURE] Could not capture the screen.")
    return None


def _grab_pil():
    from PIL import ImageGrab
    return ImageGrab.grab()


def _grab_pyautogui():
    import pyautogui
    return pyautogui.screenshot()


def ask_gemini(contents, label: str) -> str | None:
    """Run a one-shot Gemini request, trying each VISION_MODELS entry until one answers."""
    from config import VISION_MODELS

    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        log.error(f"[{label}] GEMINI_API_KEY missing.")
        return None
    from google import genai
    client = genai.Client(api_key=api_key)
    for model in VISION_MODELS:
        try:
            resp = client.models.generate_content(model=model, contents=contents)
            if resp and resp.text:
                log.info(f"[{label}] Answered by {model}.")
                return resp.text.strip()
        except Exception as err:
            log.warning(f"[{label}] Model {model} failed ({err}), trying the next one...")
    return None


def image_part(data: bytes, mime_type: str):
    from google.genai import types
    return types.Part.from_bytes(data=data, mime_type=mime_type)
