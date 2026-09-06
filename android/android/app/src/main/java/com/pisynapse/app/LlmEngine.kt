package com.pisynapse.app

import android.content.Context
import com.google.ai.edge.litertlm.Backend
import com.google.ai.edge.litertlm.Conversation
import com.google.ai.edge.litertlm.ConversationConfig
import com.google.ai.edge.litertlm.Content
import com.google.ai.edge.litertlm.Contents
import com.google.ai.edge.litertlm.Engine
import com.google.ai.edge.litertlm.EngineConfig
import com.google.ai.edge.litertlm.Message
import com.google.ai.edge.litertlm.SamplerConfig
import com.google.ai.edge.litertlm.ToolProvider
import kotlinx.coroutines.flow.collect
import kotlinx.coroutines.runBlocking
import org.json.JSONObject
import java.io.File

class LlmEngine(
    private val ctx: Context,
    private val cfg: ConfigStore,
    private val toolProviders: List<ToolProvider>
) {

    @Volatile private var engine: Engine? = null
    @Volatile private var loadedPath: String? = null
    @Volatile private var conversation: Conversation? = null
    @Volatile private var convKey: String? = null
    private val lock = Any()

    fun findModel(): String? {
        val name = cfg.get("LLM_MODEL").trim()
        val dirs = mutableListOf<File>()
        ctx.getExternalFilesDir(null)?.let { dirs.add(File(it, "models")) }
        dirs.add(File(ctx.filesDir, "models"))
        for (d in dirs) {
            val files = d.listFiles { f -> f.extension == "litertlm" } ?: continue
            if (name.isNotEmpty()) {
                files.firstOrNull { it.name.contains(name, true) }?.let { return it.absolutePath }
            }
            return files.sortedByDescending { it.lastModified() }.firstOrNull()?.absolutePath
        }
        return null
    }

    fun status(): JSONObject {
        val p = findModel()
        return JSONObject()
            .put("available", p != null)
            .put("model_path", p)
            .put("model_file", p?.let { File(it).name })
            .put("configured", cfg.get("LLM_MODEL"))
            .put("loaded", engine?.isInitialized() == true && loadedPath == p)
            .put("ok", true)
    }

    fun ensureLoaded(): Boolean {
        val p = findModel() ?: return false
        synchronized(lock) {
            if (engine?.isInitialized() == true && loadedPath == p) return true
            releaseLocked()
            return try {
                val e = Engine(engineConfig(p))
                e.initialize()
                engine = e
                loadedPath = p
                e.isInitialized()
            } catch (t: Throwable) {
                releaseLocked()
                false
            }
        }
    }

    fun prewarm() {
        ensureLoaded()
        synchronized(lock) {
            val e = engine ?: return
            if (conversation == null) {
                try {
                    conversation = e.createConversation(conversationConfig("", emptyList(), sampler()))
                    convKey = null
                } catch (t: Throwable) {}
            }
        }
    }

    private fun backend(): Backend =
        when (cfg.get("LLM_BACKEND_TYPE")) {
            "gpu" -> Backend.GPU()
            "npu" -> Backend.NPU()
            else -> Backend.CPU()
        }

    private fun engineConfig(modelPath: String): EngineConfig {
        val b = backend()
        return EngineConfig(
            modelPath = modelPath,
            backend = b,
            visionBackend = b,
            audioBackend = b,
            maxNumTokens = maxTokens(),
            cacheDir = File(ctx.cacheDir, "litertlm").absolutePath
        )
    }

    private fun maxTokens(): Int =
        (cfg.getInt("LLM_NUM_CTX", 2048) + cfg.getInt("LLM_MAX_OUTPUT_TOKENS", 512))
            .coerceAtLeast(4096)
            .coerceAtMost(8192)

    private fun sampler(): SamplerConfig =
        SamplerConfig(
            topK = cfg.getInt("TOP_K", 40),
            topP = cfg.getFloat("TOP_P", 0.9f).toDouble(),
            temperature = cfg.getFloat("TEMPERATURE", 0.7f).toDouble(),
            seed = 42
        )

    private fun conversationConfig(system: String, history: List<Message>, sampler: SamplerConfig): ConversationConfig =
        ConversationConfig(
            systemInstruction = Contents.of(system),
            initialMessages = history.takeLast(16),
            tools = toolProviders,
            samplerConfig = sampler,
            automaticToolCalling = true
        )

    data class Generation(val text: String, val tokens: Int, val tps: Float, val promptMs: Long, val genMs: Long)

    fun chat(system: String, sessionId: String, history: List<Pair<String, String>>, user: String, emitChunk: (String) -> Unit): Generation {
        return synchronized(lock) {
            val e = engine ?: throw IllegalStateException("Model yüklü değil")
            val key = sessionId.ifBlank { "default" }
            val conv = getConversation(e, key, system, history)
            val t0 = System.currentTimeMillis()
            val buf = StringBuilder()
            var shown = 0
            runBlocking {
                conv.sendMessageAsync(user).collect { msg ->
                    msg.contents.contents.forEach { c ->
                        if (c is Content.Text && c.text.isNotEmpty()) {
                            buf.append(c.text)
                            if (buf.length > shown) {
                                val delta = buf.substring(shown)
                                shown = buf.length
                                if (delta.isNotEmpty()) emitChunk(delta)
                            }
                        }
                    }
                }
            }
            val genMs = System.currentTimeMillis() - t0
            val text = buf.toString().trim()
            val tokens = (text.length / 4).coerceAtLeast(1)
            Generation(text, tokens, tokens.toFloat() / (genMs / 1000f).coerceAtLeast(0.1f), 0L, genMs)
        }
    }

    private fun getConversation(e: Engine, key: String, system: String, history: List<Pair<String, String>>): Conversation {
        val existing = conversation
        if (existing != null && convKey == key) return existing
        try { existing?.close() } catch (t: Throwable) {}
        val msgs = history.map { (role, content) ->
            when (role) {
                "assistant" -> Message.model(content)
                else -> Message.user(content)
            }
        }
        val c = e.createConversation(conversationConfig(system, msgs, sampler()))
        conversation = c
        convKey = key
        return c
    }

    fun release() = synchronized(lock) { releaseLocked() }

    private fun releaseLocked() {
        try { conversation?.close() } catch (t: Throwable) {}
        conversation = null
        convKey = null
        try { engine?.close() } catch (t: Throwable) {}
        engine = null
        loadedPath = null
    }
}