package ke.co.baziqhue.umd

import org.json.JSONObject
import java.io.File

/**
 * Persistent download history — an append-only JSONL file in the public
 * `…/Universal Media Downloader/History/` folder. Because it lives in public
 * storage it survives app reinstalls, so it doubles as the desktop's "permanent
 * archive". One JSON object per line: title, url, audio?, path, size, timestamp.
 */
data class HistoryEntry(
    val title: String,
    val url: String,
    val audio: Boolean,
    val path: String,
    val sizeBytes: Long,
    val timestamp: Long,
)

object History {

    private fun file(): File = File(Storage.historyDir(), "history.jsonl")

    fun add(e: HistoryEntry) {
        try {
            val o = JSONObject()
                .put("title", e.title)
                .put("url", e.url)
                .put("audio", e.audio)
                .put("path", e.path)
                .put("size", e.sizeBytes)
                .put("ts", e.timestamp)
            file().appendText(o.toString() + "\n")
        } catch (_: Exception) {
        }
    }

    /** All entries, newest first. */
    fun all(): List<HistoryEntry> {
        val f = file()
        if (!f.exists()) return emptyList()
        return try {
            f.readLines().mapNotNull { line ->
                if (line.isBlank()) return@mapNotNull null
                val o = JSONObject(line)
                HistoryEntry(
                    title = o.optString("title"),
                    url = o.optString("url"),
                    audio = o.optBoolean("audio"),
                    path = o.optString("path"),
                    sizeBytes = o.optLong("size"),
                    timestamp = o.optLong("ts"),
                )
            }.reversed()
        } catch (_: Exception) {
            emptyList()
        }
    }

    /** Remove a single entry (matched by url + timestamp). */
    fun remove(entry: HistoryEntry) {
        val f = file()
        if (!f.exists()) return
        try {
            val kept = f.readLines().filter { line ->
                if (line.isBlank()) return@filter false
                val o = try { JSONObject(line) } catch (_: Exception) { return@filter true }
                !(o.optString("url") == entry.url && o.optLong("ts") == entry.timestamp)
            }
            f.writeText(if (kept.isEmpty()) "" else kept.joinToString("\n") + "\n")
        } catch (_: Exception) {
        }
    }

    fun clear() {
        try { file().writeText("") } catch (_: Exception) {}
    }
}
