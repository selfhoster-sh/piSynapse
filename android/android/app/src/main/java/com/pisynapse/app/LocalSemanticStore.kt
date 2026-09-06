package com.pisynapse.app

import android.content.Context
import android.util.Base64
import org.json.JSONArray
import org.json.JSONObject
import java.io.File

/**
 * Device-side semantic index over chat messages and memories, plus a small
 * "tools for query" corpus router — the local analog of the server's embedding
 * consumers (save/search messages & memories, memory dedup, history retrieval,
 * intent tool-corpus, warmup).
 *
 * Vectors are produced by [EmbeddingEngine] (mpnet, dim 768) and persisted
 * side-by-side in semantic_index.json so offline search keeps working.
 */
class LocalSemanticStore private constructor(
    private val ctx: Context,
    private val engine: EmbeddingEngine = EmbeddingEngine.instance(ctx),
) {

    companion object {
        const val MEMORY_DEDUP_THRESHOLD = 0.68f
        const val INDEX_VERSION = 1

        @Volatile
        private var inst: LocalSemanticStore? = null

        fun instance(ctx: Context): LocalSemanticStore =
            inst ?: synchronized(this) {
                inst ?: LocalSemanticStore(ctx.applicationContext).also { inst = it }
            }
    }

    data class Item(val id: String, val text: String, val vec: FloatArray? = null)

    @Volatile
    private var messages: List<Item> = emptyList()

    @Volatile
    private var memories: List<Item> = emptyList()

    @Volatile
    private var toolDesc: List<Pair<String, String>> = emptyList()

    @Volatile
    private var toolVecs: List<Pair<String, FloatArray>> = emptyList()

    @Volatile
    var ready: Boolean = false
        private set

    @Volatile
    var initError: String? = null
        private set

    @Volatile
    var modelMissing: Boolean = false
        private set

    @Volatile
    var toolCount: Int = 0
        private set

    private val lock = Any()

    private val indexFile: File = File(ctx.filesDir, "semantic_index.json")

    fun setToolDescriptions(tools: List<Pair<String, String>>) {
        toolDesc = tools
        if (ready) {
            rebuildToolVecs()
        }
        toolCount = tools.size
    }

    private fun rebuildToolVecs() {
        if (!ready) return
        val out = mutableListOf<Pair<String, FloatArray>>()
        for ((name, desc) in toolDesc) {
            val v = engine.embed("$name: $desc") ?: continue
            out.add(Pair(name, v))
        }
        toolVecs = out
    }

    /** Ensure the model + index are usable. Returns null on success or error text. */
    fun ensureReady(): String? {
        if (ready && engine.ready) return null
        initError = null
        modelMissing = false
        when (val err = engine.ensureReady()) {
            "model-missing" -> {
                modelMissing = true
                initError = "model-missing"
                return initError
            }
            null -> {}
            else -> {
                initError = err
                return initError
            }
        }
        synchronized(lock) {
            loadIndex()
            if (toolDesc.isNotEmpty()) rebuildToolVecs()
            ready = true
        }
        return null
    }

    // ── Persistence ────────────────────────────────────────────────────────
    private fun loadIndex() {
        if (!indexFile.exists()) return
        try {
            val js = JSONObject(indexFile.readText())
            if (js.optInt("v", 0) != INDEX_VERSION) return
            messages = parseItems(js.optJSONArray("messages"))
            memories = parseItems(js.optJSONArray("memories"))
        } catch (e: Exception) {
            // corrupt index — start clean
        }
    }

    private fun parseItems(arr: JSONArray?): List<Item> {
        if (arr == null) return emptyList()
        val out = ArrayList<Item>(arr.length())
        for (i in 0 until arr.length()) {
            val o = arr.getJSONObject(i)
            out.add(Item(o.optString("id"), o.optString("text"), decodeVar(o.optString("e"))))
        }
        return out
    }

    private fun persist() {
        try {
            val js = JSONObject().put("v", INDEX_VERSION)
                .put("messages", itemsJson(messages))
                .put("memories", itemsJson(memories))
            indexFile.parentFile?.mkdirs()
            indexFile.writeText(js.toString())
        } catch (e: Exception) {
        }
    }

    private fun itemsJson(items: List<Item>): JSONArray {
        val arr = JSONArray()
        for (i in items) {
            val v = i.vec ?: continue
            arr.put(JSONObject().put("id", i.id).put("text", i.text).put("e", encodeVar(v)))
        }
        return arr
    }

    private fun encodeVar(v: FloatArray): String {
        val b = ByteArray(v.size * 4)
        for (i in v.indices) {
            val bits = java.lang.Float.floatToIntBits(v[i])
            b[i * 4] = (bits ushr 24).toByte()
            b[i * 4 + 1] = (bits ushr 16).toByte()
            b[i * 4 + 2] = (bits ushr 8).toByte()
            b[i * 4 + 3] = bits.toByte()
        }
        return Base64.encodeToString(b, Base64.NO_WRAP)
    }

    private fun decodeVar(s: String): FloatArray? {
        if (s.isEmpty()) return null
        return try {
            val b = Base64.decode(s, Base64.NO_WRAP)
            if (b.size % 4 != 0) return null
            FloatArray(b.size / 4) { i ->
                val bits = (b[i * 4].toInt() shl 24) or (b[i * 4 + 1].toInt() shl 16) or
                    (b[i * 4 + 2].toInt() shl 8) or (b[i * 4 + 3].toInt() and 0xFF)
                java.lang.Float.intBitsToFloat(bits)
            }
        } catch (e: Exception) {
            null
        }
    }

    // ── Writes ─────────────────────────────────────────────────────────────
    /** Embed + remember a chat message (user or assistant turn). */
    fun rememberMessage(id: String, text: String) {
        if (!ready || text.isBlank()) return
        val v = engine.embed(text) ?: return
        synchronized(lock) {
            messages = messages.filterNot { it.id == id } + Item(id, text, v)
            if (messages.size > 3000) messages = messages.drop(messages.size - 3000)
            persist()
        }
    }

    fun rememberMemory(id: String, text: String) {
        if (!ready || text.isBlank()) return
        val v = engine.embed(text) ?: return
        synchronized(lock) {
            memories = memories.filterNot { it.id == id } + Item(id, text, v)
            persist()
        }
    }

    fun dropMemory(id: String) {
        synchronized(lock) {
            val before = memories.size
            memories = memories.filterNot { it.id == id }
            if (memories.size != before) persist()
        }
    }

    /** Returns the id of a semantically near-duplicate memory (>= threshold) or null. */
    fun duplicateMemoryId(text: String): String? {
        if (!ready || text.isBlank()) return null
        val thr = ConfigStore(ctx).getFloat("MEMORY_SIMILARITY_THRESHOLD", MEMORY_DEDUP_THRESHOLD)
            .coerceIn(0f, 1f)
        val q = engine.embed(text) ?: return null
        val src = memories
        for (m in src) {
            val v = m.vec ?: continue
            if (EmbeddingEngine.cosine(q, v) >= thr) return m.id
        }
        return null
    }

    // ── Reads ──────────────────────────────────────────────────────────────
    fun searchMessages(query: String, topK: Int): List<Pair<Item, Float>> = rank(query, messages, topK)

    fun searchMemories(query: String, topK: Int): List<Pair<Item, Float>> = rank(query, memories, topK)

    private fun rank(query: String, items: List<Item>, topK: Int): List<Pair<Item, Float>> {
        if (!ready || items.isEmpty() || query.isBlank()) return emptyList()
        val q = engine.embed(query) ?: return emptyList()
        val scored = ArrayList<Pair<Item, Float>>(items.size)
        for (i in items) {
            val v = i.vec ?: continue
            scored.add(Pair(i, EmbeddingEngine.cosine(q, v)))
        }
        scored.sortByDescending { it.second }
        return scored.take(topK.coerceAtLeast(1))
    }

    /** Combined messages+memories for context retrieval (used before a local chat). */
    fun relevantContext(query: String, topKMessages: Int, topKMemories: Int): List<String> {
        if (!ready || query.isBlank()) return emptyList()
        val out = ArrayList<String>()
        for (m in searchMemories(query, topKMemories)) out.add("[Bellek] ${m.first.text}")
        for (m in searchMessages(query, topKMessages)) out.add("[Geçmiş] ${m.first.text}")
        return out
    }

    /** Nearest tool by embedding of the tool corpus (intent/tool-call assist). */
    fun toolsForQuery(query: String): Pair<String, Float>? {
        if (!ready || query.isBlank()) return null
        if (toolVecs.isEmpty() && toolDesc.isNotEmpty()) rebuildToolVecs()
        if (toolVecs.isEmpty()) return null
        val q = engine.embed(query) ?: return null
        var best: Pair<String, Float>? = null
        for ((name, v) in toolVecs) {
            val s = EmbeddingEngine.cosine(q, v)
            if (best == null || s > best.second) best = Pair(name, s)
        }
        return best
    }

    fun status(): JSONObject = JSONObject()
        .put("ready", ready)
        .put("model_missing", modelMissing)
        .put("error", initError ?: "")
        .put("model_exists", engine.modelLocalFile.exists())
        .put("model_size", engine.modelLocalFile.length())
        .put("model_dim", EmbeddingEngine.DIM)
        .put("messages", messages.size)
        .put("memories", memories.size)
        .put("tools", toolCount)
}