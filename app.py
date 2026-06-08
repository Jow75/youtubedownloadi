"""
Universal Media Downloader (local edition)
==========================================
A Streamlit app that downloads media from YouTube, X (Twitter), Reddit,
Instagram, and any other site supported by yt-dlp.

Designed to run LOCALLY on your own machine, because:
  * Modern YouTube scrambles stream URLs with a JavaScript challenge, so
    yt-dlp needs a JS runtime (Node.js / Deno) + the yt-dlp-ejs solver scripts.
  * Cloud/datacenter IPs additionally get HTTP 403 blocks.
A residential IP + Node.js make the difference, just like browser extensions.

KEY DESIGN CHOICE: finished files are saved DIRECTLY to a folder on this PC
(your Downloads folder by default). There is no browser download, so download
managers like IDM never get a chance to interfere.

Requirements: streamlit, yt-dlp, yt-dlp-ejs (pip), plus ffmpeg and Node.js on PATH.
"""

import glob
import os
import re
import shutil
import tempfile
import uuid
from pathlib import Path

import streamlit as st
import yt_dlp

# --------------------------------------------------------------------------- #
# Page configuration
# --------------------------------------------------------------------------- #
st.set_page_config(
    page_title="Universal Media Downloader",
    page_icon="⬇️",
    layout="centered",
    initial_sidebar_state="expanded",
)

DEFAULT_DOWNLOAD_DIR = str(Path.home() / "Downloads")

# --------------------------------------------------------------------------- #
# Shared yt-dlp options
# --------------------------------------------------------------------------- #
# concurrent_fragment_downloads pulls multiple DASH fragments at once, which
# speeds up downloads when your internet has spare bandwidth. The real ceiling
# is still (a) your internet speed and (b) YouTube's per-connection throttling.
COMMON_OPTS = {
    "quiet": True,
    "no_warnings": True,
    "noplaylist": True,
    "retries": 10,
    "fragment_retries": 10,
    "geo_bypass": True,
    "concurrent_fragment_downloads": 4,
}


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #
def sanitize_filename(name):
    """Strip characters that are illegal in Windows/macOS/Linux filenames."""
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
    """Return a path inside `folder` that doesn't collide with an existing file."""
    base, ext = os.path.splitext(filename)
    candidate = os.path.join(folder, filename)
    i = 1
    while os.path.exists(candidate):
        candidate = os.path.join(folder, f"{base} ({i}){ext}")
        i += 1
    return candidate


def open_in_explorer(path):
    """Open a folder (or the parent of a file) in the OS file manager."""
    try:
        target = path if os.path.isdir(path) else os.path.dirname(path)
        os.startfile(target)  # Windows
        return True
    except Exception:  # noqa: BLE001
        return False


@st.cache_data(show_spinner=False, ttl=600)
def fetch_metadata(url):
    """Probe a URL with yt-dlp WITHOUT downloading. Cached to avoid re-hitting
    the network on Streamlit's frequent re-runs."""
    ydl_opts = {**COMMON_OPTS, "skip_download": True}
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
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


def expected_ext(fmt, audio_codec):
    if fmt == "video":
        return "mp4"
    return "m4a" if audio_codec == "m4a" else "mp3"


def build_format(fmt, quality, audio_codec):
    """Return the yt-dlp options for the chosen format/quality."""
    if fmt == "audio":
        if audio_codec == "m4a":
            # FAST path: grab the original AAC audio, no re-encoding at all.
            return {"format": "bestaudio[ext=m4a]/bestaudio/best"}
        # MP3 path: re-encode to 192 kbps with ffmpeg's LAME encoder (CPU work).
        return {
            "format": "bestaudio/best",
            "postprocessors": [
                {
                    "key": "FFmpegExtractAudio",
                    "preferredcodec": "mp3",
                    "preferredquality": "192",
                }
            ],
        }
    # Video: cap height, merge best video + best audio into MP4.
    if quality == "720p":
        selector = "bestvideo[height<=720]+bestaudio/best[height<=720]/best"
    elif quality == "480p":
        selector = "bestvideo[height<=480]+bestaudio/best[height<=480]/best"
    else:
        selector = "bestvideo+bestaudio/best"
    return {"format": selector, "merge_output_format": "mp4"}


def download_to_folder(url, fmt, quality, audio_codec, dest_dir, title,
                       progress_cb=None, status_cb=None):
    """
    Download + process into a temp dir, then MOVE the finished file into
    `dest_dir`. Returns the final saved path.

    Saving on the server side (this PC) means no browser download happens, so
    download managers such as IDM never intercept anything.
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
        elif d.get("status") == "finished":
            if progress_cb:
                progress_cb(1.0)
            if status_cb:
                if fmt == "audio" and audio_codec == "mp3":
                    status_cb("🎬 Converting to MP3 with ffmpeg…")
                elif fmt == "video":
                    status_cb("🎬 Merging video + audio with ffmpeg…")
                else:
                    status_cb("📦 Finalizing…")

    ydl_opts = {
        **COMMON_OPTS,
        "outtmpl": outtmpl,
        "progress_hooks": [_hook],
        **build_format(fmt, quality, audio_codec),
    }

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([url])

        ext = expected_ext(fmt, audio_codec)
        candidates = [
            f for f in glob.glob(os.path.join(work_dir, "*"))
            if not f.endswith(".part")
        ]
        if not candidates:
            raise RuntimeError("Download finished but no output file was produced.")
        exact = [f for f in candidates if f.lower().endswith(f".{ext}")]
        src = exact[0] if exact else max(candidates, key=os.path.getsize)

        os.makedirs(dest_dir, exist_ok=True)
        final = unique_path(dest_dir, os.path.basename(src))
        shutil.move(src, final)
        return final
    finally:
        shutil.rmtree(work_dir, ignore_errors=True)


# --------------------------------------------------------------------------- #
# Sidebar: settings
# --------------------------------------------------------------------------- #
with st.sidebar:
    st.header("⚙️ Settings")
    dest_dir = st.text_input("Save downloads to folder", value=DEFAULT_DOWNLOAD_DIR)
    st.caption(
        "Files are written straight to this folder on this PC. There's no "
        "browser download, so download managers like **IDM won't interfere**."
    )
    if st.button("📂 Open this folder", use_container_width=True):
        if not open_in_explorer(dest_dir):
            st.warning("Couldn't open that folder — check the path.")
    st.divider()
    st.caption("💡 Tip: **M4A (original)** audio skips conversion and is much faster "
               "than MP3. For bigger downloads, a faster internet connection helps most.")


# --------------------------------------------------------------------------- #
# Main
# --------------------------------------------------------------------------- #
st.title("⬇️ Universal Media Downloader")

mode = st.radio("Mode", ["🔗 Single link", "📚 Bulk (many links)"], horizontal=True)

# =========================================================================== #
# SINGLE MODE
# =========================================================================== #
if mode == "🔗 Single link":
    url = st.text_input(
        "Media link",
        placeholder="https://www.youtube.com/watch?v=...",
        label_visibility="collapsed",
    )

    if url != st.session_state.get("last_url"):
        st.session_state.last_url = url
        st.session_state.pop("saved_path", None)

    metadata = None
    if url.strip():
        with st.spinner("Fetching media details…"):
            try:
                metadata = fetch_metadata(url.strip())
            except Exception as exc:  # noqa: BLE001
                st.error(
                    "Couldn't read that link. It may be private, unsupported, or "
                    f"need a login.\n\nDetails: `{exc}`"
                )

    if metadata:
        st.success(f"**Found:** {metadata['title']}")
        c1, c2 = st.columns([2, 1])
        with c1:
            if metadata["uploader"]:
                st.write(f"**By:** {metadata['uploader']}")
            if metadata["duration"]:
                st.write(f"**Length:** {human_duration(metadata['duration'])}")
            if metadata["extractor"]:
                st.write(f"**Source:** {metadata['extractor']}")
        with c2:
            if metadata["thumbnail"]:
                st.image(metadata["thumbnail"], use_container_width=True)

        st.divider()

        fmt_label = st.radio("Format", ["🎬 Video (MP4)", "🎵 Audio Only"],
                             horizontal=True)
        is_video = fmt_label.startswith("🎬")
        fmt = "video" if is_video else "audio"
        quality, audio_codec = None, "mp3"

        if is_video:
            quality = st.selectbox("Quality", ["Best Available", "720p", "480p"])
        else:
            audio_choice = st.radio(
                "Audio format",
                ["MP3 (universal — converted)", "M4A (original — faster)"],
                horizontal=True,
                help="M4A copies the original audio with no re-encoding, so it's "
                     "much faster. MP3 plays everywhere but must be converted.",
            )
            audio_codec = "mp3" if audio_choice.startswith("MP3") else "m4a"

        if st.button("⬇️ Download", type="primary", use_container_width=True):
            st.session_state.pop("saved_path", None)
            bar = st.progress(0.0)
            status = st.empty()
            status.info("⏳ Starting…")
            try:
                path = download_to_folder(
                    url.strip(), fmt, quality, audio_codec, dest_dir,
                    metadata["title"],
                    progress_cb=lambda f: bar.progress(f),
                    status_cb=lambda t: status.info(t),
                )
                bar.progress(1.0)
                st.session_state.saved_path = path
                status.empty()
            except Exception as exc:  # noqa: BLE001
                bar.empty()
                status.error(f"Failed: `{exc}`")

        if st.session_state.get("saved_path"):
            saved = st.session_state.saved_path
            st.balloons()
            st.success(f"🎉 Saved to your folder:\n\n`{saved}`")
            if st.button("📂 Open folder", use_container_width=True):
                open_in_explorer(saved)

# =========================================================================== #
# BULK MODE
# =========================================================================== #
else:
    st.caption(
        "Paste links **one per line**. Put each link in the column for the format "
        "you want, then hit **Download all** — every file is saved to your folder."
    )
    col_v, col_a = st.columns(2)
    with col_v:
        st.markdown("### 🎬 Video → MP4")
        video_links = st.text_area(
            "video links", height=220, label_visibility="collapsed",
            placeholder="https://...\nhttps://...\nhttps://...",
        )
        bulk_quality = st.selectbox("Quality for all videos",
                                    ["Best Available", "720p", "480p"])
    with col_a:
        st.markdown("### 🎵 Audio → MP3")
        audio_links = st.text_area(
            "audio links", height=220, label_visibility="collapsed",
            placeholder="https://...\nhttps://...\nhttps://...",
        )

    def _parse(text):
        return [ln.strip() for ln in text.splitlines() if ln.strip()]

    if st.button("⬇️ Download all", type="primary", use_container_width=True):
        jobs = ([(u, "video") for u in _parse(video_links)]
                + [(u, "audio") for u in _parse(audio_links)])
        if not jobs:
            st.warning("Paste at least one link into a column first.")
        else:
            st.write(f"### Downloading {len(jobs)} item(s)…")
            overall = st.progress(0.0)
            ok = 0
            for i, (u, f) in enumerate(jobs, 1):
                row = st.empty()
                bar = st.progress(0.0)
                row.info(f"[{i}/{len(jobs)}] 🔎 Fetching… {u}")
                try:
                    info = fetch_metadata(u)
                    row.info(f"[{i}/{len(jobs)}] ⬇️ {info['title']}")
                    path = download_to_folder(
                        u, f, bulk_quality, "mp3", dest_dir, info["title"],
                        progress_cb=lambda x, b=bar: b.progress(x),
                        status_cb=None,
                    )
                    bar.progress(1.0)
                    row.success(f"[{i}/{len(jobs)}] ✅ {os.path.basename(path)}")
                    ok += 1
                except Exception as exc:  # noqa: BLE001
                    bar.empty()
                    row.error(f"[{i}/{len(jobs)}] ❌ {u}\n\n`{exc}`")
                overall.progress(i / len(jobs))

            if ok:
                st.balloons()
            st.success(f"Done — saved **{ok} of {len(jobs)}** to `{dest_dir}`. "
                       "Use **📂 Open this folder** in the sidebar to see them.")

# --------------------------------------------------------------------------- #
# Footer
# --------------------------------------------------------------------------- #
st.divider()
st.caption(
    "Built with Streamlit + yt-dlp + ffmpeg, running locally. "
    "Only download content you have the rights to."
)
