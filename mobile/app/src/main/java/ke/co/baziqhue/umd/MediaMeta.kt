package ke.co.baziqhue.umd

import android.media.MediaMetadataRetriever
import java.io.File

/**
 * Resolves a track's artist with the priority George asked for:
 *   1. embedded metadata (ARTIST / ALBUMARTIST tag — yt-dlp writes these via
 *      --embed-metadata, sourced from the uploader/channel),
 *   2. filename parsing ("Artist - Title"),
 *   3. "Unknown".
 * (AI classification stays a manual fallback in the Title clean-up tool.)
 *
 * Results are cached per path — MediaMetadataRetriever is slow, so callers should
 * warm the cache off the main thread.
 */
object MediaMeta {

    private val cache = HashMap<String, String>()
    private val artCache = HashMap<String, ByteArray?>()
    private val artistsCache = HashMap<String, List<String>>()

    // Separators that join collaborating artists. "x" / "and" / "vs" only match as
    // WHOLE words so we never split inside a real name (Maxwell, Sanderson, …).
    private val ARTIST_SPLIT = Regex(
        """(?i)\s*(?:,|;|/|&|＋|\+|×|\bx\b|\bvs\.?\b|\band\b|\bfeat\.?\b|\bft\.?\b|\bfeaturing\b|\bwith\b)\s*"""
    )

    @Synchronized
    fun artist(f: File): String {
        cache[f.absolutePath]?.let { return it }
        // Artist hierarchy (metadata first, guessing last):
        //   1. captured source metadata (yt-dlp artist/creator/channel) — the truth,
        //   2. embedded ID3/media ARTIST tag,
        //   3. "Artist - Title" filename parse,
        //   4. "Unknown".
        // (AI title clean-up is the optional manual backup, not in this path.)
        val raw = ArtistStore.get(f.absolutePath) ?: readEmbedded(f) ?: filenameArtist(f)
        // Canonicalize cross-platform aliases (from the optional "Merge aliases (AI)" tool).
        val a = ArtistAlias.canonical(raw)
        cache[f.absolutePath] = a
        return a
    }

    /**
     * EVERY individual artist a track belongs to. A collaboration attaches to ALL
     * participants — "Diamond Platnumz Ft Mbosso - Kanyaga" shows up under BOTH
     * "Diamond Platnumz" AND "Mbosso", never as a combined "… Ft …" bucket. This is
     * what keeps the Artists view one-artist-per-entry: open any artist and you see
     * every song they're on, solo or featured.
     *
     * Sources, merged: (1) the resolved primary credit (which may itself be a combo
     * like "Mario, The Voice"), and (2) the artist segment of the filename before
     * " - " ("A Ft B - Title"). Each name is canonicalized via [ArtistAlias] so the
     * "Merge aliases (AI)" tool still folds different spellings together.
     */
    @Synchronized
    fun artists(f: File): List<String> {
        artistsCache[f.absolutePath]?.let { return it }
        val out = LinkedHashSet<String>()
        splitArtists(artist(f)).forEach { out.add(it) }
        splitArtists(artistSegment(f.nameWithoutExtension)).forEach { out.add(it) }
        val cleaned = out.asSequence()
            .map { ArtistAlias.canonical(cleanArtist(it)) }
            .filter { it.isNotBlank() && !it.equals("unknown", true) }
            .distinct().toList()
            .ifEmpty { listOf("Unknown") }
        artistsCache[f.absolutePath] = cleaned
        return cleaned
    }

    /** Normalized identity key — collapses case / spacing / punctuation AND accents,
     *  so the same artist written differently maps to one key ("BAD BUNNY" == "Bad
     *  Bunny", and "Beyoncé" == "Beyonce"). NFKD splits an accented letter into base +
     *  combining mark, which we then strip (é → e, ñ → n) before dropping non-alphanumerics. */
    fun artistKey(name: String): String =
        java.text.Normalizer.normalize(name.lowercase(), java.text.Normalizer.Form.NFKD)
            .replace(Regex("\\p{Mn}+"), "")          // fold accents (strip combining marks)
            .replace(Regex("[^a-z0-9]"), "")

    /**
     * Collapse a per-name artist count map so case / spacing / punctuation variants of
     * the SAME artist merge into ONE entry, shown with their best-looking spelling.
     * The automatic "one artist = one artist" fix (no AI needed): "BAD BUNNY" and
     * "Bad Bunny" become a single "Bad Bunny" row with the combined count. Best
     * spelling = most-used, then nicest case (Title over ALL-CAPS / all-lower), then longest.
     */
    fun collapseArtistCounts(counts: Map<String, Int>): List<Pair<String, Int>> {
        val byKey = LinkedHashMap<String, MutableList<Pair<String, Int>>>()
        counts.forEach { (name, c) ->
            val k = artistKey(name)
            if (k.isNotEmpty()) byKey.getOrPut(k) { mutableListOf() }.add(name to c)
        }
        return byKey.values.map { variants ->
            val total = variants.sumOf { it.second }
            val best = variants.maxWith(
                compareBy<Pair<String, Int>> { it.second }
                    .thenBy { caseScore(it.first) }
                    .thenBy { it.first.length }
            ).first
            best to total
        }
    }

    // Nicer-looking spelling scores higher: Mixed/Title > all-lower > ALL CAPS.
    private fun caseScore(s: String): Int = when {
        s == s.uppercase() && s != s.lowercase() -> 0
        s == s.lowercase() -> 1
        else -> 2
    }

    private fun splitArtists(s: String): List<String> =
        if (s.isBlank()) emptyList()
        else s.split(ARTIST_SPLIT).map { it.trim() }.filter { it.isNotBlank() }

    /** The artist portion of a filename: text before the first " - " / " – " / " — ".
     *  No dash → "" (we don't risk parsing a dash-less title into fake artists). */
    private fun artistSegment(name: String): String {
        val dash = Regex("""\s[-–—]\s""").find(name) ?: return ""
        return name.substring(0, dash.range.first)
    }

    /** Tidy one artist name (drop YouTube-isms / stray punctuation). Conservative —
     *  deeper "same artist, different spelling" cases are left to alias-merge. */
    private fun cleanArtist(s: String): String {
        var x = s.trim()
        x = x.replace(Regex("""(?i)\s*-\s*Topic\b"""), "")
        x = x.replace(Regex("""(?i)\bVEVO\b"""), "")
        x = x.replace(Regex("""\s+"""), " ").trim()
        return x.trim('-', '–', '—', ',', '&', '/', '.', ' ').trim()
    }

    /** Drop cached values for a path (e.g. after capturing fresh download metadata). */
    @Synchronized
    fun forget(path: String) { cache.remove(path); artCache.remove(path); artistsCache.remove(path) }

    /** Drop ALL cached artist resolutions (e.g. after an alias merge). */
    @Synchronized
    fun clearAll() { cache.clear(); artistsCache.clear() }

    /**
     * Embedded album art (cover) as raw bytes, or null if the file has none.
     * Cached per path (bounded) — decoding/reading is slow, so warm off the main
     * thread. Powers the artwork thumbnails in the Library and player.
     */
    @Synchronized
    fun artwork(f: File): ByteArray? {
        val key = f.absolutePath
        if (artCache.containsKey(key)) return artCache[key]
        if (artCache.size > 250) artCache.clear()   // keep memory bounded on huge libraries
        val bytes = readArt(f)
        artCache[key] = bytes
        return bytes
    }

    private fun readArt(f: File): ByteArray? {
        if (!f.exists()) return null
        val r = MediaMetadataRetriever()
        return try {
            r.setDataSource(f.absolutePath)
            r.embeddedPicture
        } catch (_: Exception) {
            null
        } finally {
            try { r.release() } catch (_: Exception) {}
        }
    }

    /**
     * The track's real "Artist - Title" rebuilt from its EMBEDDED tags (yt-dlp writes
     * these via --embed-metadata). Powers "Restore names from tags": a filename change
     * never touches the audio/art/tags inside the file, so this recovers the true name
     * with no AI and no re-download — the fix for any earlier bad rename. Returns null
     * if the file has no usable embedded title.
     */
    @Synchronized
    fun embeddedName(f: File): String? {
        if (!f.exists()) return null
        val r = MediaMetadataRetriever()
        return try {
            r.setDataSource(f.absolutePath)
            val title = r.extractMetadata(MediaMetadataRetriever.METADATA_KEY_TITLE)?.trim()
            val artist = (r.extractMetadata(MediaMetadataRetriever.METADATA_KEY_ARTIST)
                ?: r.extractMetadata(MediaMetadataRetriever.METADATA_KEY_ALBUMARTIST))?.trim()
            when {
                title.isNullOrBlank() -> null
                !artist.isNullOrBlank() && !artist.equals("unknown", true)
                    && !title.contains(artist, ignoreCase = true) -> "$artist - $title"
                else -> title
            }
        } catch (_: Exception) {
            null
        } finally {
            try { r.release() } catch (_: Exception) {}
        }
    }

    private fun readEmbedded(f: File): String? {
        if (!f.exists()) return null
        val r = MediaMetadataRetriever()
        return try {
            r.setDataSource(f.absolutePath)
            val a = (r.extractMetadata(MediaMetadataRetriever.METADATA_KEY_ARTIST)
                ?: r.extractMetadata(MediaMetadataRetriever.METADATA_KEY_ALBUMARTIST))?.trim()
            a?.takeIf { it.isNotBlank() && !it.equals("unknown", true) && !it.equals("various artists", true) }
        } catch (_: Exception) {
            null
        } finally {
            try { r.release() } catch (_: Exception) {}
        }
    }

    private fun filenameArtist(f: File): String {
        val n = f.nameWithoutExtension
        // Match "Artist - Title", "Artist – Title" (en dash) or "Artist — Title" (em dash).
        val m = Regex("""^(.{1,60}?)\s[-–—]\s+.+""").find(n) ?: return "Unknown"
        return m.groupValues[1].trim().ifBlank { "Unknown" }
    }
}
