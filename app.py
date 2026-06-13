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
from datetime import datetime
from pathlib import Path

import streamlit as st

import ai
import archive
import branding
import downloader as dl
import downloads
import history as hist
import library
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


# History persistence now happens inside the background worker (downloads.py)
# the moment each file finishes — so it works even while you browse other tabs.


# --------------------------------------------------------------------------- #
# Sidebar
# --------------------------------------------------------------------------- #
with st.sidebar:
    st.header("⚙️ Settings")

    if library.is_enabled():
        main_dir = st.text_input("Save downloads to folder",
                                 value=library.get_root(), disabled=True,
                                 help="Managed library is ON — files auto-organize "
                                      "here. Turn it off in Managed Library below "
                                      "to pick a custom folder.")
        st.caption("📚 **Managed library is ON** — MP3 → Music/MP3, M4A → "
                   "Music/M4A, MP4 → Videos/MP4.")
    else:
        main_dir = st.text_input("Save downloads to folder",
                                 value=DEFAULT_DOWNLOAD_DIR)
        st.caption("Files are written straight to this folder on this PC. No "
                   "browser download, so **IDM won't interfere**.")

    separate = st.checkbox("📂 Separate folders for Video and Audio", value=False)
    if separate:
        video_dir = st.text_input("🎬 Video folder", value=main_dir)
        audio_dir = st.text_input("🎵 Audio folder", value=main_dir)
    else:
        video_dir = audio_dir = main_dir

    if st.button("📂 Open main folder", use_container_width=True):
        if not open_in_explorer(main_dir):
            st.warning("Couldn't open that folder — check the path.")

    with st.expander("🗂️ Managed Library"):
        lib_root = st.text_input("Library location", value=library.get_root(),
                                 help="A tidy workspace the app organizes for you.")
        if lib_root.strip() and lib_root.strip() != library.get_root():
            library.save(root=lib_root.strip())
        lib_on = st.checkbox(
            "Auto-organize downloads into this library",
            value=library.is_enabled(),
            help="MP3 → Music/MP3, M4A → Music/M4A, MP4 → Videos/MP4. "
                 "When on, this overrides the folder above.")
        if lib_on != library.is_enabled():
            library.save(enabled=lib_on)
            st.rerun()
        if st.button("🏗️ Create / repair folders", use_container_width=True):
            n = len(library.ensure_structure())
            st.success(f"Library ready ({n} folders) at {library.get_root()}")
        st.caption("Music/MP3 · Music/M4A · Videos/MP4 · Images · Downloads · "
                   "AI Library · Metadata · Logs · Temp")

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
    with st.expander("🤖 AI Settings"):
        prov = ai.current_provider()
        pinfo = ai.PROVIDERS[prov]

        if ai.is_available():
            st.success("AI is ready ✓")
            mk = ai.masked_key()
            st.caption((f"Key `{mk}`" if mk else "Using a developer key")
                       + f"  ·  {pinfo['label']}  ·  model `{ai.current_model()}`")
            st.session_state.ai_on = st.checkbox(
                "Enable AI features", value=st.session_state.get("ai_on", False),
                help="Turn on Smart Library and other AI tools. Only titles are "
                     "sent online — never your media files.")
        else:
            st.session_state.ai_on = False
            st.info("AI is off. Add an API key to unlock AI features. Your license "
                    "and your AI key are separate.")

        prov_keys = list(ai.PROVIDERS.keys())
        sel = st.selectbox("Provider", prov_keys,
                           index=prov_keys.index(prov),
                           format_func=lambda k: ai.PROVIDERS[k]["label"])
        if sel != prov:
            ai.save_settings(provider=sel)
            st.rerun()
        st.caption(f"Get a key: {pinfo['get_key_url']}")

        new_key = st.text_input("API key", type="password", value="",
                                placeholder=f"{pinfo['key_prefix']}…  paste, then Save")
        kc1, kc2 = st.columns(2)
        if kc1.button("💾 Save key", use_container_width=True):
            k = new_key.strip()
            if not k:
                st.warning("Paste a key first.")
            else:
                with st.spinner("Checking the key…"):
                    ok, res = ai.validate_key(sel, k)
                if ok:
                    ai.save_settings(provider=sel, key=k)
                    st.success(f"Saved ✓ — {len(res)} models available.")
                    st.rerun()
                elif "rejected" in str(res).lower():
                    st.error(res)
                else:
                    ai.save_settings(provider=sel, key=k)
                    st.warning(f"Saved, but couldn't verify right now ({res}). "
                               "It'll be used once you're online.")
                    st.rerun()
        if kc2.button("🗑️ Remove key", use_container_width=True):
            ai.clear_key()
            st.session_state.ai_on = False
            st.rerun()

        if ai.is_available():
            m = st.text_input("Model (advanced)", value=ai.current_model(),
                              help="Which model to use for AI features.")
            if m.strip() and m.strip() != ai.current_model():
                ai.save_settings(model=m.strip())
                st.rerun()
        st.caption("🔒 Your key is encrypted on this PC (masked, never shown in "
                   "full) and is never sent anywhere except your chosen provider.")

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

    with st.expander("ℹ️ About / Contact publisher"):
        st.markdown(branding.contact_md())
        st.caption(f"{branding.APP_NAME} v{branding.VERSION}  ·  "
                   f"{branding.COPYRIGHT}")

    st.divider()
    st.caption("💡 **M4A** audio skips conversion = faster. Public posts need no "
               "cookies. A faster internet speeds downloads the most.")


# --- License gate (only blocks when ENFORCE_LICENSE is on, e.g. shipped build) #
if ENFORCE_LICENSE and not licensing.LicenseManager().is_licensed():
    st.title("🔒 Activate Universal Media Downloader")
    st.warning("This copy needs a license key to use. If it was shared with you, "
               "it won't work until you get your own key for **this** computer.")
    _lm = licensing.LicenseManager()
    st.write("**1.** Send the publisher this computer's ID:")
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
    st.divider()
    st.subheader("📨 Get a license / upgrade")
    st.write("Contact the publisher to buy or renew a key:")
    st.markdown(branding.contact_md())
    st.caption(f"{branding.APP_NAME} v{branding.VERSION} · {branding.COPYRIGHT}")
    st.stop()


# --- First-run setup: choose where the media library lives -------------------#
if not library.is_configured():
    st.title("👋 Welcome to Universal Media Downloader")
    st.write("Let's set up your **media library** — one tidy place for everything "
             "you download, organized automatically by type.")
    loc = st.text_input("Where should your library live?",
                        value=library.default_root())
    st.caption("The app creates `Music/MP3`, `Videos/MP4`, etc. inside this "
               "folder, and files each download into the right place.")
    w1, w2 = st.columns(2)
    if w1.button("✅ Set up my library here", type="primary",
                 use_container_width=True):
        library.save(root=(loc.strip() or library.default_root()),
                     enabled=True, configured=True)
        library.ensure_structure()
        st.success("Library ready! Loading the app…")
        st.rerun()
    if w2.button("Not now — use my Downloads folder", use_container_width=True):
        library.save(configured=True, enabled=False)
        st.rerun()
    st.caption("You can change this anytime in the sidebar → **Managed Library**.")
    st.stop()


def resolve_dir(fmt):
    return video_dir if fmt == "video" else audio_dir


def enqueue(jobs, lane=downloads.LANE_NOW):
    """Hand a list of jobs to the background queue and return immediately, so
    the UI never blocks. Each job: url, fmt, quality?, audio_codec?, title?,
    trim?. Current sidebar settings are captured per-job at enqueue time."""
    opts = {"use_aria2c": use_aria2c, "cookiefile": cookiefile,
            "embed_meta": embed_meta}
    specs = []
    for j in jobs:
        fmt = j["fmt"]
        codec = j.get("audio_codec", "mp3")
        dest = (library.route(fmt, codec) if library.is_enabled()
                else resolve_dir(fmt))
        specs.append({
            "url": j["url"], "fmt": fmt, "quality": j.get("quality"),
            "audio_codec": codec,
            "dest_dir": dest, "title": j.get("title", ""),
            "opts": {**opts, "trim": j.get("trim")},
        })
    downloads.get_manager().add_jobs(specs, lane)
    return len(specs)


@st.fragment(run_every=2.0)  # numeric seconds — avoids Streamlit importing pandas
def downloads_panel():
    """Always-visible, self-refreshing queue. Lives in its own fragment so it
    updates progress every 2s WITHOUT rerunning (or disturbing) the rest of the
    page — switch tabs freely while this keeps ticking."""
    mgr = downloads.get_manager()
    jobs = mgr.snapshot()
    c = mgr.counts()
    active = [j for j in jobs if j.status in ("downloading", "queued")]
    finished = [j for j in jobs if j.status in ("done", "error", "canceled")]

    with st.container(border=True):
        h1, h2, h3 = st.columns([5, 1.1, 1.1])
        bits = []
        if c["active"]:
            bits.append(f"⬇️ {c['active']} downloading")
        if c["queued"]:
            bits.append(f"🕒 {c['queued']} queued")
        if c["done"]:
            bits.append(f"✅ {c['done']} done")
        if c["error"]:
            bits.append(f"❌ {c['error']} failed")
        h1.markdown("**Downloads** — " + (" · ".join(bits) if bits
                    else "idle — queue anything; it keeps going while you browse"))
        if active and h2.button("Cancel all", key="dl_cancel_all",
                                use_container_width=True):
            mgr.cancel_all()
            st.rerun(scope="fragment")
        if finished and h3.button("Clear done", key="dl_clear",
                                  use_container_width=True):
            mgr.clear_finished()
            st.rerun(scope="fragment")

        for j in active[:60]:
            lane = "📦" if j.lane == downloads.LANE_BATCH else "⚡"
            r1, r2 = st.columns([7, 1])
            r1.markdown(
                f"{lane} **{j.label}**  \n"
                f"<span style='color:#888;font-size:.8em'>{j.detail}</span>",
                unsafe_allow_html=True)
            if r2.button("✕", key=f"dlc_{j.id}", help="Cancel this download"):
                mgr.cancel(j.id)
                st.rerun(scope="fragment")
            r1.progress(j.progress if j.status == "downloading" else 0.0)

        for j in finished[:25]:
            icon = ("✅" if j.status == "done"
                    else "⛔" if j.status == "canceled" else "❌")
            sub = (j.error if j.status == "error"
                   else os.path.basename(j.result) if j.result else j.detail)
            r1, r2 = st.columns([7, 1])
            r1.markdown(
                f"{icon} **{j.label}**  \n"
                f"<span style='color:#888;font-size:.8em'>{sub}</span>",
                unsafe_allow_html=True)
            if j.status == "done" and j.result:
                if r2.button("📂", key=f"dlo_{j.id}", help="Open containing folder"):
                    open_in_explorer(j.result)
            elif j.status == "error" and st.session_state.get("ai_on"):
                if r2.button("🤖", key=f"dlx_{j.id}", help="Ask AI why this failed"):
                    with st.spinner("Asking the AI…"):
                        st.session_state.setdefault("err_help", {})[j.id] = \
                            ai.explain_error(j.label, j.error or "")
            exp = st.session_state.get("err_help", {}).get(j.id)
            if exp:
                r1.info("🤖 " + exp)


# --------------------------------------------------------------------------- #
# Main
# --------------------------------------------------------------------------- #
st.title("⬇️ Universal Media Downloader")
downloads_panel()

_mode_opts = ["🔗 Single link", "📺 Channel / Profile", "📚 Bulk (many links)"]
if st.session_state.get("ai_on"):
    _mode_opts.append("🤖 Assistant")
mode = st.radio("Mode", _mode_opts, horizontal=True)

# =========================================================================== #
# SINGLE MODE
# =========================================================================== #
if mode == "🔗 Single link":
    url = st.text_input(
        "Media link",
        placeholder="Paste a link from YouTube, X, TikTok, Reddit, Instagram…",
        label_visibility="collapsed",
    )

    st.session_state.last_url = url

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
            if whole_playlist:
                with st.spinner("Reading playlist…"):
                    try:
                        pl = fetch_playlist(url.strip(), cookiefile)
                    except Exception as exc:  # noqa: BLE001
                        pl = None
                        st.error(f"Couldn't read the playlist: `{exc}`")
                if pl and pl["entries"]:
                    jobs = [{"url": e["url"], "fmt": fmt, "quality": quality,
                             "audio_codec": audio_codec, "title": e["title"]}
                            for e in pl["entries"]]
                    n = enqueue(jobs, downloads.LANE_BATCH)
                    st.success(f"📦 Queued **{n}** item(s) from *{pl['title']}* — "
                               "track them in **Downloads** above.")
                elif pl:
                    st.warning("No items found in that playlist.")
            else:
                trim = None
                s = dl.parse_time(start_txt)
                e = dl.parse_time(end_txt)
                if s is not None or e is not None:
                    end_val = e if e is not None else (metadata["duration"] or 10 ** 9)
                    trim = (s or 0.0, end_val)
                enqueue([{"url": url.strip(), "fmt": fmt, "quality": quality,
                          "audio_codec": audio_codec, "title": metadata["title"],
                          "trim": trim}], downloads.LANE_NOW)
                st.success("⚡ Queued — it's downloading now in **Downloads** "
                           "above. You can paste another link or switch tabs.")

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
    with st.expander("📅 Only a date range (optional)"):
        st.caption("Grab just the videos posted in a window — e.g. **2025-01-01 → "
                   "2026-12-31**. Leave blank for everything. *Note: filtering by "
                   "date reads each video's upload date, so scanning is slower; "
                   "pairing it with a Max-videos cap keeps it quick.*")
        dcol1, dcol2 = st.columns(2)
        date_after = dcol1.text_input("From (YYYY-MM-DD)", value="",
                                      placeholder="2025-01-01")
        date_before = dcol2.text_input("To (YYYY-MM-DD)", value="",
                                       placeholder="2026-12-31")

    if sc1.button("🔎 Scan channel / profile", type="primary", use_container_width=True):
        if not ch_url.strip():
            st.warning("Paste a channel or profile link first.")
        else:
            dated = bool(date_after.strip() or date_before.strip())
            msg = ("Reading dates for each video… this is slower."
                   if dated else "Reading every video… big channels take a moment.")
            with st.spinner(msg):
                try:
                    res = dl.list_media(ch_url.strip(), cookiefile, max_items or None,
                                        date_after=date_after, date_before=date_before)
                    st.session_state.channel_res = res
                    st.session_state.ch_page = 1
                    st.session_state.pop("ch_search", None)
                except Exception as exc:  # noqa: BLE001
                    st.session_state.pop("channel_res", None)
                    st.error("Couldn't read that channel/profile. It may be private, "
                             "unsupported, or need login cookies (sidebar → Speed & "
                             f"advanced).\n\nDetails: `{exc}`")

    res = st.session_state.get("channel_res")
    if res and res.get("entries"):
        entries = res["entries"]
        rng = " in your date range" if res.get("dated") else ""
        st.success(f"**{res['title']}** — found **{len(entries)}** video(s){rng}"
                   + (f"  ·  by {res['uploader']}" if res.get("uploader") else ""))

        # -- Grab everything ------------------------------------------------ #
        st.markdown("#### ⚡ Grab everything")
        gq = st.selectbox("Video quality (for MP4)", ["Best Available", "720p", "480p"])
        ga, gb = st.columns(2)
        if ga.button("🎵 Download ALL as MP3", use_container_width=True):
            n = enqueue([{"url": e["url"], "title": e["title"], "fmt": "audio",
                          "audio_codec": "mp3"} for e in entries],
                        downloads.LANE_BATCH)
            st.success(f"📦 Queued **{n}** as MP3 — see **Downloads** above.")
        if gb.button("🎬 Download ALL as MP4", use_container_width=True):
            n = enqueue([{"url": e["url"], "title": e["title"], "fmt": "video",
                          "quality": gq} for e in entries], downloads.LANE_BATCH)
            st.success(f"📦 Queued **{n}** as MP4 — see **Downloads** above.")

        # -- AI Triage: let AI classify + pre-pick what to grab ------------- #
        if st.session_state.get("ai_on"):
            with st.expander("🤖 AI Triage — let AI pick what to grab", expanded=False):
                st.caption("AI reads every title and sorts them, so you can grab "
                           "just what you want (e.g. **official music only**, skip "
                           "shorts / vlogs / interviews). Only titles are sent.")
                ch_titles = [e["title"] for e in entries]
                cache = ai.cached_analysis()
                done = [e for e in entries if e["title"] in cache]
                if st.button(f"✨ Analyze these {len(entries)} videos with AI",
                             key="triage_run"):
                    bar = st.progress(0.0)
                    note = st.empty()

                    def _tp(d, n, _b=bar, _n=note):
                        _b.progress(d / max(n, 1))
                        _n.caption(f"Classifying… {d}/{n}")

                    with st.spinner("AI is sorting the channel… (big ones take a bit)"):
                        ai.analyze_titles(ch_titles, progress=_tp)
                    st.rerun()

                if done:
                    from collections import Counter
                    cats = Counter(cache[e["title"]]["category"] for e in done)
                    st.caption(f"Classified **{len(done)}/{len(entries)}**.  "
                               + " · ".join(f"{c}: {n}" for c, n in cats.most_common()))
                    cat_opts = [c for c, _ in cats.most_common()]
                    default = [c for c in cat_opts if c == "Music"] or cat_opts[:1]
                    pick = st.multiselect("Categories to include", cat_opts,
                                          default=default, key="triage_cats")
                    official = st.checkbox("Official releases only", value=True,
                                           key="triage_official")
                    chosen = [e for e in done
                              if cache[e["title"]]["category"] in pick
                              and (not official or cache[e["title"]].get("is_official"))]
                    tf1, tf2 = st.columns(2)
                    tfmt = tf1.radio("Format", ["🎵 MP3", "🎬 MP4"], horizontal=True,
                                     key="triage_fmt")
                    tq = tf2.selectbox("Quality", ["Best Available", "720p", "480p"],
                                       key="triage_q",
                                       disabled=tfmt.startswith("🎵"))
                    st.write(f"**{len(chosen)}** video(s) match your picks.")
                    if st.button(f"📦 Queue {len(chosen)} AI-picked video(s)",
                                 type="primary", key="triage_go",
                                 disabled=not chosen, use_container_width=True):
                        is_aud = tfmt.startswith("🎵")
                        jobs = [{"url": e["url"], "title": e["title"],
                                 "fmt": "audio" if is_aud else "video",
                                 "quality": None if is_aud else tq,
                                 "audio_codec": "mp3"} for e in chosen]
                        n = enqueue(jobs, downloads.LANE_BATCH)
                        st.success(f"📦 Queued **{n}** AI-picked video(s) — see "
                                   "**Downloads** above.")

        # -- Search + per-video chooser (paginated) ------------------------- #
        FMT_OPTIONS = ["🎵 MP3", "🎵 M4A (fast)", "🎬 MP4 — Best",
                       "🎬 MP4 — 720p", "🎬 MP4 — 480p", "⛔ Skip"]
        PER_PAGE = 50
        st.markdown("#### 🎚️ Or pick per video")

        srch = st.text_input("🔎 Search these videos by name",
                             key="ch_search", placeholder="Type part of a title…")
        # keep (global index, entry) so per-video choices stay stable across pages
        indexed = list(enumerate(entries))
        if srch.strip():
            q = srch.strip().lower()
            indexed = [(gi, e) for gi, e in indexed if q in e["title"].lower()]

        total_pages = max(1, (len(indexed) + PER_PAGE - 1) // PER_PAGE)
        page = min(st.session_state.get("ch_page", 1), total_pages)
        nav1, nav2, nav3 = st.columns([1, 2, 1])
        if nav1.button("← Prev", disabled=page <= 1, use_container_width=True):
            st.session_state.ch_page = page - 1
            st.rerun()
        page = min(st.session_state.get("ch_page", 1), total_pages)
        start = (page - 1) * PER_PAGE
        shown = indexed[start:start + PER_PAGE]
        nav2.markdown(f"<div style='text-align:center;padding-top:6px'>Page "
                      f"**{page}** of **{total_pages}** · showing "
                      f"{len(shown)} of {len(indexed)}"
                      f"{' matching' if srch.strip() else ''}</div>",
                      unsafe_allow_html=True)
        if nav3.button("Next →", disabled=page >= total_pages,
                       use_container_width=True):
            st.session_state.ch_page = page + 1
            st.rerun()

        if not shown:
            st.info("No videos match that search.")
        for gi, e in shown:
            pc1, pc2 = st.columns([3, 2])
            dur = dl.human_duration(e["duration"]) if e.get("duration") else ""
            pc1.write(f"**{e['title']}**" + (f"  ·  {dur}" if dur else ""))
            pc2.selectbox("format", FMT_OPTIONS, key=f"ch_fmt_{gi}",
                          label_visibility="collapsed")

        bc1, bc2 = st.columns(2)
        if bc1.button("⬇️ Download chosen (all pages)", type="primary",
                      use_container_width=True):
            jobs = []
            for gi, e in enumerate(entries):
                choice = st.session_state.get(f"ch_fmt_{gi}", "🎵 MP3")
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
                           "least one (your picks are remembered across pages).")
            else:
                n = enqueue(jobs, downloads.LANE_BATCH)
                st.success(f"📦 Queued **{n}** chosen video(s) — see **Downloads** "
                           "above.")
        if bc2.button("↺ Reset all picks to Skip", use_container_width=True):
            for gi in range(len(entries)):
                st.session_state[f"ch_fmt_{gi}"] = "⛔ Skip"
            st.rerun()
    elif res is not None:
        st.warning("No videos found there. Private content (e.g. TikTok **liked** "
                   "videos) needs a cookies.txt and a public 'Liked' list — set the "
                   "cookies path in the sidebar → Speed & advanced.")

# =========================================================================== #
# ASSISTANT MODE (natural language → actions)
# =========================================================================== #
elif mode == "🤖 Assistant":
    st.caption("Tell me what you want in plain language — I'll work out the rest.")
    st.markdown("*Try:* `download Diamond Platnumz Fine as mp3` · "
                "`grab https://youtu.be/… in 720p` · "
                "`how do I download a whole TikTok profile?`")
    instruction = st.text_input("What would you like to do?", key="agent_input",
                                placeholder="download Diamond Platnumz Fine as mp3")
    if st.button("✨ Ask the assistant", type="primary"):
        if not instruction.strip():
            st.warning("Type a request first.")
        else:
            with st.spinner("Thinking…"):
                st.session_state.agent_plan = ai.agent_plan(instruction.strip())
            st.session_state.pop("agent_results", None)

    plan = st.session_state.get("agent_plan")
    if plan:
        action = plan.get("action")
        is_aud = str(plan.get("fmt", "mp3")).lower() != "mp4"
        flabel = "MP3" if is_aud else f"MP4 ({plan.get('quality', 'Best Available')})"

        def _job(url, title=""):
            return {"url": url, "title": title, "fmt": "audio" if is_aud else "video",
                    "quality": None if is_aud else plan.get("quality", "Best Available"),
                    "audio_codec": "mp3"}

        if action == "help":
            st.info(plan.get("answer")
                    or "I'm here to help — ask me to download something, or how a "
                       "feature works.")
        elif action == "download" and plan.get("url"):
            st.success(f"**Plan:** download `{plan['url']}` as **{flabel}**")
            if st.button("⬇️ Do it", type="primary", key="agent_dl"):
                enqueue([_job(plan["url"])], downloads.LANE_NOW)
                st.success("⚡ Queued — see **Downloads** above.")
                st.session_state.pop("agent_plan", None)
        elif action == "channel" and plan.get("url"):
            st.success(f"**Plan:** grab the whole channel `{plan['url']}` as **{flabel}**")
            if st.button("📦 Grab channel", type="primary", key="agent_ch"):
                with st.spinner("Reading the channel…"):
                    res = dl.list_media(plan["url"], cookiefile)
                n = enqueue([_job(e["url"], e["title"]) for e in res["entries"]],
                            downloads.LANE_BATCH)
                st.success(f"📦 Queued **{n}** from *{res['title']}* — see **Downloads** above.")
                st.session_state.pop("agent_plan", None)
        else:  # search (also handles channel-by-name)
            q = plan.get("query") or instruction
            st.success(f"**Plan:** search for **{q}**, then you pick what to grab "
                       f"as **{flabel}**.")
            if st.button(f"🔎 Search “{q}”", type="primary", key="agent_sr"):
                with st.spinner("Searching YouTube…"):
                    st.session_state.agent_results = dl.search(
                        q, max(5, int(plan.get("count") or 1)), cookiefile)
            results = st.session_state.get("agent_results")
            if results:
                st.write(f"**Top {len(results)} result(s)** — tap ⬇️ to grab:")
                for i, r in enumerate(results):
                    rc1, rc2 = st.columns([6, 1])
                    dur = dl.human_duration(r["duration"]) if r.get("duration") else ""
                    rc1.markdown(
                        f"**{r['title']}**{(' · ' + dur) if dur else ''}  \n"
                        f"<span style='color:#888;font-size:.82em'>"
                        f"{r.get('uploader', '')}</span>", unsafe_allow_html=True)
                    if rc2.button("⬇️", key=f"agent_pick_{i}", help=f"Grab as {flabel}"):
                        enqueue([_job(r["url"], r["title"])], downloads.LANE_NOW)
                        st.success(f"⚡ Queued **{r['title']}** — see **Downloads** above.")

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
                n = enqueue(jobs, downloads.LANE_NOW)
                st.success(f"⚡ Queued **{n}** item(s) — they're downloading in "
                           "**Downloads** above while you keep working.")

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
                    n = enqueue(jobs, downloads.LANE_NOW)
                    st.success(f"⚡ Queued **{n}** item(s) — see **Downloads** "
                               "above.")

# =========================================================================== #
# DOWNLOAD HISTORY  (persistent — survives refresh & restart)
# =========================================================================== #
st.divider()
all_hist = hist.load_history()
st.subheader(f"🕘 Download history ({len(all_hist)})")

ai_on = bool(st.session_state.get("ai_on"))
ai_cache = ai.cached_analysis() if ai_on else {}

if ai_on and all_hist:
    titles_all = [h.get("title") or h.get("filename") for h in all_hist]
    analyzed = [t for t in titles_all if t in ai_cache]
    with st.expander(f"🤖 Smart Library — organize with AI "
                     f"({len(analyzed)}/{len(titles_all)} analyzed)", expanded=False):
        st.caption("AI cleans each title and tags it by **artist** and "
                   "**category**, so your downloads become a real library. "
                   "Only titles are sent online.")
        ac1, ac2 = st.columns(2)
        if ac1.button("✨ Analyze with AI", use_container_width=True,
                      help="Analyzes any titles not done yet (cached, so it's "
                           "one-time). Large histories take a little while."):
            bar = st.progress(0.0)
            note = st.empty()

            def _prog(done, total, _b=bar, _n=note):
                _b.progress(done / max(total, 1))
                _n.caption(f"Analyzing… {done}/{total}")

            with st.spinner("Asking the AI to clean up your titles…"):
                ai.analyze_titles(titles_all, progress=_prog)
            st.rerun()
        if ac2.button("🏷️ Write tags to files", use_container_width=True,
                      help="Writes artist/title/genre into the actual files "
                           "(only where the file still exists)."):
            done = 0
            for _h in all_hist:
                _t = _h.get("title") or _h.get("filename")
                _m = ai_cache.get(_t)
                if _m and os.path.isfile(_h.get("path", "")):
                    if ai.write_tags(_h["path"], artist=_m.get("artist"),
                                     title=_m.get("clean_title"),
                                     genre=_m.get("category")):
                        done += 1
            st.success(f"Tagged {done} file(s).")
        if analyzed:
            from collections import Counter
            cats = Counter(ai_cache[t]["category"] for t in analyzed)
            arts = Counter(ai_cache[t]["artist"] for t in analyzed
                           if ai_cache[t].get("artist"))
            g1, g2 = st.columns(2)
            g1.markdown("**By category**")
            for c, n in cats.most_common():
                g1.write(f"- {c}: **{n}**")
            g2.markdown("**Top artists**")
            for a, n in arts.most_common(8):
                g2.write(f"- {a}: **{n}**")

            # AI duplicate detection — same artist+work, beyond filename match
            groups = {}
            for _h in all_hist:
                _m = ai_cache.get(_h.get("title") or _h.get("filename"))
                if _m and _m.get("artist") and _m.get("clean_title"):
                    k = (_m["artist"].strip().lower(),
                         _m["clean_title"].strip().lower())
                    groups.setdefault(k, []).append(_h)
            dupes = {k: v for k, v in groups.items() if len(v) > 1}
            if dupes:
                st.markdown("---")
                tot = sum(len(v) for v in dupes.values())
                st.markdown(f"**🔁 Possible duplicates** — {tot} files in "
                            f"{len(dupes)} group(s) (matched by AI artist + title, "
                            "not just filename)")
                for (artist, _t), grp in list(dupes.items())[:12]:
                    nice = (ai_cache.get(grp[0].get('title')
                            or grp[0].get('filename'), {}).get('clean_title')
                            or grp[0].get('title'))
                    st.caption(f"**{artist.title()} — {nice}** · {len(grp)} copies")
                    for it in grp:
                        d1, d2, d3 = st.columns([7, 1, 1])
                        d1.write(f"   • {it.get('filename')}  "
                                 f"<span style='color:#888;font-size:.8em'>"
                                 f"({it.get('fmt')}, {fmt_size(it.get('size', 0))})"
                                 f"</span>", unsafe_allow_html=True)
                        if d2.button("📂", key=f"dup_o_{it['id']}",
                                     help="Open folder"):
                            open_in_explorer(it["path"])
                        if d3.button("✕", key=f"dup_d_{it['id']}",
                                     help="Remove from history"):
                            hist.delete_entry(it["id"])
                            st.rerun()

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
    pc1, pc2, pc3 = st.columns([2.5, 1.3, 1.2])
    pc1.caption(f"Showing **{len(filtered)}** of {len(all_hist)} downloads  ·  "
                f"{fmt_size(total_size)} total")
    per_sel = pc2.selectbox("Per page",
                            ["10 per page", "20 per page", "30 per page",
                             "50 per page", "Show all"], index=1,
                            key="hist_per_page", label_visibility="collapsed")
    if pc3.button("🗑️ Clear all", use_container_width=True,
                  help="Permanently remove every entry from your history"):
        hist.clear_history()
        st.rerun()

    if not filtered:
        st.info("No downloads match those filters.")
    else:
        # Page the (already filtered) list into chunks, or show the full list.
        if per_sel.startswith("Show"):
            page_items = filtered
        else:
            per = int(per_sel.split()[0])
            total_pages = max(1, (len(filtered) + per - 1) // per)
            cur_page = min(st.session_state.get("hist_page", 1), total_pages)
            n1, n2, n3 = st.columns([1, 2, 1])
            if n1.button("← Prev", key="hist_prev", disabled=cur_page <= 1,
                         use_container_width=True):
                st.session_state.hist_page = cur_page - 1
                st.rerun()
            n2.markdown(f"<div style='text-align:center;padding-top:6px'>Page "
                        f"**{cur_page}** of **{total_pages}**</div>",
                        unsafe_allow_html=True)
            if n3.button("Next →", key="hist_next", disabled=cur_page >= total_pages,
                         use_container_width=True):
                st.session_state.hist_page = cur_page + 1
                st.rerun()
            start = (cur_page - 1) * per
            page_items = filtered[start:start + per]

        # Re-download recovery: rebuild a job from a history record.
        def _hist_job(h):
            ext = os.path.splitext(h.get("filename", ""))[1].lower()
            if h.get("fmt") == "audio":
                return {"url": h.get("url"), "title": h.get("title", ""),
                        "fmt": "audio",
                        "audio_codec": "m4a" if ext == ".m4a" else "mp3"}
            return {"url": h.get("url"), "title": h.get("title", ""),
                    "fmt": "video", "quality": "Best Available"}

        redl = [h for h in page_items if h.get("url")]
        if redl and st.button(f"⤓ Re-download this page ({len(redl)})",
                              help="Re-fetch these from their original links — "
                                   "handy if files were moved or deleted"):
            n = enqueue([_hist_job(h) for h in redl], downloads.LANE_NOW)
            st.success(f"⚡ Queued **{n}** re-download(s) — see **Downloads** above.")

        for h in page_items:
            icon = "🎬" if h.get("fmt") == "video" else "🎵"
            hc1, hc2, hc3, hc4 = st.columns([7, 1, 1, 1])
            _m = ai_cache.get(h.get("title") or h.get("filename")) if ai_on else None
            ai_badge = ""
            if _m:
                ai_badge = (f" · 🏷️ {_m.get('category', '')}"
                            + (f" · {_m['artist']}" if _m.get("artist") else ""))
            on_disk = bool(h.get("path") and os.path.isfile(h["path"]))
            miss = "" if on_disk else " · ⚠️ file missing"
            hc1.markdown(
                f"{icon} **{h.get('title') or h.get('filename')}**  \n"
                f"<span style='color:#888;font-size:0.82em'>"
                f"{h.get('site', '')} · {when_label(h.get('ts'))} · "
                f"{fmt_size(h.get('size', 0))}{ai_badge}{miss}</span>",
                unsafe_allow_html=True)
            if hc2.button("⤓", key=f"hredl_{h['id']}", help="Re-download",
                          disabled=not h.get("url")):
                enqueue([_hist_job(h)], downloads.LANE_NOW)
                st.success(f"⚡ Re-downloading **{h.get('title') or 'item'}**.")
            if hc3.button("📂", key=f"hopen_{h['id']}", help="Open containing folder"):
                if not open_in_explorer(h["path"]):
                    st.warning("That file/folder may have been moved or deleted.")
            if hc4.button("✕", key=f"hdel_{h['id']}",
                          help="Remove from history (keeps the file)"):
                hist.delete_entry(h["id"])
                st.rerun()

# =========================================================================== #
# ARCHIVE RECOVERY CENTER  (permanent catalog — survives Clear History)
# =========================================================================== #
st.divider()


@st.cache_data(show_spinner=False)
def _load_archive(_mtime):
    return archive.load()


arch_all = _load_archive(archive.mtime())
with st.expander(f"🗄️ Archive Recovery Center — {len(arch_all)} record(s) "
                 "(survives Clear History)"):
    st.caption("A permanent, lightweight catalog of everything you've ever "
               "downloaded. It is **not** cleared when you clear history — so you "
               "can always find and re-download past media, even if the files or "
               "history were removed.")
    if not arch_all:
        st.caption("Your downloads are catalogued here automatically.")
    else:
        a1, a2, a3, a4 = st.columns([2.4, 1.3, 1.3, 1.2])
        aq = a1.text_input("Search archive", key="arch_q",
                           placeholder="Search title / artist / link…",
                           label_visibility="collapsed")
        asite = a2.selectbox("Site", ["All sites"] + archive.sites(arch_all),
                             key="arch_site", label_visibility="collapsed")
        atype = a3.selectbox("Type", ["All types", "🎬 Video", "🎵 Audio"],
                             key="arch_type", label_visibility="collapsed")
        awhen = a4.selectbox("When", ["All time", "Last 7 days", "Last 30 days",
                                      "Last year"], key="arch_when",
                             label_visibility="collapsed")
        af = archive.filter_records(arch_all, aq, asite, atype, awhen)

        s1, s2, s3 = st.columns([3, 1.2, 1.2])
        s1.caption(f"Showing **{len(af)}** of {len(arch_all)} archived "
                   f"download(s) · {fmt_size(sum(r.get('size', 0) for r in af))}")
        s2.download_button("⬇️ Export CSV", archive.to_csv(af),
                           file_name="umd_archive.csv", mime="text/csv",
                           use_container_width=True, disabled=not af)
        ap = af[:200]
        if ap and s3.button(f"⤓ Re-download ({len(ap)})", key="arch_redl_all",
                            use_container_width=True,
                            help="Re-fetch the shown records from their links"):
            jobs = [{"url": r["url"], "title": r.get("title", ""),
                     "fmt": r.get("fmt", "audio"),
                     "audio_codec": "m4a" if r.get("ext") == ".m4a" else "mp3",
                     "quality": "Best Available"} for r in ap if r.get("url")]
            n = enqueue(jobs, downloads.LANE_BATCH)
            st.success(f"⚡ Queued **{n}** re-download(s) — see **Downloads** above.")

        if not af:
            st.info("No archived downloads match those filters.")
        for r in ap:
            icon = "🎬" if r.get("fmt") == "video" else "🎵"
            ac1, ac2, ac3 = st.columns([7, 1, 1])
            ac1.markdown(
                f"{icon} **{r.get('title') or r.get('url')}**  \n"
                f"<span style='color:#888;font-size:0.82em'>"
                f"{r.get('site', '')} · {when_label(r.get('ts'))} · "
                f"{r.get('ext', '')} · {fmt_size(r.get('size', 0))}</span>",
                unsafe_allow_html=True)
            if ac2.button("⤓", key=f"arc_redl_{r.get('id') or r.get('url')}",
                          help="Re-download"):
                enqueue([{"url": r["url"], "title": r.get("title", ""),
                          "fmt": r.get("fmt", "audio"),
                          "audio_codec": "m4a" if r.get("ext") == ".m4a" else "mp3",
                          "quality": "Best Available"}], downloads.LANE_NOW)
                st.success(f"⚡ Re-downloading **{r.get('title') or 'item'}**.")
            if ac3.button("↩️", key=f"arc_rest_{r.get('id') or r.get('url')}",
                          help="Restore this record to visible History"):
                hist.add_archived(r)
                st.success("Restored to History.")


# =========================================================================== #
# LIBRARY & CLEANUP  (exact-dup finder — content hash only, quarantine first)
# =========================================================================== #
st.divider()
st.subheader("🗂️ Library & Cleanup")
_scan_base = library.get_root() if library.is_enabled() else main_dir
scan_folders = library.collapse_folders([_scan_base])

st.caption("Finds **only exact** duplicate files — identical **content** "
           "(same size **and** same SHA-256 hash). Never by filename. "
           "Scanning: " + (" · ".join(f"`{p}`" for p in scan_folders)
                           or "no valid folder"))
sc1, sc2 = st.columns([2, 1])
if sc1.button("🔍 Scan for duplicates", disabled=not scan_folders,
              use_container_width=True):
    bar = st.progress(0.0)
    note = st.empty()

    def _dp(d, n, _b=bar, _n=note):
        _b.progress(d / max(n, 1))
        _n.caption(f"Hashing… {d}/{n}")

    with st.spinner("Hashing file contents…"):
        st.session_state.dup_groups = library.scan_duplicates(scan_folders,
                                                              progress=_dp)
    note.empty()
    st.rerun()

dup_groups = st.session_state.get("dup_groups")
if dup_groups is not None:
    if not dup_groups:
        st.success("No exact duplicates found — nothing to clean. 🎉")
    else:
        total_recover = sum(g["recover"] for g in dup_groups)
        total_files = sum(len(g["dups"]) for g in dup_groups)
        st.warning(f"Found **{total_files}** exact duplicate(s) in "
                   f"{len(dup_groups)} group(s) · **{fmt_size(total_recover)}** "
                   "reclaimable. Review the evidence, then move them to "
                   "**Quarantine** (you can restore anytime).")
        for g in dup_groups[:80]:
            with st.container(border=True):
                st.markdown(f"✅ **Keep:** `{g['keeper']}`")
                for d in g["dups"]:
                    st.markdown(f"🟠 **Duplicate:** `{d}`")
                st.caption(f"{g['reason']} · {fmt_size(g['size'])} each · "
                           f"SHA-256 `{g['hash_short']}…` · "
                           f"reclaims {fmt_size(g['recover'])}")
        q1, q2 = st.columns([2, 1])
        if q1.button("🛡️ Move duplicates to Quarantine", type="primary",
                     use_container_width=True,
                     help="Moves (not deletes) the duplicates into "
                          "Quarantine/Duplicates — fully restorable"):
            to_move = [d for g in dup_groups for d in g["dups"]]
            batch, moved = library.quarantine(to_move, root=_scan_base)
            st.success(f"Moved **{moved}** duplicate(s) to Quarantine "
                       f"(`{batch}`). Restore anytime below.")
            st.session_state.pop("dup_groups", None)
        if q2.button("Keep all", use_container_width=True):
            st.session_state.pop("dup_groups", None)
            st.rerun()

# -- Quarantine management (restore / permanent delete) --------------------- #
_batches = library.list_quarantine(root=_scan_base)
if _batches:
    qtot = sum(b["bytes"] for b in _batches)
    with st.expander(f"🛡️ Quarantine — {sum(len(b['items']) for b in _batches)} "
                     f"file(s), {fmt_size(qtot)} (restorable)"):
        st.caption("Quarantined duplicates are still on disk. Restore them, or "
                   "permanently delete (to the Recycle Bin) once you're sure.")
        for b in _batches:
            with st.container(border=True):
                bc1, bc2, bc3 = st.columns([3, 1, 1])
                bc1.markdown(f"**{b['name']}** · {len(b['items'])} file(s) · "
                             f"{fmt_size(b['bytes'])}")
                if bc2.button("♻️ Restore", key=f"qr_{b['name']}",
                              use_container_width=True):
                    n = library.restore_batch(b["batch"])
                    st.success(f"Restored **{n}** file(s) to their original "
                               "locations.")
                    st.rerun()
                if bc3.button("🗑️ Delete", key=f"qp_{b['name']}",
                              use_container_width=True,
                              help="Permanently remove this batch (to Recycle Bin)"):
                    n = library.purge_batch(b["batch"])
                    st.success(f"Permanently removed **{n}** file(s) "
                               "(to the Recycle Bin).")
                    st.rerun()
                for it in b["items"][:8]:
                    bc1.caption(f"• {os.path.basename(it['quarantined'])} "
                                f"← {it['original']}")

# --------------------------------------------------------------------------- #
# Footer
# --------------------------------------------------------------------------- #
st.divider()
fcol1, fcol2 = st.columns([3, 2])
fcol1.caption("Built with Streamlit + yt-dlp + ffmpeg, running locally. "
              "Only download content you have the rights to.")
fcol2.markdown(
    f"<div style='text-align:right;font-size:0.82em;color:#888'>"
    f"{branding.APP_NAME} v{branding.VERSION} · Published by "
    f"<b>{branding.PUBLISHER}</b>, {branding.COUNTRY}<br>"
    f"<a href='mailto:{branding.EMAIL}'>{branding.EMAIL}</a> · "
    f"<a href='{branding.WEBSITE}'>{branding.WEBSITE}</a></div>",
    unsafe_allow_html=True)
