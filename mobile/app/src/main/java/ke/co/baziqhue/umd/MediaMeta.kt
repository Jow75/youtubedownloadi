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
    private val artCache = HashMap<String, ByteArray?>()

    @Synchronized
    fun artist(f: File): String {
        cache[f.absolutePath]?.let { return it }
        // Artist hierarchy (metadata first, guessing last):
        //   1. captured source metadata (yt-dlp artist/creator/channel) — the truth,
        //   2. embedded ID3/media ARTIST tag,
        //   3. "Artist - Title" filename parse,
        //   4. "Unknown".
        // (AI title clean-up is the optional manual backup, not in this path.)
        val a = ArtistStore.get(f.absolutePath) ?: readEmbedded(f) ?: filenameArtist(f)
        cache[f.absolutePath] = a
        return a
    }

    /** Drop cached values for a path (e.g. after capturing fresh download metadata). */
    @Synchronized
    fun forget(path: String) { cache.remove(path); artCache.remove(path) }

    /**
     * Embedded album art (cover) as raw bytes, or null if the file has none.
     * Cached per path (bounded) — decoding/reading is slow, so warm off the main
     * thread. Powers the artwork thumbnails in the Library and player.
     */
    @Synchronized
    fun artwork(f: File): ByteArray? {
        val key = f.absolutePath
        if (artCache.containsKey(key)) return artCache[key]
        if (artCache.size > 250) artCache.clear()   // keep memory bounded on huge libraries
        val bytes = readArt(f)
        artCache[key] = bytes
        return bytes
    }

    private fun readArt(f: File): ByteArray? {
        if (!f.exists()) return null
        val r = MediaMetadataRetriever()
        return try {
            r.setDataSource(f.absolutePath)
            r.embeddedPicture
        } catch (_: Exception) {
            null
        } finally {
            try { r.release() } catch (_: Exception) {}
        }
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
        // Match "Artist - Title", "Artist – Title" (en dash) or "Artist — Title" (em dash).
        val m = Regex("""^(.{1,60}?)\s[-–—]\s+.+""").find(n) ?: return "Unknown"
        return m.groupValues[1].trim().ifBlank { "Unknown" }
    }
}
