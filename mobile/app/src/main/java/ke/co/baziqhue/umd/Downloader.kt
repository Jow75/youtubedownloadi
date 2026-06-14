package ke.co.baziqhue.umd

import android.content.Context
import android.os.Environment
import com.yausername.ffmpeg.FFmpeg
import com.yausername.youtubedl_android.YoutubeDL
import com.yausername.youtubedl_android.YoutubeDLRequest
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import java.io.File

/**
 * Thin wrapper over youtubedl-android (Python + yt-dlp + ffmpeg, bundled for
 * Android). Same engine as the desktop, so behaviour matches.
 */
object Downloader {

    @Volatile private var ready = false

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

    private fun outDir(context: Context): File {
        // App-specific external dir — no storage permission needed, works on all
        // Android versions. (Follow-up: publish to the public Music/Movies folder
        // via MediaStore so files show in the system Files app.)
        val dir = File(
            context.getExternalFilesDir(Environment.DIRECTORY_MUSIC),
            "UniversalMediaDownloader"
        )
        if (!dir.exists()) dir.mkdirs()
        return dir
    }

    fun outputFolder(context: Context): String = outDir(context).absolutePath

    /**
     * Download [url] as audio (mp3) or video (mp4). [onProgress] gets 0..100.
     * Returns the result message. Run from a coroutine (it blocks).
     */
    suspend fun download(
        context: Context,
        url: String,
        audio: Boolean,
        quality: String,
        onProgress: (Float, String) -> Unit,
    ): Result<String> = withContext(Dispatchers.IO) {
        try {
            ensureInit(context)
            val req = YoutubeDLRequest(url)
            req.addOption("--no-mtime")
            req.addOption("-o", File(outDir(context), "%(title)s.%(ext)s").absolutePath)
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
                onProgress(if (progress < 0) 0f else progress, line ?: "")
            }
            Result.success("Saved to ${outDir(context).name}/")
        } catch (e: Exception) {
            Result.failure(e)
        }
    }
}
