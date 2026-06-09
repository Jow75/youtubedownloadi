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
from datetime import datetime
from pathlib import Path

import streamlit as st

import downloader as dl
import history as hist
import licensing


def fmt_size(n):
    """Bytes -> compact human size (e.g. '4 MB', '1.2 GB')."""
    n = float(n or 0)
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024 or unit == "GB":
            return f"{n:.0f} {unit}" if unit in ("B", "KB") else f"{n:.1f} {unit}"
        n /= 1024
    return f"{n:.1f} TB"


def when_label(ts):
    """ISO timestamp -> friendly relative time (e.g. '3 h ago', 'Jun 09, 2026')."""
    try:
        d = datetime.fromisoformat(ts)
    except (ValueError, TypeError):
        return ""
    s = (datetime.now() - d).total_seconds()
    if s < 60:
        return "just now"
    if s < 3600:
        return f"{int(s // 60)} min ago"
    if s < 86400:
        return f"{int(s // 3600)} h ago"
    if s < 7 * 86400:
        return f"{int(s // 86400)} d ago"
    return d.strftime("%b %d, %Y")

# Flip to enforce licensing in distributed builds: set env UMD_ENFORCE_LICENSE=1.
# Left OFF here so local/owner use is never blocked during development.
ENFORCE_LICENSE = os.environ.get("UMD_ENFORCE_LICENSE", "0") == "1"

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


def add_history(path, title, fmt, url="", extractor=""):
    """Persist a finished download to disk so it survives refresh/restart."""
    try:
        hist.add_entry(path, title, fmt, url=url, extractor=extractor)
    except Exception:  # noqa: BLE001 — history must never break a download
        pass


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
            "Turbo downloads (aria2c) for non-YouTube sites",
            value=_aria_ok, disabled=not _aria_ok,
            help="Multi-connection turbo for sites that allow it (e.g. X). "
                 "YouTube THROTTLES multi-connection, so it auto-uses its faster "
                 "native downloader. Safe to leave on.",
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
    with st.expander("🔑 License / Activation"):
        lm = licensing.LicenseManager()
        st.write(lm.status())
        st.caption("Your computer's ID (send this to get a key):")
        st.code(lm.get_machine_id(), language=None)
        _key = st.text_input("Paste your license key", value="",
                             placeholder="UMDL-...")
        cga, cgb = st.columns(2)
        if cga.button("Activate", use_container_width=True):
            ok, msg = lm.activate(_key)
            (st.success if ok else st.error)(msg)
        if cgb.button("Remove", use_container_width=True):
            lm.deactivate()
            st.info("License removed.")

    st.divider()
    st.caption("💡 **M4A** audio skips conversion = faster. Public posts need no "
               "cookies. A faster internet speeds downloads the most.")


# --- License gate (only blocks when ENFORCE_LICENSE is on, e.g. shipped build) #
if ENFORCE_LICENSE and not licensing.LicenseManager().is_licensed():
    st.title("🔒 Activate Universal Media Downloader")
    st.warning("This copy needs a license key to use.")
    _lm = licensing.LicenseManager()
    st.write("**1.** Send the seller this computer's ID:")
    st.code(_lm.get_machine_id(), language=None)
    st.write("**2.** Paste the license key you receive and click Activate:")
    _k = st.text_input("License key", placeholder="UMDL-...")
    if st.button("Activate", type="primary"):
        ok, msg = _lm.activate(_k)
        if ok:
            st.success(msg)
            st.rerun()
        else:
            st.error(msg)
    st.stop()


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
            add_history(path, title, job["fmt"], url=url)
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

mode = st.radio("Mode",
                ["🔗 Single link", "📺 Channel / Profile", "📚 Bulk (many links)"],
                horizontal=True)

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
                    add_history(path, metadata["title"], fmt, url=url.strip(),
                                extractor=metadata.get("extractor", ""))
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
# CHANNEL / PROFILE MODE
# =========================================================================== #
elif mode == "📺 Channel / Profile":
    st.caption("Paste an artist's **YouTube channel**, a **TikTok profile**, or "
               "any playlist link. Scan it to list every video, then grab them "
               "**all as MP3 or MP4** — or pick per-video.")
    ch_url = st.text_input(
        "Channel / profile / playlist link",
        placeholder="https://www.youtube.com/@artist   ·   https://www.tiktok.com/@user",
        label_visibility="collapsed",
    )
    sc1, sc2 = st.columns([3, 1])
    max_items = sc2.number_input("Max videos (0 = all)", min_value=0, value=0, step=10,
                                 help="Cap how many to list — handy for huge channels.")
    if sc1.button("🔎 Scan channel / profile", type="primary", use_container_width=True):
        if not ch_url.strip():
            st.warning("Paste a channel or profile link first.")
        else:
            with st.spinner("Reading every video… big channels take a moment."):
                try:
                    res = dl.list_media(ch_url.strip(), cookiefile, max_items or None)
                    st.session_state.channel_res = res
                except Exception as exc:  # noqa: BLE001
                    st.session_state.pop("channel_res", None)
                    st.error("Couldn't read that channel/profile. It may be private, "
                             "unsupported, or need login cookies (sidebar → Speed & "
                             f"advanced).\n\nDetails: `{exc}`")

    res = st.session_state.get("channel_res")
    if res and res.get("entries"):
        entries = res["entries"]
        st.success(f"**{res['title']}** — found **{len(entries)}** video(s)"
                   + (f"  ·  by {res['uploader']}" if res.get("uploader") else ""))

        st.markdown("#### ⚡ Grab everything")
        gq = st.selectbox("Video quality (for MP4)", ["Best Available", "720p", "480p"])
        ga, gb = st.columns(2)
        grab_mp3 = ga.button("🎵 Download ALL as MP3", use_container_width=True)
        grab_mp4 = gb.button("🎬 Download ALL as MP4", use_container_width=True)
        if grab_mp3 or grab_mp4:
            is_aud = bool(grab_mp3)
            jobs = [{"url": e["url"], "title": e["title"],
                     "fmt": "audio" if is_aud else "video",
                     "quality": None if is_aud else gq, "audio_codec": "mp3"}
                    for e in entries]
            st.write(f"### Downloading {len(jobs)} item(s) as "
                     f"{'MP3' if is_aud else 'MP4'}…")
            ok, total = run_jobs(jobs)
            if ok:
                st.balloons()
            st.success(f"Done — saved **{ok} of {total}**.")

        FMT_OPTIONS = ["🎵 MP3", "🎵 M4A (fast)", "🎬 MP4 — Best",
                       "🎬 MP4 — 720p", "🎬 MP4 — 480p", "⛔ Skip"]
        with st.expander(f"🎚️ Or choose per video ({len(entries)})", expanded=False):
            st.caption("Pick a format for each (or **Skip**), then download the chosen ones.")
            for idx, e in enumerate(entries):
                pc1, pc2 = st.columns([3, 2])
                dur = dl.human_duration(e["duration"]) if e.get("duration") else ""
                pc1.write(f"**{e['title']}**" + (f"  ·  {dur}" if dur else ""))
                pc2.selectbox("format", FMT_OPTIONS, key=f"ch_fmt_{idx}",
                              label_visibility="collapsed")
            if st.button("⬇️ Download chosen videos", type="primary",
                         use_container_width=True):
                jobs = []
                for idx, e in enumerate(entries):
                    choice = st.session_state.get(f"ch_fmt_{idx}", "🎵 MP3")
                    if choice.startswith("⛔"):
                        continue
                    job = {"url": e["url"], "title": e["title"]}
                    if choice.startswith("🎬"):
                        job["fmt"] = "video"
                        job["quality"] = ("720p" if "720" in choice
                                          else "480p" if "480" in choice
                                          else "Best Available")
                    else:
                        job["fmt"] = "audio"
                        job["audio_codec"] = "m4a" if "M4A" in choice else "mp3"
                    jobs.append(job)
                if not jobs:
                    st.warning("Every video is set to Skip — pick a format for at "
                               "least one.")
                else:
                    st.write(f"### Downloading {len(jobs)} item(s)…")
                    ok, total = run_jobs(jobs)
                    if ok:
                        st.balloons()
                    st.success(f"Done — saved **{ok} of {total}**.")
    elif res is not None:
        st.warning("No videos found there. Private content (e.g. TikTok **liked** "
                   "videos) needs a cookies.txt and a public 'Liked' list — set the "
                   "cookies path in the sidebar → Speed & advanced.")

# =========================================================================== #
# BULK MODE
# =========================================================================== #
else:
    bulk_method = st.radio(
        "Bulk method",
        ["⚡ Two columns (recommended)", "🎚️ Scan & choose per link"],
        horizontal=True,
        help="**Two columns**: fastest — drop links into the MP4 or MP3 box and "
             "go. **Scan & choose**: paste all links, see their titles, then pick "
             "the exact format/quality for each one individually.",
    )

    def _parse(text):
        return [ln.strip() for ln in text.splitlines() if ln.strip()]

    # ----- Option 1: two columns (recommended) ----------------------------- #
    if bulk_method.startswith("⚡"):
        st.caption("Paste links **one per line** in the column for the format "
                   "you want, then hit **Download all**.")
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

    # ----- Option 2: scan & choose per link (secondary) -------------------- #
    else:
        st.caption("Paste all links, **🔎 Scan** to see their titles, then pick "
                   "the format/quality for each, and **Download selected**.")
        links_text = st.text_area("All links (one per line)", height=160,
                                   placeholder="https://...\nhttps://...")
        if st.button("🔎 Scan links"):
            urls = _parse(links_text)
            if not urls:
                st.warning("Paste at least one link first.")
            else:
                items, prog = [], st.progress(0.0)
                for i, u in enumerate(urls, 1):
                    try:
                        m = fetch_metadata(u, cookiefile)
                        items.append({"url": u, "title": m["title"],
                                      "duration": m["duration"], "ok": True})
                    except Exception as exc:  # noqa: BLE001
                        items.append({"url": u, "title": u, "ok": False,
                                      "err": str(exc)})
                    prog.progress(i / len(urls))
                prog.empty()
                st.session_state.scan_items = items

        items = st.session_state.get("scan_items", [])
        if items:
            good = [it for it in items if it["ok"]]
            st.write(f"### Found {len(good)} item(s) — choose format for each")
            FMT_OPTIONS = ["🎵 MP3", "🎵 M4A (fast)", "🎬 MP4 — Best",
                           "🎬 MP4 — 720p", "🎬 MP4 — 480p"]
            for idx, it in enumerate(items):
                if not it["ok"]:
                    st.error(f"❌ Couldn't read: {it['url']}")
                    continue
                cc1, cc2 = st.columns([3, 2])
                dur = dl.human_duration(it["duration"]) if it.get("duration") else ""
                cc1.write(f"**{it['title']}**" + (f"  ·  {dur}" if dur else ""))
                cc2.selectbox("format", FMT_OPTIONS, key=f"scan_fmt_{idx}",
                              label_visibility="collapsed")

            if st.button("⬇️ Download selected", type="primary",
                         use_container_width=True):
                jobs = []
                for idx, it in enumerate(items):
                    if not it["ok"]:
                        continue
                    choice = st.session_state.get(f"scan_fmt_{idx}", "🎵 MP3")
                    job = {"url": it["url"], "title": it["title"]}
                    if choice.startswith("🎬"):
                        job["fmt"] = "video"
                        job["quality"] = ("720p" if "720" in choice
                                          else "480p" if "480" in choice
                                          else "Best Available")
                    else:
                        job["fmt"] = "audio"
                        job["audio_codec"] = "m4a" if "M4A" in choice else "mp3"
                    jobs.append(job)
                if jobs:
                    st.write(f"### Downloading {len(jobs)} item(s)…")
                    ok, total = run_jobs(jobs)
                    if ok:
                        st.balloons()
                    st.success(f"Done — saved **{ok} of {total}**.")

# =========================================================================== #
# DOWNLOAD HISTORY  (persistent — survives refresh & restart)
# =========================================================================== #
st.divider()
all_hist = hist.load_history()
st.subheader(f"🕘 Download history ({len(all_hist)})")

if not all_hist:
    st.caption("Your downloads will appear here and stay saved between sessions.")
else:
    f1, f2, f3, f4 = st.columns([2.4, 1.3, 1.3, 1.2])
    hq = f1.text_input("Search history", placeholder="Search title or filename…",
                       label_visibility="collapsed")
    site_sel = f2.selectbox("Site", ["All sites"] + hist.all_sites(all_hist),
                            label_visibility="collapsed")
    type_sel = f3.selectbox("Type", ["All types", "🎬 Video", "🎵 Audio"],
                            label_visibility="collapsed")
    date_sel = f4.selectbox("When", ["All time", "Today", "Last 7 days",
                                     "Last 30 days"], label_visibility="collapsed")

    def _match(h):
        if hq and hq.lower() not in (
                (h.get("title", "") + " " + h.get("filename", "")).lower()):
            return False
        if site_sel != "All sites" and h.get("site") != site_sel:
            return False
        if type_sel.endswith("Video") and h.get("fmt") != "video":
            return False
        if type_sel.endswith("Audio") and h.get("fmt") != "audio":
            return False
        if date_sel != "All time":
            try:
                ts = datetime.fromisoformat(h.get("ts", ""))
            except (ValueError, TypeError):
                return False
            if date_sel == "Today":
                if ts.date() != datetime.now().date():
                    return False
            else:
                days = 7 if "7" in date_sel else 30
                if (datetime.now() - ts).days >= days:
                    return False
        return True

    filtered = [h for h in all_hist if _match(h)]
    total_size = sum(h.get("size", 0) for h in filtered)
    sc1, sc2 = st.columns([4, 1])
    sc1.caption(f"Showing **{len(filtered)}** of {len(all_hist)} downloads  ·  "
                f"{fmt_size(total_size)} total")
    if sc2.button("🗑️ Clear all", use_container_width=True,
                  help="Permanently remove every entry from your history"):
        hist.clear_history()
        st.rerun()

    if not filtered:
        st.info("No downloads match those filters.")
    for h in filtered[:300]:
        icon = "🎬" if h.get("fmt") == "video" else "🎵"
        hc1, hc2, hc3 = st.columns([7, 1, 1])
        hc1.markdown(
            f"{icon} **{h.get('title') or h.get('filename')}**  \n"
            f"<span style='color:#888;font-size:0.82em'>"
            f"{h.get('site', '')} · {when_label(h.get('ts'))} · "
            f"{fmt_size(h.get('size', 0))}</span>",
            unsafe_allow_html=True)
        if hc2.button("📂", key=f"hopen_{h['id']}", help="Open containing folder"):
            if not open_in_explorer(h["path"]):
                st.warning("That file/folder may have been moved or deleted.")
        if hc3.button("✕", key=f"hdel_{h['id']}", help="Remove from history"):
            hist.delete_entry(h["id"])
            st.rerun()

# --------------------------------------------------------------------------- #
# Footer
# --------------------------------------------------------------------------- #
st.divider()
st.caption("Built with Streamlit + yt-dlp + ffmpeg, running locally. "
           "Only download content you have the rights to.")
