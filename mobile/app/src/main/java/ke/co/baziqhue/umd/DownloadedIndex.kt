package ke.co.baziqhue.umd

import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.setValue
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext

/**
 * A live index of what's already in the local library, by normalized title — so
 * Discover/search cards can show a green "you already have this" tick instead of
 * the download arrow. It's reactive: [refresh] rescans the filesystem (call it when
 * Discover opens / resumes), and [add] marks a freshly-finished download. Deleting a
 * file just drops it on the next refresh, so the tick reverts to a download arrow.
 */
object DownloadedIndex {

    var names by mutableStateOf<Set<String>>(emptySet())
        private set

    private fun norm(s: String): String = s.lowercase().replace(Regex("[^a-z0-9]"), "")

    /** True if a media file whose name matches [title] is in the library. */
    fun has(title: String): Boolean {
        if (title.isBlank()) return false
        val n = norm(title)
        return n.isNotEmpty() && n in names
    }

    /** Mark a just-saved file as present (so the tick appears without a full rescan). */
    fun add(name: String) {
        val n = norm(name)
        if (n.isNotEmpty()) names = names + n
    }

    /** Rescan the library folders. Cheap (just file names). Run off the main thread. */
    suspend fun refresh() {
        names = withContext(Dispatchers.IO) {
            Library.mediaFiles().map { norm(it.nameWithoutExtension) }.filter { it.isNotEmpty() }.toSet()
        }
    }
}
