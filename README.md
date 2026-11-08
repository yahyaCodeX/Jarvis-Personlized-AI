<div align="center">
  <img src="https://img.icons8.com/color/150/000000/iron-man.png" alt="Jarvis AI Logo" width="120" height="120"/>
  
  # 🤖 Jarvis Personal AI
  
  **An advanced, personalized AI assistant powered by Gemini Live API with Windows automation, voice biometrics, and more.**
  
  ![Python](https://img.shields.io/badge/Python-3.10+-blue?style=for-the-badge&logo=python&logoColor=white)
  ![Gemini API](https://img.shields.io/badge/Gemini_Live_API-Powering_Brain-orange?style=for-the-badge&logo=google&logoColor=white)
  ![Windows](https://img.shields.io/badge/Platform-Windows-blue?style=for-the-badge&logo=windows&logoColor=white)
</div>

---

## 🌟 Features

- 🎙️ **Voice Biometrics & Speech Recognition:** Uses SpeechBrain for speaker recognition and pywin32 for reliable Windows SAPI text-to-speech.
- 🧠 **Gemini Powered:** Integrates `google-genai` for advanced, context-aware conversational capabilities.
- ⚙️ **System Automation:** Control volume, manage processes, take screenshots, and read clipboard via Python utilities.
- 🌐 **Browser Automation:** Playwright drives an assistive browser (navigation, checkout, MUET attendance login).
- 🗣️ **Natural conversation:** talk over Jarvis to interrupt it (barge-in), see the live transcript in the HUD.
- 📝 **Academic Tools:** Generates Word documents automatically for academic assignments using `python-docx`.

## 🔐 Security Model

Jarvis can see your screen, browse the web and edit files, so text on a web page could try to give it instructions (prompt injection). These protections are on by default:

- **Voice biometrics:** a session only starts after your voice matches `auth/owner_voice.wav` (run `python enroll_voice.py` first). Errors deny access.
- **Spoken confirmation:** writing files, force-closing apps and filling checkout forms need you to say **"confirm"**. The server checks your real microphone transcript, so the AI can't approve its own actions.
- **Folder sandbox:** file tools only work inside `JARVIS_ALLOWED_DIRS`. `.env`, `profile.json`, `.git` and your voiceprint are always blocked. Every overwrite keeps a `.bak` copy.
- **No shell injection:** apps are launched and closed with validated names, without passing text through `cmd.exe`.
- **Local-only socket:** websites you visit can't connect to `ws://localhost:8765`.

Settings live in `.env` (see `.env.example`).

## 🛠️ Tech Stack

- **Core:** Python, Requests
- **Audio & Speech:** SpeechRecognition, pyaudio, SpeechBrain, Torchaudio
- **AI & Logic:** google-genai
- **Automation:** Playwright, psutil, pillow, pyautogui, pywin32, python-docx

## 🚀 Installation & Setup

1. **Clone the repository**
   ```bash
   git clone https://github.com/yahyaCodeX/Jarvis-Personlized-AI.git
   cd Jarvis-Personlized-AI
   ```

2. **Install dependencies**
   ```bash
   pip install -r requirements.txt
   playwright install chromium
   ```

3. **Configure secrets and your profile** (both files are gitignored, never commit them)
   ```bash
   copy .env.example .env                    # then fill in GEMINI_API_KEY, MIS_CNIC, MIS_PASSWORD
   copy profile.example.json profile.json    # then fill in your name, phone, addresses, city, MIS class
   ```

4. **Enroll your voice** (once)
   ```bash
   python enroll_voice.py
   ```

5. **Build the HUD** (once, needs Flutter)
   ```bash
   cd jarvis_ui && flutter build windows
   ```

6. **Run Jarvis:** double-click `start_jarvis.bat`. It opens the HUD and starts the server. Press **INITIALIZE DUPLEX** in the HUD and speak to verify your voice.

7. **Run the tests**
   ```bash
   pytest
   ```

## 📂 Project Structure

| Path | What it does |
|---|---|
| `jarvis_server.py` | Main entry point: Gemini Live voice session, tool dispatch, WebSocket bridge to the HUD |
| `tools/` | Everything Jarvis can do, one module per area (see below) |
| `audio_gate.py` | Barge-in: lets your voice through while Jarvis is talking, blocks its echo |
| `safety.py` | Folder sandbox and spoken-confirmation gate |
| `config.py` | Loads `.env`, `profile.json`, model names and logging |
| `personality.txt` | Jarvis's persona and speaking style (edit freely) |
| `auth/voice_auth.py`, `enroll_voice.py` | Voice biometrics |
| `jarvis_ui/` | Flutter HUD: status, telemetry, live transcript, Confirm/Cancel |
| `scripts/` | Mic and audio diagnostics (`list_mic_devices.py`, `mic_levels.py`, `live_audio_check.py`) |
| `logs/jarvis.log` | Rotating log (set `JARVIS_LOG_LEVEL=DEBUG` for detail) |

## 🧰 Tools

Each module in `tools/` groups related abilities:

| Module | Tools |
|---|---|
| `info.py` | time & date, weather |
| `web.py` | open websites, Google, Maps, YouTube, browser tabs, scrolling |
| `browser.py` | Jarvis's own Playwright browser: assistive navigation, checkout form filling |
| `files.py` | read / write / find files (sandboxed), create and open folders |
| `apps.py` | open & close apps, volume, brightness, media keys, lock, screenshot |
| `vision.py` | screen reader, Ghost Coder debugger |
| `academic.py` | MIS attendance, assignment generator, local Qwen |
| `memory.py` | long-term memory |

**Adding a tool** takes one function. Its Gemini declaration is generated from the signature:

```python
from .registry import tool

@tool("Tells a joke about the topic.", params={"topic": "What the joke is about"})
def tell_joke(topic: str = "computers") -> str:
    return f"Why did the {topic} go to therapy? Too many unresolved issues."
```

Add `confirm=lambda args: "summary of what will happen"` for anything risky, and Jarvis will ask you to say "confirm" first.

## 🗣️ Interrupting Jarvis (barge-in)

Just start talking while Jarvis speaks and it stops to listen. With laptop speakers, the mic also hears Jarvis, so your voice must be clearly louder than that echo. If Jarvis cuts itself off, raise `JARVIS_BARGE_IN_RATIO` in `.env` (or set `JARVIS_BARGE_IN=0`). Headphones work best. Barge-in pauses while Jarvis waits for you to say "confirm", so its own voice can never approve an action.

## 🤝 Contributing

Contributions, issues, and feature requests are welcome!

---
<div align="center">
  <i>Built with ❤️ for personalized automation and AI assistance.</i>
</div>
