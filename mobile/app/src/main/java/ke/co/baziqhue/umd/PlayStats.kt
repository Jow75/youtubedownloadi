package ke.co.baziqhue.umd

import androidx.compose.runtime.mutableStateMapOf
import org.json.JSONObject
import java.io.File

/**
 * Per-track play counts + last-played time (keyed by absolute path), for the
 * "Recently played" and "Most played" sort modes. Persisted to playstats.json.
 */
object PlayStats {

    private val plays = mutableStateMapOf<String, Int>()
    private val last = mutableStateMapOf<String, Long>()
    private var loaded = false
    private fun file(): File = File(Storage.aiDir(), "playstats.json")

    fun ensureLoaded() {
        if (loaded) return
        loaded = true
        try {
            val f = file()
            if (f.exists()) {
                val o = JSONObject(f.readText())
                o.optJSONObject("plays")?.let { pj -> pj.keys().forEach { plays[it] = pj.optInt(it) } }
                o.optJSONObject("last")?.let { lj -> lj.keys().forEach { last[it] = lj.optLong(it) } }
            }
        } catch (_: Exception) {
        }
    }

    fun record(path: String) {
        if (path.isBlank()) return
        ensureLoaded()
        plays[path] = (plays[path] ?: 0) + 1
        last[path] = System.currentTimeMillis()
        save()
    }

    fun count(path: String): Int = plays[path] ?: 0
    fun lastPlayed(path: String): Long = last[path] ?: 0L

    private fun save() {
        try {
            val pj = JSONObject(); for ((k, v) in plays) pj.put(k, v)
            val lj = JSONObject(); for ((k, v) in last) lj.put(k, v)
            file().writeText(JSONObject().put("plays", pj).put("last", lj).toString())
        } catch (_: Exception) {
        }
    }
}
