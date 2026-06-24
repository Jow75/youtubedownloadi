"""
Per-file artist resolution for the desktop — a faithful port of the mobile
app's MediaMeta artist logic, so both products group artists identically.

Priority (never AI first): embedded tag (platform metadata, written by yt-dlp
--embed-metadata) -> "Artist - Title" filename -> AI cache -> "Unknown".
A collaboration belongs to EACH artist (split on ft/feat/&/x/,/with…); and
case/spacing variants merge into one ("BAD BUNNY" == "Bad Bunny").
"""

import os
import re
import unicodedata

# Separators that join collaborating artists. "x"/"and"/"vs" only as whole words.
_SPLIT = re.compile(
    r"(?i)\s*(?:,|;|/|&|＋|\+|×|\bx\b|\bvs\.?\b|\band\b|\bfeat\.?\b|\bft\.?\b|\bfeaturing\b|\bwith\b)\s*")
_DASH = re.compile(r"\s[-–—]\s")
_FNAME = re.compile(r"^(.{1,60}?)\s[-–—]\s+.+")


def artist_key(name):
    """Normalized identity — collapses case, spacing, punctuation AND accents, so
    'Beyoncé' == 'Beyonce' and 'BAD BUNNY' == 'Bad Bunny' map to one key."""
    s = unicodedata.normalize("NFKD", (name or "").lower())
    s = "".join(c for c in s if not unicodedata.combining(c))   # fold accents é→e
    return re.sub(r"[^a-z0-9]", "", s)


def _case_score(s):
    # Mixed/Title (2) beats all-lower (1) beats ALL CAPS (0).
    if s == s.upper() and s != s.lower():
        return 0
    if s == s.lower():
        return 1
    return 2


def _clean_artist(s):
    x = (s or "").strip()
    x = re.sub(r"(?i)\s*-\s*Topic\b", "", x)
    x = re.sub(r"(?i)\bVEVO\b", "", x)
    x = re.sub(r"[\(\)\[\]\{\}]", " ", x)        # drop stray brackets from "(feat. …)"
    x = re.sub(r"\s+", " ", x).strip()
    return x.strip(" -–—,&/.\"'").strip()


def _split(s):
    if not s or not s.strip():
        return []
    return [p.strip() for p in _SPLIT.split(s) if p.strip()]


def _artist_segment(name):
    """The artist portion of a filename: text before the first ' - '/'–'/'—'."""
    m = _DASH.search(name or "")
    return name[:m.start()] if m else ""


def _embedded_artist(path):
    try:
        import mutagen
        f = mutagen.File(path, easy=True)
        if f and f.tags:
            for k in ("artist", "albumartist"):
                v = f.tags.get(k)
                if v:
                    a = (v[0] if isinstance(v, list) else str(v)).strip()
                    if a and a.lower() not in ("unknown", "various artists"):
                        return a
    except Exception:  # noqa: BLE001
        pass
    return None


def _filename_artist(path):
    n = os.path.splitext(os.path.basename(path))[0]
    m = _FNAME.match(n)
    return (m.group(1).strip() if m else "") or "Unknown"


def _ai_artist(path, ai_cache):
    if not ai_cache:
        return None
    n = os.path.splitext(os.path.basename(path))[0]
    info = ai_cache.get(n) or {}
    return info.get("artist") or None


def primary_artist(path, ai_cache=None):
    """Single best artist (metadata-first, AI last)."""
    a = _embedded_artist(path)
    if a:
        return a
    fn = _filename_artist(path)
    if fn and fn != "Unknown":
        return fn
    ai = _ai_artist(path, ai_cache)
    if ai:
        return ai
    return "Unknown"


def artists_of(path, ai_cache=None):
    """EVERY individual artist a file belongs to (a collab attaches to each).
    Mirrors MediaMeta.artists: split the resolved credit + the filename's
    pre-dash segment, clean + de-dupe by normalized key."""
    raw = list(_split(primary_artist(path, ai_cache)))
    raw += _split(_artist_segment(os.path.splitext(os.path.basename(path))[0]))
    out, seen = [], set()
    for a in raw:
        c = _clean_artist(a)
        k = artist_key(c)
        if c and c.lower() != "unknown" and k and k not in seen:
            seen.add(k)
            out.append(c)
    return out or ["Unknown"]


def collapse_artist_counts(counts):
    """{name: count} -> [(best_display, total)], merging case/spacing variants.
    Best display = most-used spelling, then nicest case, then longest."""
    by = {}
    for name, c in counts.items():
        k = artist_key(name)
        if k:
            by.setdefault(k, []).append((name, c))
    out = []
    for variants in by.values():
        total = sum(c for _, c in variants)
        best = max(variants, key=lambda nc: (nc[1], _case_score(nc[0]), len(nc[0])))[0]
        out.append((best, total))
    return out
