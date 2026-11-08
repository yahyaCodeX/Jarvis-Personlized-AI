"""File tools: read / write / find (sandboxed to JARVIS_ALLOWED_DIRS), folders."""

from __future__ import annotations

import logging
import os
import shutil

from safety import allowed_dirs, check_path
from .registry import tool

log = logging.getLogger("jarvis.tools")

MAX_READ_BYTES = 200 * 1024  # don't stream huge files into the voice model


def _summarize_write(args: dict) -> str | None:
    ok, resolved = check_path(args.get("filepath", ""))
    if not ok:
        return None  # blocked path: the tool itself returns the refusal, no need to ask
    new_lines = (args.get("new_content") or "").count("\n") + 1
    if os.path.isfile(resolved):
        try:
            with open(resolved, "r", encoding="utf-8", errors="replace") as f:
                old_lines = f.read().count("\n") + 1
        except Exception:
            old_lines = "?"
        return (f"overwrite {os.path.basename(resolved)} ({old_lines} lines now, {new_lines} lines after) "
                f"in {os.path.dirname(resolved)}")
    return f"create a new file {resolved} with {new_lines} lines"


@tool("Reads the full text or source code of a local file. Use this to review code, configs or logs before "
      "changing them. Only files inside the user's allowed folders can be read.",
      params={"filepath": "Absolute or relative path, e.g. 'D:/Development/My-Personal-AI/jarvis_server.py'"})
def read_local_file(filepath: str) -> str:
    """
    Reads the full text/code of a local file on the user's machine.
    Returns the raw content prefixed with the resolved absolute path.
    Files over MAX_READ_BYTES are refused (too long to be useful in a voice session).
    """
    ok, resolved = check_path(filepath)
    if not ok:
        log.warning(f"[FILE I/O BLOCKED] read {filepath}: {resolved}")
        return resolved
    filepath = resolved
    if os.path.isfile(filepath) and os.path.getsize(filepath) > MAX_READ_BYTES:
        return f"File is too large to read aloud ({os.path.getsize(filepath) // 1024} KB, limit {MAX_READ_BYTES // 1024} KB)."
    log.info(f"[FILE I/O] Reading: {filepath}")
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            content = f.read()
        lines = content.count('\n') + 1
        log.info(f"[FILE I/O] Read {lines} lines from {filepath}.")
        return f"--- FILE: {filepath} ({lines} lines) ---\n{content}"
    except UnicodeDecodeError:
        # Fallback for files with mixed encodings (e.g. legacy Windows source)
        try:
            with open(filepath, 'r', encoding='latin-1') as f:
                content = f.read()
            return f"--- FILE (latin-1): {filepath} ---\n{content}"
        except Exception as enc_err:
            return f"Failed to decode file (tried utf-8 and latin-1): {enc_err}"
    except FileNotFoundError:
        return f"File not found: {filepath}"
    except Exception as e:
        return f"Failed to read file: {e}"



@tool("Overwrites (or creates) a local file with completely new content, keeping a .bak of the old version. "
      "ALWAYS write the ENTIRE file, never partial snippets. The user must confirm out loud first.",
      params={"filepath": "Absolute or relative path to the file to write",
              "new_content": "The complete, fully corrected file content"},
      confirm=_summarize_write)
def write_local_file(filepath: str, new_content: str) -> str:
    """
    Overwrites a local file with completely new content.
    Creates parent directories if they do not exist.
    Always writes the ENTIRE file — never partial snippets.
    """
    ok, resolved = check_path(filepath)
    if not ok:
        log.warning(f"[FILE I/O BLOCKED] write {filepath}: {resolved}")
        return resolved
    filepath = resolved
    log.info(f"[FILE I/O] Writing: {filepath}")
    try:
        os.makedirs(os.path.dirname(filepath), exist_ok=True)
        # Keep the previous version so any AI edit can be undone
        if os.path.isfile(filepath):
            shutil.copy2(filepath, filepath + ".bak")
        # Atomic-safe write: write to a temp file first, then replace
        tmp_path = filepath + ".jarvis_tmp"
        with open(tmp_path, 'w', encoding='utf-8') as f:
            f.write(new_content)
        os.replace(tmp_path, filepath)
        lines = new_content.count('\n') + 1
        log.info(f"[FILE I/O] Successfully wrote {lines} lines to {filepath}.")
        backup_note = f" Previous version saved as {os.path.basename(filepath)}.bak." if os.path.isfile(filepath + ".bak") else ""
        return f"Successfully updated and saved {lines} lines of code to {filepath}.{backup_note}"
    except Exception as e:
        # Clean up temp file if it exists
        try:
            if os.path.exists(filepath + ".jarvis_tmp"):
                os.remove(filepath + ".jarvis_tmp")
        except Exception:
            pass
        return f"Failed to write to file: {e}"



@tool("Searches the user's allowed folders for a file by name or partial name. ALWAYS call this before "
      "read_local_file or write_local_file if you don't know the exact path. Never guess file paths.",
      params={"filename": "File name or part of it, e.g. 'jarvis_server.py' or 'MainActivity'",
              "root_dir": "Optional folder to search in, e.g. 'D:/Development'"})
def find_local_file(filename: str, root_dir: str = "") -> str:
    matches = []
    target = filename.lower()

    # Only search inside folders Jarvis is allowed to access
    if root_dir:
        ok, resolved = check_path(root_dir)
        if not ok:
            return resolved
        search_dirs = [resolved]
    else:
        search_dirs = [os.getcwd()] + allowed_dirs()

    skip_dirs = {".git", "node_modules", "__pycache__", ".venv", "venv", "build", ".dart_tool"}
    try:
        for search_dir in search_dirs:
            for root, dirs, files in os.walk(search_dir):
                dirs[:] = [d for d in dirs if d not in skip_dirs]
                for file in files:
                    full = os.path.abspath(os.path.join(root, file))
                    if target in file.lower() and check_path(full)[0]:
                        matches.append(full)
                if len(matches) >= 25:
                    break
            
            # If found in the first directory (project), stop searching to save time
            if matches:
                break
                    
        if not matches:
            return f"Could not find '{filename}' anywhere in {search_dirs}."
            
        result_str = f"Found {len(matches)} matching files:\n"
        for match in set(matches): # Use set to remove duplicates
            result_str += f"- {match}\n"
        return result_str
    except Exception as e:
        return f"Error searching for file: {e}"


_COMMON_FOLDERS = {
    "desktop": "Desktop", "downloads": "Downloads", "documents": "Documents",
    "pictures": "Pictures", "videos": "Videos", "music": "Music",
}


def _resolve_location(location: str) -> str:
    """'Desktop' / 'Downloads' / 'Projects' / absolute path → absolute folder path."""
    home = os.path.expanduser("~")
    loc = (location or "Desktop").strip().strip("\"'")
    key = loc.lower().removesuffix(" folder")
    if key in _COMMON_FOLDERS:
        return os.path.join(home, _COMMON_FOLDERS[key])
    if key in ("projects", "development", "dev"):
        return r"D:\Development" if os.path.exists(r"D:\Development") else os.path.join(home, "Projects")
    if len(loc) == 2 and loc[1] == ":":          # "d:" → "D:\"
        return loc.upper() + "\\"
    return loc if os.path.isabs(loc) else os.path.join(home, loc)


@tool("Creates a folder on the Desktop, Downloads, Documents, Projects (D:/Development) or another allowed path.",
      params={"folder_name": "Name of the new folder",
              "location": "'Desktop', 'Downloads', 'Documents', 'Projects', or an absolute path (default Desktop)"})
def create_folder(folder_name: str, location: str = "Desktop") -> str:
    name = (folder_name or "").strip()
    if not name or any(c in name for c in '<>:"|?*') or ".." in name.replace("\\", "/").split("/"):
        return "Please give me a valid folder name, sir."
    ok, target = check_path(os.path.join(_resolve_location(location), name))
    if not ok:
        return target
    try:
        os.makedirs(target, exist_ok=True)
        return f"Folder '{name}' created at {target}, sir."
    except Exception as e:
        return f"Failed to create folder '{name}': {e}"


@tool("Opens a folder in Windows File Explorer (reuses an open Explorer window). Works for Desktop, Downloads, "
      "Documents, Pictures, Projects, a drive like 'D:', or any absolute folder path.",
      params={"target_path": "Folder name like 'Downloads', or an absolute path"})
def open_local_folder(target_path: str) -> str:
    folder = os.path.abspath(_resolve_location(target_path))
    if not os.path.isdir(folder):
        return f"I couldn't find a folder at {folder}, sir."
    try:
        import win32com.client
        shell = win32com.client.Dispatch("Shell.Application")
        for window in shell.Windows():
            try:
                if window.Name in ("File Explorer", "Windows Explorer"):
                    window.Navigate(folder)
                    return f"Opened {folder} in File Explorer, sir."
            except Exception:
                continue
        os.startfile(folder)   # isdir() checked above, so this only ever opens a folder
        return f"Opened {folder} in File Explorer, sir."
    except Exception as e:
        return f"Failed to open folder: {e}"
