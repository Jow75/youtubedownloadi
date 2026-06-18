package ke.co.baziqhue.umd

import android.media.MediaMetadataRetriever
import java.io.File

/**
 * Resolves a track's artist with the priority George asked for:
 *   1. embedded metadata (ARTIST / ALBUMARTIST tag — yt-dlp writes these via
 *      --embed-metadata, sourced from the uploader/channel),
 *   2. filename parsing ("Artist - Title"),
 *   3. "Unknown".
 * (AI classification stays a manual fallback in the Title clean-up tool.)
 *
 * Results are cached per path — MediaMetadataRetriever is slow, so callers should
 * warm the cache off the main thread.
 */
object MediaMeta {

    private val cache = HashMap<String, String>()

    @Synchronized
    fun artist(f: File): String {
        cache[f.absolutePath]?.let { return it }
        val a = readEmbedded(f) ?: filenameArtist(f)
        cache[f.absolutePath] = a
        return a
    }

    private fun readEmbedded(f: File): String? {
        if (!f.exists()) return null
        val r = MediaMetadataRetriever()
        return try {
            r.setDataSource(f.absolutePath)
            val a = (r.extractMetadata(MediaMetadataRetriever.METADATA_KEY_ARTIST)
                ?: r.extractMetadata(MediaMetadataRetriever.METADATA_KEY_ALBUMARTIST))?.trim()
            a?.takeIf { it.isNotBlank() && !it.equals("unknown", true) && !it.equals("various artists", true) }
        } catch (_: Exception) {
            null
        } finally {
            try { r.release() } catch (_: Exception) {}
        }
    }

    private fun filenameArtist(f: File): String {
        val n = f.nameWithoutExtension
        val i = n.indexOf(" - ")
        return if (i > 0) n.substring(0, i).trim().ifBlank { "Unknown" } else "Unknown"
    }
}
