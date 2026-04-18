#!/usr/bin/env python3
"""
Install or remove Jarvis as a macOS login agent.

Usage:
  python autostart.py install          # start on login in voice mode
  python autostart.py install --web    # start on login with web HUD
  python autostart.py uninstall        # remove autostart
  python autostart.py status           # check if running
"""

import argparse
import os
import subprocess
import sys
from pathlib import Path

LABEL = "com.jarvis.assistant"
PLIST_PATH = Path.home() / "Library" / "LaunchAgents" / f"{LABEL}.plist"

PROJECT_DIR = Path(__file__).resolve().parent
PYTHON = PROJECT_DIR / ".venv" / "bin" / "python"
JARVIS = PROJECT_DIR / "jarvis.py"
LOG_DIR = PROJECT_DIR / "logs"


def _plist(mode_flag: str) -> str:
    LOG_DIR.mkdir(exist_ok=True)
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
  "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>{LABEL}</string>

    <key>ProgramArguments</key>
    <array>
        <string>{PYTHON}</string>
        <string>{JARVIS}</string>
        <string>{mode_flag}</string>
    </array>

    <key>WorkingDirectory</key>
    <string>{PROJECT_DIR}</string>

    <!-- Start on login -->
    <key>RunAtLoad</key>
    <true/>

    <!-- Restart if it crashes -->
    <key>KeepAlive</key>
    <true/>

    <!-- Wait 5 s before restarting after a crash -->
    <key>ThrottleInterval</key>
    <integer>5</integer>

    <key>StandardOutPath</key>
    <string>{LOG_DIR}/jarvis.log</string>

    <key>StandardErrorPath</key>
    <string>{LOG_DIR}/jarvis_error.log</string>

    <!-- Inherit the user's PATH so apps can be found -->
    <key>EnvironmentVariables</key>
    <dict>
        <key>PATH</key>
        <string>/usr/local/bin:/usr/bin:/bin:/opt/homebrew/bin</string>
        <key>HOME</key>
        <string>{Path.home()}</string>
    </dict>
</dict>
</plist>
"""


def install(mode_flag: str = "--voice") -> None:
    if not PYTHON.exists():
        print(f"Error: virtualenv not found at {PYTHON}")
        print("Run: python -m venv .venv && source .venv/bin/activate && pip install -r requirements.txt")
        sys.exit(1)

    PLIST_PATH.parent.mkdir(parents=True, exist_ok=True)
    PLIST_PATH.write_text(_plist(mode_flag))
    print(f"Wrote: {PLIST_PATH}")

    # Unload first in case it was already loaded
    subprocess.run(["launchctl", "unload", str(PLIST_PATH)],
                   capture_output=True)

    result = subprocess.run(["launchctl", "load", str(PLIST_PATH)],
                            capture_output=True, text=True)
    if result.returncode != 0:
        print(f"Warning: launchctl load returned {result.returncode}: {result.stderr.strip()}")
    else:
        mode_label = "Web HUD (localhost:7777)" if mode_flag == "--web" else "Voice mode"
        print(f"\n✓ Jarvis will now start automatically on login.")
        print(f"  Mode    : {mode_label}")
        print(f"  Logs    : {LOG_DIR}/jarvis.log")
        print(f"\nTo stop it now:   python autostart.py stop")
        print(f"To remove:        python autostart.py uninstall")


def uninstall() -> None:
    if not PLIST_PATH.exists():
        print("Jarvis autostart is not installed.")
        return
    subprocess.run(["launchctl", "unload", str(PLIST_PATH)], capture_output=True)
    PLIST_PATH.unlink()
    print(f"✓ Removed {PLIST_PATH}")
    print("Jarvis will no longer start on login.")


def status() -> None:
    result = subprocess.run(
        ["launchctl", "list", LABEL],
        capture_output=True, text=True,
    )
    if result.returncode == 0:
        print(f"✓ Jarvis agent is loaded:\n{result.stdout}")
    else:
        print("Jarvis agent is NOT loaded (not installed or stopped).")

    if PLIST_PATH.exists():
        print(f"  Plist: {PLIST_PATH}")
    log = LOG_DIR / "jarvis.log"
    if log.exists():
        print(f"\n── Last 10 log lines ──────────────────────────────────")
        lines = log.read_text().splitlines()
        for line in lines[-10:]:
            print(f"  {line}")


def stop() -> None:
    result = subprocess.run(
        ["launchctl", "stop", LABEL],
        capture_output=True, text=True,
    )
    if result.returncode == 0:
        print("✓ Jarvis stopped. It will restart automatically next login.")
        print("  To prevent restart: python autostart.py uninstall")
    else:
        print(f"Could not stop: {result.stderr.strip()}")


def start() -> None:
    if not PLIST_PATH.exists():
        print("Not installed. Run: python autostart.py install")
        return
    subprocess.run(["launchctl", "start", LABEL])
    print("✓ Jarvis started.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Jarvis autostart manager")
    sub = parser.add_subparsers(dest="cmd")

    p_install = sub.add_parser("install", help="Install autostart")
    p_install.add_argument("--web", action="store_true",
                           help="Start in web HUD mode instead of voice mode")

    sub.add_parser("uninstall", help="Remove autostart")
    sub.add_parser("status",    help="Check if running")
    sub.add_parser("stop",      help="Stop current instance")
    sub.add_parser("start",     help="Start now")

    args = parser.parse_args()

    if args.cmd == "install":
        install("--web" if args.web else "--voice")
    elif args.cmd == "uninstall":
        uninstall()
    elif args.cmd == "status":
        status()
    elif args.cmd == "stop":
        stop()
    elif args.cmd == "start":
        start()
    else:
        parser.print_help()
