# 📖 Universal Media Downloader — User Guide

A simple, complete guide to using the app. Keep it handy.

---

## 1. Starting the app
- **Double-click `run.bat`** (Windows). A browser tab opens at `http://localhost:8501`.
- Keep the little black window open while you use it. Close it to stop the app.
- First time only: make sure **ffmpeg** and **Node.js** are installed (the app needs
  them for YouTube + converting). If a download says "ffmpeg not found", **reboot once**.

---

## 2. The two modes (top of the page)

### 🔗 Single link
1. Paste one link → the app shows the **title, channel, length, thumbnail**.
2. Choose **🎬 Video (MP4)** or **🎵 Audio Only**.
   - For audio, pick **MP3** (plays everywhere) or **M4A** (original quality, **much faster** — no conversion).
   - For video, pick a **quality** (Best / 720p / 480p).
3. Click **⬇️ Download**. A progress bar shows speed + size. When done, the file is
   **saved straight to your folder** and a **📂 Open folder** button appears.

### 📚 Bulk (many links)
Two methods (pick at the top):
- **⚡ Two columns (recommended):** paste links into the **🎬 MP4** box or the **🎵 MP3**
  box (one per line), set the video quality, click **Download all**.
- **🎚️ Scan & choose per link:** paste all links → **🔎 Scan** → see each title → choose
  the exact format/quality for **each** one → **Download selected**.

---

## 3. Where files go (sidebar)
- **Save downloads to folder:** type any folder path (default is your Downloads).
- **📂 Separate folders for Video and Audio:** tick this to send MP4s and MP3s to
  **different** folders (set each path). Leave unticked to put everything in one folder.
- Files are written **directly to disk** — there is **no browser download**, so
  download managers like **IDM never interfere**.

---

## 4. Extra options (sidebar → ⚡ Speed & advanced)
- **Turbo downloads (aria2c):** multi-connection speed boost for non-YouTube sites.
  YouTube throttles multi-connection, so the app **auto-uses YouTube's faster native
  method**. Safe to leave **on**.
- **🏷️ Embed cover art + tags:** puts the thumbnail as cover art and writes the
  title/artist into the file — great for a clean music library. Leave **on**.
- **Path to a cookies.txt file:** only for **private / login-required** content. Leave
  **blank** for normal public videos. (See section 6.)

---

## 5. Trimming a clip (Single mode)
Open **✂️ Trim a clip (optional)**, type a **Start** and **End** (e.g. `1:30` and `2:45`),
then download. You'll get just that section. (It re-encodes for exact cuts, so it's a
little slower — that's normal.)

---

## 6. 🍪 Cookies — for Reddit / private X / Instagram (IMPORTANT)
Some sites require you to be **logged in**. The app can't log in for you, but it can use
your browser's login via a **cookies.txt** file:

1. In **Chrome**, install the extension **"Get cookies.txt LOCALLY"**
   ⚠️ It must say **LOCALLY** (the other "Get cookies.txt" was malware and removed).
2. **Log in** to the site (e.g. Reddit) in Chrome, and open the page you want.
3. Click the extension icon → **Export** → it saves a `cookies.txt` file (to Downloads).
4. In the app sidebar → **⚡ Speed & advanced** → paste the **full path** to that file in
   **"Path to a cookies.txt file"**, e.g. `C:\Users\You\Downloads\cookies.txt`.
5. Download the link normally. **Leave the box blank** for everything else.

> Cookies expire — if a site stops working later, re-export a fresh cookies.txt.

---

## 7. 🕘 Download history
A list of everything downloaded this session appears at the bottom, each with a **📂**
button to open its folder.

---

## 8. 🔑 License / Activation (sidebar)
If this is a licensed copy:
1. Open **🔑 License / Activation** and copy your **computer ID** (`UMD-XXXX-XXXX-XXXX`).
2. Send it to the seller; you'll get a **license key** (`UMDL-...`).
3. Paste the key, click **Activate**. The status shows your expiry date.

---

## 9. Troubleshooting
| Problem | Fix |
|---|---|
| "ffmpeg not found" | Install ffmpeg (`winget install Gyan.FFmpeg`) and **reboot once**. |
| YouTube "video unavailable" (sometimes) | Transient throttling — try again in a minute. |
| X (Twitter) link fails sometimes | X rate-limits; the app retries automatically. Re-run it. |
| Reddit "authentication required" | Use a **cookies.txt** (section 6). |
| Download is slow | Mostly your internet speed. Turbo helps non-YouTube sites. |
| A whole playlist | Single mode → tick **📜 Download the ENTIRE playlist/channel**. |

> Only download content you have the rights to. DRM sites (Netflix, Spotify) can't be downloaded by any tool.
