"""
AI engine for Universal Media Downloader.
=========================================
A provider-agnostic AI layer that's a first-class part of the app — separate
from licensing. The app is unlocked by a LICENSE key; AI features are unlocked
by an AI PROVIDER API key the user supplies in AI Settings.

Design goals
------------
* Bring-your-own-key: no API key is embedded in the shipped exe. The user pastes
  a key in AI Settings; it's encrypted at rest (Windows DPAPI, tied to their
  account) and only ever shown masked.
* Provider-agnostic: OpenAI-compatible providers (NVIDIA today, others later).
* Rate-limit friendly: results are cached on disk so each title is analyzed once
  (NVIDIA's free tier is ~tens of requests/min — caching keeps us well under).
* Privacy: only TEXT (titles, prompts) is ever sent — never your media files.
"""

import base64
import json
import os
import re
import threading
import urllib.error
import urllib.request
from pathlib import Path

import licensing

HERE = Path(__file__).resolve().parent
_LOCK = threading.Lock()

# OpenAI-compatible providers. Add more here as needed.
PROVIDERS = {
    "nvidia": {
        "label": "NVIDIA (build.nvidia.com)",
        "base_url": "https://integrate.api.nvidia.com/v1",
        "default_model": "meta/llama-3.3-70b-instruct",
        "key_prefix": "nvapi-",
        "get_key_url": "https://build.nvidia.com/",
    },
    "openai": {
        "label": "OpenAI",
        "base_url": "https://api.openai.com/v1",
        "default_model": "gpt-4o-mini",
        "key_prefix": "sk-",
        "get_key_url": "https://platform.openai.com/api-keys",
    },
}
DEFAULT_PROVIDER = "nvidia"

CATEGORIES = ["Music", "Live Performance", "Interview", "Vlog",
              "Behind The Scenes", "Podcast", "News", "Comedy", "Sports",
              "Gaming", "Tutorial", "Trailer", "Audiobook", "Other"]


# --------------------------------------------------------------------------- #
# Secure storage (encrypted at rest)
# --------------------------------------------------------------------------- #
def _settings_file():
    return licensing.config_dir() / "ai_settings.json"


def _protect(secret):
    """Encrypt a string for storage. Windows DPAPI (account-bound) when
    available; otherwise a light base64 obfuscation (still never plaintext)."""
    raw = (secret or "").encode("utf-8")
    try:
        import win32crypt
        blob = win32crypt.CryptProtectData(raw, "UMD-AI", None, None, None, 0)
        return "dpapi:" + base64.b64encode(blob).decode()
    except Exception:  # noqa: BLE001
        return "b64:" + base64.b64encode(raw).decode()


def _unprotect(stored):
    try:
        scheme, _, data = (stored or "").partition(":")
        blob = base64.b64decode(data) if data else b""
        if scheme == "dpapi":
            import win32crypt
            return win32crypt.CryptUnprotectData(
                blob, None, None, None, 0)[1].decode("utf-8")
        if scheme == "b64":
            return blob.decode("utf-8")
    except Exception:  # noqa: BLE001
        return ""
    return ""


def load_settings():
    try:
        p = _settings_file()
        return json.loads(p.read_text(encoding="utf-8")) if p.is_file() else {}
    except (OSError, ValueError):
        return {}


def save_settings(provider=None, model=None, key=None):
    """Persist AI settings. `key` is encrypted before writing; pass "" to clear."""
    with _LOCK:
        d = load_settings()
        if provider is not None:
            d["provider"] = provider
        if model is not None:
            d["model"] = model
        if key is not None:
            d["key"] = _protect(key) if key else ""
        try:
            _settings_file().write_text(json.dumps(d), encoding="utf-8")
        except OSError:
            pass


def clear_key():
    save_settings(key="")


def current_provider():
    p = load_settings().get("provider") or DEFAULT_PROVIDER
    return p if p in PROVIDERS else DEFAULT_PROVIDER


def current_model():
    return load_settings().get("model") or PROVIDERS[current_provider()]["default_model"]


def stored_key():
    return _unprotect(load_settings().get("key", ""))


def masked_key():
    k = stored_key()
    if not k:
        return ""
    return (k[:6] + "•" * 8 + k[-4:]) if len(k) > 12 else "•" * len(k)


# --------------------------------------------------------------------------- #
# Key resolution + availability
# --------------------------------------------------------------------------- #
def _key():
    """Stored (in-app) key first, then env, then a dev nvidia.key file."""
    k = stored_key()
    if k:
        return k
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


def validate_key(provider, key):
    """Check a key by listing models. Returns (ok, models_or_error)."""
    base = PROVIDERS.get(provider, {}).get("base_url")
    if not base:
        return False, "Unknown provider."
    try:
        req = urllib.request.Request(base + "/models",
                                     headers={"Authorization": f"Bearer {key}"})
        data = json.loads(urllib.request.urlopen(req, timeout=25).read())
        return True, sorted(m["id"] for m in data.get("data", []))
    except urllib.error.HTTPError as e:
        return False, f"Key rejected (HTTP {e.code})."
    except Exception as e:  # noqa: BLE001
        return False, f"Could not reach provider: {e}"


# --------------------------------------------------------------------------- #
# Cache
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
# Low-level chat call (provider-aware)
# --------------------------------------------------------------------------- #
def _chat(prompt, max_tokens=1400, temperature=0.1, timeout=120):
    key = _key()
    if not key:
        raise RuntimeError("No AI API key configured.")
    url = PROVIDERS[current_provider()]["base_url"] + "/chat/completions"
    body = json.dumps({
        "model": current_model(),
        "messages": [{"role": "user", "content": prompt}],
        "temperature": temperature, "max_tokens": max_tokens,
    }).encode("utf-8")
    req = urllib.request.Request(
        url, data=body,
        headers={"Authorization": f"Bearer {key}",
                 "Content-Type": "application/json"})
    resp = json.loads(urllib.request.urlopen(req, timeout=timeout).read())
    return resp["choices"][0]["message"]["content"]


def _extract_json(text):
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
# Smart Library: analyze titles -> clean metadata
# --------------------------------------------------------------------------- #
def analyze_titles(titles, progress=None, batch=12):
    """Return {title: {artist, clean_title, category, is_official}}, using the
    cache and only calling the API for new titles. `progress(done, total)` is
    called as batches complete."""
    titles = [t for t in dict.fromkeys(titles) if t]
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
        except Exception:  # noqa: BLE001
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
    return _load_cache()


# --------------------------------------------------------------------------- #
# Write tags to a downloaded file (mutagen)
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
