"""
Permanent download archive for Universal Media Downloader.
==========================================================
A hidden, append-only recovery catalog that records EVERY download as a tiny
reference (no media, no thumbnails). It is separate from the visible history:

  * Visible history  (history.py)  — user-facing, searchable, clearable.
  * Permanent archive (this file)  — survives "Clear All History", so you can
    always find and re-download past media.

Storage is JSONL (one compact JSON record per line) in the app data folder.
Each record is ~150-250 bytes, so 100,000 downloads is only a few MB. Writes are
O(1) appends (lock-guarded); duplicates are collapsed at read time.

Pure logic, NO Streamlit — importable/testable and identical when frozen.
"""

import json
import os
import threading
import time
from datetime import datetime

import licensing

_LOCK = threading.Lock()


def _file():
    return licensing.config_dir() / "archive.jsonl"


def mtime():
    """File modification time (for cache invalidation). 0 if absent."""
    try:
        return _file().stat().st_mtime
    except OSError:
        return 0.0


def add(rec):
    """Append one lightweight record. No-op without a URL (can't recover)."""
    if not rec or not rec.get("url"):
        return
    with _LOCK:
        try:
            with _file().open("a", encoding="utf-8") as f:
                f.write(json.dumps(rec, ensure_ascii=False) + "\n")
        except OSError:
            pass


def add_from_history(entry):
    """Build an archive record from a history entry dict and store it."""
    if not entry or not entry.get("url"):
        return
    add({
        "id": entry.get("id", ""),
        "url": entry.get("url", ""),
        "title": entry.get("title", ""),
        "artist": entry.get("artist", ""),
        "site": entry.get("site", ""),
        "ts": entry.get("ts", "") or datetime.now().replace(microsecond=0).isoformat(),
        "fmt": entry.get("fmt", ""),
        "ext": os.path.splitext(entry.get("filename", ""))[1].lower(),
        "size": int(entry.get("size", 0) or 0),
    })


def load(dedup=True):
    """All records, newest first. With dedup, collapse repeats of the same
    (url, fmt, ext) keeping the newest. Never raises."""
    p = _file()
    rows = []
    try:
        if p.is_file():
            with p.open(encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        rows.append(json.loads(line))
                    except ValueError:
                        continue
    except OSError:
        return []
    rows.reverse()  # file is oldest-first; show newest-first
    if not dedup:
        return rows
    seen, out = set(), []
    for r in rows:
        k = (r.get("url", ""), r.get("fmt", ""), r.get("ext", ""))
        if k in seen:
            continue
        seen.add(k)
        out.append(r)
    return out


def sites(records=None):
    records = records if records is not None else load()
    seen = []
    for r in records:
        s = r.get("site") or "Other"
        if s not in seen:
            seen.append(s)
    return sorted(seen)


def filter_records(records, query="", site="All sites", mtype="All types",
                   when="All time"):
    q = (query or "").lower().strip()
    out = []
    now = datetime.now()
    for r in records:
        if q and q not in (
                (r.get("title", "") + " " + r.get("artist", "") + " "
                 + r.get("url", "")).lower()):
            continue
        if site != "All sites" and r.get("site") != site:
            continue
        if mtype.endswith("Video") and r.get("fmt") != "video":
            continue
        if mtype.endswith("Audio") and r.get("fmt") != "audio":
            continue
        if when != "All time":
            try:
                ts = datetime.fromisoformat(r.get("ts", ""))
            except (ValueError, TypeError):
                continue
            days = 7 if "7" in when else 30 if "30" in when else 365
            if (now - ts).days >= days:
                continue
        out.append(r)
    return out


def to_csv(records):
    """Render records to CSV text (for export)."""
    import csv
    import io
    cols = ["ts", "title", "artist", "site", "fmt", "ext", "size", "url"]
    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=cols, extrasaction="ignore")
    w.writeheader()
    for r in records:
        w.writerow({c: r.get(c, "") for c in cols})
    return buf.getvalue()
