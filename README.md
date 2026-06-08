# ⬇️ Universal Media Downloader

A local Streamlit web app that downloads media from **YouTube, X (Twitter),
TikTok, Reddit, Instagram**, and 1,800+ other sites supported by
[`yt-dlp`](https://github.com/yt-dlp/yt-dlp). Audio is converted to 192 kbps MP3
(or kept as original M4A), video/audio are merged into MP4 via `ffmpeg`, and
files are saved **straight to a folder on your PC**.

## Why local?
Modern YouTube scrambles stream URLs with a JavaScript challenge, so yt-dlp
needs a JS runtime (**Node.js** or Deno) plus the `yt-dlp-ejs` solver scripts.
Running locally also uses your residential IP (cloud/datacenter IPs get HTTP
403). That's why this is built to run on your machine, not on a cloud host.

## Features
- **Single** link or **Bulk** mode (paste many links into MP4 / MP3 columns).
- **Saves directly to disk** — no browser download, so download managers like
  IDM never interfere.
- **Separate folders** for video vs audio (optional).
- **Embedded cover art + tags** for a clean music library.
- **Playlist / channel**: one link grabs every item.
- **Clip trimming**, **MP3 or fast M4A**, **aria2c turbo**, optional cookies.
- **Download history** with open-folder buttons.

## Files
| File | Purpose |
|------|---------|
| `app.py` | Streamlit UI. |
| `downloader.py` | Core download engine (no Streamlit — testable on its own). |
| `requirements.txt` | Python dependencies. |
| `packages.txt` | System deps for Linux hosts (`ffmpeg`). |
| `run.bat` | Double-click launcher (Windows). |

## Run locally (Windows)
```powershell
pip install -r requirements.txt
winget install Gyan.FFmpeg          # ffmpeg (audio/video processing)
winget install aria2.aria2          # optional: turbo multi-connection downloads
# Node.js is required for YouTube (winget install OpenJS.NodeJS.LTS)
```
Then double-click **`run.bat`**, or:
```powershell
python -m streamlit run app.py
```
A browser tab opens at http://localhost:8501.

> If `ffmpeg`/`aria2c` aren't found right after installing, reboot once so
> Windows refreshes PATH.

## Login cookies (advanced)
Some content needs a login (private Instagram, protected X, certain Reddit/age
‑gated posts). Export a `cookies.txt` with a "Get cookies.txt" browser
extension and paste its path in the sidebar under **Speed & advanced**. Public
posts need nothing.

## Notes
- Respect copyright and each platform's Terms of Service.
- DRM-protected streams (Netflix, Spotify) cannot be downloaded by any tool.
