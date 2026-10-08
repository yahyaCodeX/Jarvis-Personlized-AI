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

3. **Configure Environment Variables**
   Create a `.env` file in the root directory and add your required API keys (e.g., Gemini API key).

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
