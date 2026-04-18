"""
Flask web interface for J.A.R.V.I.S.

Serves the Iron Man HUD at localhost:{WEB_PORT} and exposes a REST API
for chat, knowledge base management, and task viewing.
"""

from __future__ import annotations

import os
import threading
from pathlib import Path

from flask import Flask, jsonify, render_template, request

from agent import chat as agent_chat
from config import config
from database import load_recent_history
from tools.knowledge_base import (
    add_knowledge,
    delete_knowledge,
    import_claude_conversation,
    import_file,
    list_knowledge,
    search_knowledge,
)
from tools.tasks import list_tasks

app = Flask(__name__, template_folder="templates")
app.config["MAX_CONTENT_LENGTH"] = 16 * 1024 * 1024  # 16 MB upload limit

# Separate conversation history for the web session
_web_history: list[dict] = []
_web_lock = threading.Lock()


# ── Pages ────────────────────────────────────────────────────────────────────

@app.route("/")
def index():
    return render_template("index.html", user_name=config.USER_NAME)


# ── Chat ─────────────────────────────────────────────────────────────────────

@app.route("/api/chat", methods=["POST"])
def api_chat():
    global _web_history
    data = request.get_json(silent=True) or {}
    message = (data.get("message") or "").strip()
    if not message:
        return jsonify({"error": "No message provided"}), 400

    with _web_lock:
        try:
            reply, _web_history = agent_chat(message, _web_history)
            return jsonify({"reply": reply})
        except Exception as exc:
            return jsonify({"error": str(exc)}), 500


@app.route("/api/chat/history", methods=["GET"])
def api_chat_history():
    history = load_recent_history(config.HISTORY_LIMIT)
    # Return only user/assistant text pairs for the web UI
    messages = []
    for msg in history:
        if isinstance(msg["content"], str):
            messages.append({"role": msg["role"], "content": msg["content"]})
        elif isinstance(msg["content"], list):
            for block in msg["content"]:
                if isinstance(block, dict) and block.get("type") == "text":
                    messages.append({"role": msg["role"], "content": block["text"]})
    return jsonify({"messages": messages})


# ── Knowledge base ────────────────────────────────────────────────────────────

@app.route("/api/kb", methods=["GET"])
def api_kb_list():
    return jsonify(list_knowledge(limit=100))


@app.route("/api/kb/search", methods=["POST"])
def api_kb_search():
    data = request.get_json(silent=True) or {}
    query = (data.get("query") or "").strip()
    if not query:
        return jsonify({"error": "No query provided"}), 400
    return jsonify(search_knowledge(query, n_results=10))


@app.route("/api/kb/add", methods=["POST"])
def api_kb_add():
    data = request.get_json(silent=True) or {}
    content = (data.get("content") or "").strip()
    title = (data.get("title") or "").strip()
    tags = (data.get("tags") or "").strip()
    if not content:
        return jsonify({"error": "Content is required"}), 400
    return jsonify(add_knowledge(content, title=title, tags=tags))


@app.route("/api/kb/<doc_id>", methods=["DELETE"])
def api_kb_delete(doc_id: str):
    return jsonify(delete_knowledge(doc_id))


@app.route("/api/kb/import/claude", methods=["POST"])
def api_kb_import_claude():
    data = request.get_json(silent=True) or {}
    json_text = (data.get("json_text") or "").strip()
    title = (data.get("title") or "").strip()
    if not json_text:
        return jsonify({"error": "json_text is required"}), 400
    return jsonify(import_claude_conversation(json_text, title=title))


@app.route("/api/kb/import/file", methods=["POST"])
def api_kb_import_file():
    if "file" not in request.files:
        return jsonify({"error": "No file provided"}), 400
    f = request.files["file"]
    if not f.filename:
        return jsonify({"error": "Empty filename"}), 400

    # Save to a temp location, import, then delete
    import tempfile
    suffix = Path(f.filename).suffix
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
        f.save(tmp.name)
        tmp_path = tmp.name

    try:
        result = import_file(tmp_path, title=Path(f.filename).stem)
    finally:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass

    return jsonify(result)


# ── Tasks ─────────────────────────────────────────────────────────────────────

@app.route("/api/tasks", methods=["GET"])
def api_tasks():
    status = request.args.get("status", "all")
    return jsonify(list_tasks(status=status))


# ── Runner ────────────────────────────────────────────────────────────────────

def run_web(port: int | None = None, open_browser: bool = True) -> None:
    """Start the Flask server in a background daemon thread."""
    port = port or config.WEB_PORT

    def _serve() -> None:
        import logging
        log = logging.getLogger("werkzeug")
        log.setLevel(logging.ERROR)  # suppress request logs
        app.run(host="127.0.0.1", port=port, debug=False, use_reloader=False)

    t = threading.Thread(target=_serve, name="jarvis-web", daemon=True)
    t.start()

    if open_browser:
        import time
        import webbrowser
        time.sleep(0.8)  # brief pause for Flask to bind
        webbrowser.open(f"http://127.0.0.1:{port}")
