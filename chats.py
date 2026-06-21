"""
Chat sessions for the desktop Assistant.
========================================
A faithful port of the mobile app's ChatStore.kt: persists multiple chat
sessions (ChatGPT-style) to chats.json so your conversations survive restarts.
Each session = {id, title, messages[]}; each message = {user, text, url, title}.
(`url` lets a downloaded-in-chat item be tracked + played from the conversation.)
"""

import json
import time

import licensing


def _file():
    return licensing.config_dir() / "chats.json"


def load():
    """Return (sessions_newest_first, current_id)."""
    f = _file()
    if not f.is_file():
        return [], ""
    try:
        root = json.loads(f.read_text(encoding="utf-8"))
        sessions = root.get("sessions") or []
        # tolerate older/odd shapes
        clean = []
        for s in sessions:
            if not isinstance(s, dict):
                continue
            clean.append({
                "id": str(s.get("id") or int(time.time() * 1000)),
                "title": s.get("title") or "New chat",
                "messages": [m for m in (s.get("messages") or []) if isinstance(m, dict)],
            })
        return clean, str(root.get("current") or "")
    except Exception:  # noqa: BLE001
        return [], ""


def save(sessions, current_id):
    try:
        _file().write_text(
            json.dumps({"sessions": sessions, "current": current_id}, ensure_ascii=False),
            encoding="utf-8")
    except OSError:
        pass


def clear():
    save([], "")


def new_session(title="New chat"):
    return {"id": str(int(time.time() * 1000)), "title": title, "messages": []}
