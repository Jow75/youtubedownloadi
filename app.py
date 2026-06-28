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

import base64
import html
import logging
import os
import random
import re
from datetime import datetime, timedelta
from pathlib import Path

import streamlit as st
import streamlit.components.v1 as components

# Silence Streamlit's deprecation log spam for `st.components.v1.html` and
# `use_container_width`. We KEEP components.html on purpose: the floating player
# needs a sandboxed iframe with JavaScript (window.frameElement to drag/float,
# and isolated CSS). st.html renders INLINE — it would leak the player's CSS into
# the whole app and null out frameElement — so it isn't a drop-in replacement.
# Streamlit is pinned (requirements.txt) to a version that still ships
# components.html; a proper player migration is tracked as a separate task.
_dep_logger = logging.getLogger("streamlit.deprecation_util")
if not getattr(_dep_logger, "_umd_quiet", False):
    _DEPREC_NEEDLES = ("components.v1.html", "use_container_width", "st.iframe")
    _dep_logger.addFilter(lambda r: not any(n in r.getMessage() for n in _DEPREC_NEEDLES))
    _dep_logger._umd_quiet = True

import ai
import archive
import artists
import branding
import chats
import discover
import downloader as dl
import downloads
import follows
import history as hist
import library
import licensing
import player
import playlists


def _esc(s):
    """HTML-escape a dynamic value before embedding it in an unsafe_allow_html
    markdown string. Media titles/labels come from remote metadata (yt-dlp / the
    YouTube API), so a crafted title like '<img onerror=…>' must never render as
    live HTML in the app's WebView. Ordinary titles are unaffected (only & < > "
    are rewritten, which the browser renders back as the original characters)."""
    return html.escape(str(s if s is not None else ""))


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
    layout="wide",
    initial_sidebar_state="expanded",
)

# BAZIQ HUE app-icon mark (gradient square + download arrow) — same artwork as mobile.
_BRAND_SVG = (
    '<svg width="56" height="56" viewBox="0 0 108 108" xmlns="http://www.w3.org/2000/svg">'
    '<defs><linearGradient id="umdg" x1="0" y1="0" x2="108" y2="108" gradientUnits="userSpaceOnUse">'
    '<stop offset="0" stop-color="#7C6CFF"/><stop offset="1" stop-color="#22D3EE"/></linearGradient></defs>'
    '<rect width="108" height="108" rx="24" fill="url(#umdg)"/>'
    '<path d="M50,34 L58,34 L58,52 L66,52 L54,68 L42,52 L50,52 Z" fill="#fff"/>'
    '<path d="M41,73 L67,73 A2,2 0 0 1 67,79 L41,79 A2,2 0 0 1 41,73 Z" fill="#fff"/></svg>')


def _inject_brand_css():
    """Premium BAZIQ HUE styling on top of the dark theme — readable width, brand
    tabs/buttons, rounded cards, and the gradient hero used on the Home screen."""
    st.markdown("""
    <style>
      #MainMenu, footer, [data-testid="stToolbar"], [data-testid="stDecoration"] { visibility:hidden; height:0; }
      /* Always keep the sidebar show/hide control reachable (the arrow that
         reopens the left panel after you collapse it). */
      [data-testid="stSidebarCollapsedControl"], [data-testid="collapsedControl"],
      [data-testid="stSidebarCollapseButton"], [data-testid="stExpandSidebarButton"],
      [data-testid="stSidebarCollapsedControl"] button, [data-testid="stSidebarHeader"] button {
        visibility:visible !important; opacity:1 !important; z-index:1000000 !important; }
      .block-container { padding-top:1.6rem; padding-bottom:3rem; max-width:1200px; }
      button[data-baseweb="tab"] { font-weight:600; font-size:14.5px; }
      [data-baseweb="tab-highlight"] { background-color:#8B6CFF !important; }
      .stButton > button { border-radius:12px; font-weight:600; transition:all .15s ease; }
      .stButton > button:hover { border-color:#8B6CFF; transform:translateY(-1px); }
      [data-testid="stMetric"] { background:#171128; border:1px solid #2a2342; border-radius:16px; padding:14px 18px; }
      .stTextInput input, .stTextArea textarea { border-radius:10px; }
      h1, h2, h3 { letter-spacing:-.3px; }
      [data-testid="stImage"] img { border-radius:12px; transition:transform .18s ease, box-shadow .18s ease; }
      [data-testid="stImage"]:hover img { transform:scale(1.03); box-shadow:0 10px 24px -10px rgba(0,0,0,.65); }
      .umd-hero { background:linear-gradient(125deg,#7C5CFF 0%,#B44DFF 48%,#18C8FF 100%);
        border-radius:24px; padding:26px 30px; color:#fff; margin:2px 0 18px;
        box-shadow:0 16px 44px -14px rgba(124,92,255,.55); }
      .umd-hero h1 { font-size:30px; margin:0; color:#fff; letter-spacing:-.5px; }
      .umd-hero p { opacity:.95; margin:6px 0 0; font-size:15px; }
      .umd-chip { display:inline-block; background:rgba(255,255,255,.18); border:1px solid rgba(255,255,255,.32);
        padding:5px 13px; border-radius:999px; font-size:12.5px; font-weight:600; margin:12px 8px 0 0; }
      /* ---- Persistent floating mini-player (hidden control bridge) ---- */
      .st-key-mp_controls { display:none !important; }

      /* ---- Assistant — natural chat flow (Gemini / Claude style) ---- */
      /* User → right, ONE subtle bubble that hugs its text. */
      [class*="st-key-umsg_"] { width:fit-content !important; max-width:76% !important;
        align-self:flex-end !important; margin:6px 0 18px auto !important;
        background:#272140 !important; border:1px solid #332b54; border-radius:18px 18px 6px 18px;
        padding:2px 17px !important; }
      [class*="st-key-umsg_"] [data-testid="stMarkdownContainer"] p { color:#F2EFFB !important; }
      /* Assistant → left, NO box at all: just text that breathes. */
      [class*="st-key-amsg_"] { background:transparent !important; border:none !important;
        padding:0 !important; margin:6px 0 22px 2px !important; max-width:94% !important; }
      [class*="st-key-umsg_"] [data-testid="stMarkdownContainer"] p,
      [class*="st-key-amsg_"] [data-testid="stMarkdownContainer"] p { font-size:15px; line-height:1.7; }
      [class*="st-key-amsg_"] [data-testid="stMarkdownContainer"] p:first-child { margin-top:0; }
      [class*="st-key-amsg_"] code, [class*="st-key-umsg_"] code { background:#241a3a;
        padding:1px 6px; border-radius:6px; font-size:13.5px; }
      [data-testid="stChatInput"] { border-radius:16px; }

      /* ---- Discover library-awareness (✅ downloaded · 🔄 downloading) ---- */
      .umd-thumb { position:relative; line-height:0; }
      .umd-thumb img { width:100%; border-radius:12px; display:block; }
      .umd-badge { position:absolute; top:7px; right:7px; width:26px; height:26px;
        border-radius:50%; display:flex; align-items:center; justify-content:center;
        font-size:15px; font-weight:800; box-shadow:0 2px 8px rgba(0,0,0,.5); }
      .umd-have { background:#16a34a; color:#fff; }
      .umd-busy { background:rgba(0,0,0,.62); }
      .umd-have-txt { color:#3ad07a; font-weight:600; font-size:13px; }
      .umd-busy-txt { color:#cbb9ff; font-weight:600; font-size:13px;
        display:inline-flex; align-items:center; gap:7px; }
      .umd-spinner { width:14px; height:14px; border:2px solid rgba(255,255,255,.35);
        border-top-color:#fff; border-radius:50%; display:inline-block;
        animation:umd-spin .8s linear infinite; }
      @keyframes umd-spin { to { transform:rotate(360deg); } }
    </style>""", unsafe_allow_html=True)


_inject_brand_css()


def _home_hero():
    st.markdown(f"""
    <div class="umd-hero">
      <div style="display:flex;align-items:center;gap:16px;">
        {_BRAND_SVG}
        <div>
          <h1>Universal Media Downloader</h1>
          <p>Download anything · organise it beautifully · play it anywhere — by <b>BAZIQ HUE</b></p>
        </div>
      </div>
      <div>
        <span class="umd-chip">🎵 MP3 &amp; 🎬 MP4</span>
        <span class="umd-chip">🔭 Discover</span>
        <span class="umd-chip">🤖 AI Assistant</span>
        <span class="umd-chip">📚 Smart library</span>
      </div>
    </div>""", unsafe_allow_html=True)

DEFAULT_DOWNLOAD_DIR = str(Path.home() / "Downloads")


def open_in_explorer(path):
    try:
        target = path if os.path.isdir(path) else os.path.dirname(path)
        os.startfile(target)  # Windows
        return True
    except Exception:  # noqa: BLE001
        return False


def open_and_select(path):
    """Open Explorer with the file highlighted (so you land right on it)."""
    import subprocess
    try:
        if path and os.path.isfile(path):
            subprocess.Popen(["explorer", "/select,", os.path.normpath(path)])
            return True
    except Exception:  # noqa: BLE001
        pass
    return open_in_explorer(path)


def media_job(h):
    """Build a re-download job from a history/record dict."""
    ext = os.path.splitext(h.get("filename", "") or "")[1].lower()
    if h.get("fmt") == "audio":
        return {"url": h.get("url"), "title": h.get("title", ""), "fmt": "audio",
                "audio_codec": "m4a" if ext == ".m4a" else "mp3"}
    return {"url": h.get("url"), "title": h.get("title", ""), "fmt": "video",
            "quality": "Best Available"}


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

    if st.button("📂 Open main folder", width="stretch"):
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
        if st.button("🏗️ Create / repair folders", width="stretch"):
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
            if "ai_on" not in st.session_state:
                st.session_state.ai_on = ai.is_enabled()   # remembered across restarts
            _prev_on = st.session_state.ai_on
            st.session_state.ai_on = st.checkbox(
                "Enable AI features", value=_prev_on,
                help="Turn on the AI tools. Stays on across restarts. Only titles are "
                     "sent online — never your media files.")
            if st.session_state.ai_on != _prev_on:
                ai.save_settings(enabled=st.session_state.ai_on)
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
        if kc1.button("💾 Save key", width="stretch"):
            k = new_key.strip()
            if not k:
                st.warning("Paste a key first.")
            else:
                with st.spinner("Checking the key…"):
                    ok, res = ai.validate_key(sel, k)
                if ok:
                    ai.save_settings(provider=sel, key=k, enabled=True)
                    st.session_state.ai_on = True
                    st.success(f"Saved ✓ — {len(res)} models available. AI is now on.")
                    st.rerun()
                elif "rejected" in str(res).lower():
                    st.error(res)
                else:
                    ai.save_settings(provider=sel, key=k, enabled=True)
                    st.session_state.ai_on = True
                    st.warning(f"Saved, but couldn't verify right now ({res}). "
                               "It'll be used once you're online.")
                    st.rerun()
        if kc2.button("🗑️ Remove key", width="stretch"):
            ai.clear_key()
            ai.save_settings(enabled=False)
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
        if cga.button("Activate", width="stretch"):
            ok, msg = lm.activate(_key)
            (st.success if ok else st.error)(msg)
        if cgb.button("Remove", width="stretch"):
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
                 width="stretch"):
        library.save(root=(loc.strip() or library.default_root()),
                     enabled=True, configured=True)
        library.ensure_structure()
        st.success("Library ready! Loading the app…")
        st.rerun()
    if w2.button("Not now — use my Downloads folder", width="stretch"):
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


def _extract_raw_art(path):
    """Raw embedded cover-art bytes from a media file (mp3 APIC / mp4 covr /
    flac pictures), or None. yt-dlp embeds the thumbnail on download, so most
    files have one."""
    try:
        import mutagen
        f = mutagen.File(path)
        if f is None:
            return None
        tags = getattr(f, "tags", None)
        if tags:
            for k in list(tags.keys()):
                if str(k).startswith("APIC"):
                    try:
                        return tags[k].data
                    except Exception:  # noqa: BLE001
                        pass
            if "covr" in tags:
                try:
                    return bytes(tags["covr"][0])
                except Exception:  # noqa: BLE001
                    pass
        pics = getattr(f, "pictures", None)
        if pics:
            return pics[0].data
    except Exception:  # noqa: BLE001
        return None
    return None


@st.cache_data(show_spinner=False, max_entries=400)
def _cover_art(path, _sig):
    """Embedded cover art as small JPEG thumbnail bytes (or None). Cached per
    (path, _sig) — pass the file's mtime as _sig so it refreshes if the file
    changes. Resized small so a whole library of cards stays light to render."""
    raw = _extract_raw_art(path)
    if not raw:
        return None
    try:
        import io

        from PIL import Image
        im = Image.open(io.BytesIO(raw)).convert("RGB")
        im.thumbnail((240, 240))
        buf = io.BytesIO()
        im.save(buf, format="JPEG", quality=82)
        return buf.getvalue()
    except Exception:  # noqa: BLE001
        return raw


def _art_for(path):
    """Convenience: cover art for a path, cache-keyed on its mtime."""
    try:
        return _cover_art(path, os.path.getmtime(path))
    except Exception:  # noqa: BLE001
        return None


@st.cache_data(show_spinner=False, max_entries=5000)
def _duration_s(path, _sig):
    """Track length in seconds (cached per path+mtime) via mutagen."""
    try:
        import mutagen
        f = mutagen.File(path)
        return int(getattr(f.info, "length", 0) or 0) if f else 0
    except Exception:  # noqa: BLE001
        return 0


def _fmt_dur(s):
    s = int(s or 0)
    return f"{s // 60}:{s % 60:02d}" if s > 0 else ""


def _empty(icon, title, hint=""):
    """A centered, friendly empty state (instead of a bare caption)."""
    st.markdown(
        f"<div style='text-align:center;padding:40px 12px;color:#9a93b5;'>"
        f"<div style='font-size:46px;line-height:1'>{icon}</div>"
        f"<div style='font-size:16px;font-weight:600;margin-top:10px;color:#cfcadf'>{title}</div>"
        f"<div style='font-size:13px;margin-top:4px'>{hint}</div></div>",
        unsafe_allow_html=True)


def _lib_placeholder(fmt):
    return ("<div style='aspect-ratio:1;border-radius:12px;display:flex;align-items:center;"
            "justify-content:center;font-size:34px;background:linear-gradient(135deg,#2a2342,#171128);'>"
            f"{'🎬' if fmt == 'video' else '🎵'}</div>")


# --------------------------------------------------------------------------- #
# In-app player queue — drives the persistent floating mini-player.            #
# The IDM-proof blob engine lives in player.py; here we only manage the queue. #
# --------------------------------------------------------------------------- #
def _mp_state():
    ss = st.session_state
    ss.setdefault("mp_queue", [])        # list of file paths
    ss.setdefault("mp_index", 0)
    ss.setdefault("mp_open", False)
    ss.setdefault("mp_shuf", False)      # shuffle on?  (key differs from the button)
    ss.setdefault("mp_rep", "off")       # repeat: off | all | one
    ss.setdefault("mp_order", [])        # play order (indices) — shuffled when on
    return ss


def _mp_reshuffle():
    """Rebuild the play order, keeping the current track first when shuffling."""
    ss = _mp_state()
    n = len(ss.mp_queue)
    order = list(range(n))
    if ss.mp_shuf and n > 1:
        rest = [i for i in order if i != ss.mp_index]
        random.shuffle(rest)
        order = [ss.mp_index] + rest
    ss.mp_order = order


def _mp_play(paths, index=0):
    """Start a queue and play the chosen track in the floating mini-player.
    (Videos open in the expanded view automatically — the iframe decides that.)"""
    paths = [p for p in paths if p and os.path.isfile(p)]
    if not paths:
        return
    ss = _mp_state()
    ss.mp_queue = paths
    ss.mp_index = max(0, min(index, len(paths) - 1))
    ss.mp_open = True
    _mp_reshuffle()


def _mp_step(delta):
    """Move within the play order, honoring shuffle + repeat. Stops politely at
    the end when repeat is off (the iframe handles that case without looping)."""
    ss = _mp_state()
    n = len(ss.mp_queue)
    if n == 0:
        ss.mp_open = False
        return
    order = ss.mp_order or list(range(n))
    try:
        pos = order.index(ss.mp_index)
    except ValueError:
        pos = 0
    pos += delta
    if pos < 0:
        pos = n - 1 if ss.mp_rep == "all" else 0
    elif pos >= n:
        pos = 0 if ss.mp_rep == "all" else n - 1
    ss.mp_index = order[pos % n]


def _mp_has_next():
    """Is there a track after the current one (given shuffle + repeat)?"""
    ss = _mp_state()
    n = len(ss.mp_queue)
    if n == 0:
        return False
    if ss.mp_rep in ("all", "one"):
        return True
    order = ss.mp_order or list(range(n))
    try:
        return order.index(ss.mp_index) < n - 1
    except ValueError:
        return False


def _mp_current():
    ss = _mp_state()
    if not ss.mp_open or not ss.mp_queue:
        return None
    if ss.mp_index >= len(ss.mp_queue):
        ss.mp_index = 0
    p = ss.mp_queue[ss.mp_index]
    return p if os.path.isfile(p) else None


@st.cache_data(show_spinner=False, max_entries=3)
def _media_data_uri(path, _sig):
    """Whole media file as a base64 data: URI (IDM-proof). Cached small (only the
    last 3 tracks) so memory stays bounded even when inlining ~75 MB videos —
    audio is tiny, and the player only ever embeds the CURRENT track."""
    return player.media_data_uri(path)


def _art_data_uri(path):
    art = _art_for(path)
    if not art:
        return ""
    return "data:image/jpeg;base64," + base64.b64encode(art).decode("ascii")


_MP_QUEUE_CAP = 40        # Up-Next rows + their hidden jump-buttons (keeps reruns light)


@st.fragment
def _mini_player():
    """The persistent now-playing UI, rendered once at the top level (outside the
    tabs) so it floats over every screen. It's a @st.fragment so transport actions
    rerun ONLY this player — never the whole 8-tab app, which is what made playback
    snappy instead of re-scanning the library each time. The visible card is ONE
    player.py iframe (mini + full share one <audio>/<video>, so Expand never stops
    the music); the hidden buttons below are the bridge its in-iframe controls click."""
    ss = _mp_state()
    order = ss.mp_order or list(range(len(ss.mp_queue)))

    # Hidden control bridge — the iframe clicks these via `.st-key-<key> button`.
    # (Expand/collapse + dragging happen inside the iframe with no rerun at all.)
    with st.container(key="mp_controls"):
        if st.button("prev", key="mp_prev"):
            _mp_step(-1); st.rerun(scope="fragment")
        if st.button("next", key="mp_next"):
            _mp_step(+1); st.rerun(scope="fragment")
        if st.button("close", key="mp_close"):
            ss.mp_open = False; st.rerun(scope="fragment")
        if st.button("shuffle", key="mp_shuffle"):
            ss.mp_shuf = not ss.mp_shuf; _mp_reshuffle(); st.rerun(scope="fragment")
        if st.button("repeat", key="mp_repeat"):
            ss.mp_rep = {"off": "all", "all": "one", "one": "off"}[ss.mp_rep]
            st.rerun(scope="fragment")
        if st.button("openfile", key="mp_openfile"):
            cur = _mp_current()
            if cur:
                open_and_select(cur)
        # One jump-button per visible Up-Next row; the iframe clicks mpq_<index>.
        for qi in order[:_MP_QUEUE_CAP]:
            if st.button("jump", key=f"mpq_{qi}"):
                ss.mp_index = qi; st.rerun(scope="fragment")

    path = _mp_current()
    if not path:
        return

    title = os.path.splitext(os.path.basename(path))[0]
    try:
        artist = artists.primary_artist(path) or "Now playing"
    except Exception:  # noqa: BLE001
        artist = "Now playing"
    is_vid = player.is_video(path)
    key = player.track_key(path)
    at_end = not _mp_has_next()
    thumb = _art_data_uri(path)
    inlineable = player.can_inline(path)
    try:
        src = _media_data_uri(path, os.path.getmtime(path)) if inlineable else ""
    except OSError:
        src = ""

    # Build the Up-Next list (in play order) for inside the iframe.
    qitems = []
    for qi in order[:_MP_QUEUE_CAP]:
        qp = ss.mp_queue[qi]
        nm = os.path.splitext(os.path.basename(qp))[0][:48]
        qitems.append((qi, nm, player.is_video(qp), qi == ss.mp_index))
    qhtml = player.queue_items_html(qitems)

    html_doc = player.player_html(title, artist, thumb, src, key, qhtml,
                                  is_vid=is_vid, inlineable=inlineable,
                                  shuffle=ss.mp_shuf, repeat=ss.mp_rep, at_end=at_end)
    components.html(html_doc, height=0, scrolling=False)


@st.cache_data(show_spinner=False, max_entries=5000)
def _artists_cached(path, _sig):
    """All artists for a file (cached per path+mtime) — see artists.artists_of."""
    return artists.artists_of(path)


_LIB_SORTS = ["Newest", "Oldest", "A → Z", "Z → A", "Most songs", "Fewest songs"]


def _sort_songs(items, sort):
    if sort == "Oldest":
        return sorted(items, key=lambda m: m.get("mtime", 0))
    if sort == "A → Z":
        return sorted(items, key=lambda m: os.path.basename(m["path"]).lower())
    if sort == "Z → A":
        return sorted(items, key=lambda m: os.path.basename(m["path"]).lower(), reverse=True)
    if sort == "Most songs":            # for songs: biggest files first
        return sorted(items, key=lambda m: m.get("size", 0), reverse=True)
    if sort == "Fewest songs":
        return sorted(items, key=lambda m: m.get("size", 0))
    return sorted(items, key=lambda m: m.get("mtime", 0), reverse=True)


def _sort_artist_rows(rows, sort, recency):
    def rec(n):
        return recency.get(artists.artist_key(n), 0)
    if sort == "Fewest songs":
        return sorted(rows, key=lambda x: (x[1], x[0].lower()))
    if sort == "A → Z":
        return sorted(rows, key=lambda x: x[0].lower())
    if sort == "Z → A":
        return sorted(rows, key=lambda x: x[0].lower(), reverse=True)
    if sort == "Newest":
        return sorted(rows, key=lambda x: (-rec(x[0]), x[0].lower()))
    if sort == "Oldest":
        return sorted(rows, key=lambda x: (rec(x[0]), x[0].lower()))
    return sorted(rows, key=lambda x: (-x[1], x[0].lower()))


def _sort_playlists(pls, sort):
    if sort == "Fewest songs":
        return sorted(pls, key=lambda p: (len(p["paths"]), p["name"].lower()))
    if sort == "A → Z":
        return sorted(pls, key=lambda p: p["name"].lower())
    if sort == "Z → A":
        return sorted(pls, key=lambda p: p["name"].lower(), reverse=True)
    if sort == "Oldest":
        return sorted(pls, key=lambda p: p["id"])
    if sort == "Most songs":
        return sorted(pls, key=lambda p: (len(p["paths"]), p["name"].lower()), reverse=True)
    return sorted(pls, key=lambda p: p["id"], reverse=True)   # Newest (id = creation time)


_PAGE_SIZES = {"10": 10, "20": 20, "30": 30, "50": 50, "All": 10 ** 9}


def _paginate(items, key, default="20", noun="item", scope="app"):
    """Paginator with a HARD-TO-MISS page indicator, so users realise more items
    live on other pages (a short Artists page once read as 'artist missing').
    Per-page selector + Prev / 'Page x of N' / Next; state persists per `key`.
    `scope="fragment"` when called inside a fragment (Discover) so paging doesn't
    flash the whole app."""
    total = len(items)
    _sizes = list(_PAGE_SIZES)
    top = st.columns([3, 1.4])
    per = _PAGE_SIZES[top[1].selectbox("Per page", _sizes, index=_sizes.index(default),
                                       key=f"{key}_per", label_visibility="collapsed")]
    pages = max(1, (total + per - 1) // per)
    pk = f"{key}_pg"
    pg = min(st.session_state.get(pk, 1), pages)
    start = (pg - 1) * per
    lo, hi = (start + 1 if total else 0), min(start + per, total)
    plural = noun + ("" if total == 1 else "s")
    if pages > 1:
        top[0].markdown(
            f"<div style='padding-top:7px'><b>{total} {plural}</b> · showing "
            f"<b>{lo}–{hi}</b> · <span style='color:#9b86ff'>page <b>{pg} of {pages}</b></span>"
            f" — use ← / → for the rest</div>", unsafe_allow_html=True)
        nav = st.columns([1, 2, 1])
        if nav[0].button("← Prev", key=f"{key}_prev", disabled=pg <= 1, width="stretch"):
            st.session_state[pk] = pg - 1; st.rerun(scope=scope)
        nav[1].markdown(f"<div style='text-align:center;padding-top:6px;font-weight:700'>"
                        f"Page {pg} / {pages}</div>", unsafe_allow_html=True)
        if nav[2].button("Next →", key=f"{key}_next", disabled=pg >= pages, width="stretch"):
            st.session_state[pk] = pg + 1; st.rerun(scope=scope)
    else:
        top[0].markdown(f"<div style='padding-top:7px'><b>{total} {plural}</b></div>",
                        unsafe_allow_html=True)
    return items[start:start + per]


def _lib_song_grid(items, key_prefix, sort="Newest", cols=6):
    """Grid of media cards (cover art + name + duration + play/open), paginated."""
    items = _sort_songs(items, sort)
    page = _paginate(items, key_prefix, noun="song")
    for s in range(0, len(page), cols):
        cs = st.columns(cols)
        for col, it in zip(cs, page[s:s + cols]):
            with col:
                art = _art_for(it["path"])
                if art:
                    st.image(art, width="stretch")
                else:
                    st.markdown(_lib_placeholder(it["fmt"]), unsafe_allow_html=True)
                nm = os.path.splitext(os.path.basename(it["path"]))[0]
                _dur = _fmt_dur(_duration_s(it["path"], it.get("mtime", 0)))
                st.markdown(f"**{nm[:34]}**")
                st.caption(f"{it['ext'][1:].upper()} · {fmt_size(it['size'])}"
                           + (f" · {_dur}" if _dur else ""))
                _b = st.columns(2)
                if _b[0].button("▶", key=f"{key_prefix}_play_{it['path']}",
                                width="stretch", help="Play in app"):
                    _queue = [m["path"] for m in items]
                    _mp_play(_queue, _queue.index(it["path"]))
                    st.rerun()
                if _b[1].button("📂", key=f"{key_prefix}_open_{it['path']}",
                                width="stretch", help="Open folder"):
                    open_and_select(it["path"])


def _lib_artists_view(media, q, sort="Most songs"):
    """Spotify-style Artists: each artist's image (a track's cover art) + track
    count; click to drill into their songs. Collabs count for EACH artist; case
    variants merge — via artists.py (mobile parity)."""
    audio = [m for m in media if m["fmt"] == "audio"]
    counts, rep, recency = {}, {}, {}
    for m in audio:
        _mt = m.get("mtime", 0)
        for a in _artists_cached(m["path"], _mt):
            counts[a] = counts.get(a, 0) + 1
            k = artists.artist_key(a)
            if k and k not in rep:
                rep[k] = m["path"]
            if k:
                recency[k] = max(recency.get(k, 0), _mt)

    open_artist = st.session_state.get("lib_artist")
    if open_artist:
        if st.button("← All artists", key="lib_artist_back"):
            st.session_state.pop("lib_artist", None)
            st.rerun()
        st.markdown(f"### 🎤 {open_artist}")
        ak = artists.artist_key(open_artist)
        songs = [m for m in audio
                 if ak in {artists.artist_key(x) for x in _artists_cached(m["path"], m.get("mtime", 0))}]
        st.caption(f"{len(songs)} track(s)")
        _lib_song_grid(songs, "libart")
        return

    collapsed = artists.collapse_artist_counts(counts)
    if q.strip():
        ql = q.strip().lower()
        collapsed = [(n, c) for n, c in collapsed if ql in n.lower()]
    collapsed = _sort_artist_rows(collapsed, sort, recency)
    cols_n = 6
    page = _paginate(collapsed, "lib_art", noun="artist")
    for s in range(0, len(page), cols_n):
        cs = st.columns(cols_n)
        for col, (name, n) in zip(cs, page[s:s + cols_n]):
            with col:
                rp = rep.get(artists.artist_key(name))
                art = _art_for(rp) if rp else None
                if art:
                    st.image(art, width="stretch")
                else:
                    st.markdown(_lib_placeholder("audio"), unsafe_allow_html=True)
                st.markdown(f"**{name[:26]}**")
                st.caption(f"{n} track(s)")
                if st.button("Open", key=f"libartist_{artists.artist_key(name)}", width="stretch"):
                    st.session_state["lib_artist"] = name
                    st.rerun()


def _lib_playlists_view(media, sort="Newest"):
    """User playlists — create, open, add/remove songs, delete. Mirrors mobile."""
    pls = st.session_state.setdefault("desk_playlists", playlists.load())
    by_path = {m["path"]: m for m in media}
    audio = [m for m in media if m["fmt"] == "audio"]
    open_id = st.session_state.get("lib_playlist")

    if open_id:
        pl = next((p for p in pls if p["id"] == open_id), None)
        if not pl:
            st.session_state.pop("lib_playlist", None)
            st.rerun()
        if st.button("← All playlists", key="pl_back"):
            st.session_state.pop("lib_playlist", None)
            st.rerun()
        st.markdown(f"### 🎶 {pl['name']}")
        st.caption(f"{len(pl['paths'])} song(s)")
        with st.expander("➕ Add songs from your library"):
            _names = {os.path.basename(m["path"]): m["path"] for m in audio
                      if m["path"] not in pl["paths"]}
            _pick = st.multiselect("Songs", list(_names.keys()), key="pl_add_sel",
                                   label_visibility="collapsed")
            if st.button("Add selected", key="pl_add_btn") and _pick:
                playlists.add_paths(pls, pl["id"], [_names[n] for n in _pick])
                st.rerun()
        _items = [by_path[p] for p in pl["paths"] if p in by_path]
        if _items:
            _lib_song_grid(_items, "plview")
        else:
            st.caption("Empty — add songs above.")
        st.divider()
        _da, _db = st.columns(2)
        if pl["paths"]:
            _rmnames = {os.path.basename(p): p for p in pl["paths"] if p in by_path}
            _rm = _da.selectbox("Remove a song", ["—"] + list(_rmnames.keys()), key="pl_rm_sel")
            if _rm != "—" and _da.button("➖ Remove", key="pl_rm_btn"):
                playlists.remove_path(pls, pl["id"], _rmnames[_rm])
                st.rerun()
        if _db.button("🗑️ Delete playlist", key="pl_del"):
            playlists.delete(pls, pl["id"])
            st.session_state.pop("lib_playlist", None)
            st.rerun()
        return

    _pc = st.columns([3, 1, 1.4])
    _new = _pc[0].text_input("New playlist", key="pl_new", label_visibility="collapsed",
                             placeholder="New playlist name…")
    if _pc[1].button("➕ Create", key="pl_create", width="stretch") and _new.strip():
        playlists.create(pls, _new.strip())
        st.rerun()
    if _pc[2].button("🪄 Auto-group", key="pl_auto", width="stretch",
                     help="AI: group your library into genre & language/region playlists"):
        if not st.session_state.get("ai_on"):
            st.warning("Turn on AI in the sidebar → AI Settings first.")
        else:
            with st.spinner("Classifying your library by genre & language…"):
                _titles = {os.path.splitext(os.path.basename(m["path"]))[0]: m["path"] for m in audio}
                _tags = ai.classify_tracks(list(_titles.keys()))
            _groups = {}
            for _nm, _path in _titles.items():
                _tg = _tags.get(_nm) or {}
                _g = (_tg.get("genre") or "").strip()
                _l = (_tg.get("language") or "").strip()
                if _g and _g.lower() != "other":
                    _groups.setdefault(f"🎵 {_g}", []).append(_path)
                if _l and _l.lower() not in ("unknown", "mixed"):
                    _groups.setdefault(f"🗣 {_l}", []).append(_path)
            _n = 0
            for _gname, _paths in _groups.items():
                if len(_paths) >= 3:
                    _ex = next((p for p in pls if p["name"] == _gname), None)
                    _pl = _ex or playlists.create(pls, _gname)
                    playlists.add_paths(pls, _pl["id"], _paths)
                    _n += 1
            st.success(f"Built {_n} genre/language playlist(s)." if _n
                       else "Need ≥3 songs of a genre/language to group.")
            st.rerun()
    if not pls:
        st.caption("No playlists yet — name one above and Create, then add songs.")
        return
    _cols_n = 6
    _pls_view = _paginate(_sort_playlists(pls, sort), "lib_pls", noun="playlist")
    for _s in range(0, len(_pls_view), _cols_n):
        _cs = st.columns(_cols_n)
        for _col, _pl in zip(_cs, _pls_view[_s:_s + _cols_n]):
            with _col:
                _first = next((p for p in _pl["paths"] if p in by_path), None)
                _art = _art_for(_first) if _first else None
                if _art:
                    st.image(_art, width="stretch")
                else:
                    st.markdown(_lib_placeholder("audio"), unsafe_allow_html=True)
                st.markdown(f"**{_pl['name'][:24]}**")
                st.caption(f"{len(_pl['paths'])} song(s)")
                if st.button("Open", key=f"plopen_{_pl['id']}", width="stretch"):
                    st.session_state["lib_playlist"] = _pl["id"]
                    st.rerun()


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

    # PHASE ECHO (refined) — refresh the rest of the app ONCE, when the queue fully
    # DRAINS (everything finished), so the Assistant card / Library / Discover ticks
    # update on their own. Doing it per-song caused the page you're on (e.g. a
    # Discover search) to flicker/rebuild repeatedly during a batch — so we now only
    # rerun on the active→idle transition, never mid-batch.
    _active_now = c["active"] + c["queued"]
    _prev_active = st.session_state.get("_dl_active_prev", 0)
    st.session_state["_dl_active_prev"] = _active_now
    if _prev_active and _active_now == 0:
        st.rerun()                       # queue just drained — one full-app refresh

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
                                width="stretch"):
            mgr.cancel_all()
            st.rerun(scope="fragment")
        if finished and h3.button("Clear done", key="dl_clear",
                                  width="stretch"):
            mgr.clear_finished()
            st.session_state.pop("dl_page", None)
            st.rerun(scope="fragment")

        display = active + finished     # in-progress first, then finished
        if not display:
            st.caption("idle — queue anything; it keeps going while you browse.")
        else:
            # Page the queue into chunks so a big batch isn't one huge list.
            _per = {"5": 5, "10": 10, "20": 20, "30": 30, "40": 40, "All": 10 ** 9}
            pp1, pp2 = st.columns([3, 1.2])
            pp1.caption(f"{len(active)} active · {len(finished)} done")
            per = _per[pp2.selectbox("Show", list(_per), index=1, key="dl_per",
                                     label_visibility="collapsed")]
            total_pages = max(1, (len(display) + per - 1) // per)
            page = min(st.session_state.get("dl_page", 1), total_pages)
            if total_pages > 1:
                nv1, nv2, nv3 = st.columns([1, 2, 1])
                if nv1.button("← Prev", key="dl_prev", disabled=page <= 1,
                              width="stretch"):
                    st.session_state.dl_page = page - 1
                    st.rerun(scope="fragment")
                nv2.markdown(f"<div style='text-align:center;padding-top:6px'>"
                             f"Page **{page}** of **{total_pages}**</div>",
                             unsafe_allow_html=True)
                if nv3.button("Next →", key="dl_next", disabled=page >= total_pages,
                              width="stretch"):
                    st.session_state.dl_page = page + 1
                    st.rerun(scope="fragment")
            start = (page - 1) * per
            for j in display[start:start + per]:
                if j.status in ("downloading", "queued"):
                    lane = "📦" if j.lane == downloads.LANE_BATCH else "⚡"
                    r1, r2 = st.columns([7, 1])
                    r1.markdown(
                        f"{lane} **{_esc(j.label)}**  \n"
                        f"<span style='color:#888;font-size:.8em'>{_esc(j.detail)}</span>",
                        unsafe_allow_html=True)
                    if r2.button("✕", key=f"dlc_{j.id}", help="Cancel this download"):
                        mgr.cancel(j.id)
                        st.rerun(scope="fragment")
                    r1.progress(j.progress if j.status == "downloading" else 0.0)
                else:
                    icon = ("✅" if j.status == "done"
                            else "⛔" if j.status == "canceled" else "❌")
                    sub = (j.error if j.status == "error"
                           else os.path.basename(j.result) if j.result else j.detail)
                    art = (_art_for(j.result) if j.status == "done" and j.result
                           and os.path.isfile(j.result) else None)
                    if art:
                        tcol, r1, r2 = st.columns([0.8, 6.2, 1])
                        tcol.image(art, width=44)
                    else:
                        r1, r2 = st.columns([7, 1])
                    r1.markdown(
                        f"{icon} **{_esc(j.label)}**  \n"
                        f"<span style='color:#888;font-size:.8em'>{_esc(sub)}</span>",
                        unsafe_allow_html=True)
                    if j.status == "done" and j.result:
                        if r2.button("📂", key=f"dlo_{j.id}",
                                     help="Open containing folder"):
                            open_in_explorer(j.result)
                    elif j.status == "error" and st.session_state.get("ai_on"):
                        if r2.button("🤖", key=f"dlx_{j.id}",
                                     help="Ask AI why this failed"):
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
_mini_player()          # persistent floating now-playing bar (lives above all tabs)


all_hist = hist.load_history()
ai_on = bool(st.session_state.get("ai_on"))
ai_cache = ai.cached_analysis() if ai_on else {}

# =========================================================================== #
#  DISCOVER  (YouTube Data API v3 — mirrors the mobile app's Discover)
# =========================================================================== #
@st.cache_data(ttl=discover.TRENDING_TTL, show_spinner=False)
def _disc_trending(region, cat):
    try:
        return [v.as_dict() for v in discover.trending(region, cat)], None
    except Exception as e:  # noqa: BLE001
        return [], str(e)


@st.cache_data(ttl=discover.SEARCH_TTL, show_spinner="Searching YouTube…")
def _disc_search(query, order):
    try:
        r = discover.search_mixed(query, order)
        return {"videos": [v.as_dict() for v in r["videos"]],
                "channels": [c.as_dict() for c in r["channels"]],
                "playlists": [p.as_dict() for p in r["playlists"]]}, None
    except Exception as e:  # noqa: BLE001
        return None, str(e)


@st.cache_data(ttl=discover.TRENDING_TTL, show_spinner="Loading uploads…")
def _disc_uploads(channel_id):
    try:
        return [v.as_dict() for v in discover.latest_uploads(channel_id)], None
    except Exception as e:  # noqa: BLE001
        return [], str(e)


@st.cache_data(ttl=discover.TRENDING_TTL, show_spinner=False)
def _disc_playlist(playlist_id):
    try:
        return [v.as_dict() for v in discover.playlist_items(playlist_id)], None
    except Exception as e:  # noqa: BLE001
        return [], str(e)


def _disc_norm(s):
    """Title/filename identity — lowercase, alphanumerics only (mirrors mobile
    DownloadedIndex.norm), so a Discover title matches its saved file name."""
    return re.sub(r"[^a-z0-9]", "", (s or "").lower())


def _yt_id(url):
    """Extract the 11-char YouTube video id from a URL (or '')."""
    m = re.search(r"(?:v=|/shorts/|youtu\.be/|/embed/|/v/)([A-Za-z0-9_-]{11})", url or "")
    return m.group(1) if m else ""


@st.cache_data(show_spinner=False)
def _disc_lib_index(sig):
    """What's already in the library, for Discover ticks: (video_ids, title_norms)
    from history entries whose file still exists on disk. Cached on `sig` =
    len(all_hist) (NO leading underscore — leading-underscore args are excluded
    from st.cache_data's key, which previously froze this index), so it rebuilds
    when history grows. A deleted file drops out on the next rebuild."""
    _ = sig  # cache key only
    vids, norms = set(), set()
    for h in all_hist:
        p = h.get("path")
        if not (p and os.path.isfile(p)):
            continue
        v = _yt_id(h.get("url", ""))
        if v:
            vids.add(v)
        for s in (h.get("title"), os.path.splitext(os.path.basename(p))[0]):
            n = _disc_norm(s)
            if n:
                norms.add(n)
    return vids, norms


def _safe_mtime(p):
    try:
        return os.path.getmtime(p)
    except OSError:
        return 0


@st.cache_data(show_spinner=False, max_entries=4)
def _media_files_cached(folders, sig):
    """The Library disk scan, CACHED. `sig` = (history size + folder mtimes) and is
    part of the cache key (NO leading underscore — that would exclude it and was
    the bug that made new downloads never appear). It changes whenever a download
    lands or a file is added/removed, so the list stays current; a plain rerun
    (e.g. pressing ▶ Play) keeps the same sig -> cache HIT -> no disk re-walk ->
    instant playback."""
    _ = sig  # cache key only
    return library.media_files(list(folders))


def _disc_live():
    """Live download state from the manager: (busy_urls, busy_vids, done_vids).
    done_vids = freshly-FINISHED downloads (status 'done' + a real file) so the ✅
    tick flips the instant a download completes — independent of when the history
    file is written (which lags the job status and was causing the stale tick)."""
    busy_urls, busy_vids, done_vids = set(), set(), set()
    try:
        for j in downloads.get_manager().snapshot():
            v = _yt_id(j.url)
            if j.status in ("queued", "downloading"):
                busy_urls.add(j.url)
                if v:
                    busy_vids.add(v)
            elif j.status == "done" and j.result and os.path.isfile(j.result):
                if v:
                    done_vids.add(v)
    except Exception:  # noqa: BLE001
        pass
    return busy_urls, busy_vids, done_vids


def _disc_thumb(thumb, state):
    """Thumbnail with a corner badge: state 'have' = green ✅, 'busy' = spinner."""
    badge = ""
    if state == "have":
        badge = "<span class='umd-badge umd-have'>✓</span>"
    elif state == "busy":
        badge = "<span class='umd-badge umd-busy'><span class='umd-spinner'></span></span>"
    inner = (f"<img src='{thumb}'>" if thumb
             else "<div style='aspect-ratio:16/9;background:linear-gradient(135deg,#2a2342,#171128);"
                  "border-radius:12px;display:flex;align-items:center;justify-content:center;"
                  "font-size:30px'>🎬</div>")
    st.markdown(f"<div class='umd-thumb'>{inner}{badge}</div>", unsafe_allow_html=True)


def _disc_video_grid(items, key_prefix, cols=4):
    """A grid of video cards that KNOWS the library: every card is in exactly one
    state — ✅ already downloaded · 🔄 downloading · ⬇️ MP3/MP4. Works on every
    Discover surface (search, trending, channel, playlist, artist/follow shelves)."""
    have_vids, have_norms = _disc_lib_index(len(all_hist))
    busy_urls, busy_vids, done_vids = _disc_live()
    for start in range(0, len(items), cols):
        row = items[start:start + cols]
        columns = st.columns(cols)
        for idx, (col, it) in enumerate(zip(columns, row)):
            gi = start + idx
            with col:
                vid = it.get("video_id", "")
                downloaded = (vid in have_vids or vid in done_vids
                              or _disc_norm(it.get("title", "")) in have_norms)
                downloading = (not downloaded) and (it.get("url") in busy_urls or vid in busy_vids)
                _disc_thumb(it.get("thumb"),
                            "have" if downloaded else "busy" if downloading else "none")
                dur = it.get("duration_sec") or 0
                meta = f"{dur // 60}:{dur % 60:02d}" if dur else ""
                st.markdown(f"**{it['title'][:70]}**")
                st.caption(it["channel"] + (f"  ·  {meta}" if meta else ""))
                if downloaded:
                    st.markdown("<span class='umd-have-txt'>✓ In your library</span>",
                                unsafe_allow_html=True)
                elif downloading:
                    st.markdown("<span class='umd-busy-txt'><span class='umd-spinner'></span>"
                                " Downloading…</span>", unsafe_allow_html=True)
                else:
                    b = st.columns(2)
                    # NO explicit st.rerun() here: the button click already reruns
                    # once (which preserves the Discover tab). A second programmatic
                    # rerun per click let rapid clicks "ghost" onto Home widgets —
                    # flipping the tab and auto-playing a Recent song. The toast is
                    # the confirmation; the ✅/spinner badge updates on the next run.
                    if b[0].button("🎵 MP3", key=f"{key_prefix}_a_{gi}_{vid}", width="stretch"):
                        enqueue([{"url": it["url"], "fmt": "audio", "title": it["title"]}])
                        st.toast(f"Queued MP3 · {it['title'][:36]}")
                    if b[1].button("🎬 MP4", key=f"{key_prefix}_v_{gi}_{vid}", width="stretch"):
                        enqueue([{"url": it["url"], "fmt": "video", "title": it["title"]}])
                        st.toast(f"Queued MP4 · {it['title'][:36]}")


@st.cache_data(ttl=discover.TRENDING_TTL, show_spinner=False)
def _disc_chinfo(channel_id):
    try:
        return discover.channel_info(channel_id), None
    except Exception as e:  # noqa: BLE001
        return None, str(e)


@st.cache_data(ttl=discover.TRENDING_TTL, show_spinner=False)
def _disc_chpls(channel_id):
    try:
        return [p.as_dict() for p in discover.channel_playlists(channel_id)], None
    except Exception as e:  # noqa: BLE001
        return [], str(e)


@st.cache_data(ttl=discover.SEARCH_TTL, show_spinner="Loading artist…")
def _disc_artist(name):
    try:
        return [v.as_dict() for v in discover.search(name, "relevance")], None
    except Exception as e:  # noqa: BLE001
        return [], str(e)


def _fmt_count(n):
    try:
        n = int(n)
    except (TypeError, ValueError):
        return ""
    if n >= 1_000_000:
        return f"{n / 1_000_000:.1f}M".replace(".0M", "M")
    if n >= 1_000:
        return f"{n / 1_000:.1f}K".replace(".0K", "K")
    return str(n)


def _top_artists(n=3, limit=150):
    """Your most-downloaded artists (from recent history) — for personalized shelves."""
    counts = {}
    for h in all_hist[:limit]:
        p = h.get("path")
        if p and os.path.isfile(p):
            try:
                for a in _artists_cached(p, os.path.getmtime(p)):
                    if a.lower() != "unknown":
                        counts[a] = counts.get(a, 0) + 1
            except Exception:  # noqa: BLE001
                pass
    collapsed = artists.collapse_artist_counts(counts)
    return [name for name, _c in sorted(collapsed, key=lambda x: -x[1])[:n]]


def _disc_on_search():
    """Fires ONLY when YOU edit the search box (not on background reruns). Sets the
    sticky active query and forces a fresh fetch — so downloading never changes the
    view, and the search stays put until you search again or hit Discover Home."""
    st.session_state["disc_query"] = (st.session_state.get("disc_q") or "").strip()
    st.session_state.pop("disc_results", None)
    for k in ("disc_open_channel", "disc_open_playlist", "disc_open_title"):
        st.session_state.pop(k, None)


@st.fragment   # clicks inside Discover rerun ONLY here -> no full-page flash
def discover_panel():
    """Download-first 'mini YouTube' — trending shelves + mixed search, mirroring
    the mobile Discover. Every result is one tap to MP3/MP4 via the same engine."""
    if not discover.has_key():
        st.info("🔭 **Discover is unavailable** — no YouTube key is configured "
                "(place your key in a `youtube.key` file next to the app).")
        return

    # Honour a "Discover Home" click from last run: clear the box BEFORE the widget
    # is created (you can't set a widget value after it's instantiated).
    if st.session_state.pop("_disc_clear_box", False):
        st.session_state["disc_q"] = ""
    sc = st.columns([5, 1.7, 0.8])
    sc[0].text_input("Search", key="disc_q", on_change=_disc_on_search,
                     label_visibility="collapsed",
                     placeholder="🔎 Search artists, songs, channels…")
    order = sc[1].selectbox("Sort", ["relevance", "date", "viewCount"],
                            format_func=lambda o: {"relevance": "Relevance", "date": "Newest",
                                                   "viewCount": "Most viewed"}[o],
                            key="disc_order", label_visibility="collapsed")
    # Manual refresh — re-queries YouTube; everything else is served from the
    # snapshot/cache so leaving and returning never re-fetches.
    if sc[2].button("🔄", key="disc_refresh", help="Refresh Discover (re-query YouTube)",
                    width="stretch"):
        for _fn in (_disc_search, _disc_trending, _disc_uploads, _disc_playlist,
                    _disc_chinfo, _disc_chpls, _disc_artist, _disc_lib_index):
            _fn.clear()                       # also rebuild the ✅ downloaded index
        st.session_state.pop("disc_results", None)
        st.rerun(scope="fragment")
    # STICKY: the view is driven by this session value, set only when you edit the
    # box — never by a background rerun. Downloads can't change what you're viewing.
    query = st.session_state.get("disc_query", "").strip()
    _follows = st.session_state.setdefault("desk_follows", follows.load())

    # An opened channel/playlist shows its videos at the top (above results/trending).
    open_ch = st.session_state.get("disc_open_channel")
    open_pl = st.session_state.get("disc_open_playlist")

    # One-click return to default Discover — only shown when you're in a search or
    # an opened channel/playlist (so there's somewhere to go back from).
    if query or open_ch or open_pl:
        if st.button("🏠  Discover Home — trending, music & your follows",
                     key="disc_home", width="stretch"):
            for k in ("disc_query", "disc_results", "disc_open_channel",
                      "disc_open_playlist", "disc_open_title"):
                st.session_state.pop(k, None)
            st.session_state["_disc_clear_box"] = True
            st.rerun(scope="fragment")

    def _disc_close_btn(col):
        if col.button("✕ Close", key="disc_close"):
            for k in ("disc_open_channel", "disc_open_playlist", "disc_open_title"):
                st.session_state.pop(k, None)
            st.rerun(scope="fragment")

    if open_ch:
        info, _ie = _disc_chinfo(open_ch)
        _ch_title = (info or {}).get("title") or st.session_state.get("disc_open_title", "Channel")
        _ch_thumb = (info or {}).get("thumb") or ""
        hc = st.columns([1, 4, 1.3, 1])
        if _ch_thumb:
            hc[0].image(_ch_thumb, width="stretch")
        hc[1].markdown(f"### 📡 {_ch_title}")
        _meta = []
        if info and info.get("subs"):
            _meta.append(f"👥 {_fmt_count(info['subs'])} subscribers")
        if info and info.get("videos"):
            _meta.append(f"🎬 {_fmt_count(info['videos'])} videos")
        if _meta:
            hc[1].caption("  ·  ".join(_meta))
        # ⭐ Follow toggle — stored locally; powers the "New from <channel>" shelves.
        _following = follows.is_following(_follows, open_ch)
        if hc[2].button("⭐ Following" if _following else "☆ Follow", key="disc_follow",
                        width="stretch", type="secondary" if _following else "primary"):
            now = follows.toggle(_follows, open_ch, _ch_title, _ch_thumb)
            st.toast(("⭐ Following " if now else "Unfollowed ") + _ch_title[:30])
            st.rerun(scope="fragment")
        _disc_close_btn(hc[3])
        st.markdown("##### ▶️ Recent uploads")
        _ups, _uerr = _disc_uploads(open_ch)
        if _ups:
            _disc_video_grid(_ups, "disc_open")
        else:
            st.caption(_uerr or "No recent uploads found.")
        _chpls, _ = _disc_chpls(open_ch)
        if _chpls:
            st.markdown("##### 🎶 Playlists")
            for _cpl in _chpls:
                _pcc = st.columns([1, 4, 2])
                if _cpl["thumb"]:
                    _pcc[0].image(_cpl["thumb"], width="stretch")
                _pcc[1].markdown(f"**{_cpl['title']}**")
                if _pcc[2].button("Open", key=f"disc_cpl_{_cpl['playlist_id']}"):
                    st.session_state["disc_open_playlist"] = _cpl["playlist_id"]
                    st.session_state.pop("disc_open_channel", None)
                    st.session_state["disc_open_title"] = _cpl["title"]
                    st.rerun(scope="fragment")
        st.divider()
    elif open_pl:
        hc = st.columns([6, 1])
        hc[0].markdown(f"### 🎶 {st.session_state.get('disc_open_title', 'Playlist')}")
        _disc_close_btn(hc[1])
        items, err = _disc_playlist(open_pl)
        if err:
            st.warning(err)
        elif items:
            _disc_video_grid(items, "disc_open")
        else:
            st.caption("Nothing to show here.")
        st.divider()

    if query:
        # Snapshot the results in session_state so returning to Discover shows the
        # exact same page without re-querying — we only fetch when the query/order
        # actually changes (or you hit 🔄 Refresh, which clears the snapshot).
        snap = st.session_state.get("disc_results")
        if not snap or snap.get("q") != query or snap.get("order") != order:
            res, err = _disc_search(query, order)
            snap = {"q": query, "order": order, "res": res, "err": err}
            st.session_state["disc_results"] = snap
        res, err = snap["res"], snap["err"]
        if err:
            st.warning(err)
            if st.button("🔄 Try again", key="disc_retry"):
                _disc_search.clear()
                st.session_state.pop("disc_results", None)
                st.rerun(scope="fragment")
            return
        if res["channels"]:
            st.markdown("##### 📡 Channels — follow, or open to browse & download")
            for ch in res["channels"]:
                cc = st.columns([1, 3.4, 1.3, 1.6])
                if ch["thumb"]:
                    cc[0].image(ch["thumb"], width="stretch")
                cc[1].markdown(f"**{ch['title']}**")
                _f = follows.is_following(_follows, ch["channel_id"])
                if cc[2].button("⭐" if _f else "☆ Follow", key=f"disc_fol_{ch['channel_id']}",
                                width="stretch", help="Following" if _f else "Follow this channel"):
                    now = follows.toggle(_follows, ch["channel_id"], ch["title"], ch["thumb"])
                    st.toast(("⭐ Following " if now else "Unfollowed ") + ch["title"][:30])
                    st.rerun(scope="fragment")
                if cc[3].button("Latest uploads", key=f"disc_ch_{ch['channel_id']}",
                                width="stretch"):
                    st.session_state["disc_open_channel"] = ch["channel_id"]
                    st.session_state.pop("disc_open_playlist", None)
                    st.session_state["disc_open_title"] = ch["title"]
                    st.rerun(scope="fragment")
        if res["playlists"]:
            st.markdown("##### 🎶 Playlists — open to grab the whole list")
            for pl in res["playlists"]:
                pc = st.columns([1, 4, 2])
                if pl["thumb"]:
                    pc[0].image(pl["thumb"], width="stretch")
                pc[1].markdown(f"**{pl['title']}**")
                if pc[2].button("Open playlist", key=f"disc_pl_{pl['playlist_id']}"):
                    st.session_state["disc_open_playlist"] = pl["playlist_id"]
                    st.session_state.pop("disc_open_channel", None)
                    st.session_state["disc_open_title"] = pl["title"]
                    st.rerun(scope="fragment")
        if res["videos"]:
            st.markdown("##### ▶️ Videos — tap to download")
            _disc_video_grid(_paginate(res["videos"], "disc_v", noun="video",
                                       scope="fragment"), "disc_v")
        if not (res["videos"] or res["channels"] or res["playlists"]):
            _empty("🔎", "No results", f"Nothing found for “{query}” — try another search.")
    elif not (open_ch or open_pl):
        # ⭐ Following — newest uploads from channels you follow, one shelf each.
        for _fc in _follows[:6]:
            _fu, _ = _disc_uploads(_fc["id"])
            if not _fu:
                continue
            _fh = st.columns([5, 1])
            _fh[0].markdown(f"### ⭐ New from {_fc['title']}")
            if _fh[1].button("Open channel", key=f"disc_fopen_{_fc['id']}", width="stretch"):
                st.session_state["disc_open_channel"] = _fc["id"]
                st.session_state.pop("disc_open_playlist", None)
                st.session_state["disc_open_title"] = _fc["title"]
                st.rerun(scope="fragment")
            _disc_video_grid(_fu[:8], f"disc_fol_{_fc['id']}")
        for label, region, cat in (("🔥 Trending in Kenya", "KE", None),
                                    ("🌍 Trending Worldwide", "US", None),
                                    ("🎵 Trending Music", "KE", "10")):
            st.markdown(f"### {label}")
            items, err = _disc_trending(region, cat)
            if err:
                st.caption(f"Couldn't load — {err}")
            elif items:
                _disc_video_grid(items, f"disc_t_{region}_{cat}")
        # Personalized — "More from <artist>" from your most-downloaded artists.
        for _artist in _top_artists():
            _avids, _ae = _disc_artist(_artist)
            if _avids:
                st.markdown(f"### 🎧 More from {_artist}")
                _disc_video_grid(_avids[:8], f"disc_a_{artists.artist_key(_artist)}")


# =========================================================================== #
#  ASSISTANT  (a real chatbot with saved history — mirrors the mobile assistant)
# =========================================================================== #
def _assistant_run(prompt, history):
    """One assistant turn -> (reply_text, dl_url, dl_title). Downloads happen
    immediately (conversational) and are tracked by url so the chat can show
    progress and play them inline."""
    if not st.session_state.get("ai_on"):
        return ("⚠️ Add your AI key in the sidebar → **AI Settings** to use the assistant.",
                None, None)
    plan = ai.agent_plan(prompt, context=history[-6:]) or {}
    action = plan.get("action")
    is_aud = str(plan.get("fmt", "mp3")).lower() != "mp4"
    fmt = "audio" if is_aud else "video"
    quality = None if is_aud else plan.get("quality", "Best Available")
    flabel = "MP3" if is_aud else f"MP4 {plan.get('quality', '')}".strip()

    def _job(url, title):
        return {"url": url, "title": title, "fmt": fmt, "quality": quality, "audio_codec": "mp3"}

    if action == "help":
        return (plan.get("answer") or "I can download a song or video, grab a whole channel, "
                "or explain a feature — just ask. e.g. *download Sauti Sol Melanin as mp3*.",
                None, None)
    if action == "channel" and plan.get("url"):
        try:
            res = dl.list_media(plan["url"], cookiefile)
            n = enqueue([_job(e["url"], e["title"]) for e in res["entries"]], downloads.LANE_BATCH)
            return (f"📦 Queued **{n}** videos from *{res['title']}* as {flabel} — "
                    "they're downloading below.", None, None)
        except Exception as e:  # noqa: BLE001
            return (f"❌ I couldn't read that channel — {e}", None, None)
    if action == "download" and plan.get("url"):
        title = plan.get("query") or plan["url"]
        enqueue([_job(plan["url"], title)], downloads.LANE_NOW)
        return (f"⬇️ Downloading **{title}** as {flabel}…", plan["url"], title)
    # search -> grab the top match, conversationally (like the phone)
    q = plan.get("query") or prompt
    try:
        results = dl.search(q, 1, cookiefile)
    except Exception:  # noqa: BLE001
        results = None
    if results:
        r = results[0]
        enqueue([_job(r["url"], r["title"])], downloads.LANE_NOW)
        return (f"🔎 Found **{r['title']}** — downloading as {flabel}…", r["url"], r["title"])
    return (f"😕 I couldn't find “{q}”. Try another name, or paste a direct link.", None, None)


def _render_chat_download(url, idx):
    """Show a chat-initiated download's live status + an inline player when done."""
    job = next((j for j in reversed(downloads.get_manager().snapshot()) if j.url == url), None)
    if not job:
        return
    if job.status in ("queued", "downloading"):
        p = float(job.progress or 0.0)
        frac = p / 100.0 if p > 1 else p
        st.progress(min(1.0, max(0.0, frac)),
                    text=f"{job.status}…" + (f" {int(frac * 100)}%" if frac else ""))
    elif job.status == "done" and job.result:
        path = job.result
        _cc = st.columns(2)
        if _cc[0].button("▶ Play", key=f"chat_play_{idx}", width="stretch"):
            _mp_play([path], 0)            # plays in the floating mini-player (IDM-proof)
            st.rerun()
        if _cc[1].button("📂 Show in folder", key=f"chat_open_{idx}", width="stretch"):
            open_and_select(path)
    elif job.status == "error":
        st.error(f"Download failed — {job.error or 'unknown error'}")


def _chat_send(prompt):
    """Append the user's message and flag that a reply is owed, then rerun at once
    so the message shows INSTANTLY. The slow AI call runs on the next rerun (behind
    a spinner) — so your text never waits on the model to appear."""
    sessions = st.session_state["chat_sessions"]
    cur = next((s for s in sessions if s["id"] == st.session_state.get("chat_current")), None)
    if cur is None:
        return
    cur["messages"].append({"user": True, "text": prompt})
    if (cur["title"] or "New chat") in ("New chat", ""):
        cur["title"] = prompt[:40]
    chats.save(sessions, st.session_state["chat_current"])
    st.session_state["chat_pending"] = True
    st.rerun()


def assistant_panel():
    """ChatGPT/Claude-style assistant: a saved-chat history rail + a conversation
    that can download (and play) media inline, remembering context. The input is a
    bottom-pinned st.chat_input. Mirrors the mobile app."""
    if "chat_loaded" not in st.session_state:
        sessions, current = chats.load()
        st.session_state["chat_sessions"] = sessions
        st.session_state["chat_current"] = current
        st.session_state["chat_loaded"] = True
    sessions = st.session_state["chat_sessions"]
    ai_on = bool(st.session_state.get("ai_on"))

    def _cur():
        return next((s for s in sessions if s["id"] == st.session_state.get("chat_current")), None)

    if _cur() is None:
        if not sessions:
            sessions.insert(0, chats.new_session())
        st.session_state["chat_current"] = sessions[0]["id"]

    left, mainc = st.columns([1, 3], gap="medium")

    with left:
        if st.button("➕  New chat", width="stretch", type="primary"):
            s = chats.new_session()
            sessions.insert(0, s)
            st.session_state["chat_current"] = s["id"]
            chats.save(sessions, s["id"])
            st.rerun()
        st.caption("HISTORY")
        for s in sessions:
            active = s["id"] == st.session_state["chat_current"]
            row = st.columns([5, 1.1])
            label = ("🟣  " if active else "💬  ") + (s["title"] or "New chat")[:22]
            if row[0].button(label, key=f"chat_sel_{s['id']}", width="stretch",
                             type="primary" if active else "secondary"):
                st.session_state["chat_current"] = s["id"]
                chats.save(sessions, s["id"])
                st.rerun()
            with row[1].popover("⋯", width="stretch"):
                nm = st.text_input("Rename chat", value=s["title"], key=f"chat_rn_{s['id']}")
                if st.button("Save name", key=f"chat_rnb_{s['id']}", width="stretch"):
                    s["title"] = (nm or s["title"]).strip() or s["title"]
                    chats.save(sessions, st.session_state["chat_current"])
                    st.rerun()
                if st.button("🗑️  Delete chat", key=f"chat_del_{s['id']}", width="stretch"):
                    sessions[:] = [x for x in sessions if x["id"] != s["id"]]
                    if not sessions:
                        sessions.insert(0, chats.new_session())
                    if st.session_state["chat_current"] == s["id"]:
                        st.session_state["chat_current"] = sessions[0]["id"]
                    chats.save(sessions, st.session_state["chat_current"])
                    st.rerun()

    with mainc:
        if not ai_on:
            st.info("🤖 Add your AI key in the sidebar → **AI Settings** to chat.")
        cur = _cur()
        if not cur["messages"]:
            st.markdown(
                "<div style='text-align:center;padding:24px 10px 8px;'>"
                "<div style='font-size:42px;line-height:1'>🤖</div>"
                "<div style='font-size:20px;font-weight:700;color:#ECEAF6;margin-top:10px'>How can I help?</div>"
                "<div style='font-size:13.5px;color:#9a93b5;margin-top:5px'>"
                "Ask me to grab a song, pull a whole channel, or how a feature works — "
                "I remember this chat.</div></div>", unsafe_allow_html=True)
            sugg = ["Download Sauti Sol — Melanin as mp3",
                    "Get Diamond Platnumz's latest video",
                    "How does the library organise my music?"]
            sc = st.columns(len(sugg))
            for i, q in enumerate(sugg):
                if sc[i].button(q, key=f"chat_sg_{i}", width="stretch", disabled=not ai_on):
                    _chat_send(q)
        else:
            for i, m in enumerate(cur["messages"]):
                if m.get("user"):
                    # User → right side, subtle bubble.
                    with st.container(key=f"umsg_{i}"):
                        st.markdown(m.get("text", ""))
                else:
                    # Assistant → left side, plain text (no box); a download card
                    # sits just beneath it.
                    with st.container(key=f"amsg_{i}"):
                        st.markdown(m.get("text", ""))
                    if m.get("url"):
                        _render_chat_download(m["url"], i)

        # The AI reply runs HERE — after your message is already on screen — so the
        # spinner shows while the model thinks, not while your own text waits.
        if (ai_on and st.session_state.get("chat_pending")
                and cur["messages"] and cur["messages"][-1].get("user")):
            with st.spinner("Thinking…"):
                _last = cur["messages"][-1]["text"]
                _reply, _url, _title = _assistant_run(_last, cur["messages"][:-1])
            cur["messages"].append({"user": False, "text": _reply, "url": _url, "title": _title})
            chats.save(sessions, st.session_state["chat_current"])
            st.session_state["chat_pending"] = False
            st.rerun()

    prompt = st.chat_input(
        "Message the assistant — e.g. download Sauti Sol Melanin as mp3",
        disabled=not ai_on)
    if prompt and prompt.strip():
        _chat_send(prompt.strip())


_t_home, _t_dl, _t_discover, _t_assistant, _t_hist, _t_insights, _t_arch, _t_clean = st.tabs([
    "🏠  Home",
    "⬇️  Download",
    "🔭  Discover",
    "🤖  Assistant",
    f"🕓  History ({len(all_hist)})",
    "📊  Insights",
    "🗄️  Archive",
    "🗂️  Library & Cleanup",
])

with _t_home:
    _home_hero()
    _on_disk = sum(1 for _h in all_hist if _h.get("path") and os.path.isfile(_h["path"]))
    _size = sum((_h.get("size") or 0) for _h in all_hist)
    _c = downloads.get_manager().counts()
    _m = st.columns(4)
    _m[0].metric("Downloads", len(all_hist))
    _m[1].metric("In your library", _on_disk)
    _m[2].metric("Total size", fmt_size(_size))
    _m[3].metric("In queue", _c.get("active", 0) + _c.get("queued", 0))

    st.markdown("#### ⚡ Quick download")
    _q = st.columns([6, 1, 1])
    _qurl = _q[0].text_input("Quick link", key="home_q", label_visibility="collapsed",
                             placeholder="Paste any link — YouTube, TikTok, X, Instagram…")
    if _q[1].button("🎵 MP3", key="home_mp3", width="stretch") and _qurl.strip():
        enqueue([{"url": _qurl.strip(), "fmt": "audio", "title": ""}], downloads.LANE_NOW)
        st.toast("Queued MP3 — see the queue below.")
    if _q[2].button("🎬 MP4", key="home_mp4", width="stretch") and _qurl.strip():
        enqueue([{"url": _qurl.strip(), "fmt": "video", "title": ""}], downloads.LANE_NOW)
        st.toast("Queued MP4 — see the queue below.")

    st.markdown("#### 🕘 Recent")
    _recent = sorted(all_hist, key=lambda h: h.get("ts", ""), reverse=True)[:6]
    if not _recent:
        st.caption("Nothing yet — paste a link above, or open the 🔭 Discover tab.")
    _recent_paths = [h.get("path", "") for h in _recent
                     if h.get("path") and os.path.isfile(h["path"])]
    for _i, _h in enumerate(_recent):
        _rc = st.columns([6, 1.6, 1, 1])
        _t = (_h.get("title") or _h.get("filename") or _h.get("url", ""))[:64]
        _rc[0].markdown(f"{'🎬' if _h.get('fmt') == 'video' else '🎵'} **{_t}**")
        _rc[1].caption(when_label(_h.get("ts", "")) or "")
        _p = _h.get("path", "")
        if _p and os.path.isfile(_p):
            if _rc[2].button("▶", key=f"home_play_{_i}", width="stretch", help="Play"):
                _mp_play(_recent_paths, _recent_paths.index(_p))
                st.rerun()
            if _rc[3].button("📂", key=f"home_open_{_i}", width="stretch", help="Open folder"):
                open_and_select(_p)

with _t_discover:
    discover_panel()

with _t_assistant:
    assistant_panel()

with _t_dl:
    _mode_opts = ["🔗 Single link", "📺 Channel / Profile", "📚 Bulk (many links)"]
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
                    st.image(metadata["thumbnail"], width="stretch")

            st.divider()

            fmt_label = st.radio("Format", ["🎵 Audio Only", "🎬 Video (MP4)"],
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

            if st.button("⬇️ Download", type="primary", width="stretch"):
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

        if sc1.button("🔎 Scan channel / profile", type="primary", width="stretch"):
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
            if ga.button("🎵 Download ALL as MP3", width="stretch"):
                n = enqueue([{"url": e["url"], "title": e["title"], "fmt": "audio",
                              "audio_codec": "mp3"} for e in entries],
                            downloads.LANE_BATCH)
                st.success(f"📦 Queued **{n}** as MP3 — see **Downloads** above.")
            if gb.button("🎬 Download ALL as MP4", width="stretch"):
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
                                     disabled=not chosen, width="stretch"):
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
            if nav1.button("← Prev", disabled=page <= 1, width="stretch"):
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
                           width="stretch"):
                st.session_state.ch_page = page + 1
                st.rerun()

            if not shown:
                st.info("No videos match that search.")
            for gi, e in shown:
                pc1, pc2 = st.columns([3, 2])
                dur = dl.human_duration(e["duration"]) if e.get("duration") else ""
                pc1.write(f"**{e['title']}**" + (f"  ·  {dur}" if dur else ""))
                pc2.selectbox("format", FMT_OPTIONS, key=f"ch_fmt_{gi}",
                              index=len(FMT_OPTIONS) - 1,   # default ⛔ Skip — pick per video
                              label_visibility="collapsed")

            bc1, bc2 = st.columns(2)
            if bc1.button("⬇️ Download chosen (all pages)", type="primary",
                          width="stretch"):
                jobs = []
                for gi, e in enumerate(entries):
                    # Default ⛔ Skip: videos on pages you never opened (no widget
                    # was created) are NOT grabbed — only the ones you actually
                    # picked. Use "Grab everything" above for a whole-channel pull.
                    choice = st.session_state.get(f"ch_fmt_{gi}", "⛔ Skip")
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
            if bc2.button("↺ Reset all picks to Skip", width="stretch"):
                for gi in range(len(entries)):
                    st.session_state[f"ch_fmt_{gi}"] = "⛔ Skip"
                st.rerun()
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

            if st.button("⬇️ Download all", type="primary", width="stretch"):
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
                             width="stretch"):
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


with _t_hist:
    if ai_on and all_hist:
        titles_all = [h.get("title") or h.get("filename") for h in all_hist]
        analyzed = [t for t in titles_all if t in ai_cache]
        with st.expander(f"🤖 Smart Library — organize with AI "
                         f"({len(analyzed)}/{len(titles_all)} analyzed)", expanded=False):
            st.caption("AI cleans each title and tags it by **artist** and "
                       "**category**, so your downloads become a real library. "
                       "Only titles are sent online.")
            ac1, ac2 = st.columns(2)
            if ac1.button("✨ Analyze with AI", width="stretch",
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
            if ac2.button("🏷️ Write tags to files", width="stretch",
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

                def _ai_of(h):
                    return ai_cache.get(h.get("title") or h.get("filename")) or {}

                cats = Counter(ai_cache[t]["category"] for t in analyzed)
                # Merge artist variants the same way Insights + Library Artists do,
                # so History shows ONE "Bad Bunny", not split counts.
                _raw_arts = Counter(ai_cache[t]["artist"] for t in analyzed
                                    if ai_cache[t].get("artist"))
                arts = Counter(dict(artists.collapse_artist_counts(dict(_raw_arts))))
                st.caption("👇 Click any category or artist to see those exact files — "
                           "then open each in its folder (highlighted) or re-download it.")
                g1, g2 = st.columns(2)
                g1.markdown("**By category**")
                for c, n in cats.most_common():
                    if g1.button(f"{c} · {n}", key=f"smcat_{c}",
                                 width="stretch"):
                        st.session_state.smart_pick = ("category", c)
                g2.markdown("**Top artists**")
                for a, n in arts.most_common(12):
                    if g2.button(f"{a} · {n}", key=f"smart_{a}",
                                 width="stretch"):
                        st.session_state.smart_pick = ("artist", a)

                pick = st.session_state.get("smart_pick")
                if pick:
                    kind, val = pick
                    if kind == "artist":       # match every spelling/case/accent variant
                        _ak = artists.artist_key(val)
                        items = [h for h in all_hist
                                 if artists.artist_key(_ai_of(h).get("artist") or "") == _ak]
                    else:
                        items = [h for h in all_hist if _ai_of(h).get(kind) == val]
                    pk1, pk2 = st.columns([4, 1])
                    pk1.markdown(f"#### {val} — {len(items)} file(s)")
                    if pk2.button("Close", key="smart_close"):
                        st.session_state.pop("smart_pick", None)
                        st.rerun()
                    for it in _paginate(items, "smart_items"):
                        on_disk = bool(it.get("path") and os.path.isfile(it["path"]))
                        e1, e2, e3 = st.columns([7, 1, 1])
                        e1.markdown(
                            f"{'🎬' if it.get('fmt') == 'video' else '🎵'} "
                            f"**{_esc(it.get('title') or it.get('filename'))}**  \n"
                            f"<span style='color:#888;font-size:.8em'>"
                            f"{it.get('site', '')} · {fmt_size(it.get('size', 0))}"
                            f"{'' if on_disk else ' · ⚠️ file missing'}</span>",
                            unsafe_allow_html=True)
                        if e2.button("📂", key=f"smp_o_{it['id']}", disabled=not on_disk,
                                     help="Open the folder & highlight this file"):
                            open_and_select(it["path"])
                        if e3.button("⤓", key=f"smp_r_{it['id']}",
                                     disabled=not it.get("url"), help="Re-download"):
                            enqueue([media_job(it)], downloads.LANE_NOW)
                            st.success(f"⚡ Re-downloading **{it.get('title') or 'item'}**.")

                # Same song/artist grouping (AI artist+title) — VERSIONS, not byte dups.
                groups = {}
                for _h in all_hist:
                    _m = _ai_of(_h)
                    if _m.get("artist") and _m.get("clean_title"):
                        k = (_m["artist"].strip().lower(),
                             _m["clean_title"].strip().lower())
                        groups.setdefault(k, []).append(_h)
                multi = {k: v for k, v in groups.items() if len(v) > 1}
                if multi:
                    st.markdown("---")
                    tot = sum(len(v) for v in multi.values())
                    st.markdown(f"**🎭 Same song / artist — multiple files** · {tot} "
                                f"files in {len(multi)} group(s)")
                    st.caption("Grouped by AI **artist + title**, so these are often "
                               "different **versions** (official video, visualizer, "
                               "live, teaser) — **not** necessarily identical files. "
                               "Same-size items are flagged *likely identical*; to "
                               "remove only true byte-for-byte copies **safely**, use "
                               "**Library & Cleanup** below (it verifies by hash and "
                               "quarantines, never deletes blindly).")
                    for (artist, _tt), grp in list(multi.items())[:15]:
                        nice = _ai_of(grp[0]).get("clean_title") or grp[0].get("title")
                        szc = Counter(round((it.get("size", 0) or 0) / 1024)
                                      for it in grp)
                        with st.container(border=True):
                            st.caption(f"**{artist.title()} — {nice}** · {len(grp)} files")
                            for it in grp:
                                likely = szc[round((it.get("size", 0) or 0) / 1024)] > 1
                                d1, d2 = st.columns([8, 1])
                                d1.markdown(
                                    f"• {_esc(it.get('filename'))} "
                                    f"<span style='color:#888;font-size:.8em'>"
                                    f"({fmt_size(it.get('size', 0))}"
                                    f"{' · 🟠 likely identical' if likely else ' · unique size'})"
                                    f"</span>", unsafe_allow_html=True)
                                if d2.button("📂", key=f"sg_o_{it['id']}",
                                             help="Open & highlight"):
                                    open_and_select(it["path"])

    if not all_hist:
        st.caption("Your downloads will appear here and stay saved between sessions.")
    else:
        def _hist_job(h):
            ext = os.path.splitext(h.get("filename", ""))[1].lower()
            if h.get("fmt") == "audio":
                return {"url": h.get("url"), "title": h.get("title", ""),
                        "fmt": "audio",
                        "audio_codec": "m4a" if ext == ".m4a" else "mp3"}
            return {"url": h.get("url"), "title": h.get("title", ""),
                    "fmt": "video", "quality": "Best Available"}

        def _hist_csv(rows):
            import csv as _csv
            import io as _io
            cols = ["ts", "title", "site", "fmt", "size", "url", "filename", "path"]
            buf = _io.StringIO()
            w = _csv.DictWriter(buf, fieldnames=cols, extrasaction="ignore")
            w.writeheader()
            for r in rows:
                w.writerow({c: r.get(c, "") for c in cols})
            return buf.getvalue()

        f1, f2, f3, f4, f5 = st.columns([2, 1.2, 1.1, 1.3, 1.4])
        hq = f1.text_input("Search history", placeholder="Search title or filename…",
                           label_visibility="collapsed")
        site_sel = f2.selectbox("Site", ["All sites"] + hist.all_sites(all_hist),
                                label_visibility="collapsed")
        type_sel = f3.selectbox("Type", ["All types", "🎬 Video", "🎵 Audio"],
                                label_visibility="collapsed")
        date_sel = f4.selectbox("When", ["All time", "Today", "Yesterday",
                                         "This week", "This month", "This year",
                                         "Custom range…"], label_visibility="collapsed")
        sort_opts = ["Newest", "Oldest", "Title A–Z", "Largest", "Smallest", "Source"]
        if ai_on:
            sort_opts.append("Artist")
        sort_sel = f5.selectbox("Sort", sort_opts, label_visibility="collapsed")

        cust_from = cust_to = None
        if date_sel == "Custom range…":
            dca, dcb = st.columns(2)
            cust_from = dca.date_input("From", value=None, key="hist_from")
            cust_to = dcb.date_input("To", value=None, key="hist_to")

        def _in_when(ts):
            now = datetime.now()
            d = ts.date()
            if date_sel == "Today":
                return d == now.date()
            if date_sel == "Yesterday":
                return (now.date() - d).days == 1
            if date_sel == "This week":
                return d >= (now.date() - timedelta(days=now.weekday()))
            if date_sel == "This month":
                return d.year == now.year and d.month == now.month
            if date_sel == "This year":
                return d.year == now.year
            if date_sel == "Custom range…":
                if cust_from and d < cust_from:
                    return False
                if cust_to and d > cust_to:
                    return False
                return True
            return True

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
                if not _in_when(ts):
                    return False
            return True

        def _artist(h):
            m = ai_cache.get(h.get("title") or h.get("filename")) if ai_on else None
            return (m or {}).get("artist") or ""

        filtered = [h for h in all_hist if _match(h)]
        _sorters = {
            "Newest": (lambda h: h.get("ts", ""), True),
            "Oldest": (lambda h: h.get("ts", ""), False),
            "Title A–Z": (lambda h: (h.get("title") or "").lower(), False),
            "Largest": (lambda h: h.get("size", 0), True),
            "Smallest": (lambda h: h.get("size", 0), False),
            "Source": (lambda h: (h.get("site") or "").lower(), False),
            "Artist": (lambda h: _artist(h).lower(), False),
        }
        _key, _rev = _sorters.get(sort_sel, _sorters["Newest"])
        filtered = sorted(filtered, key=_key, reverse=_rev)

        total_size = sum(h.get("size", 0) for h in filtered)
        pc1, pc2, pc3, pc4 = st.columns([2.2, 1.3, 1.3, 1.2])
        pc1.caption(f"Showing **{len(filtered)}** of {len(all_hist)} downloads  ·  "
                    f"{fmt_size(total_size)} total")
        per_sel = pc2.selectbox("Per page",
                                ["10 per page", "20 per page", "30 per page",
                                 "50 per page", "Show all"], index=1,
                                key="hist_per_page", label_visibility="collapsed")
        pc3.download_button("⬇️ Export", _hist_csv(filtered),
                            file_name="umd_history.csv", mime="text/csv",
                            width="stretch", disabled=not filtered)
        if pc4.button("🗑️ Clear all", width="stretch",
                      help="Permanently remove every VISIBLE history entry "
                           "(your permanent archive is kept)"):
            hist.clear_history()
            st.rerun()
        _redl_all = [h for h in filtered if h.get("url")]
        if _redl_all and st.button(f"⤓ Re-download all filtered ({len(_redl_all)})",
                                   key="hist_redl_filtered"):
            n = enqueue([_hist_job(h) for h in _redl_all], downloads.LANE_BATCH)
            st.success(f"⚡ Queued **{n}** re-download(s) — see **Downloads** above.")

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
                             width="stretch"):
                    st.session_state.hist_page = cur_page - 1
                    st.rerun()
                n2.markdown(f"<div style='text-align:center;padding-top:6px'>Page "
                            f"**{cur_page}** of **{total_pages}**</div>",
                            unsafe_allow_html=True)
                if n3.button("Next →", key="hist_next", disabled=cur_page >= total_pages,
                             width="stretch"):
                    st.session_state.hist_page = cur_page + 1
                    st.rerun()
                start = (cur_page - 1) * per
                page_items = filtered[start:start + per]

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
                    ai_badge = (f" · 🏷️ {_esc(_m.get('category', ''))}"
                                + (f" · {_esc(_m['artist'])}" if _m.get("artist") else ""))
                on_disk = bool(h.get("path") and os.path.isfile(h["path"]))
                miss = "" if on_disk else " · ⚠️ file missing"
                hc1.markdown(
                    f"{icon} **{_esc(h.get('title') or h.get('filename'))}**  \n"
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


with _t_arch:


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
                               width="stretch", disabled=not af)
            ap = af[:200]
            if ap and s3.button(f"⤓ Re-download ({len(ap)})", key="arch_redl_all",
                                width="stretch",
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
                    f"{icon} **{_esc(r.get('title') or r.get('url'))}**  \n"
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



with _t_clean:
    st.subheader("🗂️ Library & Cleanup")
    # Scan wherever the media ACTUALLY lives — the managed library, the real
    # Downloads folder, AND every folder your tracked files sit in (e.g. files
    # downloaded before you turned the library on). collapse_folders keeps it
    # overlap-safe so nothing is ever counted twice.
    _quarantine_root = library.get_root() if library.is_enabled() else main_dir
    _scan_roots = {DEFAULT_DOWNLOAD_DIR, main_dir}
    if library.is_enabled():
        _scan_roots.add(library.get_root())
    for _h in all_hist:
        _p = _h.get("path")
        if _p:
            _d = os.path.dirname(_p)
            if _d and len(_d) > 3:        # skip blanks / drive roots like "C:\"
                _scan_roots.add(_d)
    scan_folders = library.collapse_folders(_scan_roots)

    # ---- Visual media browser (cover-art cards, Spotify-style) ----------- #
    # Cached scan: re-walks only when history grew or a folder changed, so pressing
    # ▶ Play (a plain rerun) doesn't re-scan the disk and playback feels instant.
    _msig = (len(all_hist), tuple(_safe_mtime(f) for f in scan_folders))
    _media = _media_files_cached(tuple(scan_folders), _msig)
    st.markdown("#### 🎵 Your library")
    _lc = st.columns([3, 2.4, 1.4])
    _lib_q = _lc[0].text_input("Filter", key="lib_filter", label_visibility="collapsed",
                               placeholder="🔎 Filter by name…")
    _lib_view = _lc[1].radio("View", ["All", "Songs", "Videos", "Artists", "Playlists"],
                             horizontal=True, key="lib_view", label_visibility="collapsed")
    _lib_sort = _lc[2].selectbox("Sort", _LIB_SORTS, key="lib_sort",
                                 label_visibility="collapsed")
    # Playback now happens in the persistent floating mini-player (▶ on any card).
    if not _media:
        _empty("🎵", "Your library is empty", "Download something and it'll show up here with its artwork.")
    elif _lib_view == "Artists":
        _lib_artists_view(_media, _lib_q, _lib_sort)
    elif _lib_view == "Playlists":
        _lib_playlists_view(_media, _lib_sort)
    else:
        _items = _media
        if _lib_view == "Songs":
            _items = [m for m in _items if m["fmt"] == "audio"]
        elif _lib_view == "Videos":
            _items = [m for m in _items if m["fmt"] == "video"]
        if _lib_q.strip():
            _ql = _lib_q.strip().lower()
            _items = [m for m in _items if _ql in os.path.basename(m["path"]).lower()]
        st.caption(f"{len(_items)} item(s)")
        _lib_song_grid(_items, "lib", _lib_sort)
    st.divider()

    with st.expander("🔧 Rebuild library index"):
        st.caption("Scans your folders and **reconstructs missing history records** "
                   "for media already on disk — recovering the original download "
                   "link from the permanent archive where possible. It only **adds** "
                   "records; it never moves or deletes files.")
        if st.button("🔧 Rebuild now", disabled=not scan_folders):
            bar = st.progress(0.0)
            note = st.empty()

            def _rp(d, n, _b=bar, _n=note):
                _b.progress(d / max(n, 1))
                _n.caption(f"Indexing… {d}/{n}")

            with st.spinner("Re-indexing your library…"):
                res = library.rebuild(scan_folders, progress=_rp)
            note.empty()
            st.success(f"Scanned **{res['scanned']}** file(s) · added "
                       f"**{res['added']}** new record(s) · recovered "
                       f"**{res['recovered_links']}** download link(s) from the "
                       f"archive · {res['already_tracked']} already tracked.")

    st.caption("Finds **only exact** duplicate files — identical **content** "
               "(same size **and** same SHA-256 hash). Never by filename. "
               "Scanning: " + (" · ".join(f"`{p}`" for p in scan_folders)
                               or "no valid folder"))
    sc1, sc2 = st.columns([2, 1])
    if sc1.button("🔍 Scan for duplicates", disabled=not scan_folders,
                  width="stretch"):
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
            for gi, g in enumerate(dup_groups[:80]):
                with st.container(border=True):
                    kc1, kc2 = st.columns([9, 1])
                    kc1.markdown(f"✅ **Keep:** `{g['keeper']}`")
                    if kc2.button("📂", key=f"dupk_{gi}",
                                  help="Open the folder & highlight the kept file"):
                        open_and_select(g["keeper"])
                    for di, d in enumerate(g["dups"]):
                        dc1, dc2 = st.columns([9, 1])
                        dc1.markdown(f"🟠 **Duplicate:** `{d}`")
                        if dc2.button("📂", key=f"dupd_{gi}_{di}",
                                      help="Open the folder & highlight this duplicate"):
                            open_and_select(d)
                    st.caption(f"{g['reason']} · {fmt_size(g['size'])} each · "
                               f"SHA-256 `{g['hash_short']}…` · "
                               f"reclaims {fmt_size(g['recover'])}")
            q1, q2 = st.columns([2, 1])
            if q1.button("🛡️ Move duplicates to Quarantine", type="primary",
                         width="stretch",
                         help="Moves (not deletes) the duplicates into "
                              "Quarantine/Duplicates — fully restorable"):
                to_move = [d for g in dup_groups for d in g["dups"]]
                batch, moved = library.quarantine(to_move, root=_quarantine_root)
                st.success(f"Moved **{moved}** duplicate(s) to Quarantine "
                           f"(`{batch}`). Restore anytime below.")
                st.session_state.pop("dup_groups", None)
            if q2.button("Keep all", width="stretch"):
                st.session_state.pop("dup_groups", None)
                st.rerun()

    # -- Quarantine management (restore / permanent delete) --------------------- #
    _batches = library.list_quarantine(root=_quarantine_root)
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
                                  width="stretch"):
                        n = library.restore_batch(b["batch"])
                        st.success(f"Restored **{n}** file(s) to their original "
                                   "locations.")
                        st.rerun()
                    if bc3.button("🗑️ Delete", key=f"qp_{b['name']}",
                                  width="stretch",
                                  help="Permanently remove this batch (to Recycle Bin)"):
                        n = library.purge_batch(b["batch"])
                        st.success(f"Permanently removed **{n}** file(s) "
                                   "(to the Recycle Bin).")
                        st.rerun()
                    for it in b["items"][:8]:
                        bc1.caption(f"• {os.path.basename(it['quarantined'])} "
                                    f"← {it['original']}")


# =========================================================================== #
# INSIGHTS + SMART COLLECTIONS (Wave D — preference learning)
# =========================================================================== #
def _ai_meta(h):
    return ai_cache.get(h.get("title") or h.get("filename")) or {}


with _t_insights:
    st.subheader("📊 Library Insights")
    if not all_hist:
        st.caption("Download a few things and your insights appear here.")
    else:
        from collections import Counter

        n = len(all_hist)
        total_sz = sum(h.get("size", 0) for h in all_hist)
        aud = sum(1 for h in all_hist if h.get("fmt") == "audio")
        vid = n - aud
        sites = Counter(h.get("site") or "Other" for h in all_hist)
        # Merge artist case/spacing/accent variants the SAME way Library Artists
        # does (artists.collapse_artist_counts), so "Bad Bunny" never splits into
        # two rows with different counts. `arts` stays a Counter for the rest of
        # the code (most_common); it just holds the canonical, merged names.
        _raw_arts = Counter(_ai_meta(h).get("artist") for h in all_hist
                            if _ai_meta(h).get("artist"))
        arts = Counter(dict(artists.collapse_artist_counts(dict(_raw_arts))))
        cats = Counter(_ai_meta(h).get("category") for h in all_hist
                       if _ai_meta(h).get("category"))
        hours, wdays = Counter(), Counter()
        for h in all_hist:
            try:
                ts = datetime.fromisoformat(h.get("ts", ""))
            except (ValueError, TypeError):
                continue
            hours[ts.hour] += 1
            wdays[ts.weekday()] += 1

        k1, k2, k3, k4 = st.columns(4)
        k1.metric("Downloads", n)
        k2.metric("Library size", fmt_size(total_sz))
        k3.metric("Artists", len(arts) if arts else 0)
        k4.metric("Sources", len(sites))

        st.markdown(f"**Format mix** — 🎵 Audio **{aud}** "
                    f"({aud * 100 // max(n, 1)}%) · 🎬 Video **{vid}** "
                    f"({vid * 100 // max(n, 1)}%)")
        if hours:
            st.markdown("**When you download (by hour of day)**")
            st.bar_chart({"downloads": [hours.get(hh, 0) for hh in range(24)]})

        ic1, ic2, ic3 = st.columns(3)
        ic1.markdown("**Top artists**")
        if arts:
            for a, x in arts.most_common(8):
                ic1.write(f"- {a}: **{x}**")
        else:
            ic1.caption("Run **Smart Library → Analyze with AI** to unlock.")
        ic2.markdown("**Top categories**")
        if cats:
            for c, x in cats.most_common(8):
                ic2.write(f"- {c}: **{x}**")
        else:
            ic2.caption("Analyze with AI to unlock.")
        ic3.markdown("**Top sources**")
        for s, x in sites.most_common(8):
            ic3.write(f"- {s}: **{x}**")

        st.markdown("**💡 Recommendations from your habits**")
        recs = []
        if aud >= vid:
            recs.append(f"You grab **audio** {aud * 100 // max(n, 1)}% of the time "
                        "— Single mode already defaults to Audio for you.")
        else:
            recs.append(f"You grab **video** {vid * 100 // max(n, 1)}% of the time "
                        "— consider keeping a separate Videos folder.")
        if sites:
            recs.append(f"Your main source is **{sites.most_common(1)[0][0]}**.")
        if hours:
            pk = hours.most_common(1)[0][0]
            recs.append(f"You're most active around **{pk:02d}:00**.")
        if arts:
            recs.append(f"Your most-downloaded artist is **{arts.most_common(1)[0][0]}**.")
        for r in recs:
            st.markdown(f"- {r}")

        if ai_on and st.button("✨ AI summary of my habits", key="ins_ai"):
            facts = (f"{n} downloads, {aud} audio / {vid} video, top sources "
                     f"{dict(sites.most_common(3))}, top artists "
                     f"{dict(arts.most_common(5))}, top categories "
                     f"{dict(cats.most_common(5))}, busiest hour "
                     f"{hours.most_common(1)[0][0] if hours else 'n/a'}.")
            with st.spinner("Thinking…"):
                try:
                    st.info("✨ " + ai.summarize_habits(facts))
                except Exception as exc:  # noqa: BLE001
                    st.error(f"AI summary failed: {exc}")

        # ---- Smart Collections -------------------------------------------- #
        st.divider()
        st.subheader("🎶 Smart Collections")
        st.caption("Auto-made from your AI tags — tap a collection to open it.")
        if not (arts or cats):
            st.caption("Run **Smart Library → Analyze with AI** to build collections.")
        else:
            colls = ([("🎤 " + a, "artist", a, x) for a, x in arts.most_common(12)]
                     + [("🏷️ " + c, "category", c, x) for c, x in cats.most_common()])
            cc = st.columns(3)
            for i, (label, kind, val, cnt) in enumerate(colls):
                if cc[i % 3].button(f"{label} · {cnt}", key=f"coll_{kind}_{val}",
                                    width="stretch"):
                    st.session_state.coll_pick = (kind, val)

            cp = st.session_state.get("coll_pick")
            if cp:
                ckind, cval = cp
                if ckind == "artist":          # match every spelling/case/accent variant
                    _ck = artists.artist_key(cval)
                    citems = [h for h in all_hist
                              if artists.artist_key(_ai_meta(h).get("artist") or "") == _ck]
                else:
                    citems = [h for h in all_hist if _ai_meta(h).get(ckind) == cval]
                t1, t2 = st.columns([4, 1])
                t1.markdown(f"#### {cval} — {len(citems)} item(s)")
                if t2.button("Close", key="coll_close"):
                    st.session_state.pop("coll_pick", None)
                    st.rerun()
                credl = [h for h in citems if h.get("url")]
                if credl and st.button(
                        f"⤓ Re-download whole collection ({len(credl)})",
                        key="coll_redl"):
                    nn = enqueue([media_job(h) for h in credl], downloads.LANE_BATCH)
                    st.success(f"⚡ Queued **{nn}** — see **Downloads** above.")
                for it in _paginate(citems, "coll_items"):
                    on_disk = bool(it.get("path") and os.path.isfile(it["path"]))
                    r1, r2, r3 = st.columns([7, 1, 1])
                    r1.markdown(
                        f"{'🎬' if it.get('fmt') == 'video' else '🎵'} "
                        f"**{_esc(it.get('title') or it.get('filename'))}**  \n"
                        f"<span style='color:#888;font-size:.8em'>"
                        f"{it.get('site', '')} · {fmt_size(it.get('size', 0))}"
                        f"{'' if on_disk else ' · ⚠️ file missing'}</span>",
                        unsafe_allow_html=True)
                    if r2.button("📂", key=f"coll_o_{it['id']}", disabled=not on_disk,
                                 help="Open & highlight"):
                        open_and_select(it["path"])
                    if r3.button("⤓", key=f"coll_r_{it['id']}",
                                 disabled=not it.get("url"), help="Re-download"):
                        enqueue([media_job(it)], downloads.LANE_NOW)
                        st.success(f"⚡ Re-downloading **{it.get('title') or 'item'}**.")


# --------------------------------------------------------------------------- #
# Footer
# --------------------------------------------------------------------------- #
st.divider()
fcol1, fcol2 = st.columns([3, 2])
fcol1.caption("Please only download content you have the rights to.")
fcol2.markdown(
    f"<div style='text-align:right;font-size:0.82em;color:#888'>"
    f"{branding.APP_NAME} v{branding.VERSION} · Published by "
    f"<b>{branding.PUBLISHER}</b>, {branding.COUNTRY}<br>"
    f"<a href='mailto:{branding.EMAIL}'>{branding.EMAIL}</a> · "
    f"<a href='{branding.WEBSITE}'>{branding.WEBSITE}</a></div>",
    unsafe_allow_html=True)
