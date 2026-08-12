import sys
import os
import requests

# Import components from our project
import commands
import brain

# Mock TTS speaking to print to console only (bypassing SAPI audio output during tests)
def mock_speak(text, wait=False):
    print(f"\033[96m🤖  Jarvis:\033[0m {text}")

brain.speak = mock_speak
brain.wait_for_speech = lambda: None

def run_interactive():
    print("\033[95m=====================================================")
    print("🤖  JARVIS INTERACTIVE TEST (TEXT-ONLY MODE)")
    print("This mode tests the actual model (Ollama) via text.")
    print("=====================================================\033[0m\n")

    # 1. Check if Ollama is running
    try:
        r = requests.get("http://localhost:11434", timeout=3)
        if r.status_code != 200:
            print(f"\033[91m⚠️  Ollama server returned status code {r.status_code}\033[0m")
        else:
            print("\033[92m✅  Ollama server is running.\033[0m")
    except Exception as e:
        print("\033[91m❌  Ollama server is not running at http://localhost:11434.")
        print("Please start Ollama before running this test.\033[0m\n")
        return

    # 2. Check if the specified model is downloaded
    print(f"⏳ Checking if model '{brain.MODEL}' is available...")
    try:
        r = requests.post("http://localhost:11434/api/show", json={"name": brain.MODEL}, timeout=5)
        if r.status_code == 200:
            print(f"\033[92m✅  Model '{brain.MODEL}' is loaded and ready.\033[0m\n")
        else:
            print(f"\033[91m❌  Model '{brain.MODEL}' is not pulled in Ollama.")
            print(f"Please run this command in your terminal first: ollama pull {brain.MODEL}\033[0m\n")
            return
    except Exception as e:
        print(f"\033[93m⚠️  Could not verify model availability: {e}. Attempting to run anyway...\033[0m\n")

    print("Type your query and press Enter. Type 'exit' or 'goodbye' to quit.\n")
    
    while True:
        try:
            user_input = input("\033[93m👂  You: \033[0m").strip()
        except (KeyboardInterrupt, EOFError):
            print("\nGoodbye.")
            break

        if not user_input:
            continue

        if user_input.lower() in ["exit", "quit", "goodbye"]:
            print("Shutting down interactive test.")
            break

        # Check local commands first
        local_response = commands.handle_command(user_input)
        if local_response:
            if local_response == "__CLEAR_MEMORY__":
                print("\033[94m[System] Memory cleared.\033[0m")
            else:
                mock_speak(local_response)
            continue

        # Fallback to Ollama AI model
        print("\033[90mThinking...\033[0m")
        brain.ask_jarvis(user_input)
        print()

if __name__ == '__main__':
    run_interactive()
