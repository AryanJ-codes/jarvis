# J.A.R.V.I.S.
### Just A Rather Very Intelligent System

A fully local, Iron Man–inspired personal AI assistant powered by Claude. Responds to your voice, manages tasks, searches the web, controls your computer, sends emails, and delivers a daily briefing — all orchestrated through Claude's tool-use API.

---

## Demo features

| Feature | Description |
|---|---|
| 🎙 **Wake word** | Say *"Jarvis"* — detected locally via Whisper, no API key needed |
| 🔊 **Voice replies** | Responds in a British voice using macOS `say -v Daniel` |
| 🖥 **Floating overlay** | Iron Man–style HUD in the top-right corner shows STANDBY / LISTENING / THINKING / SPEAKING |
| 🌐 **Web HUD** | Full Iron Man dashboard at `localhost:7777` — chat, knowledge base, task list |
| ✅ **Task manager** | Create, update, complete, and delete tasks stored in SQLite |
| 📧 **Email** | Send emails (with attachments) via Gmail SMTP |
| 🔍 **Web search** | Live search via Brave Search API |
| 🧠 **Knowledge base** | Add notes, import Claude conversations, upload PDFs — searched automatically |
| 🖥 **App control** | Open and close macOS applications by name |
| ☀️ **Daily briefing** | Scheduled morning summary of tasks and priorities |
| 🚀 **Autostart** | Runs on login like Siri via macOS LaunchAgent |

---

## Architecture & pipeline

```
┌─────────────────────────────────────────────────────────────────┐
│                         USER INPUT                              │
│              Voice ("Jarvis") / CLI / Web HUD                   │
└────────────────────────────┬────────────────────────────────────┘
                             │
              ┌──────────────▼──────────────┐
              │      VOICE PIPELINE         │
              │  sounddevice InputStream    │  (persistent — no mic blink)
              │  → Whisper wake word scan   │
              │  → Wake word detected       │
              │  → record_until_silence()   │
              │  → Whisper STT transcript   │
              └──────────────┬──────────────┘
                             │  text
┌────────────────────────────▼────────────────────────────────────┐
│                     AGENT LOOP  (agent.py)                      │
│                                                                 │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │  Claude claude-opus-4-6  ←  system prompt (JARVIS)      │   │
│  │         +  conversation history (SQLite, last 40 msgs)  │   │
│  │         +  21 tool definitions                          │   │
│  └──────────────────────┬──────────────────────────────────┘   │
│                         │ stop_reason == "tool_use"             │
│  ┌──────────────────────▼──────────────────────────────────┐   │
│  │              TOOL DISPATCHER                            │   │
│  │                                                         │   │
│  │  Tasks        ──► tools/tasks.py    ──► SQLite          │   │
│  │  Email        ──► tools/email.py    ──► Gmail SMTP      │   │
│  │  Web search   ──► tools/search.py   ──► Brave API       │   │
│  │  Browser      ──► tools/browser.py  ──► Playwright      │   │
│  │  Apps         ──► tools/apps.py     ──► subprocess      │   │
│  │  Knowledge    ──► tools/kb.py       ──► SQLite FTS5     │   │
│  │  Briefing     ──► tools/briefing.py ──► DB query        │   │
│  └──────────────────────┬──────────────────────────────────┘   │
│                         │ tool results fed back to Claude       │
│                         └── loops until stop_reason=end_turn   │
└────────────────────────────┬────────────────────────────────────┘
                             │  final text reply
              ┌──────────────▼──────────────┐
              │      OUTPUT PIPELINE        │
              │  Rich terminal panel        │
              │  + macOS say -v Daniel TTS  │
              │  + Overlay → SPEAKING state │
              └─────────────────────────────┘
```

### Data flow summary

1. **Wake word** — a single persistent `sounddevice.InputStream` buffers audio into 2.5 s chunks. Whisper scans each chunk for "Jarvis". No repeated open/close → no blinking mic indicator.
2. **STT** — on activation, `record_until_silence()` captures the user's command; Whisper transcribes it.
3. **Agent loop** — the transcript is sent to Claude with the full tool catalogue. Claude calls tools as needed (multiple rounds), receives results, and produces a final reply.
4. **TTS** — the reply is spoken aloud via `say -v Daniel` and displayed in the terminal and overlay.
5. **Scheduler** — a background thread fires daily briefings and overdue task reminders independently of the voice loop.

---

## Project structure

```
jarvis/
├── jarvis.py               # Entry point — CLI / voice / web modes
├── agent.py                # Claude tool-use orchestration loop
├── config.py               # .env loader + typed settings
├── database.py             # SQLite: tasks, conversation history, knowledge base
├── autostart.py            # macOS LaunchAgent installer
│
├── tools/
│   ├── tasks.py            # Task CRUD (SQLite)
│   ├── email_tool.py       # Gmail SMTP (plain + attachments)
│   ├── search.py           # Brave Search API
│   ├── browser.py          # Chrome automation (Playwright)
│   ├── apps.py             # Open / close macOS applications
│   ├── briefing.py         # Daily briefing data gatherer
│   ├── knowledge_base.py   # SQLite FTS5 KB + Claude chat importer
│   ├── voice_input.py      # Whisper wake word + STT
│   ├── voice_output.py     # macOS say TTS
│   ├── scheduler.py        # Background cron (briefings, reminders)
│   └── overlay.py          # Floating tkinter HUD overlay
│
└── web/
    ├── app.py              # Flask REST API
    └── templates/
        └── index.html      # Iron Man HUD (vanilla JS, no framework)
```

---

## Setup

### 1. Clone & install

```bash
git clone https://github.com/AryanJ-codes/jarvis.git
cd jarvis
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
playwright install chromium
```

### 2. Configure environment

```bash
cp .env.example .env
```

| Variable | Required | Where to get it |
|---|---|---|
| `ANTHROPIC_API_KEY` | ✅ | [console.anthropic.com](https://console.anthropic.com) |
| `BRAVE_API_KEY` | Optional | [api.search.brave.com](https://api.search.brave.com) — free tier |
| `GMAIL_ADDRESS` | Optional | Your Gmail address |
| `GMAIL_APP_PASSWORD` | Optional | [myaccount.google.com/apppasswords](https://myaccount.google.com/apppasswords) |
| `USER_NAME` | Optional | How Jarvis addresses you (default: `sir`) |
| `MORNING_BRIEFING_TIME` | Optional | Daily briefing time (default: `08:00`) |
| `WEB_PORT` | Optional | Web HUD port (default: `7777`) |

### 3. Run

```bash
# Interactive CLI
python jarvis.py

# Voice mode — say "Jarvis" to activate
python jarvis.py --voice

# Iron Man web HUD at localhost:7777
python jarvis.py --web

# Start on login (like Siri)
python autostart.py install
```

---

## Tech stack

| Layer | Technology |
|---|---|
| AI orchestration | Anthropic Claude (`claude-opus-4-6`) via tool use |
| Wake word & STT | `faster-whisper` (local, no API key) |
| TTS | macOS `say -v Daniel` (British voice) |
| Task & KB storage | SQLite + FTS5 (full-text search) |
| Web interface | Flask + vanilla JS |
| Browser automation | Playwright (Chromium) |
| Overlay | tkinter (frameless, always-on-top) |
| Autostart | macOS LaunchAgent (`launchd`) |

---

## Usage examples

```
# Voice
"Jarvis, add a high priority task to review the contract by Friday"
"Jarvis, what's on my plate today?"
"Jarvis, search for the latest news on AI"
"Jarvis, open Spotify"
"Jarvis, send Alice an email about the meeting"

# CLI / Web HUD
/briefing     → daily morning summary
/tasks        → list pending tasks
/clear        → reset conversation
/help         → show all commands
```

---

## License

MIT
