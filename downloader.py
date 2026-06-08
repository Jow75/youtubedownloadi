"""
Core download engine for Universal Media Downloader.

Pure logic, NO Streamlit — so it can be unit-tested on its own and reused.
The Streamlit UI lives in app.py and imports from here.

Handles: format/quality selection, MP3/M4A audio, embedded cover-art + tags,
optional aria2c turbo (http/https only, never HLS), optional cookies.txt,
playlist listing, clip trimming, and saving straight to a chosen folder.
"""

import glob
import os
import re
import shutil
import tempfile
import time
import uuid

import yt_dlp
from yt_dlp.utils import download_range_func

# extractor_retries rides out anonymous rate limiting (X especially).
# concurrent_fragment_downloads speeds up fragmented (HLS/DASH) downloads.
COMMON_OPTS = {
    "quiet": True,
    "no_warnings": True,
    "noplaylist": True,
    "retries": 10,
    "fragment_retries": 10,
    "extractor_retries": 3,
    "geo_bypass": True,
    "concurrent_fragment_downloads": 4,
}


# --------------------------------------------------------------------------- #
# Small helpers
# --------------------------------------------------------------------------- #
def sanitize_filename(name):
    if not name:
        return "media"
    name = re.sub(r'[\\/*?:"<>|]', "", name)
    name = re.sub(r"\s+", " ", name).strip().rstrip(". ")
    return name[:150] or "media"


def human_duration(seconds):
    try:
        seconds = int(seconds)
    except (TypeError, ValueError):
        return ""
    h, rem = divmod(seconds, 3600)
    m, s = divmod(rem, 60)
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"


def unique_path(folder, filename):
    base, ext = os.path.splitext(filename)
    candidate = os.path.join(folder, filename)
    i = 1
    while os.path.exists(candidate):
        candidate = os.path.join(folder, f"{base} ({i}){ext}")
        i += 1
    return candidate


def parse_time(text):
    """'1:23', '1:02:03', or '83' -> seconds (float). Empty/invalid -> None."""
    text = (text or "").strip()
    if not text:
        return None
    try:
        if ":" in text:
            sec = 0.0
            for part in text.split(":"):
                sec = sec * 60 + float(part)
            return sec
        return float(text)
    except ValueError:
        return None


def aria2c_available():
    return shutil.which("aria2c") is not None


def net_opts(cookiefile=""):
    """Only a cookies.txt FILE is supported (safe: an empty/invalid path simply
    means 'no cookies', so it can never break a public download)."""
    cf = (cookiefile or "").strip().strip('"')
    if cf and os.path.isfile(cf):
        return {"cookiefile": cf}
    return {}


def downloader_opts(use_aria2c):
    """aria2c for http/https only — HLS/DASH stay native, so X never breaks."""
    if use_aria2c and aria2c_available():
        return {
            "external_downloader": {"http": "aria2c", "https": "aria2c"},
            "external_downloader_args": {"aria2c": ["-x16", "-s16", "-k1M"]},
        }
    return {}


def expected_ext(fmt, audio_codec):
    if fmt == "video":
        return "mp4"
    return "m4a" if audio_codec == "m4a" else "mp3"


# --------------------------------------------------------------------------- #
# yt-dlp option builders
# --------------------------------------------------------------------------- #
def media_opts(fmt, quality, audio_codec, embed_meta):
    """Format selection + post-processors (audio extract, metadata, cover art)."""
    opts = {}
    pps = []
    if fmt == "audio":
        if audio_codec == "m4a":
            opts["format"] = "bestaudio[ext=m4a]/bestaudio/best"
        else:
            opts["format"] = "bestaudio/best"
            pps.append({"key": "FFmpegExtractAudio",
                        "preferredcodec": "mp3", "preferredquality": "192"})
    else:
        if quality == "720p":
            sel = "bestvideo[height<=720]+bestaudio/best[height<=720]/best"
        elif quality == "480p":
            sel = "bestvideo[height<=480]+bestaudio/best[height<=480]/best"
        else:
            sel = "bestvideo+bestaudio/best"
        opts["format"] = sel
        opts["merge_output_format"] = "mp4"

    if embed_meta:
        # Write tags (title/artist/etc) and embed the thumbnail as cover art.
        pps.append({"key": "FFmpegMetadata", "add_metadata": True})
        pps.append({"key": "EmbedThumbnail", "already_have_thumbnail": False})
        opts["writethumbnail"] = True

    if pps:
        opts["postprocessors"] = pps
    return opts


# --------------------------------------------------------------------------- #
# Extraction
# --------------------------------------------------------------------------- #
def extract_meta(url, cookiefile=""):
    """Probe a single item (no download)."""
    opts = {**COMMON_OPTS, "skip_download": True, **net_opts(cookiefile)}
    with yt_dlp.YoutubeDL(opts) as ydl:
        info = ydl.extract_info(url, download=False)
    if info.get("_type") == "playlist" and info.get("entries"):
        info = info["entries"][0]
    return {
        "title": info.get("title") or "media",
        "uploader": info.get("uploader") or info.get("channel") or "",
        "duration": info.get("duration"),
        "thumbnail": info.get("thumbnail"),
        "extractor": info.get("extractor_key") or info.get("extractor") or "",
    }


def list_playlist(url, cookiefile=""):
    """Flat-list a playlist/channel's items (fast, no per-item probing)."""
    opts = {**COMMON_OPTS, "skip_download": True,
            "extract_flat": "in_playlist", "noplaylist": False,
            **net_opts(cookiefile)}
    with yt_dlp.YoutubeDL(opts) as ydl:
        info = ydl.extract_info(url, download=False)
    raw = info.get("entries") if info.get("entries") is not None else [info]
    entries = []
    for e in raw:
        if not e:
            continue
        eurl = e.get("url") or e.get("webpage_url") or e.get("id")
        if eurl:
            entries.append({"url": eurl, "title": e.get("title") or "media"})
    return {"title": info.get("title") or "playlist", "entries": entries}


# --------------------------------------------------------------------------- #
# Download
# --------------------------------------------------------------------------- #
def download_to_folder(url, fmt, quality, audio_codec, dest_dir, title,
                       use_aria2c=False, cookiefile="", embed_meta=True,
                       trim=None, progress_cb=None, status_cb=None):
    """
    Download + process into a temp dir, then MOVE the finished file into
    dest_dir. Returns the final saved path. `trim` is an optional (start, end)
    tuple in seconds.
    """
    work_dir = os.path.join(tempfile.gettempdir(), f"umd_{uuid.uuid4().hex}")
    os.makedirs(work_dir, exist_ok=True)
    safe_title = sanitize_filename(title)
    outtmpl = os.path.join(work_dir, f"{safe_title}.%(ext)s")

    def _hook(d):
        if d.get("status") == "downloading":
            total = d.get("total_bytes") or d.get("total_bytes_estimate")
            done = d.get("downloaded_bytes") or 0
            if total and progress_cb:
                progress_cb(min(done / total, 1.0))
            if status_cb:
                speed = d.get("speed")
                eta = d.get("eta")
                tot = f" / {total / 1024 / 1024:.1f} MB" if total else ""
                spd = f" · {speed / 1024 / 1024:.1f} MB/s" if speed else ""
                et = f" · ~{eta}s left" if eta else ""
                status_cb(f"⬇️ Downloading {done / 1024 / 1024:.1f} MB{tot}{spd}{et}")
        elif d.get("status") == "finished" and status_cb:
            if progress_cb:
                progress_cb(1.0)
            status_cb("🎬 Processing with ffmpeg (convert / merge / tag)…")

    ydl_opts = {
        **COMMON_OPTS,
        "outtmpl": outtmpl,
        "progress_hooks": [_hook],
        **media_opts(fmt, quality, audio_codec, embed_meta),
        **net_opts(cookiefile),
    }

    if trim:
        start, end = trim
        ydl_opts["download_ranges"] = download_range_func(None, [(start, end)])
        ydl_opts["force_keyframes_at_cuts"] = True
        # Sections require the native/ffmpeg downloader; aria2c can't slice.
    else:
        ydl_opts.update(downloader_opts(use_aria2c))

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([url])

        ext = expected_ext(fmt, audio_codec)
        candidates = [f for f in glob.glob(os.path.join(work_dir, "*"))
                      if not f.endswith(".part")]
        if not candidates:
            raise RuntimeError("Download finished but no output file was produced.")
        # Ignore leftover thumbnail/temp files; prefer the real media extension.
        media = [f for f in candidates
                 if f.lower().endswith((".mp3", ".m4a", ".mp4", ".webm", ".mkv"))]
        pool = media or candidates
        exact = [f for f in pool if f.lower().endswith(f".{ext}")]
        src = exact[0] if exact else max(pool, key=os.path.getsize)

        os.makedirs(dest_dir, exist_ok=True)
        final = unique_path(dest_dir, os.path.basename(src))
        shutil.move(src, final)
        return final
    finally:
        shutil.rmtree(work_dir, ignore_errors=True)


def download_with_retry(url, fmt, quality, audio_codec, dest_dir, title,
                        use_aria2c=False, cookiefile="", embed_meta=True,
                        trim=None, progress_cb=None, status_cb=None, attempts=2):
    """Retry once after a short backoff — mainly to ride out X rate limiting."""
    last = None
    for attempt in range(attempts):
        try:
            return download_to_folder(
                url, fmt, quality, audio_codec, dest_dir, title,
                use_aria2c, cookiefile, embed_meta, trim, progress_cb, status_cb)
        except Exception as exc:  # noqa: BLE001
            last = exc
            if attempt < attempts - 1:
                if status_cb:
                    status_cb(f"⚠️ Hiccup — retrying in 3s…")
                time.sleep(3)
    raise last
