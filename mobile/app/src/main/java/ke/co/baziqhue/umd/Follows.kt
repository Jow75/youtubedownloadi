package ke.co.baziqhue.umd

import androidx.compose.runtime.mutableStateListOf
import org.json.JSONArray
import org.json.JSONObject
import java.io.File

/** A YouTube channel the user follows, to see (and grab) their new uploads. */
class FollowedChannel(val channelId: String, val title: String, val thumb: String) {
    val url get() = "https://www.youtube.com/channel/$channelId"
}

/**
 * Channels the user follows in Discover. Persisted to follows.json. Discover shows a
 * "New from <artist>" shelf for each, built from the channel's uploads (cheap — 2
 * quota units, cached). Backed by Compose state so the ⭐ toggles live.
 */
object Follows {

    private val list = mutableStateListOf<FollowedChannel>()
    private val seen = HashMap<String, String>()   // channelId -> last-seen videoId
    private var loaded = false
    private fun file(): File = File(Storage.aiDir(), "follows.json")
    private fun seenFile(): File = File(Storage.aiDir(), "follow_seen.json")

    fun ensureLoaded() {
        if (loaded) return
        loaded = true
        try {
            val f = file()
            if (f.exists()) {
                val a = JSONArray(f.readText())
                for (i in 0 until a.length()) {
                    val o = a.optJSONObject(i) ?: continue
                    list.add(FollowedChannel(o.optString("id"), o.optString("title"), o.optString("thumb")))
                }
            }
            val sf = seenFile()
            if (sf.exists()) {
                val o = JSONObject(sf.readText())
                o.keys().forEach { k -> seen[k] = o.optString(k) }
            }
        } catch (_: Exception) {
        }
    }

    /** The newest upload videoId we've already seen for a channel (for new-upload alerts). */
    fun lastSeen(channelId: String): String? { ensureLoaded(); return seen[channelId] }

    fun setLastSeen(channelId: String, videoId: String) {
        ensureLoaded()
        seen[channelId] = videoId
        try {
            val o = JSONObject()
            seen.forEach { (k, v) -> o.put(k, v) }
            seenFile().writeText(o.toString())
        } catch (_: Exception) {
        }
    }

    fun all(): List<FollowedChannel> = list.toList()
    fun isFollowed(channelId: String): Boolean = list.any { it.channelId == channelId }

    fun toggle(ch: FollowedChannel) {
        ensureLoaded()
        if (!list.removeAll { it.channelId == ch.channelId }) list.add(ch)
        save()
    }

    private fun save() {
        try {
            val a = JSONArray()
            list.forEach { a.put(JSONObject().put("id", it.channelId).put("title", it.title).put("thumb", it.thumb)) }
            file().writeText(a.toString())
        } catch (_: Exception) {
        }
    }
}
