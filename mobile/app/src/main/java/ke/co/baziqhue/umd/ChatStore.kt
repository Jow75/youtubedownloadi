package ke.co.baziqhue.umd

import org.json.JSONArray
import org.json.JSONObject
import java.io.File

/**
 * Persists the assistant's chat sessions to a JSON file in the public AI Library
 * folder, so your chats (one per artist, say) survive restarts — ChatGPT-style.
 */
object ChatStore {

    private fun file(): File = File(Storage.aiDir(), "chats.json")

    /** Returns (sessions newest-first, currentId). */
    fun load(): Pair<List<ChatSession>, String> {
        val f = file()
        if (!f.exists()) return emptyList<ChatSession>() to ""
        return try {
            val root = JSONObject(f.readText())
            val arr = root.optJSONArray("sessions") ?: JSONArray()
            val list = ArrayList<ChatSession>(arr.length())
            for (i in 0 until arr.length()) {
                val o = arr.optJSONObject(i) ?: continue
                val msgs = ArrayList<ChatMsg>()
                val ma = o.optJSONArray("messages") ?: JSONArray()
                for (j in 0 until ma.length()) {
                    val m = ma.optJSONObject(j) ?: continue
                    msgs.add(ChatMsg(m.optBoolean("u"), m.optString("t"),
                        m.optString("f").ifBlank { null }))
                }
                list.add(ChatSession(o.optString("id"), o.optString("title", "New chat"), msgs))
            }
            list to root.optString("current")
        } catch (_: Exception) {
            emptyList<ChatSession>() to ""
        }
    }

    fun save(sessions: List<ChatSession>, currentId: String) {
        try {
            val arr = JSONArray()
            for (s in sessions) {
                val o = JSONObject().put("id", s.id).put("title", s.title)
                val ma = JSONArray()
                // Copy to a plain list first to avoid concurrent-modification on the
                // live snapshot list.
                for (m in s.messages.toList()) {
                    val mo = JSONObject().put("u", m.fromUser).put("t", m.text)
                    m.filePath?.let { mo.put("f", it) }
                    ma.put(mo)
                }
                o.put("messages", ma)
                arr.put(o)
            }
            file().writeText(JSONObject().put("sessions", arr).put("current", currentId).toString())
        } catch (_: Exception) {
        }
    }

    fun clear() {
        try { file().writeText(JSONObject().put("sessions", JSONArray()).put("current", "").toString()) }
        catch (_: Exception) {}
    }
}
