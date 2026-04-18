"""
Text-to-speech output.

Primary: macOS built-in `say -v Daniel` (British male, no API key needed).
Falls back to pyttsx3 on other platforms.
"""

from __future__ import annotations

import platform
import re
import subprocess
import threading

_SYSTEM = platform.system()


def _strip_markdown(text: str) -> str:
    """Remove markdown so TTS reads naturally."""
    text = re.sub(r"\*\*(.+?)\*\*", r"\1", text)       # bold
    text = re.sub(r"\*(.+?)\*", r"\1", text)             # italic
    text = re.sub(r"__(.+?)__", r"\1", text)             # bold alt
    text = re.sub(r"`{1,3}[^`]*`{1,3}", "", text)        # code
    text = re.sub(r"^#{1,6}\s+", "", text, flags=re.M)   # headers
    text = re.sub(r"^\s*[-*+]\s+", "", text, flags=re.M) # bullets
    text = re.sub(r"https?://\S+", "a link", text)        # URLs
    text = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", text)  # markdown links
    text = re.sub(r"\n{2,}", ". ", text)
    text = re.sub(r"\n", " ", text)
    return text.strip()


def speak(text: str) -> None:
    """Speak text synchronously — blocks until done."""
    clean = _strip_markdown(text)
    if not clean:
        return

    if _SYSTEM == "Darwin":
        _say_macos(clean)
    else:
        _say_pyttsx3(clean)


def speak_async(text: str) -> None:
    """Speak text in a background thread — returns immediately."""
    t = threading.Thread(target=speak, args=(text,), daemon=True)
    t.start()


def _say_macos(text: str) -> None:
    """Use macOS `say` with the Daniel (British) voice."""
    try:
        subprocess.run(["say", "-v", "Daniel", text], check=False)
    except FileNotFoundError:
        # `say` not available (unlikely on macOS but handle gracefully)
        _say_pyttsx3(text)


def _say_pyttsx3(text: str) -> None:
    try:
        import pyttsx3  # type: ignore
        engine = pyttsx3.init()
        engine.setProperty("rate", 170)
        # Prefer a male voice if available
        voices = engine.getProperty("voices")
        for v in voices:
            if "male" in v.name.lower() or "david" in v.name.lower():
                engine.setProperty("voice", v.id)
                break
        engine.say(text)
        engine.runAndWait()
    except Exception:
        print(f"[JARVIS] {text}")
