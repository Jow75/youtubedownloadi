package ke.co.baziqhue.umd

import org.json.JSONObject
import java.io.File

/**
 * Canonical-name mapping for artist aliases — so the SAME artist written differently
 * across platforms ("Diamond Platnumz" on YouTube, "diamondplatnumz" on TikTok,
 * "Diamond Platnumz - Topic", etc.) groups under one name. Built by the optional
 * "Merge aliases (AI)" tool and applied on top of [MediaMeta]'s metadata hierarchy.
 * Persisted to artist_aliases.json. AI is the backup here, not the primary source.
 */
object ArtistAlias {

    private val map = HashMap<String, String>()   // normalized alias -> canonical name
    private var loaded = false

    private fun file(): File = File(Storage.aiDir(), "artist_aliases.json")
    private fun norm(s: String): String = s.lowercase().replace(Regex("[^a-z0-9]"), "")

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

    /** The canonical name for [artist], or [artist] itself if it isn't a known alias. */
    @Synchronized
    fun canonical(artist: String): String {
        if (artist.isBlank()) return artist
        ensureLoaded()
        return map[norm(artist)]?.takeIf { it.isNotBlank() } ?: artist
    }

    /** Store alias→canonical pairs (only the real merges, where they differ). */
    @Synchronized
    fun putAll(pairs: Map<String, String>) {
        ensureLoaded()
        pairs.forEach { (alias, canon) ->
            if (alias.isNotBlank() && canon.isNotBlank() && norm(alias) != norm(canon)) {
                map[norm(alias)] = canon.trim()
            }
        }
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
