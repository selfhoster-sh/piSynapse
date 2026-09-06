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
import com.google.ai.edge.litertlm.ThinkingConfig
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
    @Volatile private var lastUsedAtMs: Long = 0L
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
        val loaded = engine?.isInitialized() == true && loadedPath == p
        val keepAlive = keepAliveMs()
        return JSONObject()
            .put("available", p != null)
            .put("model_path", p)
            .put("model_file", p?.let { File(it).name })
            .put("configured", cfg.get("LLM_MODEL"))
            .put("loaded", loaded)
            .put("loaded_seconds", if (loaded) (System.currentTimeMillis() - lastUsedAtMs) / 1000 else 0)
            .put("keep_alive", cfg.get("LLM_KEEP_ALIVE"))
            .put("keep_alive_ms", keepAlive)
            .put("ok", true)
    }

    /** Auto-release deadline: how long the native model stays resident after last use. */
    fun keepAliveMs(): Long {
        val raw = cfg.get("LLM_KEEP_ALIVE").trim().lowercase().replace(" ", "")
        if (raw.isEmpty() || raw == "0" || raw == "never") return 0L
        val v = raw.removeSuffix("ms").takeIf { raw.endsWith("ms") }?.toLongOrNull()
            ?: raw.removeSuffix("s").takeIf { raw.endsWith("s") }?.toLongOrNull()?.times(1000)
            ?: raw.removeSuffix("m").takeIf { raw.endsWith("m") }?.toLongOrNull()?.times(60_000)
            ?: raw.removeSuffix("h").takeIf { raw.endsWith("h") }?.toLongOrNull()?.times(3_600_000)
            ?: return 0L
        return v.coerceAtLeast(1)
    }

    fun isLoaded(): Boolean = engine?.isInitialized() == true && loadedPath != null

    fun lastUsedAt(): Long = lastUsedAtMs

    fun markUsed() {
        lastUsedAtMs = System.currentTimeMillis()
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
                lastUsedAtMs = System.currentTimeMillis()
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
                    conversation = e.createConversation(conversationConfig("", emptyList(), sampler(), null))
                    convKey = null
                } catch (t: Throwable) {}
            }
            markUsed()
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

    private fun conversationConfig(
        system: String, history: List<Message>, sampler: SamplerConfig,
        thinking: ThinkingConfig? = null,
    ): ConversationConfig =
        ConversationConfig(
            systemInstruction = Contents.of(system),
            initialMessages = history.takeLast(16),
            tools = toolProviders,
            samplerConfig = sampler,
            automaticToolCalling = true,
            thinkingConfig = thinking,
            maxOutputToken = maxTokens()
        )

    data class Generation(val text: String, val reasoning: String, val tokens: Int, val tps: Float, val promptMs: Long, val genMs: Long)

    fun chat(
        system: String, sessionId: String, history: List<Pair<String, String>>, user: String,
        think: Boolean = false, reasoningEffort: String = "",
        emitChunk: (String) -> Unit, emitReasoning: (String) -> Unit,
    ): Generation {
        return synchronized(lock) {
            val e = engine ?: throw IllegalStateException("Model yüklü değil")
            val key = (sessionId.ifBlank { "default" }) + ":" + think
            val conv = getConversation(e, key, system, history, think, reasoningEffort)
            val t0 = System.currentTimeMillis()
            val buf = StringBuilder()
            val reasonBuf = StringBuilder()
            var shown = 0
            var reasonShown = 0
            runBlocking {
                conv.sendMessageAsync(user).collect { msg ->
                    val thought = msg.channels["thought"]
                    if (!thought.isNullOrEmpty()) {
                        reasonBuf.append(thought)
                        if (reasonBuf.length > reasonShown) {
                            val delta = reasonBuf.substring(reasonShown)
                            reasonShown = reasonBuf.length
                            if (delta.isNotEmpty()) emitReasoning(delta)
                        }
                    }
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
            markUsed()
            val text = buf.toString().trim()
            val reasoning = reasonBuf.toString().trim()
            val tokens = ((text.length + reasoning.length) / 4).coerceAtLeast(1)
            Generation(text, reasoning, tokens, tokens.toFloat() / (genMs / 1000f).coerceAtLeast(0.1f), 0L, genMs)
        }
    }

    private fun thinkingConfig(think: Boolean, effort: String): ThinkingConfig? {
        if (!think) return null
        val budget = when (effort.trim().lowercase()) {
            "minimal" -> 256
            "low" -> 512
            "medium" -> 1024
            "high" -> 2048
            "max", "xhigh" -> 4096
            else -> 1024
        }
        return ThinkingConfig(enableThinking = true, thinkingTokenBudget = budget)
    }

    private fun getConversation(e: Engine, key: String, system: String, history: List<Pair<String, String>>, think: Boolean, effort: String): Conversation {
        val existing = conversation
        if (existing != null && convKey == key) return existing
        try { existing?.close() } catch (t: Throwable) {}
        val msgs = history.map { (role, content) ->
            when (role) {
                "assistant" -> Message.model(content)
                else -> Message.user(content)
            }
        }
        val c = e.createConversation(conversationConfig(system, msgs, sampler(), thinkingConfig(think, effort)))
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
        lastUsedAtMs = 0L
    }
}