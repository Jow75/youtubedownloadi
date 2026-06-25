"""
Discover — YouTube content discovery for the desktop app (Data API v3).
=======================================================================
A faithful port of the mobile app's Discover.kt: the SAME endpoints, params,
caching (trending 6h, search 24h), transient-retry, and parsing — so the desktop
Discover behaves exactly like the phone's. Powers the Discover tab: Trending
(Kenya / Worldwide / Music), mixed search (videos + channels + playlists), and a
channel's latest uploads — all download-first via the existing engine.

The API key is EMBEDDED (not user-configurable), mirroring the mobile build. It
is read from, in order: env UMD_YOUTUBE_KEY -> youtube.key (app dir or config
dir) -> mobile/secret.properties (dev fallback). For the frozen exe, ship a
youtube.key next to it (gitignored, like secret.key).
"""

import json
import os
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path

import licensing

HERE = Path(__file__).resolve().parent
BASE = "https://www.googleapis.com/youtube/v3"
TRENDING_TTL = 6 * 60 * 60        # 6h (seconds)
SEARCH_TTL = 24 * 60 * 60         # 24h (search costs 100 quota units)


# --------------------------------------------------------------------------- #
#  Models
# --------------------------------------------------------------------------- #
@dataclass
class DiscoverItem:
    video_id: str
    title: str
    channel: str
    thumb: str
    duration_sec: int = 0

    @property
    def url(self):
        return f"https://www.youtube.com/watch?v={self.video_id}"

    def as_dict(self):
        return {"video_id": self.video_id, "title": self.title, "channel": self.channel,
                "thumb": self.thumb, "duration_sec": self.duration_sec, "url": self.url}


@dataclass
class DiscoverChannel:
    channel_id: str
    title: str
    thumb: str

    @property
    def url(self):
        return f"https://www.youtube.com/channel/{self.channel_id}"

    def as_dict(self):
        return {"channel_id": self.channel_id, "title": self.title, "thumb": self.thumb, "url": self.url}


@dataclass
class DiscoverPlaylist:
    playlist_id: str
    title: str
    thumb: str

    @property
    def url(self):
        return f"https://www.youtube.com/playlist?list={self.playlist_id}"

    def as_dict(self):
        return {"playlist_id": self.playlist_id, "title": self.title, "thumb": self.thumb, "url": self.url}


# --------------------------------------------------------------------------- #
#  API key (embedded, like the mobile build)
# --------------------------------------------------------------------------- #
_keys_cache = None


def _from_secret_properties():
    f = HERE / "mobile" / "secret.properties"
    if not f.is_file():
        return ""
    try:
        for line in f.read_text(encoding="utf-8").splitlines():
            s = line.strip()
            if s.startswith("YOUTUBE_API_KEY") and "=" in s:
                return s.split("=", 1)[1].strip()
    except OSError:
        pass
    return ""


def api_keys():
    """ALL configured YouTube keys, in priority order, for quota failover.
    Sources: env UMD_YOUTUBE_KEY (comma/space separated) -> youtube.key (ONE KEY
    PER LINE; '#' lines ignored) -> mobile/secret.properties. De-duped, ordered.
    Add more keys = paste more lines into youtube.key; rotation is automatic."""
    global _keys_cache
    if _keys_cache is not None:
        return _keys_cache
    out = []
    env = (os.environ.get("UMD_YOUTUBE_KEY") or "").strip()
    if env:
        out += [k.strip() for k in re.split(r"[,\s]+", env) if k.strip()]
    if not out:
        for p in (HERE / "youtube.key", licensing.config_dir() / "youtube.key"):
            try:
                if p.is_file():
                    out += [ln.strip() for ln in p.read_text(encoding="utf-8").splitlines()
                            if ln.strip() and not ln.strip().startswith("#")]
                    if out:
                        break
            except OSError:
                pass
    if not out:
        sp = _from_secret_properties()
        if sp:
            out.append(sp)
    seen, uniq = set(), []
    for k in out:
        if k not in seen:
            seen.add(k)
            uniq.append(k)
    _keys_cache = uniq
    return uniq


def api_key():
    ks = api_keys()
    return ks[0] if ks else ""


def has_key():
    return bool(api_keys())


# --------------------------------------------------------------------------- #
#  Disk cache (mirrors the Kotlin cache: {ts, body} JSON per key)
# --------------------------------------------------------------------------- #
def _cache_dir():
    d = licensing.config_dir() / "discover_cache"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _cache_file(key):
    return _cache_dir() / (re.sub(r"[^a-zA-Z0-9]", "_", key) + ".json")


def _read_cache(key, ttl, ignore_ttl):
    f = _cache_file(key)
    if not f.is_file():
        return None
    try:
        o = json.loads(f.read_text(encoding="utf-8"))
        if ignore_ttl or (time.time() - o.get("ts", 0)) < ttl:
            return o.get("body", "")
    except Exception:
        return None
    return None


def _write_cache(key, body):
    try:
        _cache_file(key).write_text(json.dumps({"ts": time.time(), "body": body}), encoding="utf-8")
    except OSError:
        pass


# --------------------------------------------------------------------------- #
#  HTTP with retry for transient failures (port of the Kotlin retry)
# --------------------------------------------------------------------------- #
class _PermanentHttp(Exception):
    """A 4xx the caller shouldn't retry (bad request / forbidden)."""


class _QuotaExceeded(_PermanentHttp):
    """403 quota/limit — rotate to the next API key if we have one."""


def _parse_err(body, code):
    try:
        if code == 403:
            return "YouTube daily limit reached — try again later."
        msg = ((json.loads(body) or {}).get("error", {}) or {}).get("message", "")
        return msg or f"Couldn't reach YouTube (HTTP {code})."
    except Exception:
        return f"Couldn't reach YouTube (HTTP {code})."


def _swap_key(url, key):
    """Put `key` into the URL's key= param (keys rotate; the rest of the URL —
    and therefore the cache key — stays the same)."""
    if not key:
        return url
    if re.search(r"[?&]key=", url):
        return re.sub(r"([?&]key=)[^&]*", lambda m: m.group(1) + key, url)
    return url + ("&" if "?" in url else "?") + "key=" + key


def _http_get_once(url):
    last = None
    for attempt in range(3):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "UMD-Discover"})
            with urllib.request.urlopen(req, timeout=30) as resp:
                return resp.read().decode("utf-8", "replace")
        except urllib.error.HTTPError as e:
            body = ""
            try:
                body = e.read().decode("utf-8", "replace")
            except Exception:
                pass
            msg = _parse_err(body, e.code)
            if e.code == 403:
                raise _QuotaExceeded(msg)             # spent key → caller rotates
            if 400 <= e.code < 500 and e.code not in (408, 429):
                raise _PermanentHttp(msg)            # permanent → don't retry
            last = IOError(msg)                       # 5xx / 408 / 429 → retry
        except (urllib.error.URLError, TimeoutError, OSError) as e:
            last = e                                  # connection-level failure → retry
        if attempt < 2:
            time.sleep(0.5 * (attempt + 1))
    raise last or IOError("Couldn't reach YouTube.")


def _http_get(url):
    """Fetch with transient-retry, AND automatic key rotation: if a key's daily
    quota is exhausted (403), fall through to the next configured key so Discover
    keeps working. With a single key this behaves exactly as before."""
    keys = api_keys() or [""]
    last = None
    for key in keys:
        try:
            return _http_get_once(_swap_key(url, key))
        except _QuotaExceeded as e:
            last = e                                  # this key is spent — try next
            continue
    raise last or _QuotaExceeded("YouTube daily limit reached on all keys.")


def _cached_fetch(cache_key, url, ttl):
    cached = _read_cache(cache_key, ttl, ignore_ttl=False)
    if cached is not None:
        return cached
    try:
        body = _http_get(url)
        _write_cache(cache_key, body)
        return body
    except Exception:
        stale = _read_cache(cache_key, ttl, ignore_ttl=True)
        if stale is not None:
            return stale
        raise


# --------------------------------------------------------------------------- #
#  Parsing
# --------------------------------------------------------------------------- #
def _thumb_url(thumbs):
    if not thumbs:
        return ""
    for k in ("high", "medium", "default"):
        u = (thumbs.get(k) or {}).get("url", "")
        if u:
            return u
    return ""


def _parse_duration(iso):
    if not iso:
        return 0
    m = re.search(r"PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?", iso)
    if not m:
        return 0
    h = int(m.group(1) or 0)
    mn = int(m.group(2) or 0)
    s = int(m.group(3) or 0)
    return h * 3600 + mn * 60 + s


def _parse_videos(body):
    out = []
    for it in (json.loads(body).get("items") or []):
        vid = it.get("id", "")
        sn = it.get("snippet") or {}
        if not vid or not sn:
            continue
        out.append(DiscoverItem(vid, sn.get("title", ""), sn.get("channelTitle", ""),
                                _thumb_url(sn.get("thumbnails")),
                                _parse_duration((it.get("contentDetails") or {}).get("duration"))))
    return out


def _parse_search(body):
    out = []
    for it in (json.loads(body).get("items") or []):
        vid = (it.get("id") or {}).get("videoId", "")
        sn = it.get("snippet") or {}
        if not vid or not sn:
            continue
        out.append(DiscoverItem(vid, sn.get("title", ""), sn.get("channelTitle", ""),
                                _thumb_url(sn.get("thumbnails")), 0))
    return out


def _parse_mixed(body):
    vids, chans, plays = [], [], []
    for it in (json.loads(body).get("items") or []):
        ido = it.get("id") or {}
        kind = ido.get("kind", "")
        sn = it.get("snippet") or {}
        if not sn:
            continue
        thumb = _thumb_url(sn.get("thumbnails"))
        if kind.endswith("video") and ido.get("videoId"):
            vids.append(DiscoverItem(ido["videoId"], sn.get("title", ""), sn.get("channelTitle", ""), thumb, 0))
        elif kind.endswith("channel") and ido.get("channelId"):
            chans.append(DiscoverChannel(ido["channelId"], sn.get("title", ""), thumb))
        elif kind.endswith("playlist") and ido.get("playlistId"):
            plays.append(DiscoverPlaylist(ido["playlistId"], sn.get("title", ""), thumb))
    return {"videos": vids, "channels": chans, "playlists": plays}


def _parse_playlist_items(body):
    out = []
    for it in (json.loads(body).get("items") or []):
        sn = it.get("snippet") or {}
        vid = (sn.get("resourceId") or {}).get("videoId", "")
        if not vid:
            continue
        ch = sn.get("videoOwnerChannelTitle") or sn.get("channelTitle", "")
        out.append(DiscoverItem(vid, sn.get("title", ""), ch, _thumb_url(sn.get("thumbnails")), 0))
    return out


# --------------------------------------------------------------------------- #
#  Public API (mirrors Discover.kt)
# --------------------------------------------------------------------------- #
def trending(region_code, category_id=None):
    """Most-popular videos for a region (1 quota unit). category_id '10' = Music."""
    if not has_key():
        raise IOError("Discover is unavailable (no YouTube key).")
    cat = f"&videoCategoryId={category_id}" if category_id else ""
    url = (f"{BASE}/videos?part=snippet,contentDetails&chart=mostPopular&maxResults=20"
           f"&regionCode={region_code}{cat}&key={api_key()}")
    return _parse_videos(_cached_fetch(f"trending_{region_code}_{category_id or 'all'}", url, TRENDING_TTL))


def search(query, order="date"):
    """Search videos by name (100 quota units, cached 24h). order = date | relevance."""
    if not has_key():
        raise IOError("Discover is unavailable (no YouTube key).")
    if not query.strip():
        return []
    q = urllib.parse.quote(query)
    url = f"{BASE}/search?part=snippet&type=video&order={order}&maxResults=20&q={q}&key={api_key()}"
    return _parse_search(_cached_fetch(f"search_{order}_{query}", url, SEARCH_TTL))


def search_mixed(query, order="relevance"):
    """Mixed keyword search — videos + channels + playlists in ONE call (cached 24h)."""
    if not has_key():
        raise IOError("Discover is unavailable (no YouTube key).")
    if not query.strip():
        return {"videos": [], "channels": [], "playlists": []}
    q = urllib.parse.quote(query)
    url = f"{BASE}/search?part=snippet&maxResults=25&order={order}&q={q}&key={api_key()}"
    return _parse_mixed(_cached_fetch(f"searchmix_{order}_{query}", url, SEARCH_TTL))


def latest_uploads(channel_id):
    """A channel's latest uploads (2 quota units, cached 6h) — for artist discovery."""
    if not has_key():
        raise IOError("Discover is unavailable (no YouTube key).")
    ch_url = f"{BASE}/channels?part=contentDetails&id={channel_id}&key={api_key()}"
    meta = json.loads(_cached_fetch(f"chmeta_{channel_id}", ch_url, TRENDING_TTL))
    items = meta.get("items") or []
    uploads = ""
    if items:
        uploads = (((items[0].get("contentDetails") or {}).get("relatedPlaylists") or {}).get("uploads", ""))
    if not uploads:
        return []
    pl_url = f"{BASE}/playlistItems?part=snippet&maxResults=12&playlistId={uploads}&key={api_key()}"
    return _parse_playlist_items(_cached_fetch(f"uploads_{channel_id}", pl_url, TRENDING_TTL))


def playlist_items(playlist_id):
    """Videos inside a playlist (1 quota unit, cached 6h) — open & bulk-download."""
    if not has_key():
        raise IOError("Discover is unavailable (no YouTube key).")
    url = f"{BASE}/playlistItems?part=snippet&maxResults=25&playlistId={playlist_id}&key={api_key()}"
    return _parse_playlist_items(_cached_fetch(f"plitems_{playlist_id}", url, TRENDING_TTL))


def channel_info(channel_id):
    """Channel header: title, image, subscriber & video counts, uploads playlist
    (1 quota unit, cached 6h). Powers the Discover channel view."""
    if not has_key():
        raise IOError("Discover is unavailable (no YouTube key).")
    url = f"{BASE}/channels?part=snippet,statistics,contentDetails&id={channel_id}&key={api_key()}"
    items = json.loads(_cached_fetch(f"chinfo_{channel_id}", url, TRENDING_TTL)).get("items") or []
    if not items:
        return None
    it = items[0]
    sn = it.get("snippet") or {}
    stt = it.get("statistics") or {}
    return {
        "id": channel_id,
        "title": sn.get("title", ""),
        "thumb": _thumb_url(sn.get("thumbnails")),
        "subs": None if stt.get("hiddenSubscriberCount") else stt.get("subscriberCount"),
        "videos": stt.get("videoCount"),
        "uploads": (((it.get("contentDetails") or {}).get("relatedPlaylists") or {}).get("uploads", "")),
    }


def channel_playlists(channel_id):
    """A channel's public playlists (1 quota unit, cached 6h)."""
    if not has_key():
        raise IOError("Discover is unavailable (no YouTube key).")
    url = (f"{BASE}/playlists?part=snippet&channelId={channel_id}&maxResults=15&key={api_key()}")
    arr = json.loads(_cached_fetch(f"chpls_{channel_id}", url, TRENDING_TTL)).get("items") or []
    out = []
    for it in arr:
        sn = it.get("snippet") or {}
        pid = it.get("id", "")
        if pid:
            out.append(DiscoverPlaylist(pid, sn.get("title", ""), _thumb_url(sn.get("thumbnails"))))
    return out
