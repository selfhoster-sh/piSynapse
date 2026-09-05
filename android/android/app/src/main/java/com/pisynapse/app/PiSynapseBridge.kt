package com.pisynapse.app

import com.getcapacitor.JSObject
import com.getcapacitor.Plugin
import com.getcapacitor.PluginCall
import com.getcapacitor.PluginMethod
import com.getcapacitor.annotation.CapacitorPlugin
import org.json.JSONObject
import java.io.File
import java.util.UUID
import java.util.concurrent.ExecutorService
import java.util.concurrent.Executors

@CapacitorPlugin(name = "PiSynapse")
class PiSynapseBridge : Plugin() {

    private val store get() = ConfigStore(context)
    private val weather get() = WeatherClient(store)
    private val notes get() = NotesClient(store)
    private val local get() = LocalStore(context)
    private val platform get() = PlatformTools(context)
    private val runner by lazy { ToolRunner(store, weather, notes, local, platform) }
    private val llm by lazy { LlmEngine(context, store, PiTools(runner).providers()) }

    private val io: ExecutorService = Executors.newCachedThreadPool()

    private fun js(o: JSONObject): JSObject = JSObject(o.toString())

    override fun load() {
        super.load()
        try {
            io.execute {
                try {
                    llm.ensureLoaded()
                } catch (t: Throwable) {}
            }
        } catch (t: Throwable) {}
    }

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

    // ── Generic tool dispatcher ────────────────────────────────────────────
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
        call.resolve(JSObject(if (f.exists()) f.readText() else "{}"))
    }

    @PluginMethod
    fun chatHistorySave(call: PluginCall) {
        val data = call.getString("data") ?: "{}"
        val f = File(context.filesDir, "chat_history.json")
        try {
            f.writeText(data)
            call.resolve(JSObject().put("ok", true))
        } catch (e: Exception) {
            call.reject(e.message ?: "write failed", e)
        }
    }

    // ── LLM (LiteRT-LM / Gemma E2B) ───────────────────────────────────────
    @PluginMethod
    fun modelStatus(call: PluginCall) {
        call.resolve(JSObject(llm.status().toString()))
    }

    @PluginMethod
    fun chatStream(call: PluginCall) {
        val payload = call.getObject("payload") ?: call.getObject("data") ?: JSObject()
        io.execute {
            try {
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