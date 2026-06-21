package ke.co.baziqhue.umd

import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateListOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.setValue
import org.json.JSONArray
import org.json.JSONObject
import java.io.File

/** A user playlist: a name + an ordered list of absolute file paths. */
class Playlist(val id: String, name: String, paths: List<String> = emptyList()) {
    var name by mutableStateOf(name)
    val paths = mutableStateListOf<String>().also { it.addAll(paths) }
}

/**
 * Playlists, persisted to playlists.json in the public AI Library folder (so they
 * survive reinstalls). Compose-observable so the UI updates live.
 */
object Playlists {

    private val items = mutableStateListOf<Playlist>()
    private var loaded = false
    private fun file(): File = File(Storage.aiDir(), "playlists.json")

    fun ensureLoaded() {
        if (loaded) return
        loaded = true
        try {
            val f = file()
            if (f.exists()) {
                val arr = JSONArray(f.readText())
                for (i in 0 until arr.length()) {
                    val o = arr.optJSONObject(i) ?: continue
                    val pa = o.optJSONArray("paths") ?: JSONArray()
                    val list = ArrayList<String>(pa.length())
                    for (j in 0 until pa.length()) list.add(pa.getString(j))
                    items.add(Playlist(o.optString("id"), o.optString("name", "Playlist"), list))
                }
            }
        } catch (_: Exception) {
        }
    }

    fun all(): List<Playlist> = items
    fun get(id: String): Playlist? = items.firstOrNull { it.id == id }

    fun create(name: String): Playlist {
        val p = Playlist(System.nanoTime().toString(), name.trim().ifBlank { "Playlist" })
        items.add(0, p); save(); return p
    }

    fun rename(id: String, name: String) {
        get(id)?.let { it.name = name.trim().ifBlank { it.name }; save() }
    }

    fun delete(id: String) { items.removeAll { it.id == id }; save() }

    // The AI auto-grouper names its playlists with these emoji prefixes (genre 🎵,
    // language 🗣, the old mood 💫). That's how we tell them from your own playlists
    // and from downloaded-playlist groups (which keep the source's real name).
    private val AUTO_PREFIXES = listOf("🎵 ", "🗣 ", "💫 ")
    fun isAuto(p: Playlist): Boolean = AUTO_PREFIXES.any { p.name.startsWith(it) }

    /** Delete every AI-auto-grouped playlist (keeps your own + downloaded playlists).
     *  Songs are never touched. Returns how many playlists were removed. */
    fun clearAuto(): Int {
        ensureLoaded()
        val gone = items.filter { isAuto(it) }
        items.removeAll(gone); save()
        return gone.size
    }

    fun addPaths(id: String, paths: List<String>) {
        get(id)?.let { pl ->
            paths.forEach { if (it.isNotBlank() && it !in pl.paths) pl.paths.add(it) }
            save()
        }
    }

    fun removePath(id: String, path: String) { get(id)?.let { it.paths.remove(path); save() } }

    /** Add a path to the playlist named [name] (case-insensitive), creating it if it
     *  doesn't exist. Keeps a downloaded playlist grouped together in the Library. */
    fun addToNamed(name: String, path: String) {
        ensureLoaded()
        val pl = all().firstOrNull { it.name.equals(name.trim(), ignoreCase = true) }
            ?: create(name.trim().ifBlank { "Playlist" })
        addPaths(pl.id, listOf(path))
    }

    fun move(id: String, from: Int, to: Int) {
        get(id)?.let { pl ->
            if (from in pl.paths.indices && to in pl.paths.indices) {
                pl.paths.add(to, pl.paths.removeAt(from)); save()
            }
        }
    }

    private fun save() {
        try {
            val arr = JSONArray()
            for (p in items) {
                val o = JSONObject().put("id", p.id).put("name", p.name)
                val pa = JSONArray()
                p.paths.toList().forEach { pa.put(it) }
                o.put("paths", pa)
                arr.put(o)
            }
            file().writeText(arr.toString())
        } catch (_: Exception) {
        }
    }
}
