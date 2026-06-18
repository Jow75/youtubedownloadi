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
                val sel = when (quality) {
                    "720p" -> "bestvideo[height<=720]+bestaudio/best[height<=720]/best"
                    "480p" -> "bestvideo[height<=480]+bestaudio/best[height<=480]/best"
                    else -> "bestvideo+bestaudio/best"
                }
                req.addOption("-f", sel)
                req.addOption("--merge-output-format", "mp4")
            }
            req.addOption("--embed-metadata")

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
            Storage.scan(context, saved)
            Storage.scan(context, dir)
            Result.success(Outcome(saved, dir, "Saved to ${Storage.displayPath(dir)}"))
        } catch (e: Exception) {
            Result.failure(e)
        }
    }

    /** One item in a channel/playlist/profile. */
    data class Entry(val title: String, val url: String)

    /**
     * List everything in a channel / playlist / profile URL without downloading
     * (flat extraction — fast). Returns the items so the user can preview them.
     */
    suspend fun scanEntries(context: Context, url: String): Result<List<Entry>> =
        withContext(Dispatchers.IO) {
            try {
                ensureInit(context)
                val req = YoutubeDLRequest(url)
                req.addOption("--flat-playlist")
                req.addOption("--dump-single-json")
                req.addOption("--no-warnings")
                val resp = YoutubeDL.getInstance().execute(req)
                val root = JSONObject(resp.out)
                val arr = root.optJSONArray("entries")
                val list = ArrayList<Entry>()
                if (arr != null) {
                    for (i in 0 until arr.length()) {
                        val e = arr.optJSONObject(i) ?: continue
                        val u = e.optString("url").ifBlank {
                            e.optString("webpage_url").ifBlank { e.optString("id") }
                        }
                        if (u.isNotBlank()) list.add(Entry(e.optString("title").ifBlank { u }, u))
                    }
                } else {
                    val u = root.optString("webpage_url").ifBlank { url }
                    list.add(Entry(root.optString("title").ifBlank { u }, u))
                }
                Result.success(list)
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
                val sel = when (quality) {
                    "720p" -> "bestvideo[height<=720]+bestaudio/best[height<=720]/best"
                    "480p" -> "bestvideo[height<=480]+bestaudio/best[height<=480]/best"
                    else -> "bestvideo+bestaudio/best"
                }
                req.addOption("-f", sel)
                req.addOption("--merge-output-format", "mp4")
            }
            req.addOption("--embed-metadata")

            YoutubeDL.getInstance().execute(req) { p, _, line ->
                onProgress(if (p < 0) 0f else p, line.orEmpty())
            }

            val after = dir.listFiles()?.toList() ?: emptyList()
            val newFiles = after.filter { f ->
                val prev = before[f.name]
                (prev == null || f.lastModified() > prev) && f.extension.lowercase() in MEDIA_EXT
            }
            newFiles.forEach { f ->
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
