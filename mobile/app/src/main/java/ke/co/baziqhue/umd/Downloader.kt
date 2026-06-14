package ke.co.baziqhue.umd

import android.content.Context
import com.yausername.ffmpeg.FFmpeg
import com.yausername.youtubedl_android.YoutubeDL
import com.yausername.youtubedl_android.YoutubeDLRequest
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import java.io.File

/**
 * Thin wrapper over youtubedl-android (Python + yt-dlp + ffmpeg, bundled for
 * Android). Same engine as the desktop, so behaviour matches. Files are written
 * to the public Downloads tree via [Storage].
 */
object Downloader {

    private val MEDIA_EXT = setOf(
        "mp3", "m4a", "aac", "opus", "ogg", "wav", "flac",
        "mp4", "mkv", "webm", "mov", "avi", "m4v",
    )

    @Volatile private var ready = false

    /** Result of a finished download: the file that landed and where. */
    data class Outcome(val file: File?, val dir: File, val message: String)

    /** Heavy one-time init (unpacks Python). Call off the main thread. */
    suspend fun ensureInit(context: Context) = withContext(Dispatchers.IO) {
        if (ready) return@withContext
        YoutubeDL.getInstance().init(context)
        FFmpeg.getInstance().init(context)
        ready = true
    }

    /** Keep yt-dlp current (sites change often). */
    suspend fun updateEngine(context: Context): String = withContext(Dispatchers.IO) {
        try {
            ensureInit(context)
            YoutubeDL.getInstance().updateYoutubeDL(context)
            "Engine updated."
        } catch (e: Exception) {
            "Update failed: ${e.message}"
        }
    }

    /** Folder a download of this type will land in (public, user-browsable). */
    fun targetDir(audio: Boolean): File = if (audio) Storage.audioDir() else Storage.videoDir()

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
            ensureInit(context)
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

            YoutubeDL.getInstance().execute(req) { progress, _, line ->
                onProgress(if (progress < 0) 0f else progress, line.orEmpty())
            }

            // Identify what actually landed: a new (or freshly rewritten) media
            // file, biggest first (the final merged file dwarfs leftover parts).
            val after = dir.listFiles()?.toList() ?: emptyList()
            val saved = after
                .filter { f ->
                    val prev = before[f.name]
                    (prev == null || f.lastModified() > prev) &&
                        f.extension.lowercase() in MEDIA_EXT
                }
                .maxByOrNull { it.length() }
                ?: after.filter { it.extension.lowercase() in MEDIA_EXT }
                    .maxByOrNull { it.lastModified() }

            saved?.let { Storage.scan(context, it) }
            Storage.scan(context, dir)

            Result.success(Outcome(saved, dir, "Saved to ${Storage.displayPath(dir)}"))
        } catch (e: Exception) {
            Result.failure(e)
        }
    }
}
