package com.pisynapse.app

import android.content.Context
import com.google.ai.edge.litertlm.Backend
import com.google.ai.edge.litertlm.Conversation
import com.google.ai.edge.litertlm.ConversationConfig
import com.google.ai.edge.litertlm.Content
import com.google.ai.edge.litertlm.Contents
import com.google.ai.edge.litertlm.Engine
import com.google.ai.edge.litertlm.EngineConfig
import com.google.ai.edge.litertlm.ExperimentalApi
import com.google.ai.edge.litertlm.ExperimentalFlags
import com.google.ai.edge.litertlm.Message
import com.google.ai.edge.litertlm.SamplerConfig
import com.google.ai.edge.litertlm.ThinkingConfig
import com.google.ai.edge.litertlm.ToolProvider
import java.util.concurrent.atomic.AtomicBoolean
import kotlinx.coroutines.flow.collect
import kotlinx.coroutines.runBlocking
import org.json.JSONObject
import java.io.File

/**
 * Mirrors llm/chat.py SUMMARY_SYSTEM_PROMPT so the on-device rolling summary
 * behaves exactly like piServe's: update the existing summary with the new
 * messages, keep only facts useful for future context, drop raw tool-call
 * artifacts, honor contradictions with newer information, reply in the
 * conversation's language, output ONLY the updated summary.
 */
val SUMMARY_SYSTEM_PROMPT = (
    "You maintain a short running summary of an ongoing conversation between a " +
    "user and an AI assistant. Update the existing summary with the new messages " +
    "below, keeping only information useful for future context: facts about the " +
    "user, ongoing tasks, decisions and preferences. " +
    "Ignore and do not include any raw tool-call syntax, malformed tags, or system " +
    "artifacts that appear in the messages — these are bugs, not user content. " +
    "Only include information explicitly present in the messages — do not infer or " +
    "invent details. If new messages contradict the existing summary (e.g. the user " +
    "changed their mind or a decision was reversed), the newer information takes " +
    "priority — drop the outdated version rather than keeping both. " +
    "Keep it to a short paragraph, roughly 3-5 sentences. If the existing summary is " +
    "already long, COMPRESS it by merging redundant details and dropping outdated " +
    "information. " +
    "Reply in the same language as the conversation. Output ONLY the updated " +
    "summary text, with no preamble or extra commentary."
)

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
    private val busy = AtomicBoolean(false)
    private var mtpArmed = false

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
                if (!"off".equals(cfg.get("LLM_MTP"), ignoreCase = true)) armMtp()
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

    @OptIn(ExperimentalApi::class)
    private fun armMtp() {
        if (!mtpArmed) {
            ExperimentalFlags.enableSpeculativeDecoding = true
            mtpArmed = true
        }
    }

    private fun backend(): Backend =
        when (cfg.get("LLM_BACKEND_TYPE")) {
            "gpu" -> Backend.GPU()
            "npu" -> Backend.NPU()
            else -> Backend.CPU(
                threadCount = cfg.getInt("LLM_CPU_THREADS", 0).takeIf { it > 0 }
            )
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
        tools: Boolean = true,
    ): ConversationConfig =
        ConversationConfig(
            systemInstruction = Contents.of(system),
            initialMessages = history.takeLast(cfg.getInt("LLM_HISTORY_LIMIT", 40).coerceAtLeast(1)),
            tools = if (tools) toolProviders else emptyList(),
            samplerConfig = sampler,
            automaticToolCalling = tools,
            thinkingConfig = thinking,
            maxOutputToken = maxTokens()
        )

    // Tool-call leak patterns (parity with llm/utils.py strip_tool_leaks): a small
    // model may echo <|tool_call|>call:name{{...}}<tool_call|> as plain text.
    private val toolCallRangeRe = Regex(
        "<\\|?/?tool[|_]call\\|?>\\s*call:(\\w+)\\s*(?:\\{\\{?([^{}]*)\\}?\\})?\\s*<\\|?/?tool[|_]call\\|?>",
        RegexOption.DOT_MATCHES_ALL,
    )
    private val toolCallBareRe = Regex("\\bcall:(\\w+)\\s*(?:\\{\\{?([^{}]*)(?:\\}?\\})?)?")
    private val toolTagRe = Regex("<\\|?/?tool[|_]call\\|?>", RegexOption.IGNORE_CASE)

    /** Strip leaked tool-call artifacts from assistant text before it is folded into a summary. */
    fun sanitizeConversationText(text: String): String =
        text
            .replace(toolCallRangeRe, "")
            .replace(toolCallBareRe, "")
            .replace(toolTagRe, "")
            .replace(Regex("\\s+"), " ")
            .trim()

    /** Rolling summary: run SUMMARY_SYSTEM_PROMPT in a throwaway conversation. */
    fun summarize(system: String, transcript: String): String {
        if (transcript.isBlank()) return ""
        if (!busy.compareAndSet(false, true)) return ""
        val text = try {
            synchronized(lock) {
                val e = engine ?: return ""
                val c = e.createConversation(conversationConfig(system, emptyList(), sampler(), tools = false))
                val buf = StringBuilder()
                try {
                    runBlocking {
                        c.sendMessageAsync(transcript).collect { msg ->
                            msg.contents.contents.forEach { cc ->
                                if (cc is Content.Text && cc.text.isNotEmpty()) buf.append(cc.text)
                            }
                        }
                    }
                } finally {
                    try { c.close() } catch (t: Throwable) {}
                }
                markUsed()
                buf.toString().trim()
            }
        } finally {
            busy.set(false)
        }
        return sanitizeConversationText(text)
    }

    data class Generation(val text: String, val reasoning: String, val tokens: Int, val tps: Float, val promptMs: Long, val genMs: Long)

    fun chat(
        system: String, sessionId: String, history: List<Pair<String, String>>, user: String,
        think: Boolean = false, reasoningEffort: String = "", summaryRev: Long = 0,
        emitChunk: (String) -> Unit, emitReasoning: (String) -> Unit,
    ): Generation {
        if (!busy.compareAndSet(false, true)) {
            throw IllegalStateException("Model şu anda yanıt üretiyor, lütfen kısa bir süre sonra tekrar deneyin.")
        }
        return try {
        synchronized(lock) {
            val e = engine ?: throw IllegalStateException("Model yüklü değil")
            val key = (sessionId.ifBlank { "default" }) + ":" + think + ":s" + summaryRev
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
        } finally {
            busy.set(false)
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