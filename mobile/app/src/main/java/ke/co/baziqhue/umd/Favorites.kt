package ke.co.baziqhue.umd

import androidx.compose.runtime.mutableStateListOf
import org.json.JSONArray
import java.io.File

/**
 * Favorite tracks — a set of absolute file paths, persisted to favorites.json in
 * the public AI Library folder. Backed by Compose state so the heart toggles live.
 */
object Favorites {

    private val paths = mutableStateListOf<String>()
    private var loaded = false

    private fun file(): File = File(Storage.aiDir(), "favorites.json")

    fun ensureLoaded() {
        if (loaded) return
        loaded = true
        try {
            val f = file()
            if (f.exists()) {
                val arr = JSONArray(f.readText())
                for (i in 0 until arr.length()) paths.add(arr.getString(i))
            }
        } catch (_: Exception) {
        }
    }

    fun isFavorite(path: String): Boolean = path.isNotBlank() && paths.contains(path)

    fun toggle(path: String) {
        if (path.isBlank()) return
        if (!paths.remove(path)) paths.add(path)
        save()
    }

    fun all(): List<String> = paths.toList()

    private fun save() {
        try { file().writeText(JSONArray(paths.toList()).toString()) } catch (_: Exception) {}
    }
}
