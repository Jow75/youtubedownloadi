# ⬇️ Universal Media Downloader

A single-file Streamlit web app that downloads media from YouTube, X (Twitter),
Reddit, Instagram, and hundreds of other sites supported by
[`yt-dlp`](https://github.com/yt-dlp/yt-dlp). Audio is converted to 192 kbps MP3
and video/audio streams are merged into MP4 using `ffmpeg`.

## Files

| File | Purpose |
|------|---------|
| `app.py` | The entire application (UI + server logic). |
| `requirements.txt` | Python dependencies. |
| `packages.txt` | System (Debian/Ubuntu) dependencies — installs `ffmpeg`. |

## Run locally

```bash
pip install -r requirements.txt
# Install ffmpeg from your OS package manager, e.g.:
#   Windows (winget):  winget install Gyan.FFmpeg
#   macOS (brew):      brew install ffmpeg
#   Debian/Ubuntu:     sudo apt install ffmpeg
streamlit run app.py
```

## Deploy to Streamlit Community Cloud

1. **Create a public GitHub repo** and push these three files to its root:
   `app.py`, `requirements.txt`, `packages.txt`.
2. Go to **https://share.streamlit.io** and sign in with GitHub.
3. Click **“Create app” → “Deploy a public app from GitHub.”**
4. Pick your **repository**, **branch** (`main`), and set **Main file path**
   to `app.py`.
5. Click **Deploy**. Streamlit installs the Python packages from
   `requirements.txt` and the system `ffmpeg` from `packages.txt` automatically.
6. Wait for the build to finish — your app gets a public
   `https://<your-app>.streamlit.app` URL. Share it or use it yourself.

> **Tip:** If a site’s extractor breaks, redeploy (or click *Reboot app*) to pull
> the latest `yt-dlp`, which is updated frequently to keep up with site changes.

## Notes

- Downloads are processed in the server’s temp directory and streamed to your
  browser; nothing is permanently stored on the host.
- Some platforms (private Instagram posts, age-restricted videos, etc.) require
  authentication and won’t download without cookies.
- Respect copyright and each platform’s Terms of Service. Only download content
  you have the right to.
