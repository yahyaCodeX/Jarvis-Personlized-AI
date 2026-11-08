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
- 🌐 **Browser Automation:** Selenium integration for automatic web tasks (e.g., MUET attendance login).
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
- **Automation:** pycaw, psutil, pillow, pyautogui, pyperclip, selenium, python-docx

## 🚀 Installation & Setup

1. **Clone the repository**
   ```bash
   git clone https://github.com/yahyaCodeX/Jarvis-Personlized-AI.git
   cd Jarvis-Personlized-AI
   ```

2. **Install dependencies**
   ```bash
   pip install -r requirements.txt
   ```

3. **Configure secrets and your profile** (both files are gitignored, never commit them)
   ```bash
   copy .env.example .env                    # then fill in GEMINI_API_KEY, MIS_CNIC, MIS_PASSWORD
   copy profile.example.json profile.json    # then fill in your name, phone, addresses, city
   ```

4. **Run Jarvis**
   ```bash
   start_jarvis.bat
   ```
   *or*
   ```bash
   python live_jarvis.py
   ```

## 📂 Project Structure

- `jarvis_ui/` - User interface components
- `commands.py` / `actions.py` - Core logic for system and automation commands.
- `brain.py` / `jarvis_server.py` - AI integration and server endpoints.
- `enroll_voice.py` - Voice biometric enrollment.
- `live_jarvis.py` - Main entry point for the assistant.

## 🤝 Contributing

Contributions, issues, and feature requests are welcome!

---
<div align="center">
  <i>Built with ❤️ for personalized automation and AI assistance.</i>
</div>
