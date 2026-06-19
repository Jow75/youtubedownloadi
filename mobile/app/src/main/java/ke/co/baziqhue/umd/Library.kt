package ke.co.baziqhue.umd

import java.io.File
import java.security.MessageDigest

/** A group of likely-duplicate files. [reason] explains why (Identical / Same title). */
class DupGroup(val reason: String, val files: List<File>)

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
     * Find likely duplicates in two passes:
     *  1. **Identical** — byte-identical files (same size + same content signature).
     *     Safe to delete extras automatically.
     *  2. **Same title** — different files that are clearly the same song/video
     *     (e.g. an MP3 and an MP4, or a re-download, or a "(1)" copy). These need a
     *     human eye, so they're flagged separately.
     *
     * The earlier version only did pass 1, which is why it reported "no duplicates"
     * even when the library obviously had repeats (same song in two formats, copies
     * with slightly different bytes). Each group's first file is the suggested keeper.
     */
    fun findDuplicates(): List<DupGroup> {
        val files = mediaFiles()
        val out = mutableListOf<DupGroup>()
        val covered = HashSet<String>()   // paths already in an "identical" group

        // Pass 1: byte-identical (cheap size pre-filter, then 1 MB signature).
        files.groupBy { it.length() }
            .filterValues { it.size > 1 }
            .forEach { (_, sameSize) ->
                sameSize.groupBy { signature(it) }
                    .filterValues { it.size > 1 }
                    .forEach { (_, dups) ->
                        val sorted = dups.sortedBy { it.name }
                        sorted.forEach { covered.add(it.absolutePath) }
                        out.add(DupGroup("Identical copy", sorted))
                    }
            }

        // Pass 2: same normalized title (catches different formats / re-downloads).
        files.groupBy { normalizedName(it) }
            .filterValues { it.size > 1 }
            .forEach { (key, sameName) ->
                if (key.isBlank()) return@forEach
                // Don't re-report files we already grouped as identical.
                val rest = sameName.filter { it.absolutePath !in covered }
                if (rest.size > 1) {
                    out.add(DupGroup("Same title", rest.sortedBy { it.name }))
                }
            }

        return out.sortedByDescending { it.files.first().length() }
    }

    /**
     * Normalize a filename so the same song downloaded twice (different format,
     * "(1)" copy, "Official Video" tag, etc.) collapses to one key.
     */
    private fun normalizedName(f: File): String {
        var s = f.nameWithoutExtension.lowercase()
        s = s.replace(Regex("\\(\\s*\\d+\\s*\\)"), " ")                 // (1) (2) copies
        s = s.replace(Regex("\\b(official|video|audio|lyrics?|hd|4k|mv|remastered|copy)\\b"), " ")
        s = s.replace(Regex("[^a-z0-9 ]"), " ")                        // punctuation
        s = s.replace(Regex("\\s+"), " ").trim()
        return s
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
