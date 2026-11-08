"""
Jarvis tools package.

Every function decorated with @tool in these modules is registered in TOOLS and
declared to Gemini automatically. To add a tool: write a function with type
hints in the right module, decorate it with @tool("what it does", params={...}),
and it is live on the next start.

    info      time, date, weather
    web       default-browser shortcuts (Google, Maps, YouTube, tabs, scrolling)
    browser   Jarvis's own Playwright browser (assistive navigation, checkout)
    files     sandboxed read / write / find, folders
    apps      open/close apps, volume, brightness, media keys, lock, screenshot
    vision    screen reader and Ghost Coder
    academic  MIS attendance, assignment generator, local Qwen
    memory    long-term facts
"""

from .registry import TOOLS, Tool, clean_args, declarations, tool  # noqa: F401
from . import info, web, browser, files, apps, vision, academic, memory  # noqa: F401  (registers tools)
from .memory import get_all_memories  # noqa: F401
