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
import shutil
from datetime import datetime
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


def _real(path):
    """Canonical identity of a physical file (case-insensitive, symlinks
    resolved) — so the SAME file is never treated as two different ones."""
    try:
        return os.path.normcase(os.path.realpath(path))
    except OSError:
        return os.path.normcase(os.path.abspath(path))


def collapse_folders(folders):
    """Drop folders that sit inside another folder in the list, so an
    overlapping pair (e.g. Downloads + Downloads/Library) is walked only ONCE.
    Returns existing, de-duplicated, non-overlapping absolute folders."""
    norm = sorted({_real(f) for f in folders if f and os.path.isdir(f)}, key=len)
    kept = []
    for f in norm:
        if not any(f == k or f.startswith(k + os.sep) for k in kept):
            kept.append(f)
    return kept


def scan_duplicates(folders, exts=None, progress=None):
    """Find EXACT duplicate files (identical content) across the given folders.

    Safety guarantees (this is destructive territory):
      * Overlapping folders are collapsed, and every physical file is indexed
        exactly ONCE (by realpath) — a file can never be a duplicate of itself.
      * Matching is by content only: group by size (cheap), then SHA-256 hash.
        Never by filename or partial metadata.
      * A group is reported only if it has 2+ DISTINCT physical files.

    Returns groups: {keeper, dups:[paths], size, hash, hash_short, recover,
    reason}. `progress(done, total)` is called while hashing.
    """
    if isinstance(folders, (str, os.PathLike)):
        folders = [folders]
    exts = {e.lower() for e in exts} if exts else None

    by_size = {}
    seen = set()
    for folder in collapse_folders(folders):
        for dirpath, _dirs, names in os.walk(folder):
            for n in names:
                if exts and os.path.splitext(n)[1].lower() not in exts:
                    continue
                p = os.path.join(dirpath, n)
                rid = _real(p)
                if rid in seen:            # already indexed this physical file
                    continue
                seen.add(rid)
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
        for hsh, plist in by_hash.items():
            # Final guard: keep only DISTINCT physical files (no self-pairs).
            uniq, rids = [], set()
            for p in plist:
                rid = _real(p)
                if rid not in rids:
                    rids.add(rid)
                    uniq.append(p)
            if len(uniq) < 2:
                continue
            # Keeper = the copy inside the library, else shortest/earliest path.
            ordered = sorted(uniq, key=lambda x: (0 if in_library(x) else 1,
                                                  len(x), x))
            groups.append({
                "keeper": ordered[0],
                "dups": ordered[1:],
                "size": sz,
                "hash": hsh,
                "hash_short": hsh[:16],
                "recover": sz * (len(ordered) - 1),
                "reason": "Identical content — same size and same SHA-256 hash",
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


# --------------------------------------------------------------------------- #
# Quarantine — the safe middle step (move, don't delete; restorable)
# --------------------------------------------------------------------------- #
def quarantine_root(root=None):
    return os.path.join(root or get_root(), "Quarantine", "Duplicates")


def _unique_dest(path):
    base, ext = os.path.splitext(path)
    i, cand = 1, path
    while os.path.exists(cand):
        cand = f"{base} ({i}){ext}"
        i += 1
    return cand


def quarantine(paths, root=None):
    """MOVE files into a timestamped quarantine batch (never deletes). Writes a
    manifest mapping each file back to its original location so it can be
    restored. Returns (batch_dir, moved_count)."""
    qroot = quarantine_root(root)
    batch = os.path.join(qroot, datetime.now().strftime("%Y-%m-%d_%H-%M-%S"))
    os.makedirs(batch, exist_ok=True)
    manifest = []
    for p in paths:
        if not os.path.exists(p):
            continue
        dest = _unique_dest(os.path.join(batch, os.path.basename(p)))
        try:
            shutil.move(p, dest)
            manifest.append({"original": os.path.abspath(p),
                             "quarantined": dest,
                             "size": os.path.getsize(dest)})
        except (OSError, shutil.Error):
            pass
    try:
        with open(os.path.join(batch, "_manifest.json"), "w",
                  encoding="utf-8") as f:
            json.dump({"created": datetime.now().isoformat(), "items": manifest},
                      f, ensure_ascii=False, indent=2)
    except OSError:
        pass
    return batch, len(manifest)


def list_quarantine(root=None):
    """Return quarantine batches newest-first: {batch, created, items[], bytes}."""
    qroot = quarantine_root(root)
    out = []
    if not os.path.isdir(qroot):
        return out
    for name in sorted(os.listdir(qroot), reverse=True):
        batch = os.path.join(qroot, name)
        mf = os.path.join(batch, "_manifest.json")
        if not os.path.isfile(mf):
            continue
        try:
            with open(mf, encoding="utf-8") as f:
                data = json.load(f)
        except (OSError, ValueError):
            continue
        items = [it for it in data.get("items", [])
                 if os.path.exists(it.get("quarantined", ""))]
        out.append({"batch": batch, "name": name,
                    "created": data.get("created", name),
                    "items": items,
                    "bytes": sum(it.get("size", 0) for it in items)})
    return out


def restore_batch(batch):
    """Move every quarantined file back to its original location. Returns count."""
    mf = os.path.join(batch, "_manifest.json")
    if not os.path.isfile(mf):
        return 0
    try:
        with open(mf, encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, ValueError):
        return 0
    n = 0
    for it in data.get("items", []):
        src, dst = it.get("quarantined"), it.get("original")
        if src and dst and os.path.exists(src):
            try:
                os.makedirs(os.path.dirname(dst), exist_ok=True)
                shutil.move(src, _unique_dest(dst))
                n += 1
            except (OSError, shutil.Error):
                pass
    if not [it for it in data.get("items", []) if os.path.exists(it.get("quarantined", ""))]:
        shutil.rmtree(batch, ignore_errors=True)
    return n


def purge_batch(batch):
    """Permanently remove a quarantine batch (to the Recycle Bin). Returns count."""
    files = []
    for dirpath, _d, names in os.walk(batch):
        for n in names:
            if n != "_manifest.json":
                files.append(os.path.join(dirpath, n))
    cnt, _to_bin = recycle(files)
    shutil.rmtree(batch, ignore_errors=True)
    return cnt
