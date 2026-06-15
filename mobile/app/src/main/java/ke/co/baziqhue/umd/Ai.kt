package ke.co.baziqhue.umd

import android.content.Context
import android.content.SharedPreferences
import androidx.security.crypto.EncryptedSharedPreferences
import androidx.security.crypto.MasterKey
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import org.json.JSONArray
import org.json.JSONObject
import java.io.IOException
import java.net.HttpURLConnection
import java.net.URL

/**
 * AI layer — a faithful port of the desktop ai.py, scoped (for now) to the
 * "explain a failed download" helper. Bring-your-own-key: the user pastes their
 * NVIDIA API key once; it's stored encrypted (Android Keystore via
 * EncryptedSharedPreferences) and only TEXT (the error + title) is ever sent.
 *
 * Same provider/model/prompt as desktop, so explanations match.
 */
object Ai {
    private const val BASE_URL = "https://integrate.api.nvidia.com/v1"
    private const val CHAT_MODEL = "meta/llama-3.3-70b-instruct"
    const val KEY_PREFIX = "nvapi-"
    const val GET_KEY_URL = "https://build.nvidia.com/"

    // ---- key storage (encrypted, with a graceful fallback) ----------------- #
    private fun prefs(ctx: Context): SharedPreferences = try {
        val master = MasterKey.Builder(ctx)
            .setKeyScheme(MasterKey.KeyScheme.AES256_GCM)
            .build()
        EncryptedSharedPreferences.create(
            ctx, "umd_ai_secure", master,
            EncryptedSharedPreferences.PrefKeyEncryptionScheme.AES256_SIV,
            EncryptedSharedPreferences.PrefValueEncryptionScheme.AES256_GCM,
        )
    } catch (e: Exception) {
        // Some devices have a flaky keystore — fall back to app-private prefs
        // (still sandboxed to this app) rather than losing the feature.
        ctx.getSharedPreferences("umd_ai_plain", Context.MODE_PRIVATE)
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

    // ---- API calls --------------------------------------------------------- #
    /** Check a key by listing models (cheap, like the desktop validate_key). */
    suspend fun validateKey(key: String): Result<Unit> = withContext(Dispatchers.IO) {
        try {
            val conn = (URL("$BASE_URL/models").openConnection() as HttpURLConnection).apply {
                requestMethod = "GET"
                setRequestProperty("Authorization", "Bearer ${key.trim()}")
                connectTimeout = 20000; readTimeout = 20000
            }
            val code = conn.responseCode
            conn.disconnect()
            if (code in 200..299) Result.success(Unit)
            else Result.failure(IOException("Key rejected (HTTP $code)."))
        } catch (e: Exception) {
            Result.failure(IOException("Couldn't reach provider: ${e.message}"))
        }
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

    private fun chat(key: String, prompt: String, maxTokens: Int): String {
        val body = JSONObject()
            .put("model", CHAT_MODEL)
            .put("messages", JSONArray().put(
                JSONObject().put("role", "user").put("content", prompt)))
            .put("temperature", 0.1)
            .put("max_tokens", maxTokens)
            .toString()
        val conn = (URL("$BASE_URL/chat/completions").openConnection() as HttpURLConnection).apply {
            requestMethod = "POST"
            setRequestProperty("Authorization", "Bearer $key")
            setRequestProperty("Content-Type", "application/json")
            doOutput = true
            connectTimeout = 30000; readTimeout = 120000
        }
        conn.outputStream.use { it.write(body.toByteArray(Charsets.UTF_8)) }
        val code = conn.responseCode
        val stream = if (code in 200..299) conn.inputStream else conn.errorStream
        val text = stream?.bufferedReader()?.use { it.readText() }.orEmpty()
        conn.disconnect()
        if (code !in 200..299) throw IOException("AI service error (HTTP $code).")
        return JSONObject(text)
            .getJSONArray("choices").getJSONObject(0)
            .getJSONObject("message").getString("content").trim()
    }
}
