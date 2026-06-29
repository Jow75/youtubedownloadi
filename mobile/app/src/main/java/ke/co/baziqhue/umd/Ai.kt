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
    private const val CHAT_MODEL = "meta/llama-3.3-70b-instruct"   // smart, for chat/errors
    private const val FAST_MODEL = "meta/llama-3.1-8b-instruct"    // ~8x faster, for bulk jobs
    private const val EMBED_MODEL = "nvidia/nv-embedqa-e5-v5"
    const val KEY_PREFIX = "nvapi-"
    const val GET_KEY_URL = "https://build.nvidia.com/"

    private val JSON = "application/json; charset=utf-8".toMediaType()

    private val http: OkHttpClient by lazy {
        OkHttpClient.Builder()
            .connectTimeout(30, TimeUnit.SECONDS)
            .readTimeout(120, TimeUnit.SECONDS)
            .writeTimeout(30, TimeUnit.SECONDS)
            .callTimeout(180, TimeUnit.SECONDS)
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
            Result.failure(IOException("Couldn't reach the AI service: ${e.message}"))
        }
    }

    private fun chat(key: String, prompt: String, maxTokens: Int, model: String = CHAT_MODEL): String {
        val payload = JSONObject()
            .put("model", model)
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

    /**
     * Clean up messy download titles -> {original: TitleInfo}. Batched in small
     * chunks on the FAST model so it returns quickly. [onProgress] reports
     * done/total as batches complete.
     *
     * SAFETY (this previously corrupted libraries): the model's reply is matched
     * back to each input by the **echoed original title** — never by array position.
     * The small model often drops / merges / reorders items within a batch; the old
     * positional mapping then silently pinned one song's name onto a *different* file
     * (e.g. a Zuchu track ending up named after another song in the same batch).
     * Identity-matching makes that impossible: a suggestion is only ever applied to
     * the exact title the model echoed back. On top of that, [sanitizeTitleInfo]
     * rejects invented artists/titles — clean-up may only REMOVE junk, never add or
     * substitute words that weren't already in the original filename.
     */
    suspend fun analyzeTitles(
        ctx: Context,
        titles: List<String>,
        onProgress: (Int, Int) -> Unit = { _, _ -> },
    ): Result<Map<String, TitleInfo>> = withContext(Dispatchers.IO) {
        val key = storedKey(ctx)
        if (key.isBlank()) return@withContext Result.failure(IOException("No AI key configured."))
        val uniq = titles.filter { it.isNotBlank() }.distinct()
        if (uniq.isEmpty()) return@withContext Result.success(emptyMap())

        val result = LinkedHashMap<String, TitleInfo>()
        val batch = 6                       // smaller batch = less chance the model drifts
        var i = 0
        while (i < uniq.size) {
            val chunk = uniq.subList(i, minOf(i + batch, uniq.size))
            val prompt = buildString {
                append("You TIDY UP media filenames for a music library. Your only job is to ")
                append("REMOVE junk — you must NEVER invent, translate, guess, or swap names.\n")
                append("For EACH item return one JSON object with these fields:\n")
                append("  \"id\": the item number, copied exactly;\n")
                append("  \"original\": the item's text, copied VERBATIM (character for character);\n")
                append("  \"artist\": the performer — but ONLY if their name already appears in the ")
                append("text; otherwise null. Never write a name that isn't in the text;\n")
                append("  \"clean_title\": the song/work name with only junk removed (e.g. ")
                append("\"Official Video\", \"(Official Music Video)\", \"[Lyrics]\", \"HD\", \"4K\", ")
                append("resolution/fps tags, channel watermarks, emojis, doubled spaces). Keep the ")
                append("real wording EXACTLY; do NOT add words, rephrase, or translate, and do NOT ")
                append("repeat the artist here;\n")
                append("  \"category\": exactly one of $CATEGORIES;\n")
                append("  \"is_official\": true if it looks like an official release, else false.\n")
                append("Return ONLY a JSON array of these objects, in the same order as given.\n\nItems:\n")
                append(chunk.mapIndexed { j, t -> "${j + 1}. $t" }.joinToString("\n"))
            }
            try {
                val arr = extractJsonArray(chat(key, prompt, maxTokens = 1300, model = FAST_MODEL))
                if (arr != null) {
                    for (k in 0 until arr.length()) {
                        val o = arr.optJSONObject(k) ?: continue
                        // Match the object back to a specific input by IDENTITY, never position.
                        val orig = matchOriginal(o, chunk) ?: continue
                        val info = sanitizeTitleInfo(o, orig) ?: continue
                        if (!result.containsKey(orig)) result[orig] = info   // first clean hit wins
                    }
                }
            } catch (_: Exception) {
                // Skip a bad batch, keep going (partial results are still useful).
            }
            i += batch
            onProgress(minOf(i, uniq.size), uniq.size)
        }
        if (result.isEmpty()) Result.failure(IOException("Couldn't analyze titles — try again."))
        else Result.success(result)
    }

    /**
     * Tie a returned object back to the EXACT input it describes. Trust the echoed
     * `original` (verbatim, then normalized); only if that's missing fall back to the
     * echoed `id`. Returns null when we can't be sure — so the file gets no suggestion
     * instead of someone else's name.
     */
    private fun matchOriginal(o: JSONObject, chunk: List<String>): String? {
        val echoed = o.optString("original").trim()
        if (echoed.isNotBlank()) {
            chunk.firstOrNull { it.equals(echoed, ignoreCase = true) }?.let { return it }
            val ne = normalizeWords(echoed)
            chunk.firstOrNull { normalizeWords(it) == ne }?.let { return it }
            return null            // model named an "original" we never sent → don't guess
        }
        val id = o.optInt("id", -1)
        return if (id in 1..chunk.size) chunk[id - 1] else null
    }

    /**
     * Anti-hallucination guard. Clean-up may only SUBTRACT text, so:
     *  - clean_title is accepted only if every significant word already exists in the
     *    original (otherwise we keep the original wording);
     *  - artist is accepted only if it literally appears in the original title.
     * This stops the model replacing a real title/artist with a different one.
     */
    private fun sanitizeTitleInfo(o: JSONObject, original: String): TitleInfo? {
        val cat = o.optString("category").let { if (it in CATEGORIES) it else "Other" }
        val official = if (o.has("is_official")) o.optBoolean("is_official") else null

        val rawClean = o.optString("clean_title").trim()
        val cleanTitle = if (rawClean.isNotBlank() && isSubsetOf(rawClean, original)) rawClean
                         else original                        // reject invented / rephrased titles

        val rawArtist = o.optString("artist").trim()
            .takeUnless { it.isBlank() || it.equals("null", true) }
        val artist = rawArtist?.takeIf { phraseIn(it, original) }   // reject invented artists

        return TitleInfo(artist, cleanTitle.ifBlank { original }, cat, official)
    }

    private fun normalizeWords(s: String): String =
        s.lowercase().replace(Regex("[^a-z0-9]+"), " ").trim()

    private fun significantWords(s: String): List<String> =
        normalizeWords(s).split(' ').filter { it.length >= 2 }

    /** True if `phrase` appears as a contiguous run inside `text` (normalized). */
    private fun phraseIn(phrase: String, text: String): Boolean {
        val p = normalizeWords(phrase)
        return p.isNotBlank() && normalizeWords(text).contains(p)
    }

    /** True if every significant word of `candidate` already exists in `original`. */
    private fun isSubsetOf(candidate: String, original: String): Boolean {
        val orig = significantWords(original).toSet()
        val cand = significantWords(candidate)
        return cand.isNotEmpty() && cand.all { it in orig }
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

    // ---- auto-playlists: classify by genre / language / region ------------- #
    data class TrackTags(val genre: String, val language: String)

    suspend fun classifyTracks(
        ctx: Context,
        titles: List<String>,
        onProgress: (Int, Int) -> Unit = { _, _ -> },
    ): Result<Map<String, TrackTags>> = withContext(Dispatchers.IO) {
        val key = storedKey(ctx)
        if (key.isBlank()) return@withContext Result.failure(IOException("No AI key configured."))
        val uniq = titles.filter { it.isNotBlank() }.distinct()
        if (uniq.isEmpty()) return@withContext Result.success(emptyMap())

        val result = LinkedHashMap<String, TrackTags>()
        val batch = 10
        var i = 0
        while (i < uniq.size) {
            val chunk = uniq.subList(i, minOf(i + batch, uniq.size))
            val prompt =
                "You sort music tracks into a FEW meaningful playlists by GENRE and by " +
                "LANGUAGE/REGION — never by mood or feeling. For EACH title return one JSON " +
                "object IN THE SAME ORDER with two fields:\n" +
                "  genre: one of Afrobeats, Amapiano, Bongo Flava, Gengetone, Rhumba, Gospel, " +
                "Hip-Hop, R&B, Pop, Reggae, Dancehall, Drill, Reggaeton, Bollywood, Country, " +
                "Classical, Other;\n" +
                "  language: the main language/region — one of Swahili, English, Nigerian, " +
                "French, Spanish, Hindi, Bengali, Marathi, Arabic, Kikuyu, Mixed, Unknown.\n" +
                "Pick the single best fit; do NOT invent new labels. If you are not " +
                "confident, use genre 'Other' and language 'Unknown' — never guess. " +
                "Return ONLY a JSON array.\n\nTitles:\n" +
                chunk.mapIndexed { j, t -> "${j + 1}. $t" }.joinToString("\n")
            try {
                val arr = extractJsonArray(chat(key, prompt, maxTokens = 700, model = FAST_MODEL))
                if (arr != null) {
                    for (j in chunk.indices) {
                        val o = arr.optJSONObject(j) ?: continue
                        result[chunk[j]] = TrackTags(
                            genre = o.optString("genre").trim(),
                            language = o.optString("language").trim(),
                        )
                    }
                }
            } catch (_: Exception) {
            }
            i += batch
            onProgress(minOf(i, uniq.size), uniq.size)
        }
        if (result.isEmpty()) Result.failure(IOException("Couldn't classify — try again."))
        else Result.success(result)
    }

    // ---- artist alias merge (cross-platform same-artist) ------------------- #
    /**
     * Cluster artist-name aliases of the SAME real artist (different spellings /
     * platforms) → a canonical name each. Returns {inputName: canonicalName}. The
     * AI backup for [MediaMeta]'s metadata-first hierarchy.
     */
    suspend fun mergeArtists(ctx: Context, names: List<String>): Result<Map<String, String>> =
        withContext(Dispatchers.IO) {
            val key = storedKey(ctx)
            if (key.isBlank()) return@withContext Result.failure(IOException("No AI key configured."))
            val uniq = names.filter { it.isNotBlank() && !it.equals("Unknown", true) }.distinct().take(80)
            if (uniq.size < 2) return@withContext Result.success(emptyMap())
            val prompt =
                "These are music artist names from a library. Some refer to the SAME real " +
                "artist written differently or from different platforms (e.g. \"Diamond Platnumz\", " +
                "\"diamondplatnumz\", \"Diamond Platnumz Official\", \"Diamond Platnumz - Topic\"). " +
                "Group the names that are the SAME artist and pick ONE clean canonical name for " +
                "each group (the cleanest real artist name). Return ONLY a JSON object mapping " +
                "EVERY input name to its canonical name. If a name is unique or you're unsure, map " +
                "it to itself. NEVER merge genuinely different artists.\n\nNames:\n" +
                uniq.joinToString("\n")
            try {
                val o = extractJsonObject(chat(key, prompt, maxTokens = 1500, model = CHAT_MODEL))
                    ?: return@withContext Result.failure(IOException("AI returned an unexpected response."))
                val result = LinkedHashMap<String, String>()
                for (n in uniq) {
                    val c = o.optString(n).trim()
                    if (c.isNotBlank() && !c.equals("null", true)) result[n] = c
                }
                Result.success(result)
            } catch (e: Exception) {
                Result.failure(e)
            }
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

    /** What the assistant knows about the product (observations 4 & 5). */
    private const val PRODUCT_BRIEF =
        "ABOUT THIS APP — use this to answer questions about it. Universal Media " +
        "Downloader is a media downloader, organizer and AI library for Android and " +
        "Windows, created by George Muraguri Muthoni under the BAZIQ HUE project. " +
        "It downloads audio (MP3) or video (MP4) from YouTube, TikTok, X and many " +
        "more — single links, or whole channels/playlists/profiles (the Channel tab). " +
        "Files save to the public Download/Universal Media Downloader folder " +
        "(Music/MP3, Videos/MP4). It has: a Download tab, a Channel/bulk tab, a " +
        "History tab (search + re-download, kept in a file so it survives reinstalls), " +
        "and a Library tab with semantic Smart Search (find by meaning), byte-identical " +
        "Duplicate cleanup (safe — it keeps one copy), and AI Title clean-up/rename. " +
        "It's unlocked by an offline, per-device license key that expires; AI features " +
        "use the user's own AI Assistant key. A built-in media player is on the roadmap. " +
        "When asked who built it, credit George Muraguri Muthoni / BAZIQ HUE."

    /** Turn a plain-language request into an action plan — ports desktop agent_plan. */
    suspend fun agentPlan(ctx: Context, instruction: String): Result<AgentPlan> =
        withContext(Dispatchers.IO) {
            val key = storedKey(ctx)
            if (key.isBlank()) return@withContext Result.failure(IOException("No AI key configured."))
            val prompt =
                PRODUCT_BRIEF + "\n\n" +
                "You are the built-in assistant of this app. Convert the user's request " +
                "into a JSON action plan. Fields: action ('download' if they gave a " +
                "specific media URL; 'channel' if they gave a channel/profile URL or want " +
                "a whole channel/artist; 'search' to find something by name; 'help' to " +
                "answer ANY question — about the app (use the ABOUT info above) or general " +
                "knowledge); url (set this ONLY if the user literally pasted a web link in " +
                "THIS message; otherwise it MUST be null — never invent or recall a link); " +
                "query (the exact song/video/artist name to search for — always fill this " +
                "for a request by name, copied from THIS message); " +
                "fmt ('mp3' for songs/audio — the default — or 'mp4' for video); quality " +
                "('Best Available' default, or '720p'/'480p'); count (1-10, default 1); " +
                "answer (a helpful reply when action is 'help', else null). For 'help' " +
                "give a friendly, specific answer. Return ONLY the JSON object.\n\n" +
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
