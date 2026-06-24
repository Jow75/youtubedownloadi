"""
Followed YouTube channels for the desktop Discover — a port of the mobile
Follows.kt. Persisted to follows.json (config_dir). Each = {id, title, thumb}.
The caller holds the live list (from load()) and toggles through here, which
saves on every change. Discover shows a "⭐ New from <channel>" shelf per follow.
(New-upload notifications are a future/APK item — see the roadmap.)
"""

import json

import licensing


def _file():
    return licensing.config_dir() / "follows.json"


def load():
    f = _file()
    if not f.is_file():
        return []
    try:
        data = json.loads(f.read_text(encoding="utf-8"))
        out = []
        for c in (data if isinstance(data, list) else []):
            if isinstance(c, dict) and c.get("id"):
                out.append({"id": str(c["id"]),
                            "title": c.get("title") or "Channel",
                            "thumb": c.get("thumb") or ""})
        return out
    except Exception:  # noqa: BLE001
        return []


def save(items):
    try:
        _file().write_text(json.dumps(items, ensure_ascii=False), encoding="utf-8")
    except OSError:
        pass


def is_following(items, channel_id):
    return any(c["id"] == channel_id for c in items)


def toggle(items, channel_id, title="", thumb=""):
    """Follow if not followed, else unfollow. Returns the new following state."""
    if is_following(items, channel_id):
        items[:] = [c for c in items if c["id"] != channel_id]
        save(items)
        return False
    items.insert(0, {"id": channel_id, "title": title or "Channel", "thumb": thumb})
    save(items)
    return True
