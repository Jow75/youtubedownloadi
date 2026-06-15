package ke.co.baziqhue.umd

import android.content.Context
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import org.json.JSONArray
import org.json.JSONObject
import java.io.File
import kotlin.math.sqrt

/**
 * Semantic search index: an on-disk map of {title -> embedding vector}, stored in
 * the public AI Library folder so it survives reinstalls. Mirrors the desktop
 * ai_embeds.json + semantic_search.
 */
object SearchIndex {

    private fun file(): File = File(Storage.aiDir(), "embeds.json")

    private fun load(): LinkedHashMap<String, FloatArray> {
        val f = file()
        if (!f.exists()) return LinkedHashMap()
        return try {
            val o = JSONObject(f.readText())
            val m = LinkedHashMap<String, FloatArray>()
            for (k in o.keys()) {
                val arr = o.getJSONArray(k)
                m[k] = FloatArray(arr.length()) { arr.getDouble(it).toFloat() }
            }
            m
        } catch (_: Exception) {
            LinkedHashMap()
        }
    }

    private fun save(map: Map<String, FloatArray>) {
        try {
            val o = JSONObject()
            for ((k, v) in map) o.put(k, JSONArray().apply { v.forEach { put(it.toDouble()) } })
            file().writeText(o.toString())
        } catch (_: Exception) {
        }
    }

    suspend fun indexedCount(): Int = withContext(Dispatchers.IO) { load().size }

    /** Embed any titles not already indexed (cached). Returns #newly added. */
    suspend fun build(
        ctx: Context,
        titles: List<String>,
        onProgress: (Int, Int) -> Unit,
    ): Result<Int> = withContext(Dispatchers.IO) {
        val map = load()
        val todo = titles.filter { it.isNotBlank() }.distinct().filter { it !in map }
        if (todo.isEmpty()) return@withContext Result.success(0)
        var added = 0
        val batch = 16
        var i = 0
        while (i < todo.size) {
            val chunk = todo.subList(i, minOf(i + batch, todo.size))
            val r = Ai.embed(ctx, chunk, "passage")
            if (r.isFailure) {
                save(map)
                return@withContext Result.failure(r.exceptionOrNull() ?: Exception("Embedding failed."))
            }
            val vecs = r.getOrThrow()
            chunk.forEachIndexed { j, t -> if (j < vecs.size) { map[t] = vecs[j]; added++ } }
            save(map)
            i += batch
            onProgress(minOf(i, todo.size), todo.size)
        }
        Result.success(added)
    }

    /** Rank [candidates] (that are indexed) by meaning-similarity to [query]. */
    suspend fun search(
        ctx: Context,
        query: String,
        candidates: List<String>,
        topK: Int = 25,
    ): Result<List<Pair<String, Float>>> = withContext(Dispatchers.IO) {
        val map = load()
        val cand = candidates.distinct().filter { it in map }
        if (cand.isEmpty()) return@withContext Result.success(emptyList())
        val qr = Ai.embed(ctx, listOf(query), "query")
        if (qr.isFailure) return@withContext Result.failure(qr.exceptionOrNull() ?: Exception("Embedding failed."))
        val qv = qr.getOrThrow().firstOrNull() ?: return@withContext Result.success(emptyList())
        val scored = cand.map { it to cosine(qv, map.getValue(it)) }.sortedByDescending { it.second }
        Result.success(scored.take(topK))
    }

    private fun cosine(a: FloatArray, b: FloatArray): Float {
        var dot = 0f; var na = 0f; var nb = 0f
        val n = minOf(a.size, b.size)
        for (i in 0 until n) { dot += a[i] * b[i]; na += a[i] * a[i]; nb += b[i] * b[i] }
        return (dot / (sqrt(na) * sqrt(nb) + 1e-9f))
    }
}
