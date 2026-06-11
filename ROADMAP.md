# Universal Media Downloader — Roadmap

**Vision:** evolve from a standalone downloader into a complete **media
management platform** — downloading, organization, AI assistance, licensing,
and cross-platform access in one ecosystem.

Four pillars, developed in phases: **Downloads · AI · Licensing · Mobile/Sync.**

---

## Architecture principles (apply to everything below)

- **AI is a pillar, not an add-on.** It should improve nearly every surface of
  the app, not live in one corner.
- **Licensing ≠ AI access.** A *license key* unlocks the app. An *AI provider
  API key* (separate) unlocks AI features. Either can change without touching
  the other.
- **Bring-your-own-key.** No API key ships inside the exe. Users paste a key in
  **AI Settings**; it's encrypted at rest (Windows DPAPI) and only shown masked.
  Your key never leaks into a distributed build; different users use different
  keys.
- **Efficiency over flash.** Free AI tiers are rate-limited (~tens of
  requests/min). Cache every result, batch requests, and prefer one smart call
  over many. Never send a request a rule could answer — but don't fake AI with
  rules where real understanding wins.
- **Privacy.** Only text (titles, prompts, metadata) is ever sent — never media
  files. AI is opt-in and off by default.
- **Provider-agnostic.** OpenAI-compatible providers behind one interface
  (NVIDIA today; OpenAI/others trivially added).

---

## Phase 1 — Desktop (primary product) — ✅ essentially done

- Single / Channel-Profile / Bulk downloading; MP3/M4A/MP4, quality, trim.
- Background **download queue** (multitask across modes; cancel; live panel).
- Channel/profile grab with search, 50/page pagination, date-range.
- Persistent **history** (filters, pagination, open/remove, clear).
- Native **desktop window** (PyWebView/WebView2) — no browser tab.
- Machine-bound **licensing** + premium **License Console** (native window).
- Custom **icon**, **publisher/contact** credit on the activation gate, v1.2,
  slim installer (~144 MB).
- **Remaining polish:** in-window link handoff (WhatsApp/email), optional
  "one-tap request a license" (prefilled WhatsApp with machine ID).

## Phase 2 — AI ecosystem (in progress)

Built in waves so AI keeps growing into a core feature.

### Wave A — Foundation ✅ done
- **AI Settings** section: provider + masked, DPAPI-encrypted, user-supplied key;
  validate / save / remove; model picker; status. (Separate from licensing.)
- **Smart Library v1:** clean titles → artist / clean-title / category /
  official; write real tags (mutagen); group history by category & top artists;
  per-row badge. Disk-cached.

### Wave B — Understanding & organization
- ✅ **Smart channel triage** — AI classifies a scanned channel and
  **pre-selects** what to grab ("official music only; skip shorts/vlogs").
- ✅ **AI duplicate detection (fuzzy)** — same song across different uploads,
  matched by AI artist + clean title (history view).
- ✅ **Managed library + auto-routing** — user-chosen workspace
  (Music/MP3, Videos/MP4, …); downloads auto-file by type.
- ✅ **Exact duplicate cleanup (deterministic)** — size + SHA-256 content match;
  confirm dialog (Delete / Keep / Review); deletes to the Recycle Bin.
- **Next:** auto file-naming (`Artist - Title`) + metadata enrichment (album/
  year/cover); auto collections/playlists; embeddings-based similarity.
- **File-management librarian (upcoming):** folder health monitoring, missing-
  metadata detection, broken/corrupted media detection, storage optimization,
  large-file + unused-file recommendations, archive management, smart
  restructuring — all confirm-before-acting, scoped to user-approved folders.
- **Models:** instruct (llama-3.3-70b / nemotron) for classification;
  embeddings (nv-embedqa / llama-3.2-nv-embedqa) for similarity.

### Wave C — Assistant & agent
- **Natural-language control / AI agent** — "download all of Diamond's songs as
  MP3" → it finds the channel, picks format, and queues the right items. Actions
  inside the app, not just chat.
- **AI support & troubleshooting** — reads a failed download's error and
  explains/fixes it in plain language (cookies needed? rate-limited? try M4A?).
- **Context-aware semantic search** — search your library by meaning ("that live
  performance from Rock City"), powered by embeddings.
- **Download quality recommendations** — suggest best format/quality per source
  and intent (music → MP3/M4A; archive → best MP4).

### Wave D — Intelligence & automation
- **Learn preferences over time** — default formats/folders from your habits.
- **Predict sources & patterns** — surface frequently used channels; "new
  uploads from artists you follow".
- **Smart scheduling / optimization** — batch big grabs for off-peak; throttle
  to dodge rate limits; resume planning.
- **Content summarization** — summarize long videos/podcasts/docs (pairs with
  transcription; vision models can read thumbnails/screens).
- **Intelligent monitoring & reporting** — weekly library digest; storage and
  category insights.

### Wave E — AI as platform
- Dedicated **AI section** (own page, separate from Downloads/Licensing/Settings)
  managing providers, keys, models, features, and **usage/quota status**.
- Multiple providers + per-feature model routing (cheap model for tagging, big
  model for the agent).
- Optional **hosted proxy** so non-technical customers get AI without their own
  key, with your server enforcing quotas (commercial-scale answer to rate
  limits).

## Phase 3 — Android / mobile

Same core, adapted for phones; the desktop stays primary.

- **Engine:** native Android app using a maintained `youtubedl-android`-style
  library that bundles Python + yt-dlp + ffmpeg on-device (this, not a Streamlit
  port, is the realistic path). The signature/JS challenge and codecs are the
  hard parts; licensing is the easy part.
- **Licensing parity:** derive a stable device ID (`UMD-XXXX-XXXX-XXXX`) and
  **reuse the same `licensing.py` HMAC** — keys issued from the *same* License
  Console work on mobile.
- **UX parity goals:** single / channel / bulk; MP3/MP4; history; AI features
  (BYO key) where feasible.

## Phase 4 — Cross-platform ecosystem & cloud

- **Library sync** across devices (history, tags, collections).
- **Shared settings & preferences.**
- **Unified licensing** — one identity, multiple devices, central management in
  the License Console.
- **Advanced cloud features** — optional backup, share links, remote queue
  ("send this to my PC to download").
- **Sync architecture options:** user-owned cloud folder vs. a lightweight sync
  service you host (also the natural home for the AI proxy and license server).

---

## Near-term order of work
1. Phase 1 polish (license-request handoff).
2. Phase 2 **Wave B** — smart channel triage first (highest "feels like AI"
   value), then duplicate detection + auto-naming.
3. Phase 2 **Wave C** — the natural-language agent + AI troubleshooting.
4. Begin Phase 3 spike (device-ID + licensing on Android) in parallel once
   Wave B lands.
