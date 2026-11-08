"""Browser shortcuts that drive the user's normal browser (not the Playwright one)."""

from __future__ import annotations

import logging
import re
import time
import urllib.parse
import webbrowser

from ._shared import focus_browser_and_page, force_open_browser
from .registry import tool

log = logging.getLogger("jarvis.tools")


@tool("Opens a website URL, or runs a Google search if given plain words, in the default browser.",
      params={"url_or_query": "A URL/domain like 'github.com', or words to search for"})
def open_website(url_or_query: str) -> str:
    target = url_or_query.strip()

    aliases = {
        "p-hub": "pornhub.com", "phub": "pornhub.com", "the hub": "pornhub.com",
        "adult site": "pornhub.com", "xv": "xvideos.com", "x-videos": "xvideos.com", "xn": "xnxx.com",
    }
    target_lower = target.lower()
    for alias, actual in aliases.items():
        if alias in target_lower:
            target = actual
            break

    if not target.startswith(("http://", "https://")):
        if "." in target and " " not in target:
            target = "https://" + target
        else:
            target = f"https://www.google.com/search?q={urllib.parse.quote(target)}"
    force_open_browser(target)
    return f"Opened {target} in browser, sir."


@tool("Performs a Google search for any topic in the default browser.",
      params={"query": "What to search for"})
def search_google(query: str) -> str:
    force_open_browser(f"https://www.google.com/search?q={urllib.parse.quote(query)}")
    return f"Searching Google for {query}, sir."


@tool("Opens Google Maps for a place, address or 'restaurants near me' style search.",
      params={"query": "Place or search, e.g. 'MUET Jamshoro'"})
def search_maps(query: str) -> str:
    try:
        url = f"https://www.google.com/maps/search/?api=1&query={urllib.parse.quote(query)}"
        force_open_browser(url)
        return f"Opened Google Maps search for '{query}', sir."
    except Exception as e:
        return f"Failed to search Google Maps: {e}"


@tool("Searches for and plays any song, music, or video on YouTube.",
      params={"query": "Song, artist or video title"})
def play_on_youtube(query: str) -> str:
    try:
        import pywhatkit
        pywhatkit.playonyt(query)
        return f"Playing '{query}' on YouTube now, sir."
    except Exception:
        force_open_browser(f"https://www.youtube.com/results?search_query={urllib.parse.quote(query)}")
        return f"Searching YouTube for {query}, sir."


@tool("Manages YouTube: 'search' opens YouTube search results, 'select_video' opens video 1, 2, 3... "
      "from the results on screen, 'play_direct' plays the best match straight away.",
      params={"action": "What to do", "query": "Search query or video title",
              "video_index": "1-based video number when action is 'select_video'"},
      enums={"action": ["search", "select_video", "play_direct"]})
def youtube_control(action: str, query: str = "", video_index: int = 1) -> str:
    action = (action or "search").lower().strip()
    if action == "search":
        if not query:
            return "Please specify a search query for YouTube, sir."
        webbrowser.open(f"https://www.youtube.com/results?search_query={urllib.parse.quote(query)}")
        return f"Searching YouTube for '{query}', sir."
    if action == "select_video":
        import pyautogui
        time.sleep(0.5)
        for _ in range(4 + max(0, int(video_index or 1) - 1)):
            pyautogui.press("tab")
            time.sleep(0.08)
        pyautogui.press("enter")
        return f"Selected video #{video_index} on YouTube, sir."
    if action == "play_direct":
        if not query:
            return "Please specify a video or song to play, sir."
        return play_on_youtube(query)
    return f"Unknown YouTube action '{action}', sir."


@tool("Manages tabs in the user's browser window.",
      params={"action": "Tab action", "tab_index": "Tab number 1-9 for 'select_tab'"},
      enums={"action": ["next_tab", "prev_tab", "close_tab", "select_tab"]})
def browser_tab_control(action: str, tab_index: int | None = None) -> str:
    act = (action or "").lower().strip()
    try:
        import pyautogui
        focus_browser_and_page()
        time.sleep(0.15)
        if act in ("next_tab", "next"):
            pyautogui.hotkey("ctrl", "tab")
            return "Switched to the next tab, sir."
        if act in ("prev_tab", "prev", "previous_tab", "previous"):
            pyautogui.hotkey("ctrl", "shift", "tab")
            return "Switched to the previous tab, sir."
        if act in ("close_tab", "close"):
            pyautogui.hotkey("ctrl", "w")
            return "Closed current tab, sir."
        if act in ("select_tab", "select") and tab_index is not None:
            idx = min(9, max(1, int(tab_index)))
            pyautogui.hotkey("ctrl", str(idx))
            return f"Switched to tab {idx}, sir."
        return f"Unknown or incomplete browser tab action '{action}', sir."
    except Exception as e:
        return f"Failed to control browser tab: {e}"


@tool("Scrolls the active browser page or window up or down.",
      params={"direction": "Scroll direction", "amount": "How far, roughly 100 per mouse-wheel notch (default 500)"},
      enums={"direction": ["up", "down"]})
def page_scroll(direction: str, amount: int = 500) -> str:
    dir_clean = (direction or "").lower().strip()
    try:
        import pyautogui
        import win32api
        import win32con

        pyautogui.FAILSAFE = False
        focus_browser_and_page()
        time.sleep(0.1)

        amt = abs(int(amount)) if amount else 500
        notches = max(1, min(20, amt // 100))
        # Native wheel event + PyAutoGUI wheel + PageUp/Down: some apps ignore one or two of them
        if "up" in dir_clean:
            win32api.mouse_event(win32con.MOUSEEVENTF_WHEEL, 0, 0, 120 * notches, 0)
            pyautogui.scroll(amt)
            pyautogui.press("pageup")
            return f"Scrolled up by {amt} units, sir."
        if "down" in dir_clean:
            win32api.mouse_event(win32con.MOUSEEVENTF_WHEEL, 0, 0, -120 * notches, 0)
            pyautogui.scroll(-amt)
            pyautogui.press("pagedown")
            return f"Scrolled down by {amt} units, sir."
        return f"Unknown scroll direction '{direction}', sir."
    except Exception as e:
        return f"Failed to scroll page: {e}"


@tool("Interacts with the page in the user's browser: 'youtube_search' types into YouTube's search box, "
      "'youtube_select_video' tabs to video N, 'page_search' finds text on the page (Ctrl+F).",
      params={"action": "What to do", "query": "Search text, or the video number for youtube_select_video"},
      enums={"action": ["youtube_search", "youtube_select_video", "page_search"]})
def site_interaction(action: str, query: str = "") -> str:
    act = (action or "").lower().strip()
    try:
        import pyautogui
        focus_browser_and_page()
        time.sleep(0.15)

        if act == "youtube_search":
            pyautogui.press("/")
            time.sleep(0.5)
            if query:
                pyautogui.hotkey("ctrl", "a")
                pyautogui.write(query)
                pyautogui.press("enter")
                return f"Searched YouTube for '{query}', sir."
            return "Activated YouTube search box, sir."
        if act == "youtube_select_video":
            digits = re.findall(r"\d+", str(query or "1"))
            count = int(digits[0]) if digits else 1
            for _ in range(count):
                pyautogui.press("tab")
                time.sleep(0.1)
            pyautogui.press("enter")
            return f"Selected YouTube video #{count}, sir."
        if act == "page_search":
            pyautogui.hotkey("ctrl", "f")
            time.sleep(0.3)
            if query:
                pyautogui.write(query)
                pyautogui.press("enter")
                return f"Searched page for '{query}', sir."
            return "Opened page search box, sir."
        return f"Unknown site interaction action '{action}', sir."
    except Exception as e:
        return f"Failed to perform site interaction: {e}"
