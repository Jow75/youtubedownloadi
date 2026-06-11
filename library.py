"""
Managed media library for Universal Media Downloader.
=====================================================
The app can own a dedicated workspace folder (chosen by the user) with a tidy
structure, auto-route downloads into it by type, and act as a safe media
librarian — finding EXACT duplicates by content hash and cleaning them up only
after the user confirms (files go to the Recycle Bin, never a silent wipe).

Exact duplicate detection here is deterministic (size + SHA-256), which is the
right tool for "is this the same file". The AI fuzzy dedup (same song across
different uploads) lives in ai.py / the history view — the two complement.

Pure logic, NO Streamlit — importable/testable and identical when frozen.
"""

import hashlib
import json
import os
from pathlib import Path

import licensing

APP_FOLDER = "Universal Media Downloader"

# Subfolders created inside the workspace (designed for future expansion).
STRUCTURE = [
    "Music/MP3", "Music/M4A", "Music/FLAC",
    "Videos/MP4", "Videos/MKV",
    "Images/JPEG", "Images/PNG",
    "Downloads", "AI Library", "Metadata", "Logs", "Temp",
]


# --------------------------------------------------------------------------- #
# Settings
# --------------------------------------------------------------------------- #
def _settings_file():
    return licensing.config_dir() / "library.json"


def load():
    try:
        p = _settings_file()
        return json.loads(p.read_text(encoding="utf-8")) if p.is_file() else {}
    except (OSError, ValueError):
        return {}


def save(root=None, enabled=None, configured=None):
    d = load()
    if root is not None:
        d["root"] = root
    if enabled is not None:
        d["enabled"] = bool(enabled)
    if configured is not None:
        d["configured"] = bool(configured)
    try:
        _settings_file().write_text(json.dumps(d), encoding="utf-8")
    except OSError:
        pass


def default_root():
    return str(Path.home() / "Downloads" / APP_FOLDER)


def get_root():
    return load().get("root") or default_root()


def is_enabled():
    return bool(load().get("enabled"))


def is_configured():
    """Has the user been through first-run setup?"""
    return bool(load().get("configured"))


# --------------------------------------------------------------------------- #
# Structure + routing
# --------------------------------------------------------------------------- #
def ensure_structure(root=None):
    """Create the workspace folder tree. Returns the list of folders made/kept."""
    root = root or get_root()
    made = []
    for sub in STRUCTURE:
        d = os.path.join(root, *sub.split("/"))
        try:
            os.makedirs(d, exist_ok=True)
            made.append(d)
        except OSError:
            pass
    return made


def route(fmt, audio_codec="mp3", root=None):
    """Where a finished download of this type should live in the library."""
    root = root or get_root()
    if fmt == "audio":
        sub = ("Music", "M4A") if audio_codec == "m4a" else ("Music", "MP3")
    else:
        sub = ("Videos", "MP4")
    d = os.path.join(root, *sub)
    os.makedirs(d, exist_ok=True)
    return d


def in_library(path, root=None):
    root = os.path.normcase(os.path.abspath(root or get_root()))
    try:
        return os.path.normcase(os.path.abspath(path)).startswith(root)
    except Exception:  # noqa: BLE001
        return False


# --------------------------------------------------------------------------- #
# Duplicate detection (exact, by content hash)
# --------------------------------------------------------------------------- #
def file_hash(path, chunk=1 << 20):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(chunk), b""):
            h.update(block)
    return h.hexdigest()


def scan_duplicates(folders, exts=None, progress=None):
    """Find exact duplicates across the given folders.

    Fast path: group by size first (cheap), only hash files that share a size.
    Returns a list of groups: {keeper, dups:[paths], size, recover, reason}.
    `progress(done, total)` is called while hashing.
    """
    if isinstance(folders, (str, os.PathLike)):
        folders = [folders]
    exts = {e.lower() for e in exts} if exts else None

    by_size = {}
    for folder in folders:
        for dirpath, _dirs, names in os.walk(folder):
            for n in names:
                if exts and os.path.splitext(n)[1].lower() not in exts:
                    continue
                p = os.path.join(dirpath, n)
                try:
                    sz = os.path.getsize(p)
                except OSError:
                    continue
                if sz > 0:
                    by_size.setdefault(sz, []).append(p)

    candidates = [(sz, ps) for sz, ps in by_size.items() if len(ps) > 1]
    total = sum(len(ps) for _sz, ps in candidates)
    done = 0
    groups = []
    for sz, ps in candidates:
        by_hash = {}
        for p in ps:
            try:
                hsh = file_hash(p)
            except OSError:
                hsh = None
            done += 1
            if progress:
                progress(done, total)
            if hsh:
                by_hash.setdefault(hsh, []).append(p)
        for plist in by_hash.values():
            if len(plist) > 1:
                # Keep the copy that's inside the library, else the shortest path
                # (usually the "main" one); the rest are duplicates.
                ordered = sorted(plist, key=lambda x: (0 if in_library(x) else 1,
                                                       len(x), x))
                groups.append({
                    "keeper": ordered[0],
                    "dups": ordered[1:],
                    "size": sz,
                    "recover": sz * (len(ordered) - 1),
                    "reason": "Identical content (same size + SHA-256 hash)",
                })
    groups.sort(key=lambda g: g["recover"], reverse=True)
    return groups


# --------------------------------------------------------------------------- #
# Safe deletion (Recycle Bin)
# --------------------------------------------------------------------------- #
def recycle(paths):
    """Send files to the Recycle Bin (recoverable). Returns (count, to_bin).
    to_bin is False if we had to fall back to permanent deletion."""
    paths = [os.path.abspath(p) for p in paths if os.path.exists(p)]
    if not paths:
        return 0, True
    try:
        from win32com.shell import shell, shellcon
        flags = (shellcon.FOF_ALLOWUNDO | shellcon.FOF_NOCONFIRMATION
                 | shellcon.FOF_SILENT | shellcon.FOF_NOERRORUI)
        src = "\0".join(paths) + "\0\0"
        rc, aborted = shell.SHFileOperation(
            (0, shellcon.FO_DELETE, src, None, flags, None, None))
        if rc == 0 and not aborted:
            return sum(0 if os.path.exists(p) else 1 for p in paths), True
    except Exception:  # noqa: BLE001
        pass
    # Last-resort permanent delete (only reached if the Recycle Bin op failed).
    n = 0
    for p in paths:
        try:
            os.remove(p)
            n += 1
        except OSError:
            pass
    return n, False
