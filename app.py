"""
Universal Media Downloader (local edition) — Streamlit UI
=========================================================
Download media from YouTube, X, TikTok, Reddit, Instagram, and 1,800+ other
sites supported by yt-dlp. Runs LOCALLY so it uses your residential IP and your
machine's Node.js to solve YouTube's signature challenge.

Features
  * Single link or Bulk (two columns: MP4 / MP3).
  * Saves files DIRECTLY to a folder on this PC (no browser download → IDM and
    other download managers never interfere).
  * Optional separate folders for video vs audio.
  * Embedded cover art + tags (clean music library).
  * Playlist / channel: one link grabs every item.
  * Optional clip trimming, MP3 vs fast M4A, aria2c turbo, cookies.txt.

The download engine lives in downloader.py (importable / testable on its own).
Requirements: streamlit, yt-dlp, yt-dlp-ejs; ffmpeg + Node.js on PATH;
aria2c optional (turbo downloads).
"""

import os
import time
from pathlib import Path

import streamlit as st

import downloader as dl

st.set_page_config(
    page_title="Universal Media Downloader",
    page_icon="⬇️",
    layout="centered",
    initial_sidebar_state="expanded",
)

DEFAULT_DOWNLOAD_DIR = str(Path.home() / "Downloads")


def open_in_explorer(path):
    try:
        target = path if os.path.isdir(path) else os.path.dirname(path)
        os.startfile(target)  # Windows
        return True
    except Exception:  # noqa: BLE001
        return False


@st.cache_data(show_spinner=False, ttl=600)
def fetch_metadata(url, cookiefile=""):
    return dl.extract_meta(url, cookiefile)


@st.cache_data(show_spinner=False, ttl=600)
def fetch_playlist(url, cookiefile=""):
    return dl.list_playlist(url, cookiefile)


def add_history(path, title, fmt):
    st.session_state.setdefault("history", [])
    st.session_state.history.insert(0, {"path": path, "title": title, "fmt": fmt})


# --------------------------------------------------------------------------- #
# Sidebar
# --------------------------------------------------------------------------- #
with st.sidebar:
    st.header("⚙️ Settings")

    main_dir = st.text_input("Save downloads to folder", value=DEFAULT_DOWNLOAD_DIR)
    st.caption("Files are written straight to this folder on this PC. No browser "
               "download, so **IDM won't interfere**.")

    separate = st.checkbox("📂 Separate folders for Video and Audio", value=False)
    if separate:
        video_dir = st.text_input("🎬 Video folder", value=main_dir)
        audio_dir = st.text_input("🎵 Audio folder", value=main_dir)
    else:
        video_dir = audio_dir = main_dir

    if st.button("📂 Open main folder", use_container_width=True):
        if not open_in_explorer(main_dir):
            st.warning("Couldn't open that folder — check the path.")

    st.divider()
    with st.expander("⚡ Speed & advanced"):
        _aria_ok = dl.aria2c_available()
        use_aria2c = st.checkbox(
            "Turbo downloads (aria2c, multi-connection)",
            value=_aria_ok, disabled=not _aria_ok,
            help="Up to 16 connections for big files. Streaming sites (X, etc.) "
                 "auto-use the standard method, so nothing breaks.",
        )
        if not _aria_ok:
            st.caption("⚠️ aria2c not found — install it and restart the app.")

        embed_meta = st.checkbox(
            "🏷️ Embed cover art + title/artist tags", value=True,
            help="Adds the thumbnail as cover art and writes tags — great for a "
                 "tidy music library. Turn off for the rawest, fastest file.",
        )

        st.markdown("**Login cookies (advanced — usually leave blank)**")
        cookiefile = st.text_input(
            "Path to a cookies.txt file", value="",
            help="Only needed for PRIVATE / login-required media (private "
                 "Instagram, protected X). Export it with a 'Get cookies.txt' "
                 "browser extension. Leave blank for normal public downloads.",
        )

    st.divider()
    st.caption("💡 **M4A** audio skips conversion = faster. Public posts need no "
               "cookies. A faster internet speeds downloads the most.")


def resolve_dir(fmt):
    return video_dir if fmt == "video" else audio_dir


def run_jobs(jobs):
    """Download a list of jobs sequentially with live progress. Each job is a
    dict: url, fmt, quality, audio_codec, title (optional)."""
    overall = st.progress(0.0)
    ok = 0
    total = len(jobs)
    for i, job in enumerate(jobs, 1):
        row = st.empty()
        bar = st.progress(0.0)
        url = job["url"]
        row.info(f"[{i}/{total}] 🔎 {job.get('title') or url}")
        try:
            title = job.get("title") or fetch_metadata(url, cookiefile)["title"]
            row.info(f"[{i}/{total}] ⬇️ {title}")
            path = dl.download_with_retry(
                url, job["fmt"], job.get("quality"),
                job.get("audio_codec", "mp3"), resolve_dir(job["fmt"]), title,
                use_aria2c, cookiefile, embed_meta, None,
                progress_cb=lambda x, b=bar: b.progress(x),
            )
            bar.progress(1.0)
            row.success(f"[{i}/{total}] ✅ {os.path.basename(path)}")
            add_history(path, title, job["fmt"])
            ok += 1
        except Exception as exc:  # noqa: BLE001
            bar.empty()
            row.error(f"[{i}/{total}] ❌ {url}\n\n`{exc}`")
        overall.progress(i / total)
        time.sleep(0.4)  # be polite between requests (helps avoid rate limits)
    return ok, total


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
        placeholder="Paste a link from YouTube, X, TikTok, Reddit, Instagram…",
        label_visibility="collapsed",
    )

    if url != st.session_state.get("last_url"):
        st.session_state.last_url = url
        st.session_state.pop("saved_path", None)

    metadata = None
    if url.strip():
        with st.spinner("Fetching media details…"):
            try:
                metadata = fetch_metadata(url.strip(), cookiefile)
            except Exception as exc:  # noqa: BLE001
                st.error("Couldn't read that link. It may be private, unsupported, "
                         f"or need a login.\n\nDetails: `{exc}`")

    if metadata:
        st.success(f"**Found:** {metadata['title']}")
        c1, c2 = st.columns([2, 1])
        with c1:
            if metadata["uploader"]:
                st.write(f"**By:** {metadata['uploader']}")
            if metadata["duration"]:
                st.write(f"**Length:** {dl.human_duration(metadata['duration'])}")
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
                help="M4A copies the original audio (no re-encoding) so it's much "
                     "faster. MP3 plays everywhere but must be converted.",
            )
            audio_codec = "mp3" if audio_choice.startswith("MP3") else "m4a"

        whole_playlist = st.checkbox(
            "📜 Download the ENTIRE playlist / channel (if this link is one)",
            value=False,
        )

        trim = None
        with st.expander("✂️ Trim a clip (optional)"):
            tc1, tc2 = st.columns(2)
            start_txt = tc1.text_input("Start (e.g. 1:30)", value="")
            end_txt = tc2.text_input("End (e.g. 2:45)", value="")
            st.caption("Leave blank to download the whole thing. "
                       "(Trimming turns off turbo for accuracy.)")

        if st.button("⬇️ Download", type="primary", use_container_width=True):
            st.session_state.pop("saved_path", None)

            if whole_playlist:
                with st.spinner("Reading playlist…"):
                    try:
                        pl = fetch_playlist(url.strip(), cookiefile)
                    except Exception as exc:  # noqa: BLE001
                        pl = None
                        st.error(f"Couldn't read the playlist: `{exc}`")
                if pl and pl["entries"]:
                    st.write(f"### Playlist: {pl['title']} — {len(pl['entries'])} item(s)")
                    jobs = [{"url": e["url"], "fmt": fmt, "quality": quality,
                             "audio_codec": audio_codec, "title": e["title"]}
                            for e in pl["entries"]]
                    ok, total = run_jobs(jobs)
                    if ok:
                        st.balloons()
                    st.success(f"Done — saved **{ok} of {total}**.")
                elif pl:
                    st.warning("No items found in that playlist.")
            else:
                s = dl.parse_time(start_txt)
                e = dl.parse_time(end_txt)
                if s is not None or e is not None:
                    end_val = e if e is not None else (metadata["duration"] or 10 ** 9)
                    trim = (s or 0.0, end_val)

                bar = st.progress(0.0)
                status = st.empty()
                status.info("⏳ Starting…")
                try:
                    path = dl.download_with_retry(
                        url.strip(), fmt, quality, audio_codec,
                        resolve_dir(fmt), metadata["title"], use_aria2c,
                        cookiefile, embed_meta, trim,
                        progress_cb=lambda f: bar.progress(f),
                        status_cb=lambda t: status.info(t),
                    )
                    bar.progress(1.0)
                    status.empty()
                    st.session_state.saved_path = path
                    add_history(path, metadata["title"], fmt)
                except Exception as exc:  # noqa: BLE001
                    bar.empty()
                    status.error(f"Failed: `{exc}`")

        if st.session_state.get("saved_path"):
            saved = st.session_state.saved_path
            st.balloons()
            st.success(f"🎉 Saved to:\n\n`{saved}`")
            if st.button("📂 Open folder", use_container_width=True):
                open_in_explorer(saved)

# =========================================================================== #
# BULK MODE
# =========================================================================== #
else:
    st.caption("Paste links **one per line** in the column for the format you "
               "want, then hit **Download all**.")
    col_v, col_a = st.columns(2)
    with col_v:
        st.markdown("### 🎬 Video → MP4")
        video_links = st.text_area("video links", height=220,
                                    label_visibility="collapsed",
                                    placeholder="https://...\nhttps://...")
        bulk_quality = st.selectbox("Quality for all videos",
                                    ["Best Available", "720p", "480p"])
    with col_a:
        st.markdown("### 🎵 Audio → MP3")
        audio_links = st.text_area("audio links", height=220,
                                   label_visibility="collapsed",
                                   placeholder="https://...\nhttps://...")

    def _parse(text):
        return [ln.strip() for ln in text.splitlines() if ln.strip()]

    if st.button("⬇️ Download all", type="primary", use_container_width=True):
        jobs = ([{"url": u, "fmt": "video", "quality": bulk_quality}
                 for u in _parse(video_links)]
                + [{"url": u, "fmt": "audio", "audio_codec": "mp3"}
                   for u in _parse(audio_links)])
        if not jobs:
            st.warning("Paste at least one link into a column first.")
        else:
            st.write(f"### Downloading {len(jobs)} item(s)…")
            ok, total = run_jobs(jobs)
            if ok:
                st.balloons()
            st.success(f"Done — saved **{ok} of {total}**. "
                       "Open the folder from the sidebar to see them.")

# =========================================================================== #
# DOWNLOAD HISTORY
# =========================================================================== #
history = st.session_state.get("history", [])
if history:
    with st.expander(f"🕘 Download history ({len(history)})", expanded=False):
        for idx, h in enumerate(history[:50]):
            icon = "🎬" if h["fmt"] == "video" else "🎵"
            hc1, hc2 = st.columns([5, 1])
            hc1.write(f"{icon} {os.path.basename(h['path'])}")
            if hc2.button("📂", key=f"hist_{idx}", help="Open containing folder"):
                open_in_explorer(h["path"])

# --------------------------------------------------------------------------- #
# Footer
# --------------------------------------------------------------------------- #
st.divider()
st.caption("Built with Streamlit + yt-dlp + ffmpeg, running locally. "
           "Only download content you have the rights to.")
