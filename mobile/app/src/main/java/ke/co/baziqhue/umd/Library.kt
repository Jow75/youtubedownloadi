package ke.co.baziqhue.umd

import java.io.File
import java.security.MessageDigest

/**
 * Local media-library helpers (no API): list downloaded files, find duplicates,
 * rename. Mirrors the desktop library.py duplicate scan, scoped to the public
 * Music/MP3 + Videos/MP4 folders.
 */
object Library {

    private val MEDIA_EXT = setOf(
        "mp3", "m4a", "aac", "opus", "ogg", "wav", "flac",
        "mp4", "mkv", "webm", "mov", "avi", "m4v",
    )

    fun mediaFiles(): List<File> =
        listOf(Storage.audioDir(), Storage.videoDir())
            .flatMap { it.listFiles()?.toList() ?: emptyList() }
            .filter { it.isFile && it.extension.lowercase() in MEDIA_EXT }

    /**
     * Groups of byte-identical files (same size + same content signature).
     * Each returned list has 2+ files; the first is the "keeper".
     */
    fun findDuplicates(): List<List<File>> {
        val groups = mutableListOf<List<File>>()
        // Only files that share a size can be duplicates — cheap pre-filter.
        mediaFiles().groupBy { it.length() }
            .filterValues { it.size > 1 }
            .forEach { (_, sameSize) ->
                sameSize.groupBy { signature(it) }
                    .filterValues { it.size > 1 }
                    .forEach { (_, dups) ->
                        groups.add(dups.sortedBy { it.name })
                    }
            }
        return groups.sortedByDescending { it.first().length() }
    }

    /** SHA-256 of the first 1 MB — fast and effectively collision-free for media. */
    private fun signature(f: File): String = try {
        val md = MessageDigest.getInstance("SHA-256")
        f.inputStream().use { ins ->
            val buf = ByteArray(1 shl 20)
            val n = ins.read(buf)
            if (n > 0) md.update(buf, 0, n)
        }
        md.digest().joinToString("") { "%02x".format(it) }
    } catch (_: Exception) {
        "size:${f.length()}"
    }

    /** Rename a media file in place (keeps its extension). Returns the new file. */
    fun rename(file: File, newBaseName: String): File? {
        val safe = newBaseName.replace(Regex("[\\\\/:*?\"<>|]"), "_").trim().take(120)
        if (safe.isBlank()) return null
        val ext = file.extension
        val target = File(file.parentFile, if (ext.isBlank()) safe else "$safe.$ext")
        if (target.absolutePath == file.absolutePath) return file
        if (target.exists()) return null
        return if (file.renameTo(target)) target else null
    }
}
