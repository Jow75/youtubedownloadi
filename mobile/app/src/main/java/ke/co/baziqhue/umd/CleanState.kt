package ke.co.baziqhue.umd

import org.json.JSONObject
import java.io.File

/**
 * Remembers which files the Title clean-up tool has already handled (renamed, or
 * the user chose to skip/ignore), so re-running "Analyze" never keeps suggesting
 * the same files. Keyed by absolute path -> the filename it had when we handled it;
 * if the file's current name still matches, we treat it as done. A later rename or
 * metadata change (which changes the name) makes it eligible again.
 *
 * Persisted to clean_state.json in the public AI Library folder.
 */
object CleanState {
    private val handled = HashMap<String, String>()   // absolutePath -> name when handled
    private var loaded = false

    private fun file(): File = File(Storage.aiDir(), "clean_state.json")

    fun ensureLoaded() {
        if (loaded) return
        loaded = true
        try {
            val f = file()
            if (f.exists()) {
                val o = JSONObject(f.readText())
                o.keys().forEach { k -> handled[k] = o.optString(k) }
            }
        } catch (_: Exception) {
        }
    }

    /** True if we've already cleaned/ignored this file and it hasn't changed since. */
    fun isHandled(f: File): Boolean {
        ensureLoaded()
        return handled[f.absolutePath] == f.name
    }

    /** Record that [f] (at its current name) should not be suggested again. */
    fun mark(f: File) {
        ensureLoaded()
        handled[f.absolutePath] = f.name
        save()
    }

    /** Record a rename: drop the old path, remember the new one as handled. */
    fun markRenamed(old: File, new: File) {
        ensureLoaded()
        handled.remove(old.absolutePath)
        handled[new.absolutePath] = new.name
        save()
    }

    private fun save() {
        try {
            val o = JSONObject()
            handled.forEach { (k, v) -> o.put(k, v) }
            file().writeText(o.toString())
        } catch (_: Exception) {
        }
    }
}
