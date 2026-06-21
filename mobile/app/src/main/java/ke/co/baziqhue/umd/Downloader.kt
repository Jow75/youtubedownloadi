package ke.co.baziqhue.umd

import android.content.Context
import com.yausername.ffmpeg.FFmpeg
import com.yausername.youtubedl_android.YoutubeDL
import com.yausername.youtubedl_android.YoutubeDLRequest
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.sync.Mutex
import kotlinx.coroutines.sync.withLock
import kotlinx.coroutines.withContext
import org.json.JSONObject
import java.io.File

/**
 * Thin wrapper over youtubedl-android (Python + yt-dlp + ffmpeg, bundled for
 * Android). Same engine as the desktop, so behaviour matches. Files are written
 * to the public Downloads tree via [Storage].
 *
 * Note: the yt-dlp binary is frozen into the APK at build time, but sites
 * (YouTube especially) change constantly, so the bundled copy goes stale fast.
 * [prepareEngine] auto-refreshes it on launch so the user never has to race the
 * "Update engine" button to get a working download.
 */
object Downloader {

    private const val PREFS = "umd_engine"
    private const val KEY_LAST_UPDATE = "yt_dlp_last_update"
    private const val UPDATE_INTERVAL_MS = 6L * 60 * 60 * 1000  // refresh at most every 6h

    private val MEDIA_EXT = setOf(
        "mp3", "m4a", "aac", "opus", "ogg", "wav", "flac",
        "mp4", "mkv", "webm", "mov", "avi", "m4v",
    )

    // yt-dlp prints the file it actually writes — parse it so we report the REAL
    // download, not a guess from the folder (which could be a previous file).
    private val DEST_RE = Regex("""Destination:\s*(.+)""")
    private val MERGE_RE = Regex("""Merging formats into "(.+)"""")
    private val ALREADY_RE = Regex("""\[download]\s+(.+?) has already been downloaded""")

    @Volatile private var ready = false
    @Volatile private var enginePrepared = false
    private val engineLock = Mutex()

    /** Result of a finished download: the file that landed and where. */
    data class Outcome(val file: File?, val dir: File, val message: String)

    private fun enginePrefs(ctx: Context) =
        ctx.getSharedPreferences(PREFS, Context.MODE_PRIVATE)

    /** Heavy one-time init (unpacks Python). Call off the main thread. */
    suspend fun ensureInit(context: Context) = withContext(Dispatchers.IO) {
        if (ready) return@withContext
        YoutubeDL.getInstance().init(context)
        FFmpeg.getInstance().init(context)
        ready = true
    }

    /**
     * Init + a throttled auto-update so the engine isn't stale on the first
     * download. Safe to call repeatedly (guarded + time-throttled). [onStatus]
     * reports progress for the UI; runs once per app session.
     */
    suspend fun prepareEngine(context: Context, onStatus: (String) -> Unit = {}) =
        withContext(Dispatchers.IO) {
            engineLock.withLock {
                ensureInit(context)
                if (enginePrepared) return@withLock
                val prefs = enginePrefs(context)
                val now = System.currentTimeMillis()
                val last = prefs.getLong(KEY_LAST_UPDATE, 0L)
                if (now - last > UPDATE_INTERVAL_MS) {
                    onStatus("🔄 Refreshing download engine…")
                    try {
                        YoutubeDL.getInstance().updateYoutubeDL(context)
                        prefs.edit().putLong(KEY_LAST_UPDATE, now).apply()
                    } catch (_: Exception) {
                        // Offline or update server down — fall back to the bundled
                        // engine; the manual button is still there.
                    }
                }
                enginePrepared = true
            }
        }

    /** Manual "Update engine" button — forces a refresh and records it. */
    suspend fun updateEngine(context: Context): String = withContext(Dispatchers.IO) {
        try {
            ensureInit(context)
            YoutubeDL.getInstance().updateYoutubeDL(context)
            enginePrefs(context).edit()
                .putLong(KEY_LAST_UPDATE, System.currentTimeMillis()).apply()
            enginePrepared = true
            "Engine updated."
        } catch (e: Exception) {
            "Update failed: ${e.message}"
        }
    }

    /** Folder a download of this type will land in (public, user-browsable). */
    fun targetDir(audio: Boolean): File = if (audio) Storage.audioDir() else Storage.videoDir()

    /** Retrying won't help clearly-permanent failures — bail early on those. */
    private fun isRetryable(msg: String?): Boolean {
        val m = (msg ?: "").lowercase()
        val permanent = listOf(
            "private video", "video unavailable", "removed by the user",
            "not available in your country", "members-only", "sign in to confirm your age",
            "requested format is not available", "no video formats", "unsupported url",
        )
        return permanent.none { it in m }
    }

    /**
     * Pull the real artist out of the source metadata (the .info.json yt-dlp wrote)
     * and record it as the authoritative artist in [ArtistStore]. Works for YouTube,
     * TikTok, Instagram, etc. — the artist comes from the platform, not the filename.
     * Then the sidecar is deleted so the public folder stays clean.
     */
    private fun captureArtist(saved: File) {
        val dir = saved.parentFile ?: return
        try {
            val exact = File(dir, saved.nameWithoutExtension + ".info.json")
            val src = if (exact.exists()) exact
            else dir.listFiles { f -> f.name.endsWith(".info.json") }?.firstOrNull()
            if (src != null && src.exists()) {
                try {
                    val artist = resolveArtist(JSONObject(src.readText()))
                    if (artist.isNotBlank()) {
                        ArtistStore.put(saved.absolutePath, artist)
                        MediaMeta.forget(saved.absolutePath)
                    }
                } catch (_: Exception) {}
            }
            // Sweep any leftover sidecars so the user never sees *.info.json files.
            dir.listFiles { f -> f.name.endsWith(".info.json") }?.forEach { runCatching { it.delete() } }
        } catch (_: Exception) {}
    }

    /** Best artist from source metadata: music artist → creator → channel → uploader. */
    private fun resolveArtist(o: JSONObject): String {
        val raw = listOf("artist", "creator", "channel", "uploader")
            .map { o.optString(it) }
            .firstOrNull { it.isNotBlank() && !it.equals("null", true) } ?: return ""
        var a = raw.trim()
        a = a.removeSuffix(" - Topic").trim()              // YouTube auto-generated artist channels
        a = a.replace(Regex("(?i)\\s*-?\\s*VEVO$"), "").trim()
        a = a.split(",").first().trim()                    // primary of "Artist A, Artist B"
        return a
    }

    /**
     * Download [url] as audio (mp3) or video (mp4). [onProgress] gets 0..100.
     * Returns the saved file + its folder. Run from a coroutine (it blocks).
     */
    suspend fun download(
        context: Context,
        url: String,
        audio: Boolean,
        quality: String,
        onProgress: (Float, String) -> Unit,
    ): Result<Outcome> = withContext(Dispatchers.IO) {
        try {
            // Make sure the engine is current before we start (no-op if already done).
            prepareEngine(context)
            val dir = targetDir(audio)
            // Snapshot so we can tell which file is the new one afterwards.
            val before = dir.listFiles()?.associate { it.name to it.lastModified() } ?: emptyMap()

            val req = YoutubeDLRequest(url)
            req.addOption("--no-mtime")
            req.addOption("--no-playlist")
            req.addOption("-o", File(dir, "%(title)s.%(ext)s").absolutePath)
            if (audio) {
                req.addOption("-x")
                req.addOption("--audio-format", "mp3")
                req.addOption("--audio-quality", "0")
            } else {
                // Force H.264 (avc1) video + AAC audio, capped at 1080p and 30fps.
                // Phones decode this in hardware smoothly; VP9/AV1, 4K, and 60fps are
                // what overload the decoder so the video stutters / drops frames and
                // "catches up" to the audio. avc1 + ≤1080p + ≤30fps keeps it in sync.
                val sel = when (quality) {
                    "720p" -> "bestvideo[vcodec^=avc1][height<=720][fps<=30]+bestaudio[ext=m4a]/best[ext=mp4][height<=720]/best[height<=720]"
                    "480p" -> "bestvideo[vcodec^=avc1][height<=480][fps<=30]+bestaudio[ext=m4a]/best[ext=mp4][height<=480]/best[height<=480]"
                    else -> "bestvideo[vcodec^=avc1][height<=1080][fps<=30]+bestaudio[ext=m4a]/best[ext=mp4][height<=1080]/bestvideo[ext=mp4]+bestaudio[ext=m4a]/best"
                }
                req.addOption("-f", sel)
                req.addOption("--merge-output-format", "mp4")
            }
            req.addOption("--embed-metadata")
            // Embed the YouTube thumbnail as cover art so the Library/player show
            // a real picture (usually the artist) instead of a placeholder tile.
            req.addOption("--embed-thumbnail")
            // Write the source metadata (artist/track/album/channel/uploader) to a
            // sidecar so we capture the REAL artist instead of guessing it from the
            // filename. We read it after the download, then delete it.
            req.addOption("--write-info-json")

            // Some sites (TikTok especially) have probabilistic anti-bot
            // responses — the same request fails one moment and succeeds the
            // next. Retry a few times before giving up so the user doesn't have
            // to keep re-tapping. Skip retries for clearly-permanent failures.
            var lastError: String? = null
            var succeeded = false
            var destLine: String? = null   // last "Destination:" path yt-dlp printed
            var mergeLine: String? = null  // "Merging formats into" path (video)
            val maxAttempts = 3
            for (attempt in 1..maxAttempts) {
                try {
                    if (attempt > 1) onProgress(0f, "Site was flaky — retrying ($attempt/$maxAttempts)…")
                    YoutubeDL.getInstance().execute(req) { progress, _, line ->
                        val l = line.orEmpty()
                        DEST_RE.find(l)?.let { destLine = it.groupValues[1].trim() }
                        MERGE_RE.find(l)?.let { mergeLine = it.groupValues[1].trim() }
                        ALREADY_RE.find(l)?.let { destLine = it.groupValues[1].trim() }
                        onProgress(if (progress < 0) 0f else progress, l)
                    }
                    succeeded = true
                    break
                } catch (e: Exception) {
                    lastError = e.message ?: "Download failed"
                    if (!isRetryable(lastError)) break
                }
            }
            if (!succeeded) return@withContext Result.failure(Exception(lastError ?: "Download failed"))

            // Prefer the file yt-dlp itself reported writing (authoritative).
            val reported = (mergeLine ?: destLine)?.let { File(it) }?.takeIf {
                it.exists() && it.extension.lowercase() in MEDIA_EXT
            }
            // Otherwise diff the folder for a genuinely NEW/changed media file.
            // No stale fallback: if nothing was produced, this is a failure — we
            // must never report a previously-downloaded file as the result.
            val after = dir.listFiles()?.toList() ?: emptyList()
            val saved = reported ?: after.filter { f ->
                val prev = before[f.name]
                (prev == null || f.lastModified() > prev) && f.extension.lowercase() in MEDIA_EXT
            }.maxByOrNull { it.length() }

            if (saved == null) {
                return@withContext Result.failure(
                    Exception("Nothing was downloaded (the source may have failed, or it already exists)."))
            }
            captureArtist(saved)   // real artist from the source metadata
            Storage.scan(context, saved)
            Storage.scan(context, dir)
            Result.success(Outcome(saved, dir, "Saved to ${Storage.displayPath(dir)}"))
        } catch (e: Exception) {
            Result.failure(e)
        }
    }

    /** One item in a channel/playlist/profile. */
    data class Entry(
        val title: String,
        val url: String,
        val durationSec: Int = 0,
        val thumb: String = "",
        val uploader: String = "",
    )

    /** Result of scanning a URL: its [title], whether it's a real playlist (vs a whole
     *  channel), and the [entries]. Only a genuine playlist is auto-grouped into a
     *  Library playlist on download. */
    data class Scan(val title: String, val isPlaylist: Boolean, val entries: List<Entry>)

    // A bare YouTube channel root lists only its TABS (Videos, Shorts, …) — so a
    // naive scan returns "2 items", not the videos. Point it at the /videos tab
    // (mirrors desktop downloader.normalize_channel_url) so we get every upload.
    private val YT_TABS = listOf(
        "/videos", "/shorts", "/streams", "/playlists", "/featured", "/community", "/about")
    private val CHANNEL_ROOT_RE =
        Regex("""youtube\.com/(@[^/]+|channel/[^/]+|c/[^/]+|user/[^/]+)$""", RegexOption.IGNORE_CASE)

    private fun normalizeChannelUrl(url: String): String {
        val u = url.trim()
        if (u.isEmpty() || "youtube.com" !in u.lowercase()) return u
        val base = u.substringBefore("?").substringBefore("#").trimEnd('/')
        if (YT_TABS.any { base.lowercase().endsWith(it) }) return base
        if (CHANNEL_ROOT_RE.containsMatchIn(base)) return "$base/videos"
        return u
    }

    private fun thumbFor(e: JSONObject, id: String): String {
        val ta = e.optJSONArray("thumbnails")
        val fromArr = if (ta != null && ta.length() > 0)
            ta.optJSONObject(ta.length() - 1)?.optString("url").orEmpty() else ""
        return when {
            fromArr.isNotBlank() -> fromArr
            id.length == 11 -> "https://i.ytimg.com/vi/$id/mqdefault.jpg"
            else -> ""
        }
    }

    // Walk nested results (a channel comes back as tabs-of-playlists), skip the
    // channel-tab pseudo-entries, and de-dupe — so leaves are real, watchable videos.
    private fun walkEntries(node: JSONObject, depth: Int, out: MutableList<Entry>, seen: MutableSet<String>) {
        if (depth > 4) return
        val subs = node.optJSONArray("entries")
        if (subs != null && subs.length() > 0) {
            for (i in 0 until subs.length()) {
                subs.optJSONObject(i)?.let { walkEntries(it, depth + 1, out, seen) }
            }
            return
        }
        val ieKey = node.optString("ie_key").ifBlank { node.optString("_type") }
        if (ieKey.equals("YoutubeTab", true)) return
        val id = node.optString("id")
        val eurl = node.optString("url").ifBlank { node.optString("webpage_url").ifBlank { id } }
        if (eurl.isBlank()) return
        val key = id.ifBlank { eurl }
        if (key in seen) return
        seen.add(key)
        out.add(Entry(
            node.optString("title").ifBlank { eurl }, eurl,
            node.optDouble("duration", 0.0).toInt(), thumbFor(node, id),
            node.optString("uploader").ifBlank { node.optString("channel") }))
    }

    /**
     * List every video in a channel / playlist / profile URL without downloading
     * (flat extraction — fast). Channel roots are rewritten to /videos and nested
     * tab-playlists are walked, so you get the real videos (not "Videos/Shorts").
     */
    suspend fun scanEntries(context: Context, url: String): Result<Scan> =
        withContext(Dispatchers.IO) {
            try {
                ensureInit(context)
                val target = normalizeChannelUrl(url.trim())
                val req = YoutubeDLRequest(target)
                req.addOption("--flat-playlist")
                req.addOption("--dump-single-json")
                req.addOption("--no-warnings")
                val resp = YoutubeDL.getInstance().execute(req)
                val root = JSONObject(resp.out)
                val list = ArrayList<Entry>()
                walkEntries(root, 0, list, HashSet())
                if (list.isEmpty()) {
                    val u = root.optString("webpage_url").ifBlank { target }
                    list.add(Entry(root.optString("title").ifBlank { u }, u))
                }
                // A real playlist URL carries list= (or /playlist); a channel never does.
                // Only a genuine playlist becomes an auto-grouped Library playlist.
                val low = url.lowercase()
                val isPlaylist = "list=" in low || "/playlist" in low
                Result.success(Scan(root.optString("title").trim(), isPlaylist, list))
            } catch (e: Exception) {
                Result.failure(e)
            }
        }

    /**
     * Download a whole channel/playlist/profile (yt-dlp iterates it natively, so
     * URL resolution is robust). [limit] caps the count (null = all). Returns how
     * many files landed; each is logged to History.
     */
    suspend fun downloadAll(
        context: Context,
        url: String,
        audio: Boolean,
        quality: String,
        limit: Int?,
        onProgress: (Float, String) -> Unit,
    ): Result<Int> = withContext(Dispatchers.IO) {
        try {
            prepareEngine(context)
            val dir = targetDir(audio)
            val before = dir.listFiles()?.associate { it.name to it.lastModified() } ?: emptyMap()

            val req = YoutubeDLRequest(url)
            req.addOption("--no-mtime")
            req.addOption("--yes-playlist")
            req.addOption("--ignore-errors")   // skip a bad entry, keep going
            if (limit != null && limit > 0) req.addOption("--playlist-end", limit.toString())
            req.addOption("-o", File(dir, "%(title)s.%(ext)s").absolutePath)
            if (audio) {
                req.addOption("-x")
                req.addOption("--audio-format", "mp3")
                req.addOption("--audio-quality", "0")
            } else {
                // Force H.264 (avc1) video + AAC audio, capped at 1080p and 30fps.
                // Phones decode this in hardware smoothly; VP9/AV1, 4K, and 60fps are
                // what overload the decoder so the video stutters / drops frames and
                // "catches up" to the audio. avc1 + ≤1080p + ≤30fps keeps it in sync.
                val sel = when (quality) {
                    "720p" -> "bestvideo[vcodec^=avc1][height<=720][fps<=30]+bestaudio[ext=m4a]/best[ext=mp4][height<=720]/best[height<=720]"
                    "480p" -> "bestvideo[vcodec^=avc1][height<=480][fps<=30]+bestaudio[ext=m4a]/best[ext=mp4][height<=480]/best[height<=480]"
                    else -> "bestvideo[vcodec^=avc1][height<=1080][fps<=30]+bestaudio[ext=m4a]/best[ext=mp4][height<=1080]/bestvideo[ext=mp4]+bestaudio[ext=m4a]/best"
                }
                req.addOption("-f", sel)
                req.addOption("--merge-output-format", "mp4")
            }
            req.addOption("--embed-metadata")
            // Embed the YouTube thumbnail as cover art so the Library/player show
            // a real picture (usually the artist) instead of a placeholder tile.
            req.addOption("--embed-thumbnail")
            // Write the source metadata (artist/track/album/channel/uploader) to a
            // sidecar so we capture the REAL artist instead of guessing it from the
            // filename. We read it after the download, then delete it.
            req.addOption("--write-info-json")

            YoutubeDL.getInstance().execute(req) { p, _, line ->
                onProgress(if (p < 0) 0f else p, line.orEmpty())
            }

            val after = dir.listFiles()?.toList() ?: emptyList()
            val newFiles = after.filter { f ->
                val prev = before[f.name]
                (prev == null || f.lastModified() > prev) && f.extension.lowercase() in MEDIA_EXT
            }
            newFiles.forEach { f ->
                captureArtist(f)
                Storage.scan(context, f)
                History.add(HistoryEntry(
                    f.nameWithoutExtension, url, audio, f.absolutePath, f.length(),
                    System.currentTimeMillis()))
            }
            Storage.scan(context, dir)
            Result.success(newFiles.size)
        } catch (e: Exception) {
            Result.failure(e)
        }
    }
}
