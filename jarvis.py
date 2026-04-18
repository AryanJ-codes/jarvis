#!/usr/bin/env python3
"""
J.A.R.V.I.S. — entry point.

Modes:
  python jarvis.py              → interactive CLI
  python jarvis.py --voice      → voice mode (wake word or press-Enter-to-talk)
  python jarvis.py --web        → Iron Man HUD at localhost:7777
  python jarvis.py --briefing   → print daily briefing and exit
  python jarvis.py --clear      → wipe conversation history and exit
  python jarvis.py "message"    → single-shot message
"""

import argparse
import queue
import sys
import threading

from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel
from rich.prompt import Prompt
from rich.status import Status
from rich.theme import Theme

from config import config
from database import clear_history, init_db, load_recent_history

# ── Theme & console ───────────────────────────────────────────────────────────

THEME = Theme({
    "jarvis": "bold cyan",
    "user":   "bold green",
    "tool":   "dim yellow",
    "error":  "bold red",
    "info":   "dim",
    "voice":  "bold magenta",
})
console = Console(theme=THEME)

BANNER = """
     ██╗ █████╗ ██████╗ ██╗   ██╗██╗███████╗
     ██║██╔══██╗██╔══██╗██║   ██║██║██╔════╝
     ██║███████║██████╔╝██║   ██║██║███████╗
██   ██║██╔══██║██╔══██╗╚██╗ ██╔╝██║╚════██║
╚█████╔╝██║  ██║██║  ██║ ╚████╔╝ ██║███████║
 ╚════╝ ╚═╝  ╚═╝╚═╝  ╚═╝  ╚═══╝  ╚═╝╚══════╝
"""

HELP_TEXT = """\
**Commands**
- `/briefing`  — daily morning briefing
- `/tasks`     — list pending tasks
- `/clear`     — wipe conversation history
- `/help`      — show this message
- `/quit`      — exit

**Modes**
- `--voice`    — voice activation (wake word or Enter-to-talk)
- `--web`      — Iron Man HUD at localhost:7777
"""

# ── Scheduler event queue ─────────────────────────────────────────────────────

_scheduler_queue: queue.Queue = queue.Queue()


def _start_scheduler() -> None:
    from tools.scheduler import start_scheduler
    start_scheduler(lambda msg: _scheduler_queue.put(msg))


# ── Shared helpers ────────────────────────────────────────────────────────────

def on_tool_call(name: str, inputs: dict) -> None:
    label = name.replace("_", " ").title()
    detail = ""
    if "title"    in inputs: detail = f": {inputs['title']}"
    elif "query"  in inputs: detail = f": {inputs['query']}"
    elif "app_name" in inputs: detail = f": {inputs['app_name']}"
    elif "to"     in inputs: detail = f" → {inputs['to']}"
    elif "url"    in inputs: detail = f": {inputs['url'][:60]}"
    console.print(f"  [tool]⚙  {label}{detail}[/tool]")


def print_jarvis(text: str) -> None:
    if not text.strip():
        return
    console.print()
    console.print(Panel(Markdown(text), title="[jarvis]J.A.R.V.I.S.[/jarvis]", border_style="cyan"))


def _drain_scheduler(history: list[dict]) -> list[dict]:
    """Process any queued scheduler events inline."""
    from agent import chat
    while not _scheduler_queue.empty():
        try:
            msg = _scheduler_queue.get_nowait()
            console.print(f"\n[jarvis]⏰ Scheduled event:[/jarvis] {msg}")
            reply, history = chat(msg, history, on_tool_call=on_tool_call)
            print_jarvis(reply)
        except queue.Empty:
            break
    return history


# ── CLI session ───────────────────────────────────────────────────────────────

def run_cli(initial_message: str = "") -> None:
    from agent import chat

    _start_scheduler()
    history = load_recent_history(config.HISTORY_LIMIT)

    def send(message: str) -> list[dict]:
        nonlocal history
        reply, history = chat(message, history, on_tool_call=on_tool_call)
        print_jarvis(reply)
        return history

    if initial_message:
        send(initial_message)
        return

    console.print(f"[jarvis]{BANNER}[/jarvis]")
    console.print(Panel(
        f"[info]Online. Awaiting your orders, {config.USER_NAME}.[/info]",
        border_style="dim",
    ))

    while True:
        history = _drain_scheduler(history)

        try:
            user_input = Prompt.ask(f"\n[user]{config.USER_NAME.capitalize()}[/user]").strip()
        except (KeyboardInterrupt, EOFError):
            console.print(f"\n[info]Goodbye, {config.USER_NAME}.[/info]")
            break

        if not user_input:
            continue

        if user_input.lower() in ("/quit", "/exit", "/q"):
            console.print(f"[info]Goodbye, {config.USER_NAME}.[/info]")
            break
        if user_input.lower() == "/help":
            console.print(Markdown(HELP_TEXT))
            continue
        if user_input.lower() == "/clear":
            clear_history()
            history = []
            console.print("[info]Conversation history cleared.[/info]")
            continue
        if user_input.lower() == "/briefing":
            user_input = "Give me my daily briefing."
        if user_input.lower() == "/tasks":
            user_input = "List all my pending tasks."

        try:
            send(user_input)
        except KeyboardInterrupt:
            console.print("\n[info](interrupted)[/info]")
        except Exception as exc:
            console.print(f"[error]Error: {exc}[/error]")


# ── Voice mode ────────────────────────────────────────────────────────────────

def run_voice() -> None:
    """
    Voice mode.
    Overlay (tkinter) runs on the main thread.
    Single persistent audio stream + state machine runs on background threads.
    """
    from agent import chat
    from tools.voice_input import run_voice_loop, wake_word_available
    from tools.voice_output import speak, speak_async
    from tools.overlay import JarvisOverlay, State as OState

    _start_scheduler()
    history = load_recent_history(config.HISTORY_LIMIT)
    _lock = threading.Lock()
    overlay = JarvisOverlay()

    def on_wake() -> None:
        overlay.set_state(OState.LISTENING)
        speak_async(f"Yes, {config.USER_NAME}?")

    def on_command(text: str) -> None:
        nonlocal history
        if not _lock.acquire(blocking=False):
            return
        try:
            console.print(f"[user]{config.USER_NAME.capitalize()}:[/user] {text}")
            overlay.set_state(OState.THINKING)
            reply, history = chat(
                text, history,
                on_tool_call=on_tool_call,
                voice_mode=True,
            )
            print_jarvis(reply)
            overlay.set_state(OState.SPEAKING)
            speak(reply)
        except Exception as exc:
            console.print(f"[error]Voice error: {exc}[/error]")
        finally:
            overlay.set_state(OState.STANDBY)
            _lock.release()

    console.print(f"[jarvis]{BANNER}[/jarvis]")

    stop_event = threading.Event()

    def _voice_thread() -> None:
        if wake_word_available():
            console.print(Panel(
                f'[voice]Voice mode active.[/voice] Say "[bold cyan]Jarvis[/bold cyan]" to activate.\n'
                "[info]Blue overlay visible top-right · Ctrl+C to exit.[/info]",
                border_style="magenta",
            ))
            speak_async(f"J.A.R.V.I.S. online. Say Jarvis to begin, {config.USER_NAME}.")
            try:
                run_voice_loop(
                    on_command=on_command,
                    on_wake=on_wake,
                    stop_event=stop_event,
                )
            except KeyboardInterrupt:
                stop_event.set()
        else:
            console.print(Panel(
                "[voice]Voice mode — press-to-talk.[/voice]\n"
                "Press [bold]Enter[/bold] to speak · [bold]Ctrl+C[/bold] to exit.",
                border_style="magenta",
            ))
            from tools.voice_input import record_until_silence, transcribe
            speak_async(f"J.A.R.V.I.S. online. Press Enter to speak, {config.USER_NAME}.")
            while not stop_event.is_set():
                try:
                    console.print("\n[info]Press Enter to speak...[/info]")
                    input()
                    speak_async("Listening.")
                    overlay.set_state(OState.LISTENING)
                    audio = record_until_silence()
                    text = transcribe(audio)
                    if text:
                        threading.Thread(target=on_command, args=(text,), daemon=True).start()
                    else:
                        console.print("[info](silence detected)[/info]")
                        overlay.set_state(OState.STANDBY)
                except (KeyboardInterrupt, EOFError):
                    stop_event.set()
                    break

        speak_async(f"Goodbye, {config.USER_NAME}.")
        console.print(f"[info]Goodbye, {config.USER_NAME}.[/info]")
        overlay.stop()

    # Voice loop runs in background; overlay owns the main thread
    threading.Thread(target=_voice_thread, daemon=True).start()
    overlay.run()   # blocks until overlay is closed


# ── Web mode ──────────────────────────────────────────────────────────────────

def run_web() -> None:
    from web.app import run_web as start_flask

    _start_scheduler()
    console.print(f"[jarvis]{BANNER}[/jarvis]")
    console.print(Panel(
        f"[jarvis]Iron Man HUD starting...[/jarvis]\n"
        f"[info]Opening[/info] [bold cyan]http://127.0.0.1:{config.WEB_PORT}[/bold cyan]\n"
        "[info]Press Ctrl+C to stop.[/info]",
        border_style="cyan",
    ))

    start_flask(port=config.WEB_PORT, open_browser=True)

    console.print(f"[jarvis]HUD online at http://127.0.0.1:{config.WEB_PORT}[/jarvis]")
    try:
        # Keep main thread alive; drain scheduler events to console too
        history = load_recent_history(config.HISTORY_LIMIT)
        import time
        while True:
            history = _drain_scheduler(history)
            time.sleep(5)
    except KeyboardInterrupt:
        console.print(f"\n[info]Web server stopped. Goodbye, {config.USER_NAME}.[/info]")


# ── Entry point ───────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(description="J.A.R.V.I.S. AI Assistant")
    parser.add_argument("--voice",    action="store_true", help="Voice mode")
    parser.add_argument("--web",      action="store_true", help="Iron Man HUD web interface")
    parser.add_argument("--briefing", action="store_true", help="Print daily briefing and exit")
    parser.add_argument("--clear",    action="store_true", help="Clear conversation history and exit")
    parser.add_argument("message",    nargs="?",           help="Single message (non-interactive)")
    args = parser.parse_args()

    missing = config.validate()
    if missing:
        console.print(
            f"[error]Missing required environment variables: {', '.join(missing)}\n"
            "Copy .env.example → .env and fill in the values.[/error]"
        )
        sys.exit(1)

    init_db()

    if args.clear:
        clear_history()
        console.print("[info]Conversation history cleared.[/info]")
        return

    if args.briefing:
        run_cli("Give me my daily briefing.")
        return

    if args.web:
        run_web()
        return

    if args.voice:
        run_voice()
        return

    if args.message:
        run_cli(args.message)
        return

    run_cli()


if __name__ == "__main__":
    main()
