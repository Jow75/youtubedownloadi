package ke.co.baziqhue.umd

import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import okhttp3.OkHttpClient
import okhttp3.Request
import org.json.JSONObject
import java.io.File
import java.io.IOException
import java.net.URLEncoder
import java.util.concurrent.TimeUnit

/** One discoverable video from YouTube. */
data class DiscoverItem(
    val videoId: String,
    val title: String,
    val channel: String,
    val thumb: String,
    val durationSec: Int,
) {
    val url get() = "https://www.youtube.com/watch?v=$videoId"
}

/** A channel hit from a Discover search — tap to browse its whole catalogue (yt-dlp). */
data class DiscoverChannel(val channelId: String, val title: String, val thumb: String) {
    val url get() = "https://www.youtube.com/channel/$channelId"
}

/** A playlist hit — tap to open in the Channel tab and bulk-download it (yt-dlp). */
data class DiscoverPlaylist(val playlistId: String, val title: String, val thumb: String) {
    val url get() = "https://www.youtube.com/playlist?list=$playlistId"
}

/** Mixed search results: videos to download + channels & playlists to open & browse. */
data class SearchResults(
    val videos: List<DiscoverItem>,
    val channels: List<DiscoverChannel>,
    val playlists: List<DiscoverPlaylist>,
)

/**
 * YouTube content discovery via the free **Data API v3**. Powers the Discover
 * shelves (Trending in Kenya / Worldwide, Music, Picks-for-you, More-from-artist).
 *
 * The API key is **embedded at build time** (secret.properties → BuildConfig) and is
 * deliberately NOT user-visible or configurable — Discover just works, like a native
 * feature. Responses are cached on disk (trending 6h, the quota-heavy search 24h) so
 * the shared key's daily quota lasts; trending changes slowly so this is plenty fresh.
 */
object Discover {

    private const val BASE = "https://www.googleapis.com/youtube/v3"
    private const val TRENDING_TTL = 6L * 60 * 60 * 1000          // 6h
    private const val SEARCH_TTL = 24L * 60 * 60 * 1000           // 24h (search costs 100 units)

    private val client = OkHttpClient.Builder()
        .connectTimeout(20, TimeUnit.SECONDS)
        .readTimeout(30, TimeUnit.SECONDS)
        .build()

    /**
     * ALL embedded keys, in priority order, for quota failover. A POOL
     * (YOUTUBE_API_KEYS, comma/space separated) is preferred — one key per SEPARATE
     * Google Cloud project adds real capacity (quota is per-project) — and falls back
     * to the single YOUTUBE_API_KEY. De-duped. Not stored in prefs, not shown, not editable.
     */
    @Volatile private var keysCache: List<String>? = null
    fun apiKeys(): List<String> {
        keysCache?.let { return it }
        val pool = BuildConfig.YOUTUBE_API_KEYS.split(Regex("[,\\s]+"))
            .map { it.trim() }.filter { it.isNotBlank() }
        val single = BuildConfig.YOUTUBE_API_KEY.trim()
        val all = (if (pool.isNotEmpty()) pool
                   else if (single.isNotBlank()) listOf(single) else emptyList()).distinct()
        keysCache = all
        return all
    }

    /** The first key (kept for any caller that just needs "a" key). */
    fun apiKey(): String = apiKeys().firstOrNull().orEmpty()
    fun hasKey(): Boolean = apiKeys().isNotEmpty()

    // --- cache ---------------------------------------------------------------- #
    private fun cacheDir(): File = File(Storage.aiDir(), "discover_cache").apply { if (!exists()) mkdirs() }
    private fun cacheFile(k: String) = File(cacheDir(), k.replace(Regex("[^a-zA-Z0-9]"), "_") + ".json")

    /** Cached body if present and within [ttlMs]; [ignoreTtl] returns even stale cache. */
    private fun readCache(k: String, ttlMs: Long, ignoreTtl: Boolean): String? {
        val f = cacheFile(k)
        if (!f.exists()) return null
        return try {
            val o = JSONObject(f.readText())
            if (ignoreTtl || System.currentTimeMillis() - o.optLong("ts") < ttlMs)
                o.optString("body") else null
        } catch (_: Exception) { null }
    }

    private fun writeCache(k: String, body: String) {
        try {
            cacheFile(k).writeText(JSONObject().put("ts", System.currentTimeMillis()).put("body", body).toString())
        } catch (_: Exception) {}
    }

    /** A 4xx the caller shouldn't retry (bad request / forbidden). */
    private open class PermanentHttp(message: String) : IOException(message)
    /** 403 daily-limit on THIS key — the caller rotates to the next key in the pool. */
    private class QuotaExceeded(message: String) : PermanentHttp(message)

    @Volatile private var rr = 0   // round-robin cursor — spreads load across projects

    /**
     * GET with key rotation + transient retry. Each call starts at a different key
     * (round-robin) so multiple projects share the traffic; on a 403 (daily quota)
     * it falls over to the next key, so one exhausted project never breaks Discover.
     * [url] must NOT already contain a key= param — this appends it per attempt, so
     * the on-disk cache key (which never includes the key) stays stable across keys.
     * With a single key this behaves exactly as before.
     */
    private fun httpGet(url: String): String {
        val keys = apiKeys().ifEmpty { listOf("") }
        val n = keys.size
        rr = (rr + 1) % n
        var last: Exception? = null
        for (i in 0 until n) {
            val key = keys[(rr + i) % n]
            try {
                return httpGetOnce(if (key.isBlank()) url else "$url&key=$key")
            } catch (e: QuotaExceeded) {
                last = e                                      // this key is spent → try next
            }
        }
        throw last ?: QuotaExceeded("YouTube daily limit reached on all keys.")
    }

    /**
     * One key's request, with automatic retry for *transient* failures (no network
     * yet, DNS not resolved, timeouts, 5xx, rate-limit). This kills the old "search
     * shows an error, toggle a filter and suddenly it works" flakiness. A 403 becomes
     * [QuotaExceeded] so the caller rotates keys; other permanent 4xx fail fast.
     */
    private fun httpGetOnce(url: String): String {
        var last: Exception? = null
        for (attempt in 0 until 3) {
            try {
                val req = Request.Builder().url(url).get().build()
                client.newCall(req).execute().use { resp ->
                    val body = resp.body?.string().orEmpty()
                    if (resp.isSuccessful) return body
                    val msg = parseErr(body, resp.code)
                    if (resp.code == 403) throw QuotaExceeded(msg)       // spent key → rotate
                    if (resp.code in 400..499 && resp.code != 408 && resp.code != 429)
                        throw PermanentHttp(msg)              // permanent → don't retry
                    last = IOException(msg)                   // 5xx / 408 / 429 → retry
                }
            } catch (e: PermanentHttp) {
                throw e
            } catch (e: IOException) {
                last = e                                      // connection-level failure → retry
            }
            if (attempt < 2) try { Thread.sleep(500L * (attempt + 1)) } catch (_: InterruptedException) {}
        }
        throw last ?: IOException("Couldn't reach YouTube.")
    }

    private fun parseErr(body: String, code: Int): String = try {
        if (code == 403) "YouTube daily limit reached — try again later."
        else JSONObject(body).optJSONObject("error")?.optString("message").orEmpty()
            .ifBlank { "Couldn't reach YouTube (HTTP $code)." }
    } catch (_: Exception) { "Couldn't reach YouTube (HTTP $code)." }

    /** Cache (fresh) or network; on failure fall back to stale cache. */
    private fun cachedFetch(cacheKey: String, url: String, ttlMs: Long): String {
        readCache(cacheKey, ttlMs, ignoreTtl = false)?.let { return it }
        return try {
            httpGet(url).also { writeCache(cacheKey, it) }
        } catch (e: Exception) {
            readCache(cacheKey, ttlMs, ignoreTtl = true) ?: throw e
        }
    }

    /** Most-popular videos for a region (1 quota unit). [categoryId] "10" = Music. */
    suspend fun trending(regionCode: String, categoryId: String? = null): Result<List<DiscoverItem>> =
        withContext(Dispatchers.IO) {
            if (!hasKey()) return@withContext Result.failure(IOException("Discover is unavailable."))
            try {
                val cat = if (categoryId != null) "&videoCategoryId=$categoryId" else ""
                val url = "$BASE/videos?part=snippet,contentDetails&chart=mostPopular&maxResults=20" +
                    "&regionCode=$regionCode$cat"
                Result.success(parseVideos(cachedFetch("trending_${regionCode}_${categoryId ?: "all"}", url, TRENDING_TTL)))
            } catch (e: Exception) {
                Result.failure(e)
            }
        }

    /** Search videos by name (100 quota units — cached 24h). [order] = date | relevance. */
    suspend fun search(query: String, order: String = "date"): Result<List<DiscoverItem>> =
        withContext(Dispatchers.IO) {
            if (!hasKey()) return@withContext Result.failure(IOException("Discover is unavailable."))
            if (query.isBlank()) return@withContext Result.success(emptyList())
            try {
                val q = URLEncoder.encode(query, "UTF-8")
                val url = "$BASE/search?part=snippet&type=video&order=$order&maxResults=20&q=$q"
                Result.success(parseSearch(cachedFetch("search_${order}_$query", url, SEARCH_TTL)))
            } catch (e: Exception) {
                Result.failure(e)
            }
        }

    /**
     * Mixed keyword search (videos + channels in ONE call — 100 units, cached 24h).
     * Lets Discover act as a download-first "mini YouTube": find a video to grab, or
     * a channel to open and browse its full catalogue via the existing Channel tab.
     */
    suspend fun searchMixed(query: String, order: String = "relevance"): Result<SearchResults> =
        withContext(Dispatchers.IO) {
            if (!hasKey()) return@withContext Result.failure(IOException("Discover is unavailable."))
            if (query.isBlank()) return@withContext Result.success(SearchResults(emptyList(), emptyList(), emptyList()))
            try {
                val q = URLEncoder.encode(query, "UTF-8")
                // No `type` → YouTube returns a mix of videos / channels / playlists.
                val url = "$BASE/search?part=snippet&maxResults=25&order=$order&q=$q"
                Result.success(parseMixed(cachedFetch("searchmix_${order}_$query", url, SEARCH_TTL)))
            } catch (e: Exception) {
                Result.failure(e)
            }
        }

    /** Latest uploads from a channel (2 quota units, cached 6h) — for "New from <artist>". */
    suspend fun latestUploads(channelId: String): Result<List<DiscoverItem>> =
        withContext(Dispatchers.IO) {
            if (!hasKey()) return@withContext Result.failure(IOException("Discover is unavailable."))
            try {
                val chUrl = "$BASE/channels?part=contentDetails&id=$channelId"
                val uploads = JSONObject(cachedFetch("chmeta_$channelId", chUrl, TRENDING_TTL))
                    .optJSONArray("items")?.optJSONObject(0)
                    ?.optJSONObject("contentDetails")?.optJSONObject("relatedPlaylists")
                    ?.optString("uploads").orEmpty()
                if (uploads.isBlank()) return@withContext Result.success(emptyList())
                val plUrl = "$BASE/playlistItems?part=snippet&maxResults=12&playlistId=$uploads"
                Result.success(parsePlaylistItems(cachedFetch("uploads_$channelId", plUrl, TRENDING_TTL)))
            } catch (e: Exception) {
                Result.failure(e)
            }
        }

    private fun parseMixed(body: String): SearchResults {
        val arr = JSONObject(body).optJSONArray("items")
            ?: return SearchResults(emptyList(), emptyList(), emptyList())
        val vids = ArrayList<DiscoverItem>()
        val chans = ArrayList<DiscoverChannel>()
        val plays = ArrayList<DiscoverPlaylist>()
        for (i in 0 until arr.length()) {
            val it = arr.optJSONObject(i) ?: continue
            val idObj = it.optJSONObject("id") ?: continue
            val kind = idObj.optString("kind")
            val sn = it.optJSONObject("snippet") ?: continue
            val thumb = thumbUrl(sn.optJSONObject("thumbnails"))
            when {
                kind.endsWith("video") -> idObj.optString("videoId").takeIf { it.isNotBlank() }?.let {
                    vids.add(DiscoverItem(it, sn.optString("title"), sn.optString("channelTitle"), thumb, 0))
                }
                kind.endsWith("channel") -> idObj.optString("channelId").takeIf { it.isNotBlank() }?.let {
                    chans.add(DiscoverChannel(it, sn.optString("title"), thumb))
                }
                kind.endsWith("playlist") -> idObj.optString("playlistId").takeIf { it.isNotBlank() }?.let {
                    plays.add(DiscoverPlaylist(it, sn.optString("title"), thumb))
                }
            }
        }
        return SearchResults(vids, chans, plays)
    }

    private fun parsePlaylistItems(body: String): List<DiscoverItem> {
        val arr = JSONObject(body).optJSONArray("items") ?: return emptyList()
        val out = ArrayList<DiscoverItem>(arr.length())
        for (i in 0 until arr.length()) {
            val sn = arr.optJSONObject(i)?.optJSONObject("snippet") ?: continue
            val vid = sn.optJSONObject("resourceId")?.optString("videoId").orEmpty()
            if (vid.isBlank()) continue
            out.add(DiscoverItem(vid, sn.optString("title"), sn.optString("videoOwnerChannelTitle")
                .ifBlank { sn.optString("channelTitle") }, thumbUrl(sn.optJSONObject("thumbnails")), 0))
        }
        return out
    }

    // --- parsing -------------------------------------------------------------- #
    private fun thumbUrl(thumbs: JSONObject?): String {
        if (thumbs == null) return ""
        for (k in listOf("high", "medium", "default")) {
            thumbs.optJSONObject(k)?.optString("url")?.takeIf { it.isNotBlank() }?.let { return it }
        }
        return ""
    }

    private fun parseVideos(body: String): List<DiscoverItem> {
        val arr = JSONObject(body).optJSONArray("items") ?: return emptyList()
        val out = ArrayList<DiscoverItem>(arr.length())
        for (i in 0 until arr.length()) {
            val it = arr.optJSONObject(i) ?: continue
            val id = it.optString("id")
            val sn = it.optJSONObject("snippet") ?: continue
            if (id.isBlank()) continue
            out.add(DiscoverItem(
                id, sn.optString("title"), sn.optString("channelTitle"),
                thumbUrl(sn.optJSONObject("thumbnails")),
                parseDuration(it.optJSONObject("contentDetails")?.optString("duration"))))
        }
        return out
    }

    private fun parseSearch(body: String): List<DiscoverItem> {
        val arr = JSONObject(body).optJSONArray("items") ?: return emptyList()
        val out = ArrayList<DiscoverItem>(arr.length())
        for (i in 0 until arr.length()) {
            val it = arr.optJSONObject(i) ?: continue
            val id = it.optJSONObject("id")?.optString("videoId").orEmpty()
            val sn = it.optJSONObject("snippet") ?: continue
            if (id.isBlank()) continue
            out.add(DiscoverItem(
                id, sn.optString("title"), sn.optString("channelTitle"),
                thumbUrl(sn.optJSONObject("thumbnails")), 0))
        }
        return out
    }

    /** ISO-8601 duration ("PT3M16S") -> seconds. */
    private fun parseDuration(iso: String?): Int {
        if (iso.isNullOrBlank()) return 0
        val m = Regex("PT(?:(\\d+)H)?(?:(\\d+)M)?(?:(\\d+)S)?").find(iso) ?: return 0
        val h = m.groupValues[1].toIntOrNull() ?: 0
        val mn = m.groupValues[2].toIntOrNull() ?: 0
        val s = m.groupValues[3].toIntOrNull() ?: 0
        return h * 3600 + mn * 60 + s
    }
}
