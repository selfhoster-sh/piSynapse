package com.pisynapse.app

import okhttp3.MediaType.Companion.toMediaType
import okhttp3.Request
import okhttp3.RequestBody.Companion.toRequestBody
import okhttp3.Response
import org.json.JSONArray
import org.json.JSONObject
import java.io.IOException

/**
 * HTTP client for the piSynapse Python server (only-server / SYNC_ALWAYS).
 * Speaks the server API contract: X-API-Key auth, JSON bodies, SSE chat stream.
 */
class ServerStore(private val cfg: ConfigStore) {

    private val apiKey get() = cfg.get("SERVER_API_KEY").trim()
    private val serverUrl get() = cfg.get("SERVER_URL").trim().trimEnd('/')
    val userId get() = cfg.get("SERVER_USER").trim().ifBlank { cfg.get("ASSISTANT_USER").trim() }.ifBlank { "default" }

    fun configured(): Boolean = serverUrl.isNotEmpty()

    private fun url(path: String): String {
        if (!configured()) throw IOException("Sunucu adresi ayarlanmamış.")
        val sep = if (path.startsWith("/")) "" else "/"
        return serverUrl + sep + path
    }

    private fun req(method: String, path: String, bodyJson: String? = null): Request {
        val headers = okhttp3.Headers.Builder()
            .add("Accept", "application/json")
            .add("Content-Type", "application/json")
            .add("X-API-Key", apiKey)
            .build()
        val body = bodyJson?.toRequestBody("application/json; charset=utf-8".toMediaType())
        return Request.Builder().url(url(path)).method(method, body).headers(headers).build()
    }

    private fun exec(method: String, path: String, body: JSONObject? = null): JSONObject {
        val r = HttpClient.client.newCall(req(method, path, body?.toString())).execute()
        r.use { resp ->
            val text = resp.body?.string() ?: ""
            if (!resp.isSuccessful) throw IOException("HTTP ${resp.code}: ${text.take(300)}")
            return try {
                JSONObject(text)
            } catch (e: Exception) {
                JSONObject().put("ok", true)
            }
        }
    }

    // ── Sync items ─────────────────────────────────────────────────────────
    fun getSyncItems(entityType: String? = null, since: String? = null): JSONArray {
        val parts = mutableListOf("user_id=${java.net.URLEncoder.encode(userId, "UTF-8")}")
        if (entityType != null) parts.add("entity_type=${java.net.URLEncoder.encode(entityType, "UTF-8")}")
        if (since != null) parts.add("since=${java.net.URLEncoder.encode(since, "UTF-8")}")
        val r = exec("GET", "/chat/sync/items?${parts.joinToString("&")}")
        return r.optJSONArray("items") ?: JSONArray()
    }

    fun postSyncItems(items: JSONArray): Int {
        val body = JSONObject().put("user_id", userId).put("items", items)
        val r = exec("POST", "/chat/sync/items", body)
        return r.optInt("applied", 0)
    }

    // ── Sessions / history ─────────────────────────────────────────────────
    fun getSessions(): JSONArray {
        return exec("GET", "/chat/sessions").optJSONArray("sessions") ?: JSONArray()
    }

    fun getHistory(sessionId: String): JSONArray {
        return exec("GET", "/chat/history?session_id=${java.net.URLEncoder.encode(sessionId, "UTF-8")}")
            .optJSONArray("messages") ?: JSONArray()
    }

    fun deleteSession(sessionId: String): Boolean {
        return exec("DELETE", "/chat/history?session_id=${java.net.URLEncoder.encode(sessionId, "UTF-8")}").optBoolean("ok", true)
    }

    fun deleteMemoryRow(id: String): Boolean {
        return exec("DELETE", "/chat/memories?user_id=${java.net.URLEncoder.encode(userId, "UTF-8")}&id=${java.net.URLEncoder.encode(id, "UTF-8")}")
            .optBoolean("ok", true)
    }

    fun listMemories(): JSONArray {
        return exec("GET", "/chat/memories?user_id=${java.net.URLEncoder.encode(userId, "UTF-8")}&limit=200")
            .optJSONArray("memories") ?: JSONArray()
    }

    /** Push a memory via the save_memory tool so it lands in the server's memory store. */
    fun saveMemoryRemote(content: String, category: String, importance: Int): Boolean {
        val body = JSONObject()
            .put("session_id", "default_session")
            .put("user_id", userId)
            .put("tool", "save_memory")
            .put("params", JSONObject()
                .put("content", content)
                .put("category", category)
                .put("importance", importance))
        val r = exec("POST", "/chat/execute", body)
        return r.optBoolean("ok", false) || !r.optString("reply").startsWith("Hata")
    }

    /** Raw SSE chat stream over the server. Calls onEach(eventJson) per data line. */
    fun chatStreamSSE(payload: JSONObject, onEach: (JSONObject) -> Unit) {
        if (!configured()) throw IOException("Sunucu adresi ayarlanmamış.")
        val rq = req("POST", "/chat/stream", payload.toString())
        val resp: Response = HttpClient.client.newCall(rq).execute()
        resp.use { r ->
            if (!r.isSuccessful) {
                val text = r.body?.string() ?: ""
                throw IOException("HTTP ${r.code}: ${text.take(300)}")
            }
            val br = r.body?.byteStream()?.bufferedReader() ?: throw IOException("empty body")
            var line = br.readLine()
            while (line != null) {
                if (line.startsWith("data:")) {
                    val data = line.removePrefix("data:").trim()
                    if (data.isNotEmpty()) {
                        try {
                            onEach(JSONObject(data))
                        } catch (e: Exception) {
                            val err = JSONObject().put("error", "sse-parse: $data")
                            onEach(err)
                        }
                    }
                }
                line = br.readLine()
            }
        }
    }
}