package ke.co.baziqhue.umd

import org.json.JSONObject
import java.io.File

/**
 * The authoritative artist for a downloaded file, captured from the SOURCE metadata
 * at download time (yt-dlp's artist/creator/channel/uploader — which YouTube, TikTok
 * and Instagram all expose) — NOT guessed from the filename. This is the top of the
 * artist hierarchy in [MediaMeta], so the library stops hallucinating artists like
 * "Hook Up Song". Persisted to artist_meta.json in the public AI Library folder, so
 * it survives restarts. Keyed by absolute path.
 */
object ArtistStore {

    private val map = HashMap<String, String>()   // absolutePath -> artist
    private var loaded = false

    private fun file(): File = File(Storage.aiDir(), "artist_meta.json")

    @Synchronized
    fun ensureLoaded() {
        if (loaded) return
        loaded = true
        try {
            val f = file()
            if (f.exists()) {
                val o = JSONObject(f.readText())
                o.keys().forEach { k -> map[k] = o.optString(k) }
            }
        } catch (_: Exception) {
        }
    }

    @Synchronized
    fun get(path: String): String? {
        ensureLoaded()
        return map[path]?.takeIf { it.isNotBlank() }
    }

    @Synchronized
    fun put(path: String, artist: String) {
        ensureLoaded()
        val a = artist.trim()
        if (a.isBlank()) return
        map[path] = a
        save()
    }

    /** Keep the store tidy when a file is renamed (Title clean-up) or removed. */
    @Synchronized
    fun move(oldPath: String, newPath: String) {
        ensureLoaded()
        val a = map.remove(oldPath) ?: return
        map[newPath] = a
        save()
    }

    private fun save() {
        try {
            val o = JSONObject()
            map.forEach { (k, v) -> o.put(k, v) }
            file().writeText(o.toString())
        } catch (_: Exception) {
        }
    }
}
