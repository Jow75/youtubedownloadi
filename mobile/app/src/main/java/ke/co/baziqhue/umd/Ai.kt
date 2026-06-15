package ke.co.baziqhue.umd

import android.content.Context
import android.content.SharedPreferences
import androidx.security.crypto.EncryptedSharedPreferences
import androidx.security.crypto.MasterKey
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.RequestBody.Companion.toRequestBody
import org.json.JSONArray
import org.json.JSONObject
import java.io.IOException
import java.util.concurrent.TimeUnit

/**
 * AI layer — a faithful port of the desktop ai.py (NVIDIA, OpenAI-compatible).
 * Bring-your-own-key: the user pastes their NVIDIA key once; it's stored
 * encrypted (Android Keystore) and only TEXT (errors / titles / prompts) is sent.
 *
 * Networking uses OkHttp, not HttpURLConnection — the latter reuses pooled
 * connections that NVIDIA may have closed, which manifested as POSTs hanging
 * until timeout ("Sorry — timeout") even though the key validated fine.
 */
object Ai {
    private const val BASE_URL = "https://integrate.api.nvidia.com/v1"
    private const val CHAT_MODEL = "meta/llama-3.3-70b-instruct"
    private const val EMBED_MODEL = "nvidia/nv-embedqa-e5-v5"
    const val KEY_PREFIX = "nvapi-"
    const val GET_KEY_URL = "https://build.nvidia.com/"

    private val JSON = "application/json; charset=utf-8".toMediaType()

    private val http: OkHttpClient by lazy {
        OkHttpClient.Builder()
            .connectTimeout(30, TimeUnit.SECONDS)
            .readTimeout(90, TimeUnit.SECONDS)
            .writeTimeout(30, TimeUnit.SECONDS)
            .callTimeout(120, TimeUnit.SECONDS)
            .retryOnConnectionFailure(true)
            .build()
    }

    // ---- key storage (encrypted, with a graceful fallback) ----------------- #
    @Volatile private var cachedPrefs: SharedPreferences? = null

    private fun prefs(ctx: Context): SharedPreferences {
        cachedPrefs?.let { return it }
        val p = try {
            val master = MasterKey.Builder(ctx.applicationContext)
                .setKeyScheme(MasterKey.KeyScheme.AES256_GCM)
                .build()
            EncryptedSharedPreferences.create(
                ctx.applicationContext, "umd_ai_secure", master,
                EncryptedSharedPreferences.PrefKeyEncryptionScheme.AES256_SIV,
                EncryptedSharedPreferences.PrefValueEncryptionScheme.AES256_GCM,
            )
        } catch (e: Exception) {
            ctx.applicationContext.getSharedPreferences("umd_ai_plain", Context.MODE_PRIVATE)
        }
        cachedPrefs = p
        return p
    }

    fun storedKey(ctx: Context): String = prefs(ctx).getString("key", "").orEmpty()
    fun saveKey(ctx: Context, key: String) = prefs(ctx).edit().putString("key", key.trim()).apply()
    fun clearKey(ctx: Context) = prefs(ctx).edit().remove("key").apply()
    fun isConfigured(ctx: Context): Boolean = storedKey(ctx).isNotBlank()

    fun maskedKey(ctx: Context): String {
        val k = storedKey(ctx)
        return when {
            k.isBlank() -> ""
            k.length > 12 -> k.take(6) + "•".repeat(8) + k.takeLast(4)
            else -> "•".repeat(k.length)
        }
    }

    // ---- HTTP helpers ------------------------------------------------------ #
    private fun postJson(path: String, key: String, payload: String): String {
        val req = Request.Builder()
            .url("$BASE_URL$path")
            .addHeader("Authorization", "Bearer $key")
            .post(payload.toRequestBody(JSON))
            .build()
        http.newCall(req).execute().use { resp ->
            val text = resp.body?.string().orEmpty()
            if (!resp.isSuccessful) throw IOException("AI service error (HTTP ${resp.code}).")
            return text
        }
    }

    /** Check a key by listing models (cheap, like the desktop validate_key). */
    suspend fun validateKey(key: String): Result<Unit> = withContext(Dispatchers.IO) {
        try {
            val req = Request.Builder()
                .url("$BASE_URL/models")
                .addHeader("Authorization", "Bearer ${key.trim()}")
                .get().build()
            http.newCall(req).execute().use { resp ->
                if (resp.isSuccessful) Result.success(Unit)
                else Result.failure(IOException("Key rejected (HTTP ${resp.code})."))
            }
        } catch (e: Exception) {
            Result.failure(IOException("Couldn't reach NVIDIA: ${e.message}"))
        }
    }

    private fun chat(key: String, prompt: String, maxTokens: Int): String {
        val payload = JSONObject()
            .put("model", CHAT_MODEL)
            .put("messages", JSONArray().put(
                JSONObject().put("role", "user").put("content", prompt)))
            .put("temperature", 0.1)
            .put("max_tokens", maxTokens)
            .toString()
        val text = postJson("/chat/completions", key, payload)
        return JSONObject(text)
            .getJSONArray("choices").getJSONObject(0)
            .getJSONObject("message").getString("content").trim()
    }

    /** Plain-language "why it failed + how to fix" — same prompt as desktop. */
    suspend fun explainError(ctx: Context, title: String, error: String): Result<String> =
        withContext(Dispatchers.IO) {
            val key = storedKey(ctx)
            if (key.isBlank()) return@withContext Result.failure(IOException("No AI key configured."))
            val prompt =
                "A media download failed in a yt-dlp-based app. In 2-4 short sentences, " +
                "explain the most likely REASON in plain language and the best practical " +
                "FIX. Consider: private/removed/region-locked video, login cookies " +
                "needed, rate-limiting (try again later), try M4A instead of MP3, " +
                "geo-block, age-restriction, or a bad link. Be specific.\n\n" +
                "Title: $title\nError: $error"
            try {
                Result.success(chat(key, prompt, maxTokens = 300))
            } catch (e: Exception) {
                Result.failure(e)
            }
        }

    // ---- embeddings (semantic search) -------------------------------------- #
    /** Embed each text (NVIDIA NeMo retriever). inputType: "passage" | "query". */
    suspend fun embed(ctx: Context, texts: List<String>, inputType: String): Result<List<FloatArray>> =
        withContext(Dispatchers.IO) {
            val key = storedKey(ctx)
            if (key.isBlank()) return@withContext Result.failure(IOException("No AI key configured."))
            try {
                val payload = JSONObject()
                    .put("model", EMBED_MODEL)
                    .put("input", JSONArray(texts))
                    .put("encoding_format", "float")
                    .put("input_type", inputType)
                    .toString()
                val body = postJson("/embeddings", key, payload)
                val data = JSONObject(body).getJSONArray("data")
                val out = ArrayList<FloatArray>(data.length())
                for (i in 0 until data.length()) {
                    val arr = data.getJSONObject(i).getJSONArray("embedding")
                    out.add(FloatArray(arr.length()) { arr.getDouble(it).toFloat() })
                }
                Result.success(out)
            } catch (e: Exception) {
                Result.failure(e)
            }
        }

    // ---- title clean-up (smart library) ------------------------------------ #
    val CATEGORIES = listOf(
        "Music", "Live Performance", "Interview", "Vlog", "Behind The Scenes",
        "Podcast", "News", "Comedy", "Sports", "Gaming", "Tutorial", "Trailer",
        "Audiobook", "Other",
    )

    data class TitleInfo(
        val artist: String?,
        val cleanTitle: String,
        val category: String,
        val official: Boolean?,
    )

    /** Clean up messy download titles -> {original: TitleInfo}. Same as desktop. */
    suspend fun analyzeTitles(ctx: Context, titles: List<String>): Result<Map<String, TitleInfo>> =
        withContext(Dispatchers.IO) {
            val key = storedKey(ctx)
            if (key.isBlank()) return@withContext Result.failure(IOException("No AI key configured."))
            val uniq = titles.filter { it.isNotBlank() }.distinct().take(40)
            if (uniq.isEmpty()) return@withContext Result.success(emptyMap())
            val prompt =
                "You clean up media download titles for a library. For EACH title " +
                "return one JSON object, in the SAME ORDER, with fields: " +
                "artist (performer/channel as a string, or null), " +
                "clean_title (the work's name without 'Official Video', tags, etc.), " +
                "category (exactly one of $CATEGORIES), " +
                "is_official (true if it looks like an official release, else false). " +
                "Return ONLY a JSON array, nothing else.\n\nTitles:\n" +
                uniq.mapIndexed { i, t -> "${i + 1}. $t" }.joinToString("\n")
            try {
                val arr = extractJsonArray(chat(key, prompt, maxTokens = 1600))
                    ?: return@withContext Result.failure(IOException("AI returned an unexpected response."))
                val map = LinkedHashMap<String, TitleInfo>()
                for (i in uniq.indices) {
                    val o = arr.optJSONObject(i) ?: continue
                    val cat = o.optString("category")
                    map[uniq[i]] = TitleInfo(
                        artist = o.optString("artist").ifBlank { null }
                            ?.takeUnless { it.equals("null", true) },
                        cleanTitle = o.optString("clean_title").ifBlank { uniq[i] },
                        category = if (cat in CATEGORIES) cat else "Other",
                        official = if (o.has("is_official")) o.optBoolean("is_official") else null,
                    )
                }
                Result.success(map)
            } catch (e: Exception) {
                Result.failure(e)
            }
        }

    /** Pull a JSON array out of a model reply (handles ```json fences / extra text). */
    private fun extractJsonArray(text: String): JSONArray? {
        val fenced = Regex("```(?:json)?\\s*(.*?)```", RegexOption.DOT_MATCHES_ALL)
            .find(text)?.groupValues?.get(1)
        val raw = (fenced ?: text).trim()
        runCatching { return JSONArray(raw) }
        val a = raw.indexOf('['); val b = raw.lastIndexOf(']')
        if (a in 0 until b) runCatching { return JSONArray(raw.substring(a, b + 1)) }
        return null
    }

    // ---- chat assistant (natural language -> action) ----------------------- #
    data class AgentPlan(
        val action: String,       // download | search | channel | help
        val url: String?,
        val query: String?,
        val fmt: String,          // mp3 | mp4
        val quality: String,      // Best Available | 720p | 480p
        val count: Int,
        val answer: String?,      // a reply when action == help
    )

    /** Turn a plain-language request into an action plan — ports desktop agent_plan. */
    suspend fun agentPlan(ctx: Context, instruction: String): Result<AgentPlan> =
        withContext(Dispatchers.IO) {
            val key = storedKey(ctx)
            if (key.isBlank()) return@withContext Result.failure(IOException("No AI key configured."))
            val prompt =
                "You are the built-in assistant of a media downloader app (YouTube, X, " +
                "TikTok, etc.). Convert the user's request into a JSON action plan. " +
                "Fields: action ('download' if they gave a specific media URL; 'channel' " +
                "if they gave a channel/profile URL or want a whole channel/artist; " +
                "'search' to find something by name; 'help' to answer a question about " +
                "using the app); url (string or null); query (search/artist text or " +
                "null); fmt ('mp3' for songs/audio — the default — or 'mp4' for video); " +
                "quality ('Best Available' default, or '720p'/'480p'); count (1-10, how " +
                "many search results, default 1); answer (a short helpful reply when " +
                "action is 'help', else null). Return ONLY the JSON object.\n\n" +
                "User: $instruction"
            try {
                val o = extractJsonObject(chat(key, prompt, maxTokens = 500))
                    ?: return@withContext Result.failure(IOException("AI returned an unexpected response."))
                fun str(k: String) = o.optString(k).ifBlank { null }?.takeUnless { it.equals("null", true) }
                Result.success(AgentPlan(
                    action = o.optString("action").ifBlank { "help" },
                    url = str("url"),
                    query = str("query"),
                    fmt = o.optString("fmt").ifBlank { "mp3" },
                    quality = o.optString("quality").ifBlank { "Best Available" },
                    count = if (o.has("count")) o.optInt("count", 1).coerceIn(1, 10) else 1,
                    answer = str("answer"),
                ))
            } catch (e: Exception) {
                Result.failure(e)
            }
        }

    private fun extractJsonObject(text: String): JSONObject? {
        val fenced = Regex("```(?:json)?\\s*(.*?)```", RegexOption.DOT_MATCHES_ALL)
            .find(text)?.groupValues?.get(1)
        val raw = (fenced ?: text).trim()
        runCatching { return JSONObject(raw) }
        val a = raw.indexOf('{'); val b = raw.lastIndexOf('}')
        if (a in 0 until b) runCatching { return JSONObject(raw.substring(a, b + 1)) }
        return null
    }
}
