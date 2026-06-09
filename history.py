"""
Persistent download history for Universal Media Downloader.
===========================================================
Survives app restarts / browser refreshes by storing every finished download
in a small JSON file under the app's data folder
(%APPDATA%\\UniversalMediaDownloader\\download_history.json).

Pure logic, NO Streamlit — so it stays importable/testable and works the same
when frozen into the .exe. The UI in app.py reads and filters this list.
"""

import json
import os
import threading
import time
from datetime import datetime

import licensing  # reuse the app's per-user config folder

MAX_ENTRIES = 2000
_LOCK = threading.Lock()


def _history_file():
    return licensing.config_dir() / "download_history.json"


def _host_from_url(url):
    """Cheap domain extraction for a 'site' label without importing urllib."""
    u = (url or "").split("//", 1)[-1]
    host = u.split("/", 1)[0].split("?", 1)[0].lower()
    if host.startswith("www."):
        host = host[4:]
    return host


def site_label(url, extractor=""):
    """A friendly source name: prefer yt-dlp's extractor, else the domain."""
    ex = (extractor or "").strip()
    if ex and ex.lower() not in ("generic", "unknown"):
        # yt-dlp uses keys like 'Youtube', 'TikTok', 'Twitter' (X), 'Reddit'...
        return "X" if ex.lower() in ("twitter", "x") else ex
    host = _host_from_url(url)
    table = {
        "youtube.com": "YouTube", "youtu.be": "YouTube",
        "twitter.com": "X", "x.com": "X",
        "tiktok.com": "TikTok", "reddit.com": "Reddit",
        "instagram.com": "Instagram", "facebook.com": "Facebook",
        "soundcloud.com": "SoundCloud", "vimeo.com": "Vimeo",
    }
    for dom, name in table.items():
        if host.endswith(dom):
            return name
    return host or "Other"


def load_history():
    """Return all entries, newest first. Never raises — a corrupt/missing file
    just yields an empty list."""
    path = _history_file()
    try:
        if not path.is_file():
            return []
        with path.open(encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, list) else []
    except (OSError, ValueError):
        return []


def _save(entries):
    path = _history_file()
    tmp = path.with_suffix(".tmp")
    try:
        with tmp.open("w", encoding="utf-8") as f:
            json.dump(entries, f, ensure_ascii=False, indent=2)
        os.replace(tmp, path)
    except OSError:
        pass


def add_entry(path, title, fmt, url="", extractor="", size=None):
    """Record one finished download (prepended; capped at MAX_ENTRIES).
    Returns the stored entry dict."""
    if size is None:
        try:
            size = os.path.getsize(path)
        except OSError:
            size = 0
    entry = {
        "id": f"{int(time.time() * 1000)}-{os.path.basename(path)}",
        "ts": datetime.now().replace(microsecond=0).isoformat(),
        "title": title or os.path.basename(path),
        "path": path,
        "filename": os.path.basename(path),
        "fmt": fmt,                       # "video" | "audio"
        "site": site_label(url, extractor),
        "url": url,
        "size": int(size or 0),
    }
    with _LOCK:
        entries = load_history()
        entries.insert(0, entry)
        del entries[MAX_ENTRIES:]
        _save(entries)
    return entry


def clear_history():
    """Wipe the whole history."""
    with _LOCK:
        _save([])


def delete_entry(entry_id):
    """Remove a single entry by id."""
    with _LOCK:
        entries = [e for e in load_history() if e.get("id") != entry_id]
        _save(entries)


def all_sites(entries=None):
    """Distinct site labels present in history (for the filter dropdown)."""
    entries = entries if entries is not None else load_history()
    seen = []
    for e in entries:
        s = e.get("site") or "Other"
        if s not in seen:
            seen.append(s)
    return sorted(seen)
