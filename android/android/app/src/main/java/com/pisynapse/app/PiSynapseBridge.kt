package com.pisynapse.app

import android.Manifest
import android.content.pm.PackageManager
import androidx.core.app.ActivityCompat
import androidx.core.content.ContextCompat
import com.getcapacitor.JSObject
import com.getcapacitor.Plugin
import com.getcapacitor.PluginCall
import com.getcapacitor.PluginMethod
import com.getcapacitor.annotation.CapacitorPlugin
import org.json.JSONArray
import org.json.JSONObject
import java.io.File
import java.io.IOException
import java.util.UUID
import java.util.concurrent.ExecutorService
import java.util.concurrent.Executors

@CapacitorPlugin(name = "PiSynapse")
class PiSynapseBridge : Plugin() {

    companion object {
        @JvmStatic
        @Volatile var instance: PiSynapseBridge? = null
    }

    private val store get() = ConfigStore(context)
    private val weather get() = WeatherClient(store)
    private val notes get() = NotesClient(store)
    private val local get() = LocalStore(context)
    private val platform get() = PlatformTools(context)
    private val server get() = ServerStore(store)
    private val runner by lazy { ToolRunner(store, weather, notes, local, platform) }
    private val llm by lazy { LlmEngine(context, store, PiTools(runner).providers()) }
    private val downloader by lazy { ModelDownloader(context, store) }

    private val io: ExecutorService = Executors.newCachedThreadPool()

    private fun js(o: JSONObject): JSObject = JSObject(o.toString())

    override fun load() {
        super.load()
        instance = this
        try {
            io.execute {
                try {
                    llm.ensureLoaded()
                } catch (t: Throwable) {}
            }
        } catch (t: Throwable) {}
    }

    /** Frees the 2.5GB native model when the OS asks for memory. Reloads lazily on next chat. */
    @PluginMethod
    fun llmRelease(call: PluginCall) {
        llmReleaseNoCall()
        call.resolve(JSObject().put("ok", true))
    }

    fun llmReleaseNoCall() {
        try {
            llm.release()
        } catch (t: Throwable) {}
    }

    // ── Server sync ────────────────────────────────────────────────────────
    /** Reports whether a server route is available and reachable. */
    @PluginMethod
    fun serverStatus(call: PluginCall) {
        call.resolve(JSObject()
            .put("configured", server.configured())
            .put("server_url", store.get("SERVER_URL"))
            .put("sync_mode", store.get("SYNC_MODE"))
            .put("sync_always", store.get("SYNC_ALWAYS")))
    }

    private fun syncMode(): String = store.get("SYNC_MODE").ifBlank { "only-phone" }

    /** Should remote data be used for this store? only-server uses the server as truth. */
    private fun wantsServer(): Boolean = syncMode() == "only-server"

    private fun wantsSyncAlways(): Boolean = store.get("SYNC_ALWAYS") == "on"

    /**
     * Push the phone's local chat history to the server so offline sessions are
     * mirrored there. Idempotent: every message is keyed by
     * `client_key:<role>:<index>` and the server skips rows it already has.
     */
    @PluginMethod
    fun chatPush(call: PluginCall) {
        val data = call.getString("data") ?: "{}"
        io.execute {
            try {
                if (!wantsServer() && !wantsSyncAlways()) {
                    call.resolve(JSObject().put("ok", true).put("pushed", 0).put("skipped", true))
                    return@execute
                }
                if (!server.configured()) throw IOException("Sunucu adresi ayarlanmamış.")
                val payload = JSONObject(data)
                val sessions = payload.optJSONArray("sessions") ?: JSONArray()
                val history = payload.optJSONObject("sessionHistory") ?: JSONObject()
                var pushed = 0
                for (i in 0 until sessions.length()) {
                    val sid = sessions.getJSONObject(i).optString("session_id")
                    if (sid.isBlank()) continue
                    val msgs = history.optJSONArray(sid) ?: continue
                    val arr = JSONArray()
                    for (j in 0 until msgs.length()) arr.put(msgs.getJSONObject(j))
                    pushed += server.importMessages(sid, arr, "phone:$sid")
                }
                call.resolve(JSObject().put("ok", true).put("pushed", pushed))
            } catch (e: Exception) {
                call.resolve(JSObject().put("ok", false).put("error", e.message ?: e.toString()))
            }
        }
    }

    /**
     * Pull sessions + full history from the server when it is the source of
     * truth (only-server), so a cold phone shows the same sidebar and
     * conversation state as the server's own dashboard.
     */
    @PluginMethod
    fun chatPull(call: PluginCall) {
        io.execute {
            try {
                if (!server.configured()) throw IOException("Sunucu adresi ayarlanmamış.")
                val (sessions, history) = server.pullHistory()
                call.resolve(JSObject()
                    .put("ok", true)
                    .put("sessions", sessions)
                    .put("sessionHistory", history))
            } catch (e: Exception) {
                call.resolve(JSObject().put("ok", false).put("error", e.message ?: e.toString()))
            }
        }
    }

    /** Refresh the phone's local session list from the server. */
    @PluginMethod
    fun chatSyncSessions(call: PluginCall) {
        io.execute {
            try {
                if (!server.configured()) throw IOException("Sunucu adresi ayarlanmamış.")
                call.resolve(JSObject().put("ok", true).put("sessions", server.getSessions()))
            } catch (e: Exception) {
                call.resolve(JSObject().put("ok", false).put("error", e.message ?: e.toString()))
            }
        }
    }

    /** Get a single remote session's conversation. */
    @PluginMethod
    fun chatHistory(call: PluginCall) {
        val sid = call.getString("session_id") ?: ""
        io.execute {
            try {
                if (!server.configured()) throw IOException("Sunucu adresi ayarlanmamış.")
                call.resolve(JSObject().put("ok", true).put("messages", server.getHistory(sid)))
            } catch (e: Exception) {
                call.resolve(JSObject().put("ok", false).put("error", e.message ?: e.toString()))
            }
        }
    }

    /**
     * Pull MASTER (server) settings into the phone (MASTER→SLAVE sync).
     * Triggered on successful server login. Only portable/secure-safe keys are
     * applied to the local ConfigStore by the JS side (NEXTCLOUD_*, personal).
     */
    @PluginMethod
    fun pullServerSettings(call: PluginCall) {
        io.execute {
            try {
                if (!server.configured()) throw IOException("Sunucu adresi ayarlanmamış.")
                call.resolve(JSObject().put("ok", true).put("settings", server.getServerSettings()))
            } catch (e: Exception) {
                call.resolve(JSObject().put("ok", false).put("error", e.message ?: e.toString()))
            }
        }
    }

    /** Delete a remote session when the phone clears its local copy. */
    @PluginMethod
    fun deleteSession(call: PluginCall) {
        val sid = call.getString("session_id") ?: ""
        io.execute {
            try {
                if (!wantsServer() && !wantsSyncAlways()) {
                    call.resolve(JSObject().put("ok", true).put("skipped", true))
                    return@execute
                }
                if (!server.configured()) throw IOException("Sunucu adresi ayarlanmamış.")
                call.resolve(JSObject().put("ok", server.deleteSession(sid)))
            } catch (e: Exception) {
                call.resolve(JSObject().put("ok", false).put("error", e.message ?: e.toString()))
            }
        }
    }

    /**
     * Two-phase two-way sync of the phone's local entities (tasks, memory):
     *  1. PUSH local items that changed since last sync (last-write-wins),
     *  2. PULL server items changed since last sync and merge (wins if newer).
     * Tombstones remove remote copies; server tombstones remove local ones.
     */
    @PluginMethod
    fun syncNow(call: PluginCall) {
        io.execute {
            try {
                val result = runSync()
                call.resolve(result)
            } catch (e: Exception) {
                call.resolve(JSObject()
                    .put("ok", false)
                    .put("error", e.message ?: e.toString()))
            }
        }
    }

    private fun lastSyncKey(type: String) = "ps_since_$type"

    fun runSync(): JSObject {
        if (!server.configured()) {
            return JSObject().put("ok", false).put("error", "Sunucu adresi ayarlanmamış.")
        }
        val summary = JSONObject().put("ok", true).put("pushed", 0).put("pulled", 0).put("applied_local", 0)
        for (type in local.entityTypes) {
            val since = store.get(lastSyncKey(type))
            // PUSH local changes since last sync.
            val localItems = local.allEntities(type)
            val pushArr = JSONArray()
            for (i in 0 until localItems.length()) {
                val o = localItems.getJSONObject(i)
                val (uuid, ts) = local.metaOf(o)
                pushArr.put(JSONObject()
                    .put("uuid", uuid)
                    .put("entity_type", type)
                    .put("data", stripMeta(o))
                    .put("updated_at", ts)
                    .put("deleted", false))
            }
            var applied = 0
            if (pushArr.length() > 0) applied = server.postSyncItems(pushArr)
            summary.put("pushed", summary.optInt("pushed") + applied)
            // PULL server changes since last sync.
            val remote = server.getSyncItems(type, since = since.ifBlank { null })
            var appliedLocal = 0
            for (i in 0 until remote.length()) {
                val item = remote.getJSONObject(i)
                val uuid = item.optString("uuid")
                val rts = item.optString("updated_at")
                val deleted = item.optBoolean("deleted")
                val existing = findLocalByUuid(type, uuid)
                if (deleted) {
                    if (local.deleteLocalByUuid(type, uuid)) appliedLocal++
                } else if (existing == null || (rts > existing.optString("_updated_at") && rts != existing.optString("_updated_at"))) {
                    val merged = if (existing != null) JSONObject(existing.toString()) else JSONObject()
                    val data = item.optJSONObject("data")
                    if (data != null) for (k in data.keys()) merged.put(k, data.get(k))
                    merged.put("_uuid", uuid).put("_updated_at", rts)
                    local.upsertLocal(type, merged)
                    appliedLocal++
                }
            }
            summary.put("applied_local", summary.optInt("applied_local") + appliedLocal)
            if (since.isBlank() || remote.length() > 0 || applied > 0) {
                store.set(lastSyncKey(type), nowIso())
            }
        }
        return JSObject(summary.toString())
    }

    private fun stripMeta(o: JSONObject): JSONObject {
        val out = JSONObject()
        for (k in o.keys()) {
            if (k == "_uuid" || k == "_updated_at") continue
            out.put(k, o.get(k))
        }
        return out
    }

    private fun findLocalByUuid(type: String, uuid: String): JSONObject? {
        val arr = local.allEntities(type)
        for (i in 0 until arr.length()) {
            if (arr.getJSONObject(i).optString("_uuid") == uuid) return arr.getJSONObject(i)
        }
        return null
    }

    private fun nowIso(): String =
        java.text.SimpleDateFormat("yyyy-MM-dd'T'HH:mm:ssXXX", java.util.Locale.US).format(java.util.Date())

    // ── Config ─────────────────────────────────────────────────────────────
    @PluginMethod
    fun configGet(call: PluginCall) {
        call.resolve(js(store.schema()))
    }

    @PluginMethod
    fun configSet(call: PluginCall) {
        val values = call.getObject("values")
        if (values == null) {
            call.reject("values gerekli")
            return
        }
        store.setValues(values)
        call.resolve(JSObject().put("ok", true))
    }

    // ── Location → city detection ────────────────────────────────────────────
    @PluginMethod
    fun detectCity(call: PluginCall) {
        val act = activity
        if (act == null || ContextCompat.checkSelfPermission(act, Manifest.permission.ACCESS_FINE_LOCATION) != PackageManager.PERMISSION_GRANTED) {
            call.resolve(JSObject().put("ok", false).put("error", "location-denied"))
            return
        }
        io.execute {
            try {
                val lm = act.getSystemService(android.content.Context.LOCATION_SERVICE) as android.location.LocationManager
                val loc = try {
                    lm.getLastKnownLocation(android.location.LocationManager.GPS_PROVIDER)
                        ?: lm.getLastKnownLocation(android.location.LocationManager.NETWORK_PROVIDER)
                } catch (t: Throwable) { null }
                if (loc == null) {
                    call.resolve(JSObject().put("ok", false).put("error", "no-location"))
                    return@execute
                }
                val city = reverseGeocode(loc.latitude, loc.longitude)
                if (city.isNullOrBlank()) {
                    call.resolve(JSObject().put("ok", false).put("error", "no-city"))
                    return@execute
                }
                val cur = store.get("DEFAULT_CITY")
                call.resolve(JSObject()
                    .put("ok", true)
                    .put("city", city)
                    .put("latitude", loc.latitude)
                    .put("longitude", loc.longitude)
                    .put("existing", cur))
            } catch (e: Exception) {
                call.resolve(JSObject().put("ok", false).put("error", e.message ?: e.toString()))
            }
        }
    }

    private fun reverseGeocode(lat: Double, lon: Double): String? {
        return try {
            val req = okhttp3.Request.Builder().url(
                "https://nominatim.openstreetmap.org/reverse?lat=${lat}&lon=${lon}&format=json&accept-language=tr"
            ).header("User-Agent", "piSynapse/0.16").build()
            HttpClient.client.newCall(req).execute().use { resp ->
                if (!resp.isSuccessful) return@use null
                val json = org.json.JSONObject(resp.body?.string() ?: return@use null)
                val addr = json.optJSONObject("address") ?: return@use null
                addr.optString("city").takeIf { it.isNotBlank() }
                    ?: addr.optString("town").takeIf { it.isNotBlank() }
                    ?: addr.optString("village").takeIf { it.isNotBlank() }
                    ?: addr.optString("county").takeIf { it.isNotBlank() }
            }
        } catch (e: Exception) { null }
    }
    @PluginMethod
    fun invokeTool(call: PluginCall) {
        val group = call.getString("group") ?: ""
        val name = call.getString("name") ?: ""
        val params = call.getObject("params") ?: JSObject()
        io.execute {
            try {
                val res = runner.run(group, name, params)
                call.resolve(JSObject(res.toString()))
            } catch (e: Exception) {
                call.resolve(JSObject()
                    .put("ok", false)
                    .put("error", e.message ?: e.toString())
                    .put("tool", name))
            }
        }
    }

    // ── Device context ─────────────────────────────────────────────────────
    @PluginMethod
    fun deviceStatus(call: PluginCall) {
        call.resolve(JSObject(platform.deviceStatus().toString()))
    }

    @PluginMethod
    fun sensorsList(call: PluginCall) {
        call.resolve(JSObject(platform.sensorsList().toString()))
    }

    // ── Local chat history (future native-proof) ───────────────────────────
    @PluginMethod
    fun chatHistoryLoad(call: PluginCall) {
        val f = File(context.filesDir, "chat_history.json")
        if (!f.exists()) {
            call.resolve(JSObject("{}"))
            return
        }
        io.execute {
            try {
                call.resolve(JSObject(f.readText()))
            } catch (e: Exception) {
                call.reject(e.message ?: "read failed", e)
            }
        }
    }

    @PluginMethod
    fun chatHistorySave(call: PluginCall) {
        val data = call.getString("data") ?: "{}"
        val f = File(context.filesDir, "chat_history.json")
        io.execute {
            try {
                f.writeText(data)
                call.resolve(JSObject().put("ok", true))
            } catch (e: Exception) {
                call.reject(e.message ?: "write failed", e)
            }
        }
    }

    // ── Memories (native, server'sız) ─────────────────────────────────────
    @PluginMethod
    fun listMemory(call: PluginCall) {
        if (wantsServer() && server.configured()) {
            io.execute {
                try {
                    val all = server.listMemories()
                    val page = org.json.JSONArray()
                    val uid = server.userId
                    for (i in 0 until all.length()) page.put(all.getJSONObject(i).put("user_id", uid).put("count", all.length()))
                    call.resolve(JSObject()
                        .put("user_id", uid)
                        .put("count", all.length())
                        .put("limit", 200)
                        .put("offset", 0)
                        .put("memories", page))
                } catch (e: Exception) {
                    call.resolve(JSObject().put("user_id", server.userId).put("count", 0).put("limit", 200).put("offset", 0).put("memories", org.json.JSONArray()))
                }
            }
            return
        }
        val limit = call.getInt("limit", 50) ?: 50
        val offset = call.getInt("offset", 0) ?: 0
        val all = local.listMemory().optJSONArray("memories")
        val page = org.json.JSONArray()
        for (i in offset until limit.coerceAtMost(all?.length() ?: 0)) {
            val o = all?.getJSONObject(i)?.put("importance", 5)
            if (o != null) page.put(o)
        }
        call.resolve(JSObject()
            .put("user_id", call.getString("user_id") ?: "default")
            .put("count", all?.length() ?: 0)
            .put("limit", limit)
            .put("offset", offset)
            .put("memories", page))
    }

    @PluginMethod
    fun deleteMemory(call: PluginCall) {
        val id = call.getString("id") ?: ""
        if (wantsServer() && server.configured()) {
            io.execute {
                try {
                    val ok = server.deleteMemoryRow(id)
                    call.resolve(JSObject().put("status", if (ok) "success" else "error")
                        .put("message", if (ok) "Memory deleted." else "Memory not found."))
                } catch (e: Exception) {
                    call.resolve(JSObject().put("status", "error").put("message", e.message ?: "error"))
                }
            }
            return
        }
        val ok = local.deleteMemory(id)
        call.resolve(JSObject().put("status", if (ok) "success" else "error")
            .put("message", if (ok) "Memory deleted." else "Memory not found."))
    }

    // ── Runtime permissions (Android özellikleri için tek seferlik izin) ──
    private fun permFor(kind: String): String? = when (kind) {
        "calendar" -> Manifest.permission.WRITE_CALENDAR
        "microphone" -> Manifest.permission.RECORD_AUDIO
        "location" -> Manifest.permission.ACCESS_FINE_LOCATION
        else -> null
    }

    @PluginMethod
    fun requestPermission(call: PluginCall) {
        val kind = call.getString("kind") ?: "calendar"
        val perm = permFor(kind)
        if (perm == null) {
            call.resolve(JSObject().put("status", "not-requestable").put("kind", kind))
            return
        }
        val activity = getActivity()
        if (activity == null) {
            call.resolve(JSObject().put("status", "no-activity").put("kind", kind))
            return
        }
        if (ContextCompat.checkSelfPermission(context, perm) == PackageManager.PERMISSION_GRANTED) {
            call.resolve(JSObject().put("status", "granted").put("kind", kind))
            return
        }
        androidx.core.app.ActivityCompat.requestPermissions(activity, arrayOf(perm), 1001)
        call.resolve(JSObject().put("status", "requested").put("kind", kind))
    }

    @PluginMethod
    fun permissionStatus(call: PluginCall) {
        val out = JSObject()
        for (k in listOf("calendar", "microphone", "location")) {
            val p = permFor(k)
            out.put(k, p != null && ContextCompat.checkSelfPermission(context, p) == PackageManager.PERMISSION_GRANTED)
        }
        call.resolve(out)
    }

// ── LLM (LiteRT-LM / Gemma E2B) ───────────────────────────────────────
    @PluginMethod
    fun modelStatus(call: PluginCall) {
        val s = JSObject(llm.status().toString())
        val dl = downloader.status()
        s.put("downloading", dl.optBoolean("downloading"))
            .put("model_size", dl.optLong("size"))
        call.resolve(s)
    }

    @PluginMethod
    fun modelDownloadStatus(call: PluginCall) {
        call.resolve(js(
            downloader.status().put(
                "targets",
                org.json.JSONArray(downloader.targets().map { t ->
                    JSObject().put("id", t.id).put("url", t.url).put("model", t.modelName)
                })
            )))
    }

    @PluginMethod
    fun startModelDownload(call: PluginCall) {
        val targetId = call.getString("target")
        io.execute {
            var lastEmit = 0L
            val r = downloader.download(targetId) { p ->
                val now = System.currentTimeMillis()
                if (p.state == "done" || now - lastEmit > 500) {
                    lastEmit = now
                    emit("modelProgress", JSObject()
                        .put("bytes", p.bytesRead)
                        .put("total", p.bytesTotal)
                        .put("percentage", if (p.bytesTotal > 0) (p.bytesRead * 100 / p.bytesTotal).toInt() else 0)
                        .put("state", p.state))
                }
            }
            if (r.cancelled) {
                emit("modelProgress", JSObject().put("state", "cancelled"))
                call.resolve(JSObject().put("ok", false).put("error", "cancelled"))
            } else if (r.path != null) {
                emit("modelProgress", JSObject()
                    .put("state", "done")
                    .put("model", store.get("LLM_MODEL"))
                    .put("path", r.path))
                call.resolve(JSObject().put("ok", true).put("path", r.path))
            } else {
                emit("modelProgress", JSObject().put("state", "failed"))
                call.resolve(JSObject().put("ok", false).put("error", "download failed"))
            }
        }
    }

    @PluginMethod
    fun cancelModelDownload(call: PluginCall) {
        downloader.cancel()
        call.resolve(JSObject().put("ok", true))
    }

    @PluginMethod
    fun chatStream(call: PluginCall) {
        val payload = call.getObject("payload") ?: call.getObject("data") ?: JSObject()
        io.execute {
            try {
                // ── Remote LLM (only-server mode) ──────────────────────────────────
                if (wantsServer() && server.configured()) {
                    // No local model needed: forward the prompt to the Python server
                    // and relay its SSE events to the JS chatEvent listener.
                    val userText = payload.optString("message", "")
                    if (userText.isBlank()) {
                        emit("chatEvent", JSObject().put("error", "Mesaj boş."))
                        call.resolve(JSObject().put("ok", false))
                        return@execute
                    }
                    val msgArr = payload.optJSONArray("messages")
                    val messages = JSONArray()
                    if (msgArr != null) {
                        for (i in 0 until msgArr.length()) messages.put(msgArr.getJSONObject(i))
                    }
                    val body = JSONObject()
                        .put("message", userText)
                        .put("session_id", payload.optString("session_id", ""))
                        .put("user_id", store.get("SERVER_USER").ifBlank { store.get("ASSISTANT_USER").ifBlank { "default" } })
                    if (messages.length() > 0) body.put("messages", messages)
                    if (payload.has("images")) body.put("images", payload.opt("images"))
                    try {
                        server.chatStreamSSE(body) { evt ->
                            // Server uses {token:...}, {done:...}, {error:...} etc — relay as-is.
                            emit("chatEvent", JSObject(evt.toString()))
                        }
                        call.resolve(JSObject().put("ok", true).put("remote", true))
                    } catch (e: Exception) {
                        emit("chatEvent", JSObject().put("error", "Sunucu hatası: ${e.message ?: e.toString()}"))
                        call.resolve(JSObject().put("ok", false).put("error", e.message ?: e.toString()))
                    }
                    return@execute
                }

                if (!llm.ensureLoaded()) {
                    val p = llm.findModel()
                    emit("chatEvent", JSObject().put("error", if (p == null)
                        "Yerel model bulunamadı. Ayarlar → Zeka'dan model seçin veya cihaza bir .litertlm dosyası ekleyin."
                    else "Model yüklenemedi: $p"))
                    call.resolve(JSObject().put("ok", false).put("error", "model not loaded"))
                    return@execute
                }

                val msgArr = payload.optJSONArray("messages")
                val system = payload.optString("system", "")
                val userText = payload.optString("message", "")
                val sessionId = payload.optString("session_id", "")
                val history = ArrayList<Pair<String, String>>()
                if (msgArr != null) {
                    for (i in 0 until msgArr.length()) {
                        val o = msgArr.getJSONObject(i)
                        val role = o.optString("role")
                        val content = o.optString("content")
                        if (content.isNotBlank() && (role == "assistant" || role == "user")) {
                            history.add(Pair(role, content))
                        }
                    }
                }

                val text = StringBuilder()
                val g = llm.chat(system, sessionId, history, userText) { chunk ->
                    text.append(chunk)
                    emit("chatEvent", JSObject().put("token", chunk))
                }
                val finalText = text.toString().trim()

                if (finalText.isBlank()) {
                    emit("chatEvent", JSObject().put("error", "Model boş yanıt döndürdü."))
                    call.resolve(JSObject().put("ok", false).put("error", "empty"))
                    return@execute
                }
                emit("chatEvent", JSObject()
                    .put("done", true)
                    .put("session_id", sessionId)
                    .put("message_id", "local-${UUID.randomUUID().toString().take(8)}")
                    .put("memories_saved", 0)
                    .put("retrieved_count", 0)
                    .put("tokens", g.tokens)
                    .put("tps", g.tps))
                call.resolve(JSObject()
                    .put("ok", true)
                    .put("tokens", g.tokens)
                    .put("tps", g.tps)
                    .put("prompt_ms", g.promptMs)
                    .put("gen_ms", g.genMs))
            } catch (ce: IllegalStateException) {
                emit("chatEvent", JSObject().put("error", ce.message ?: "Model yüklü değil"))
                call.resolve(JSObject().put("ok", false).put("error", ce.message))
            } catch (e: Exception) {
                emit("chatEvent", JSObject().put("error", e.message ?: e.toString()))
                call.resolve(JSObject().put("ok", false).put("error", e.message))
            }
        }
    }

    private fun emit(event: String, data: JSObject) {
        try {
            notifyListeners(event, data)
        } catch (e: Exception) {
        }
    }
}