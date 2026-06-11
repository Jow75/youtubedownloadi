"""
AI helpers for Universal Media Downloader (Smart Library).
==========================================================
OPTIONAL, opt-in, OFF by default. Uses an NVIDIA-hosted, OpenAI-compatible API
to turn messy download titles into clean library metadata (artist / title /
category / official?), then writes proper tags to the files.

Privacy: only TEXT (titles) is ever sent to the API — never your media files —
and only when you ask. If no API key is present, every function degrades
gracefully and the app simply hides the AI features.

The key is loaded (in priority order) from:
  1. env UMD_NVIDIA_KEY
  2. nvidia.key next to this module (git-ignored)
  3. nvidia.key in the app data folder (%APPDATA%\\UniversalMediaDownloader)
So a customer can enable AI just by dropping their own nvidia.key in the app
folder — no rebuild, and your key never ships inside the exe.
"""

import json
import os
import re
import threading
import urllib.request
from pathlib import Path

import licensing

API_URL = "https://integrate.api.nvidia.com/v1/chat/completions"
MODEL = "meta/llama-3.3-70b-instruct"
HERE = Path(__file__).resolve().parent
_LOCK = threading.Lock()

CATEGORIES = ["Music", "Live Performance", "Interview", "Vlog",
              "Behind The Scenes", "Podcast", "News", "Comedy", "Sports",
              "Gaming", "Tutorial", "Trailer", "Audiobook", "Other"]


# --------------------------------------------------------------------------- #
# Key / availability
# --------------------------------------------------------------------------- #
def _key():
    env = os.environ.get("UMD_NVIDIA_KEY")
    if env and env.strip():
        return env.strip()
    for p in (HERE / "nvidia.key", licensing.config_dir() / "nvidia.key"):
        try:
            if p.is_file():
                return p.read_text(encoding="utf-8").strip()
        except OSError:
            pass
    return ""


def is_available():
    return bool(_key())


# --------------------------------------------------------------------------- #
# Cache (so each title is analyzed once)
# --------------------------------------------------------------------------- #
def _cache_file():
    return licensing.config_dir() / "ai_cache.json"


def _load_cache():
    try:
        p = _cache_file()
        return json.loads(p.read_text(encoding="utf-8")) if p.is_file() else {}
    except (OSError, ValueError):
        return {}


def _save_cache(cache):
    try:
        _cache_file().write_text(json.dumps(cache, ensure_ascii=False, indent=1),
                                 encoding="utf-8")
    except OSError:
        pass


# --------------------------------------------------------------------------- #
# Low-level call
# --------------------------------------------------------------------------- #
def _chat(prompt, max_tokens=1400, temperature=0.1, timeout=120):
    key = _key()
    if not key:
        raise RuntimeError("No NVIDIA API key configured.")
    body = json.dumps({
        "model": MODEL,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": temperature, "max_tokens": max_tokens,
    }).encode("utf-8")
    req = urllib.request.Request(
        API_URL, data=body,
        headers={"Authorization": f"Bearer {key}",
                 "Content-Type": "application/json"})
    resp = json.loads(urllib.request.urlopen(req, timeout=timeout).read())
    return resp["choices"][0]["message"]["content"]


def _extract_json(text):
    """Pull a JSON array/object out of the model's reply (it often fences it)."""
    m = re.search(r"```(?:json)?\s*(.*?)```", text, re.S)
    raw = (m.group(1) if m else text).strip()
    try:
        return json.loads(raw)
    except ValueError:
        a, b = raw.find("["), raw.rfind("]")
        if a >= 0 and b > a:
            try:
                return json.loads(raw[a:b + 1])
            except ValueError:
                return None
    return None


# --------------------------------------------------------------------------- #
# Public: analyze titles -> clean metadata
# --------------------------------------------------------------------------- #
def analyze_titles(titles, progress=None, batch=12):
    """Return {title: {artist, clean_title, category, is_official}} for the
    given titles, using the cache and only calling the API for new ones.
    `progress(done, total)` is called as batches complete."""
    titles = [t for t in dict.fromkeys(titles) if t]  # de-dupe, keep order
    with _LOCK:
        cache = _load_cache()
    todo = [t for t in titles if t not in cache]

    for i in range(0, len(todo), batch):
        chunk = todo[i:i + batch]
        prompt = (
            "You clean up media download titles for a library. For EACH title "
            "return one JSON object, in the SAME ORDER, with fields: "
            "artist (performer/channel as a string, or null), "
            "clean_title (the work's name without 'Official Video', tags, etc.), "
            f"category (exactly one of {CATEGORIES}), "
            "is_official (true if it looks like an official release, else false). "
            "Return ONLY a JSON array, nothing else.\n\nTitles:\n"
            + "\n".join(f"{j + 1}. {t}" for j, t in enumerate(chunk)))
        try:
            data = _extract_json(_chat(prompt))
        except Exception:  # noqa: BLE001 — network/parse: skip this batch
            data = None
        if isinstance(data, list):
            for t, obj in zip(chunk, data):
                if isinstance(obj, dict):
                    cat = obj.get("category")
                    cache[t] = {
                        "artist": (obj.get("artist") or None),
                        "clean_title": (obj.get("clean_title") or t),
                        "category": cat if cat in CATEGORIES else "Other",
                        "is_official": obj.get("is_official"),
                    }
        if progress:
            progress(min(i + batch, len(todo)), len(todo))

    with _LOCK:
        merged = _load_cache()
        merged.update(cache)
        _save_cache(merged)
    return {t: cache[t] for t in titles if t in cache}


def cached_analysis():
    """Everything analyzed so far (no API call)."""
    return _load_cache()


# --------------------------------------------------------------------------- #
# Public: write tags to a downloaded file (mutagen is already bundled)
# --------------------------------------------------------------------------- #
def write_tags(path, artist=None, title=None, genre=None):
    """Write artist/title/genre tags into an audio/video file in place.
    Returns True on success. Never raises."""
    try:
        from mutagen import File as MutagenFile
        f = MutagenFile(path, easy=True)
        if f is None:
            return False
        if f.tags is None:
            try:
                f.add_tags()
            except Exception:  # noqa: BLE001
                pass
        if artist:
            f["artist"] = artist
        if title:
            f["title"] = title
        if genre:
            f["genre"] = genre
        f.save()
        return True
    except Exception:  # noqa: BLE001
        return False
