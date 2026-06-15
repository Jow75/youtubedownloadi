# Universal Media Downloader — Android (Phase 3)

A native Android app that mirrors the desktop product: it downloads media with
the **same engine** (yt-dlp + ffmpeg, bundled for Android via
[`youtubedl-android`](https://github.com/JunkFood02/youtubedl-android)) and uses
the **same licensing system** (your desktop License Console issues keys that
activate this app too).

This folder is a complete Android Studio project. I scaffolded the code here;
you build, run, and sign the APK in **Android Studio** (the SDK/Gradle/JDK it
installs are what actually compile an APK — that can't be done from the desktop
side).

---

## What works in this first version
- **License gate** — shows the device's ID (`UMD-XXXX-XXXX-XXXX`), you paste a
  key, it verifies offline (HMAC-SHA256, machine-bound, expiry-checked) exactly
  like the desktop. Expired key → re-locks (same behaviour).
- **Download** a link as **Audio (MP3)** — the default — or **Video (MP4)** with
  Best/720p/480p, with a progress bar.
- **Public, browsable saves** — files land in
  **`Download/Universal Media Downloader/`** (audio → `Music/MP3`, video →
  `Videos/MP4`), the same layout as the desktop, so they show up in your Files
  app / Gallery / music players (not the hidden `Android/data` sandbox).
- **Find your file instantly** — after each download a card shows the exact path
  with **Open folder / Play / Share**.
- **History tab** — every finished download is logged (title, type, size, date,
  folder) with **Play / Share / Re-download / Remove** and search. The log lives
  in `History/history.jsonl` in public storage, so it survives reinstalls (it
  doubles as the permanent archive).
- **Auto-updating engine** — yt-dlp refreshes itself on launch (throttled), so
  YouTube/TikTok keep working without manually pressing *Update engine*.
- **AI error helper** — when a download fails, *Explain & fix (AI)* turns the
  cryptic yt-dlp error into a plain-language reason + fix, using the same NVIDIA
  BYO key as the desktop. The key is entered in *AI assistant settings* and
  stored encrypted (Android Keystore); only the error text is ever sent.
- **Library tab (AI)** — *Smart search* (find downloads by meaning via NVIDIA
  embeddings), *Duplicate cleanup* (byte-identical files), and *Title clean-up*
  (AI-suggested artist · title · category, with one-tap rename). The search index
  lives in the public AI Library folder.
- **Channel tab** — paste a channel / playlist / profile link, **Scan** to see
  everything in it, then **Download all** (audio or video, optional cap of
  10/25/50). Each file lands in your folders and History.
- **Assistant tab** — a chat assistant: say "download lo-fi beats as mp3" or
  "get this video in 720p" and it plans + runs the download (ports the desktop
  agent_plan); ask "where do my files save?" and it answers. **Multiple chats**
  (ChatGPT-style drawer): one per artist/topic, switch/new/delete/delete-all, and
  they're saved to disk so they survive restarts. Uses the same key.
- **Modern UI** — Material You dynamic colour (themes to your wallpaper on
  Android 12+), a top app bar, and tidier screens — same flow, fresher look.
- **Storage-access gate** — one-tap prompt to grant the access needed to write to
  the public folder (All-files access on Android 11+, storage permission on 8–10).
- **Update engine** button (keeps yt-dlp current).
- Publisher/contact links on the gate (email / WhatsApp / website).

Channel/Profile, Bulk, History, and AI come next (parity with desktop, phase by
phase).

---

## Build it (Android Studio)
1. **Open** Android Studio → *File → Open* → select this **`mobile/`** folder
   (not the repo root).
2. Let **Gradle sync** finish. It downloads the Gradle wrapper, the Android SDK
   bits, and the dependencies. If it complains a version isn't found (e.g. the
   `youtubedl-android` or AGP version), accept Android Studio's suggestion to
   update to the latest — the code doesn't depend on the exact version.
3. **Set the signing secret** (one time): copy `secret.properties.example` to
   **`secret.properties`** (same folder) and paste your **`secret.key` hex** —
   the *same* value your desktop signs with. This is what makes desktop-issued
   keys activate the app. *(`secret.properties` is gitignored — never commit it.)*
4. Plug in a phone (USB debugging) or start an emulator, then **Run ▶**.

> First launch unpacks the Python runtime — give it a few seconds.

---

## Issue a license for a phone
1. Open the app → it shows **this device's ID** (`UMD-…`). Copy it.
2. On your PC, open the **License Console** (`LicenseConsole.exe`) and generate a
   key for that ID — it accepts any `UMD-XXXX-XXXX-XXXX`, desktop or mobile.
3. Paste the key in the app → **Activate**. Done until it expires.

The same secret signs both platforms, so **one License Console serves desktop
and mobile**.

---

## Notes / known follow-ups
- **Where files save:** the public **`Download/Universal Media Downloader/`** tree
  (`Music/MP3`, `Videos/MP4`, plus `Downloads/ History/ Metadata/ AI Library/`
  placeholders mirroring the desktop). Writing there needs storage access — the
  app prompts for it. (Android 11+ uses *All files access* / `MANAGE_EXTERNAL_STORAGE`;
  that's fine for sideloaded/licensed distribution but would need justification
  for Google Play — a MediaStore-only path is the Play-friendly alternative later.)
- **minSdk 26** (Android 8.0+) so the app icon can be a vector adaptive icon with
  no binary PNGs. Lower it + add PNG icons via *Asset Studio* if you need older.
- **App icon:** a vector version of the desktop download icon is included. To use
  the exact desktop art, run *Asset Studio* on `../assets/umd.png`.
- **Gradle wrapper jar:** if Android Studio reports the wrapper is missing, it
  will offer to generate it (or run `gradle wrapper` once).
- **Security:** symmetric HMAC means the secret is embedded in the APK and is
  extractable — same known limitation as the desktop exe; fine at this scale,
  harden later with asymmetric (Ed25519) signing.

---
Published by **George (Jowgei)**, Kenya · phantomtyper.review@gmail.com ·
https://baziqhue.co.ke/
