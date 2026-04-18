"""Cross-platform application launcher and closer."""

import platform
import subprocess
import shutil

_SYSTEM = platform.system()  # "Darwin", "Windows", "Linux"


def open_application(app_name: str) -> dict:
    try:
        if _SYSTEM == "Darwin":
            result = subprocess.run(
                ["open", "-a", app_name], capture_output=True, text=True
            )
            if result.returncode != 0:
                # Fallback: try as a command name
                result = subprocess.run(
                    ["open", app_name], capture_output=True, text=True
                )
        elif _SYSTEM == "Windows":
            result = subprocess.run(
                ["start", "", app_name], shell=True, capture_output=True, text=True
            )
        else:  # Linux and others
            cmd = shutil.which(app_name.lower().replace(" ", "-")) or app_name.lower()
            result = subprocess.Popen(
                [cmd], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
            )
            return {"success": True, "message": f"Launched {app_name}"}

        if result.returncode == 0:
            return {"success": True, "message": f"Opened {app_name}"}
        return {"success": False, "error": result.stderr.strip() or f"Could not open {app_name}"}
    except FileNotFoundError:
        return {"success": False, "error": f"Application not found: {app_name}"}
    except Exception as exc:
        return {"success": False, "error": str(exc)}


def close_application(app_name: str) -> dict:
    try:
        if _SYSTEM == "Darwin":
            # Try AppleScript quit first (graceful)
            script = f'tell application "{app_name}" to quit'
            result = subprocess.run(
                ["osascript", "-e", script], capture_output=True, text=True
            )
            if result.returncode != 0:
                # Fallback to pkill
                subprocess.run(["pkill", "-f", app_name], capture_output=True)
        elif _SYSTEM == "Windows":
            exe = app_name if app_name.lower().endswith(".exe") else app_name + ".exe"
            result = subprocess.run(
                ["taskkill", "/f", "/im", exe], capture_output=True, text=True
            )
            if result.returncode != 0:
                return {"success": False, "error": result.stderr.strip()}
        else:
            subprocess.run(["pkill", "-f", app_name], capture_output=True)

        return {"success": True, "message": f"Closed {app_name}"}
    except Exception as exc:
        return {"success": False, "error": str(exc)}
