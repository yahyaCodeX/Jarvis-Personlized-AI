"""University tools: MIS attendance (Playwright), assignment generator and local Qwen (Ollama)."""

from __future__ import annotations

import json
import logging
import os
import threading
import time

import requests

from config import get_secret, load_profile
from ._shared import speak
from .registry import tool

log = logging.getLogger("jarvis.tools")

MIS_LOGIN_URL = "http://misportal.muet.edu.pk/mis/login.php"
OLLAMA_URL = "http://localhost:11434/api/generate"


def _ollama_model() -> str:
    return os.getenv("OLLAMA_MODEL", "qwen2.5:7b")


# ─── MIS attendance ──────────────────────────────────────────────────
_last_attendance_time = 0.0
_attendance_cache_result: str | None = None
_attendance_cache_timestamp = 0.0
ATTENDANCE_CACHE_S = 900   # 15 minutes


def _select_option_containing(page, select, text: str) -> bool:
    """Pick the first <option> whose label contains `text` (case-insensitive)."""
    labels = select.locator("option").all_inner_texts()
    match = next((lbl for lbl in labels if text.lower() in lbl.lower()), None)
    if match is None:
        log.warning(f"[ATTENDANCE] No option containing '{text}'. Options: {labels[:15]}")
        return False
    select.select_option(label=match)   # fires input/change, so the page's AJAX runs
    page.wait_for_load_state("networkidle", timeout=10000)
    return True


@tool("Opens the user's MUET MIS portal in Jarvis's browser, logs in and shows their attendance report.")
def check_attendance() -> str:
    global _last_attendance_time, _attendance_cache_result, _attendance_cache_timestamp
    now = time.time()
    if _attendance_cache_result and now - _attendance_cache_timestamp < ATTENDANCE_CACHE_S:
        return _attendance_cache_result
    if now - _last_attendance_time < 15.0:
        return "I am already logging into the MIS portal for your attendance, sir."
    _last_attendance_time = now

    cnic, password = get_secret("MIS_CNIC"), get_secret("MIS_PASSWORD")
    if not cnic or not password:
        return "MIS login details are missing, sir. Add MIS_CNIC and MIS_PASSWORD to the .env file."
    mis = load_profile().get("mis") or {}

    from .browser import get_active_page
    try:
        page = get_active_page()
        page.goto(MIS_LOGIN_URL, timeout=20000)
        cnic_box = page.locator("#inputStudentCNIC")
        cnic_box.click()
        cnic_box.press_sequentially(cnic, delay=30)   # typed, so the CNIC input mask formats it
        page.locator("#inputStudentPassword").fill(password)
        page.locator("#studentLogin").click()

        page.locator("a:has-text('Provisional Report')").first.click(timeout=15000)
        page.locator("a:has-text('1. Under Graduate')").first.click(timeout=15000)

        selects = page.locator("select")
        selects.first.wait_for(timeout=15000)
        picked = []
        if mis.get("department") and _select_option_containing(page, selects.nth(0), mis["department"]):
            picked.append(mis["department"])
        if mis.get("class") and selects.count() >= 2 and _select_option_containing(page, selects.nth(1), mis["class"]):
            picked.append(mis["class"])

        detail = f" for {', '.join(picked)}" if picked else " (set mis.department and mis.class in profile.json to pick your class automatically)"
        result = f"I've logged into the MIS portal and opened your attendance report{detail}, sir."
        if picked:
            _attendance_cache_result, _attendance_cache_timestamp = result, now
        return result
    except Exception as e:
        log.error(f"[ATTENDANCE] {e}")
        return "I ran into a problem navigating the MIS portal, sir. It may be down or its layout changed."


# ─── Assignment generator (local Ollama → Word document) ─────────────
last_generated_doc: str | None = None


def _assignment_header() -> str:
    p = load_profile()
    lines = [f"Name: {p['name']}" if p.get("name") else "",
             f"Roll No: {p['roll_no']}" if p.get("roll_no") else "",
             f"Department: {p['department']}" if p.get("department") else ""]
    return "\n".join(line for line in lines if line)


def generate_assignment_thread(topic: str, subject: str) -> None:
    """Background job: ask Ollama for the text, save a .docx on the Desktop, announce it."""
    global last_generated_doc
    from docx import Document

    payload = {
        "model": _ollama_model(),
        "prompt": f"Write a detailed, academic university assignment on the topic: {topic} for the subject: {subject}.",
        "stream": True,
        "options": {"num_predict": 800, "temperature": 0.5, "num_ctx": 2048},
    }
    text = ""
    try:
        response = requests.post(OLLAMA_URL, json=payload, stream=True, timeout=180)
        response.raise_for_status()
        for line in response.iter_lines():
            if line:
                chunk = json.loads(line.decode("utf-8"))
                text += chunk.get("response", "")
                if chunk.get("done", False):
                    break
        text = text.strip()
    except Exception as e:
        speak(f"Sir, I failed to generate the assignment content due to an error: {e}")
        return

    if not text:
        speak("Sir, Ollama returned an empty response, so I could not create the assignment document.")
        return

    try:
        doc = Document()
        header = _assignment_header()
        if header:
            doc.add_paragraph(header)
        doc.add_paragraph(f"Subject: {subject}")
        doc.add_heading(topic, level=0)
        for paragraph in text.split("\n"):
            if paragraph.strip():
                doc.add_paragraph(paragraph.strip())

        safe_topic = "".join(c if c.isalnum() or c in " -_" else "_" for c in topic).strip().replace(" ", "_")
        path = os.path.join(os.path.expanduser("~"), "Desktop", f"{safe_topic or 'Untitled'}_Assignment.docx")
        doc.save(path)
        last_generated_doc = path
        speak(f"Sir, your assignment on {topic} for {subject} has been generated and saved to your desktop.")
    except Exception as e:
        speak(f"Sir, I encountered an error while saving the Word document: {e}")


@tool("Writes a university assignment as a Word document on the Desktop, using the local Ollama model in the "
      "background. Jarvis announces when it is ready (takes a minute or two).",
      params={"topic": "Assignment topic", "subject": "Course/subject name"})
def generate_assignment(topic: str, subject: str) -> str:
    threading.Thread(target=generate_assignment_thread, args=(topic, subject), daemon=True).start()
    return f"I am now generating the assignment on {topic} for the subject {subject} in the background, sir."


@tool("Opens the most recently generated assignment document in Word.")
def open_last_assignment() -> str:
    global last_generated_doc
    candidate = last_generated_doc if last_generated_doc and os.path.exists(last_generated_doc) else None
    if candidate is None:
        desktop = os.path.join(os.path.expanduser("~"), "Desktop")
        if os.path.isdir(desktop):
            docs = [os.path.join(desktop, f) for f in os.listdir(desktop) if f.endswith("_Assignment.docx")]
            if docs:
                candidate = max(docs, key=os.path.getctime)
    if candidate is None:
        return "I could not find any recently generated assignment document, sir."
    try:
        os.startfile(candidate)
        last_generated_doc = candidate
        return f"Opening {os.path.basename(candidate)}, sir."
    except Exception as e:
        return f"Failed to open the document: {e}"


@tool("Asks the local offline Qwen model (Ollama) a question. Use only when the user explicitly asks for the "
      "local or offline model.",
      params={"prompt": "The question or instruction for the local model"})
def ask_local_qwen(prompt: str) -> str:
    try:
        response = requests.post(OLLAMA_URL, json={"model": _ollama_model(), "prompt": prompt, "stream": False},
                                 timeout=60)
        response.raise_for_status()
        return response.json().get("response", "").strip() or "The local model returned nothing, sir."
    except Exception as e:
        return f"Error contacting the local Qwen model (is Ollama running?): {e}"
