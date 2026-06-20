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

    /** The embedded key. Not stored in prefs, not shown, not editable. */
    fun apiKey(): String = BuildConfig.YOUTUBE_API_KEY.trim()
    fun hasKey(): Boolean = apiKey().isNotBlank()

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

    private fun httpGet(url: String): String {
        val req = Request.Builder().url(url).get().build()
        client.newCall(req).execute().use { resp ->
            val body = resp.body?.string().orEmpty()
            if (!resp.isSuccessful) throw IOException(parseErr(body, resp.code))
            return body
        }
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
            val key = apiKey()
            if (key.isBlank()) return@withContext Result.failure(IOException("Discover is unavailable."))
            try {
                val cat = if (categoryId != null) "&videoCategoryId=$categoryId" else ""
                val url = "$BASE/videos?part=snippet,contentDetails&chart=mostPopular&maxResults=20" +
                    "&regionCode=$regionCode$cat&key=$key"
                Result.success(parseVideos(cachedFetch("trending_${regionCode}_${categoryId ?: "all"}", url, TRENDING_TTL)))
            } catch (e: Exception) {
                Result.failure(e)
            }
        }

    /** Search videos by name (100 quota units — cached 24h). [order] = date | relevance. */
    suspend fun search(query: String, order: String = "date"): Result<List<DiscoverItem>> =
        withContext(Dispatchers.IO) {
            val key = apiKey()
            if (key.isBlank()) return@withContext Result.failure(IOException("Discover is unavailable."))
            if (query.isBlank()) return@withContext Result.success(emptyList())
            try {
                val q = URLEncoder.encode(query, "UTF-8")
                val url = "$BASE/search?part=snippet&type=video&order=$order&maxResults=20&q=$q&key=$key"
                Result.success(parseSearch(cachedFetch("search_${order}_$query", url, SEARCH_TTL)))
            } catch (e: Exception) {
                Result.failure(e)
            }
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
