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


def classify_tracks(titles, progress=None, batch=10):
    """Sort titles -> {title: {genre, language}} for playlist auto-grouping.
    GENRE + LANGUAGE/REGION only — never mood (mirrors the mobile classifier)."""
    titles = [t for t in dict.fromkeys(titles) if t]
    out = {}
    for i in range(0, len(titles), batch):
        chunk = titles[i:i + batch]
        prompt = (
            "You sort music tracks into a FEW meaningful playlists by GENRE and by "
            "LANGUAGE/REGION — never by mood or feeling. For EACH title return one JSON "
            "object IN THE SAME ORDER with two fields:\n"
            "  genre: one of Afrobeats, Amapiano, Bongo Flava, Gengetone, Rhumba, Gospel, "
            "Hip-Hop, R&B, Pop, Reggae, Dancehall, Drill, Reggaeton, Bollywood, Country, "
            "Classical, Other;\n"
            "  language: the main language/region — one of Swahili, English, Nigerian, "
            "French, Spanish, Hindi, Bengali, Marathi, Arabic, Kikuyu, Mixed, Unknown.\n"
            "Pick the single best fit; do NOT invent new labels. Return ONLY a JSON array.\n\nTitles:\n"
            + "\n".join(f"{j + 1}. {t}" for j, t in enumerate(chunk)))
        try:
            data = _extract_json(_chat(prompt, max_tokens=700))
        except Exception:  # noqa: BLE001
            data = None
        if isinstance(data, list):
            for t, obj in zip(chunk, data):
                if isinstance(obj, dict):
                    out[t] = {"genre": (obj.get("genre") or "").strip(),
                              "language": (obj.get("language") or "").strip()}
        if progress:
            progress(min(i + batch, len(titles)), len(titles))
    return out


def cached_analysis():
    return _load_cache()


# --------------------------------------------------------------------------- #
# Wave C: natural-language assistant + troubleshooting
# --------------------------------------------------------------------------- #
def agent_plan(instruction, context=None):
    """Turn a plain-language request into a structured action plan the app can
    run. Returns a dict (or None). Fields:
      action: 'download' | 'search' | 'channel' | 'help'
      url: a URL if the user gave one, else null
      query: search text (for search / channel-by-name), else null
      fmt: 'mp3' | 'mp4'
      quality: 'Best Available' | '720p' | '480p'
      count: how many results to fetch for a search (1-10)
      answer: a helpful reply if action is 'help', else null
    """
    ctx_txt = ""
    if context:
        lines = [f"{'User' if m.get('user') else 'Assistant'}: {m.get('text', '')}"
                 for m in context[-6:] if m.get("text")]
        if lines:
            ctx_txt = "Recent conversation for context:\n" + "\n".join(lines) + "\n\n"
    prompt = (
        "You are the built-in assistant of a media downloader app (YouTube, X, "
        "TikTok, etc.). Convert the user's request into a JSON action plan. "
        "Fields: action ('download' if they gave a specific media URL; 'channel' "
        "if they gave a channel/profile URL or want a whole channel/artist; "
        "'search' to find something by name; 'help' to answer a question about "
        "using the app); url (string or null); query (search/artist text or "
        "null); fmt ('mp3' for songs/audio — the default — or 'mp4' for video); "
        "quality ('Best Available' default, or '720p'/'480p'); count (1-10, how "
        "many search results, default 1); answer (a short helpful reply when "
        "action is 'help', else null). Return ONLY the JSON object.\n\n"
        f"{ctx_txt}User: {instruction}")
    try:
        data = _extract_json(_chat(prompt, max_tokens=500))
    except Exception:  # noqa: BLE001
        return None
    if not isinstance(data, dict):
        return None
    data.setdefault("action", "help")
    data.setdefault("fmt", "mp3")
    data.setdefault("quality", "Best Available")
    data.setdefault("count", 1)
    return data


def explain_error(title, error):
    """Plain-language 'why did this fail + how to fix' for a failed download."""
    prompt = (
        "A media download failed in a yt-dlp-based app. In 2-4 short sentences, "
        "explain the most likely REASON in plain language and the best practical "
        "FIX. Consider: private/removed/region-locked video, login cookies "
        "needed, rate-limiting (try again later), try M4A instead of MP3, "
        "geo-block, age-restriction, or a bad link. Be specific.\n\n"
        f"Title: {title}\nError: {error}")
    try:
        return _chat(prompt, max_tokens=300)
    except Exception as e:  # noqa: BLE001
        return f"(Couldn't reach the AI: {e})"


# --------------------------------------------------------------------------- #
# Wave D: semantic search (embeddings) — find by meaning, not exact words
# --------------------------------------------------------------------------- #
EMBED_MODELS = {"nvidia": "nvidia/nv-embedqa-e5-v5",
                "openai": "text-embedding-3-small"}


def _embeds_file():
    return licensing.config_dir() / "ai_embeds.json"


def _load_embeds():
    try:
        p = _embeds_file()
        return json.loads(p.read_text(encoding="utf-8")) if p.is_file() else {}
    except (OSError, ValueError):
        return {}


def _save_embeds(d):
    try:
        _embeds_file().write_text(json.dumps(d), encoding="utf-8")
    except OSError:
        pass


def embeds_count():
    return len(_load_embeds())


def embed(texts, input_type="passage"):
    """Return an embedding vector per input text (OpenAI-compatible endpoint)."""
    key = _key()
    if not key:
        raise RuntimeError("No AI API key configured.")
    prov = current_provider()
    url = PROVIDERS[prov]["base_url"] + "/embeddings"
    payload = {"model": EMBED_MODELS.get(prov, "nvidia/nv-embedqa-e5-v5"),
               "input": list(texts), "encoding_format": "float"}
    if prov == "nvidia":
        payload["input_type"] = input_type      # NeMo retriever needs this
    req = urllib.request.Request(
        url, data=json.dumps(payload).encode("utf-8"),
        headers={"Authorization": f"Bearer {key}",
                 "Content-Type": "application/json"})
    resp = json.loads(urllib.request.urlopen(req, timeout=60).read())
    return [d["embedding"] for d in resp["data"]]


def build_embeddings(titles, progress=None, batch=32):
    """Embed any titles not already indexed (cached on disk). Returns the cache."""
    titles = [t for t in dict.fromkeys(titles) if t]
    with _LOCK:
        cache = _load_embeds()
    todo = [t for t in titles if t not in cache]
    for i in range(0, len(todo), batch):
        chunk = todo[i:i + batch]
        try:
            vecs = embed(chunk, "passage")
        except Exception:  # noqa: BLE001 — skip a bad batch, keep going
            vecs = []
        for t, v in zip(chunk, vecs):
            cache[t] = v
        with _LOCK:
            _save_embeds(cache)
        if progress:
            progress(min(i + batch, len(todo)), len(todo))
    return cache


def _cosine(a, b):
    import math
    s = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    return s / (na * nb + 1e-9)


def summarize_habits(facts):
    """A short, friendly read of the user's download habits + a tip or two."""
    prompt = ("Here are a user's media-download stats. In 2-3 short, friendly "
              "sentences, summarize their habits and give one practical tip "
              "(e.g. a default setting or a folder idea). Be specific, no "
              "preamble.\n\n" + facts)
    return _chat(prompt, max_tokens=220)


def semantic_search(query, titles, top_k=25):
    """Rank `titles` by meaning-similarity to `query`. Returns [(title, score)]
    for titles that have a cached embedding."""
    cache = _load_embeds()
    cand = [(t, cache[t]) for t in dict.fromkeys(titles) if t in cache]
    if not cand:
        return []
    qv = embed([query], "query")[0]
    scored = [(t, _cosine(qv, v)) for t, v in cand]
    scored.sort(key=lambda x: x[1], reverse=True)
    return scored[:top_k]


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
