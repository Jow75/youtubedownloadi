"""
Universal Media Downloader
==========================
A single-file Streamlit app that downloads media from YouTube, X (Twitter),
Reddit, Instagram, and any other site supported by yt-dlp.

- Paste a link -> the app quietly fetches the title (and a preview).
- Choose Video (MP4) or Audio Only (MP3) and a quality.
- Click "Prepare Download" -> the file is processed on the server with
  ffmpeg and handed back through the browser's download manager.

Deploy with the accompanying requirements.txt and packages.txt files.
"""

import glob
import os
import re
import tempfile
import uuid

import streamlit as st
import yt_dlp

# --------------------------------------------------------------------------- #
# Page configuration
# --------------------------------------------------------------------------- #
st.set_page_config(
    page_title="Universal Media Downloader",
    page_icon="⬇️",
    layout="centered",
    initial_sidebar_state="collapsed",
)


# --------------------------------------------------------------------------- #
# Shared yt-dlp options
# --------------------------------------------------------------------------- #
# Running from a cloud/datacenter IP (e.g. Streamlit Community Cloud) makes
# YouTube return "HTTP Error 403: Forbidden" for the default web-player stream
# URLs. Requesting the iOS / mobile / android player clients yields stream URLs
# that are far less likely to be blocked. We also add generous retries.
COMMON_OPTS = {
    "quiet": True,
    "no_warnings": True,
    "noplaylist": True,
    "retries": 10,
    "fragment_retries": 10,
    "geo_bypass": True,
    "extractor_args": {
        "youtube": {
            "player_client": ["ios", "mweb", "android", "web"],
        }
    },
}


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #
def sanitize_filename(name: str) -> str:
    """Strip characters that are illegal in filenames on Windows/macOS/Linux."""
    if not name:
        return "media"
    # Remove reserved characters, collapse whitespace, trim length.
    name = re.sub(r'[\\/*?:"<>|]', "", name)
    name = re.sub(r"\s+", " ", name).strip()
    name = name.rstrip(". ")  # Windows dislikes trailing dots/spaces
    return (name[:150] or "media")


def human_duration(seconds) -> str:
    """Turn a duration in seconds into H:MM:SS / M:SS."""
    try:
        seconds = int(seconds)
    except (TypeError, ValueError):
        return ""
    h, rem = divmod(seconds, 3600)
    m, s = divmod(rem, 60)
    if h:
        return f"{h}:{m:02d}:{s:02d}"
    return f"{m}:{s:02d}"


@st.cache_data(show_spinner=False, ttl=600)
def fetch_metadata(url: str) -> dict:
    """
    Quietly probe a URL with yt-dlp WITHOUT downloading anything.
    Cached so re-runs (Streamlit re-executes the script top-to-bottom on every
    interaction) don't re-hit the network for the same link.
    """
    ydl_opts = {**COMMON_OPTS, "skip_download": True}
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=False)

    # A playlist/collection URL returns a list of entries; grab the first item.
    if info.get("_type") == "playlist" and info.get("entries"):
        info = info["entries"][0]

    return {
        "title": info.get("title") or "media",
        "uploader": info.get("uploader") or info.get("channel") or "",
        "duration": info.get("duration"),
        "thumbnail": info.get("thumbnail"),
        "extractor": info.get("extractor_key") or info.get("extractor") or "",
    }


def build_format(fmt: str, quality: str) -> dict:
    """Return the yt-dlp options dict for the chosen format/quality."""
    if fmt == "audio":
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

    # Video: select a height cap, then merge best video + best audio into mp4.
    if quality == "720p":
        selector = "bestvideo[height<=720]+bestaudio/best[height<=720]/best"
    elif quality == "480p":
        selector = "bestvideo[height<=480]+bestaudio/best[height<=480]/best"
    else:  # Best Available
        selector = "bestvideo+bestaudio/best"

    return {
        "format": selector,
        "merge_output_format": "mp4",
    }


def download_media(url: str, fmt: str, quality: str, title: str):
    """
    Download + post-process into a fresh temp directory, then locate the
    finished file. Returns (filepath, filename, mime_type).
    """
    work_dir = os.path.join(tempfile.gettempdir(), f"umd_{uuid.uuid4().hex}")
    os.makedirs(work_dir, exist_ok=True)

    safe_title = sanitize_filename(title)
    outtmpl = os.path.join(work_dir, f"{safe_title}.%(ext)s")

    ydl_opts = {
        **COMMON_OPTS,
        "outtmpl": outtmpl,
        "restrictfilenames": False,
        **build_format(fmt, quality),
    }

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        ydl.download([url])

    target_ext = "mp3" if fmt == "audio" else "mp4"

    # Prefer the file with the expected extension; fall back to the largest
    # non-partial file in the directory.
    candidates = [
        f for f in glob.glob(os.path.join(work_dir, "*"))
        if not f.endswith(".part")
    ]
    if not candidates:
        raise RuntimeError("Download finished but no output file was produced.")

    exact = [f for f in candidates if f.lower().endswith(f".{target_ext}")]
    filepath = exact[0] if exact else max(candidates, key=os.path.getsize)

    filename = os.path.basename(filepath)
    mime = "audio/mpeg" if fmt == "audio" else "video/mp4"
    return filepath, filename, mime


# --------------------------------------------------------------------------- #
# UI
# --------------------------------------------------------------------------- #
st.title("⬇️ Universal Media Downloader")
st.caption(
    "Paste a link from **YouTube · X (Twitter) · Reddit · Instagram** "
    "and many more. Choose a format, then download straight to your device."
)

url = st.text_input(
    "Media link",
    placeholder="https://www.youtube.com/watch?v=...",
    label_visibility="collapsed",
)

# Clear any stale prepared file when the URL changes.
if url != st.session_state.get("last_url"):
    st.session_state.last_url = url
    st.session_state.pop("prepared", None)

# --- Step 1: fetch metadata -------------------------------------------------
metadata = None
if url.strip():
    with st.spinner("Fetching media details…"):
        try:
            metadata = fetch_metadata(url.strip())
        except Exception as exc:  # noqa: BLE001 - surface any extractor error
            st.error(
                "Couldn't read that link. It may be private, unsupported, "
                "or require a login.\n\n"
                f"Details: `{exc}`"
            )

# --- Step 2: options + processing ------------------------------------------
if metadata:
    st.success(f"**Found:** {metadata['title']}")

    info_col, thumb_col = st.columns([2, 1])
    with info_col:
        if metadata["uploader"]:
            st.write(f"**By:** {metadata['uploader']}")
        if metadata["duration"]:
            st.write(f"**Length:** {human_duration(metadata['duration'])}")
        if metadata["extractor"]:
            st.write(f"**Source:** {metadata['extractor']}")
    with thumb_col:
        if metadata["thumbnail"]:
            st.image(metadata["thumbnail"], use_container_width=True)

    st.divider()

    fmt_label = st.radio(
        "Format",
        ["🎬 Video (MP4)", "🎵 Audio Only (MP3)"],
        horizontal=True,
    )
    is_video = fmt_label.startswith("🎬")
    fmt = "video" if is_video else "audio"

    if is_video:
        quality = st.selectbox(
            "Quality",
            ["Best Available", "720p", "480p"],
            help="Caps the video resolution. The best matching stream is used.",
        )
    else:
        quality = None
        st.caption("🎧 Audio is extracted as a 192 kbps MP3.")

    if st.button("⬇️ Prepare Download", type="primary", use_container_width=True):
        with st.spinner("Downloading and processing with ffmpeg… this can take a moment."):
            try:
                filepath, filename, mime = download_media(
                    url.strip(), fmt, quality, metadata["title"]
                )
                with open(filepath, "rb") as fh:
                    st.session_state.prepared = {
                        "bytes": fh.read(),
                        "filename": filename,
                        "mime": mime,
                    }
                # Tidy up the temp file now that bytes are in memory.
                try:
                    os.remove(filepath)
                except OSError:
                    pass
            except Exception as exc:  # noqa: BLE001
                st.session_state.pop("prepared", None)
                st.error(f"Processing failed: `{exc}`")

    # --- Step 3: deliver ----------------------------------------------------
    prepared = st.session_state.get("prepared")
    if prepared:
        st.balloons()
        st.download_button(
            label=f"💾 Save “{prepared['filename']}”",
            data=prepared["bytes"],
            file_name=prepared["filename"],
            mime=prepared["mime"],
            type="primary",
            use_container_width=True,
        )
        size_mb = len(prepared["bytes"]) / (1024 * 1024)
        st.caption(f"Ready · {size_mb:.1f} MB")

# --------------------------------------------------------------------------- #
# Footer
# --------------------------------------------------------------------------- #
st.divider()
st.caption(
    "Built with Streamlit + yt-dlp + ffmpeg. "
    "Only download content you have the rights to."
)
