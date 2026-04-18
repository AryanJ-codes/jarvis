"""
Claude-powered JARVIS agent with tool use.

Loop:
  1. Append user message → call Claude
  2. If stop_reason == "tool_use" → dispatch tools → loop
  3. If stop_reason == "end_turn" → return final text
"""

import json
from datetime import datetime

import anthropic

from config import config
from database import save_message
from tools.apps import close_application, open_application
from tools.briefing import get_daily_briefing
from tools.browser import (
    browser_click,
    browser_close,
    browser_current_url,
    browser_fill,
    browser_get_text,
    browser_navigate,
    browser_screenshot,
)
from tools.email_tool import send_email, send_email_with_attachment
from tools.knowledge_base import add_knowledge, search_knowledge
from tools.search import search_web
from tools.tasks import add_task, delete_task, list_tasks, update_task

# ── Tool definitions ──────────────────────────────────────────────────────────

TOOLS: list[dict] = [
    {
        "name": "add_task",
        "description": "Add a new task to the task manager.",
        "input_schema": {
            "type": "object",
            "properties": {
                "title": {"type": "string", "description": "Short task title"},
                "description": {"type": "string"},
                "priority": {"type": "string", "enum": ["low", "medium", "high"]},
                "due_date": {"type": "string", "description": "YYYY-MM-DD"},
            },
            "required": ["title"],
        },
    },
    {
        "name": "list_tasks",
        "description": "List tasks with optional filters.",
        "input_schema": {
            "type": "object",
            "properties": {
                "status": {"type": "string", "enum": ["pending", "in_progress", "completed", "cancelled", "all"]},
                "priority": {"type": "string", "enum": ["low", "medium", "high", "all"]},
                "due_today": {"type": "boolean"},
            },
        },
    },
    {
        "name": "update_task",
        "description": "Update an existing task.",
        "input_schema": {
            "type": "object",
            "properties": {
                "task_id": {"type": "integer"},
                "title": {"type": "string"},
                "description": {"type": "string"},
                "priority": {"type": "string", "enum": ["low", "medium", "high"]},
                "status": {"type": "string", "enum": ["pending", "in_progress", "completed", "cancelled"]},
                "due_date": {"type": "string"},
            },
            "required": ["task_id"],
        },
    },
    {
        "name": "delete_task",
        "description": "Permanently delete a task by ID.",
        "input_schema": {
            "type": "object",
            "properties": {"task_id": {"type": "integer"}},
            "required": ["task_id"],
        },
    },
    {
        "name": "send_email",
        "description": "Send an email via Gmail.",
        "input_schema": {
            "type": "object",
            "properties": {
                "to": {"type": "string"},
                "subject": {"type": "string"},
                "body": {"type": "string"},
                "cc": {"type": "string"},
                "html": {"type": "boolean"},
            },
            "required": ["to", "subject", "body"],
        },
    },
    {
        "name": "send_email_with_attachment",
        "description": "Send an email with a local file attached.",
        "input_schema": {
            "type": "object",
            "properties": {
                "to": {"type": "string"},
                "subject": {"type": "string"},
                "body": {"type": "string"},
                "attachment_path": {"type": "string"},
                "cc": {"type": "string"},
            },
            "required": ["to", "subject", "body", "attachment_path"],
        },
    },
    {
        "name": "search_web",
        "description": "Search the web with Brave Search for current information.",
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {"type": "string"},
                "count": {"type": "integer", "description": "Results to return (1-10)"},
            },
            "required": ["query"],
        },
    },
    {
        "name": "open_application",
        "description": "Open/launch an application on the computer.",
        "input_schema": {
            "type": "object",
            "properties": {"app_name": {"type": "string"}},
            "required": ["app_name"],
        },
    },
    {
        "name": "close_application",
        "description": "Quit/close a running application.",
        "input_schema": {
            "type": "object",
            "properties": {"app_name": {"type": "string"}},
            "required": ["app_name"],
        },
    },
    {
        "name": "get_daily_briefing",
        "description": "Retrieve task and time data for the daily morning briefing.",
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "get_current_datetime",
        "description": "Get the current date, time, and day of week.",
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "search_knowledge",
        "description": (
            "Search the personal knowledge base for notes, documents, or imported "
            "conversations relevant to the query. Call this before answering factual "
            "questions or when context about past work may help."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Search terms"},
                "n_results": {"type": "integer", "description": "Max results (default 5)"},
            },
            "required": ["query"],
        },
    },
    {
        "name": "add_knowledge",
        "description": "Save a note, fact, or piece of information to the knowledge base for future reference.",
        "input_schema": {
            "type": "object",
            "properties": {
                "content": {"type": "string", "description": "The text to save"},
                "title": {"type": "string", "description": "Short title for the entry"},
                "tags": {"type": "string", "description": "Comma-separated tags"},
            },
            "required": ["content"],
        },
    },
    {
        "name": "browser_navigate",
        "description": "Open a URL in Chrome.",
        "input_schema": {
            "type": "object",
            "properties": {"url": {"type": "string"}},
            "required": ["url"],
        },
    },
    {
        "name": "browser_get_text",
        "description": "Extract visible text from the current browser page.",
        "input_schema": {
            "type": "object",
            "properties": {"selector": {"type": "string", "description": "CSS selector (default: body)"}},
        },
    },
    {
        "name": "browser_click",
        "description": "Click an element on the current page by CSS selector or visible text.",
        "input_schema": {
            "type": "object",
            "properties": {
                "selector": {"type": "string"},
                "text": {"type": "string"},
            },
        },
    },
    {
        "name": "browser_fill",
        "description": "Fill a text input on the current page.",
        "input_schema": {
            "type": "object",
            "properties": {
                "selector": {"type": "string"},
                "value": {"type": "string"},
                "submit": {"type": "boolean"},
            },
            "required": ["selector", "value"],
        },
    },
    {
        "name": "browser_screenshot",
        "description": "Take a screenshot of the current browser page.",
        "input_schema": {
            "type": "object",
            "properties": {"path": {"type": "string", "description": "Optional save path"}},
        },
    },
    {
        "name": "browser_current_url",
        "description": "Get the current browser URL and page title.",
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "browser_close",
        "description": "Close the Chrome browser window.",
        "input_schema": {"type": "object", "properties": {}},
    },
]

# ── Tool dispatcher ───────────────────────────────────────────────────────────

def _get_current_datetime() -> dict:
    now = datetime.now()
    return {
        "datetime": now.isoformat(sep=" ", timespec="seconds"),
        "date": now.strftime("%A, %B %d %Y"),
        "time": now.strftime("%I:%M %p"),
        "iso_date": now.date().isoformat(),
    }


TOOL_HANDLERS: dict = {
    "add_task": add_task,
    "list_tasks": list_tasks,
    "update_task": update_task,
    "delete_task": delete_task,
    "send_email": send_email,
    "send_email_with_attachment": send_email_with_attachment,
    "search_web": search_web,
    "open_application": open_application,
    "close_application": close_application,
    "get_daily_briefing": get_daily_briefing,
    "get_current_datetime": _get_current_datetime,
    "search_knowledge": search_knowledge,
    "add_knowledge": add_knowledge,
    "browser_navigate": browser_navigate,
    "browser_get_text": browser_get_text,
    "browser_click": browser_click,
    "browser_fill": browser_fill,
    "browser_screenshot": browser_screenshot,
    "browser_current_url": browser_current_url,
    "browser_close": browser_close,
}


def dispatch_tool(name: str, inputs: dict) -> str:
    handler = TOOL_HANDLERS.get(name)
    if handler is None:
        return json.dumps({"error": f"Unknown tool: {name}"})
    try:
        return json.dumps(handler(**inputs), default=str)
    except Exception as exc:
        return json.dumps({"error": f"Tool '{name}' raised: {exc}"})


# ── System prompt ─────────────────────────────────────────────────────────────

_SYSTEM_BASE = """\
You are J.A.R.V.I.S. (Just A Rather Very Intelligent System), a highly advanced personal AI \
assistant. You are precise, proactive, and occasionally dry — always composed, never flustered.

ADDRESS & TONE
- Address the user as "{user_name}" (e.g. "Right away, sir." / "Understood, sir.").
- Formal British tone. Dry wit is acceptable; sarcasm is not.
- Lead with the answer. Never pad with "Certainly!" or "Of course!".
- When delivering bad news or errors, be direct and offer a solution immediately.

CAPABILITIES
- Task management: full CRUD via the local database.
- Email: draft and send via Gmail, with or without attachments.
- Web search: live results via Brave Search.
- Browser: navigate, click, fill forms, screenshot via Chrome.
- App control: open and close desktop applications.
- Knowledge base: personal notes and imported documents you can search and save.
- Daily briefing: structured morning summary of tasks and priorities.

KNOWLEDGE BASE
- Before answering factual or personal questions, call search_knowledge to check if \
relevant context is stored.
- If the user shares information worth retaining ("remember that…", "note that…"), \
call add_knowledge proactively.

DAILY PLANNING
When asked about the day or schedule:
1. Call get_daily_briefing for task data.
2. Identify today's priorities and any overdue items.
3. Suggest a clear, prioritised order of work.
4. Offer to set task due dates or reminders if missing.

TOOL USE
- Always use tools rather than guessing. If unsure of a detail (e.g. email recipient), \
ask before acting.
- Chain tools logically: search before writing, list before updating.
- Report tool failures clearly and suggest fixes."""


def _build_system(voice_mode: bool = False) -> str:
    prompt = _SYSTEM_BASE.replace("{user_name}", config.USER_NAME)
    if voice_mode:
        prompt += (
            "\n\nVOICE MODE ACTIVE\n"
            "Keep all replies to 1-3 spoken sentences. No bullet points, no markdown. "
            "Write as you would speak aloud. Spell out numbers and abbreviations."
        )
    return prompt


# ── Main chat function ────────────────────────────────────────────────────────

_client = anthropic.Anthropic(api_key=config.ANTHROPIC_API_KEY)


def chat(
    user_message: str,
    conversation_history: list[dict],
    on_tool_call=None,
    voice_mode: bool = False,
) -> tuple[str, list[dict]]:
    """
    Send a user message, run the tool-use loop, return (reply, updated_history).
    on_tool_call: optional callback(tool_name, tool_inputs) for UI feedback.
    voice_mode: if True, instructs Claude to reply in short spoken sentences.
    """
    history = list(conversation_history)
    history.append({"role": "user", "content": user_message})
    save_message("user", user_message)

    while True:
        response = _client.messages.create(
            model=config.MODEL,
            max_tokens=config.MAX_TOKENS,
            system=_build_system(voice_mode),
            tools=TOOLS,
            messages=history,
        )

        history.append({"role": "assistant", "content": response.content})

        if response.stop_reason == "end_turn":
            text = next(
                (b.text for b in response.content if hasattr(b, "text")), ""
            )
            save_message("assistant", response.content)
            if len(history) > config.HISTORY_LIMIT:
                history = history[-config.HISTORY_LIMIT :]
            return text, history

        if response.stop_reason == "tool_use":
            tool_results = []
            for block in response.content:
                if block.type != "tool_use":
                    continue
                if on_tool_call:
                    on_tool_call(block.name, block.input)
                result_json = dispatch_tool(block.name, block.input)
                tool_results.append({
                    "type": "tool_result",
                    "tool_use_id": block.id,
                    "content": result_json,
                })
            history.append({"role": "user", "content": tool_results})
            continue

        return f"[Unexpected stop_reason: {response.stop_reason}]", history
