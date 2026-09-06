package com.pisynapse.app

import ai.onnxruntime.OnnxTensor
import ai.onnxruntime.OrtEnvironment
import ai.onnxruntime.OrtSession
import android.content.Context
import org.json.JSONObject
import java.io.File
import java.text.Normalizer

/**
 * Local text embeddings via ONNX Runtime (mpnet multilingual, dim 768).
 *
 * Tokenizer: hand-ported SentencePiece Unigram (paraphrase-multilingual-mpnet-base-v2),
 * matches the reference `tokenizers` ids for everyday text. Embedding = mean-pooled,
 * L2-normalized `last_hidden_state` — same recipe the server FastEmbed model uses.
 *
 * Resolution of the model file (download if absent) is handled by the caller
 * (ModelDownloader preset + LocalSemanticStore orchestration).
 */
class EmbeddingEngine private constructor(
    private val ctx: Context,
) {

    companion object Cosine {
        const val DIM = 768
        const val MAX_LEN = 512
        const val MODEL_NAME = "mpnet_qint8.onnx"

        @Volatile
        private var inst: EmbeddingEngine? = null

        fun instance(ctx: Context): EmbeddingEngine =
            inst ?: synchronized(this) {
                inst ?: EmbeddingEngine(ctx).also { inst = it }
            }

        fun cosine(a: FloatArray, b: FloatArray): Float {
            if (a.size != b.size || a.isEmpty()) return 0f
            var dot = 0.0
            for (i in a.indices) dot += a[i] * b[i].toDouble()
            return kotlin.math.min(1.0, kotlin.math.max(-1.0, dot)).toFloat()
        }
    }

    // ── Tokenizer data ─────────────────────────────────────────────────────
    private class TokenizerData(val vocab: Array<String>, val idOf: HashMap<String, Int>, val scores: FloatArray)

    @Volatile
    private var tok: TokenizerData? = null

    @Volatile
    private var session: OrtSession? = null

    @Volatile
    private var env: OrtEnvironment? = null

    @Volatile
    var ready: Boolean = false
        private set

    @Volatile
    var initError: String? = null
        private set

    val modelLocalFile: File
        get() = File(File(ctx.filesDir, "models"), MODEL_NAME)

    /** Tokenizer JSON is packaged under assets/mpnet_tokenizer.json. */
    fun tokenizerFromAssets(): Boolean {
        return try {
            val js = JSONObject(ctx.assets.open("mpnet_tokenizer.json").bufferedReader().use { it.readText() })
            val model = js.getJSONObject("model").getJSONArray("vocab")
            val n = model.length()
            val vocab = Array<String>(n) { "" }
            val scores = FloatArray(n)
            val idOf = HashMap<String, Int>(n)
            for (i in 0 until n) {
                val e = model.getJSONArray(i)
                val piece = e.getString(0)
                vocab[i] = piece
                idOf[piece] = i
                scores[i] = e.optDouble(1, -10.0).toFloat()
            }
            tok = TokenizerData(vocab, idOf, scores)
            true
        } catch (e: Exception) {
            initError = "tokenizer: ${e.message}"
            false
        }
    }

    /** Lazily (re)build the ONNX session. Returns null on success, else error text. */
    fun ensureReady(): String? {
        if (ready && session != null) return null
        initError = null
        if (tok == null && !tokenizerFromAssets()) return initError
        val f = modelLocalFile
        if (!f.exists() || f.length() == 0L) {
            initError = "model-missing"
            return initError
        }
        return try {
            if (env == null) {
                env = OrtEnvironment.getEnvironment()
            }
            val e = env!!
            val opts = OrtSession.SessionOptions()
            opts.setIntraOpNumThreads(2)
            val s = e.createSession(f.absolutePath, opts)
            session?.close()
            session = s
            ready = true
            null
        } catch (e: Exception) {
            initError = "ort: ${e.message}"
            initError
        }
    }

    // ── Tokenization (SentencePiece Unigram port) ──────────────────────────
    private val UNK_ID = 3
    private val CLS_ID = 0
    private val SEP_ID = 2
    private val UNK_SCORE = -10.0f

    data class Encoded(val ids: LongArray, val mask: LongArray)

    private fun bestSegment(word: String, td: TokenizerData): List<String> {
        val n = word.length
        val score = arrayOfNulls<Float>(n + 1)
        val path = arrayOfNulls<List<String>>(n + 1)
        score[0] = 0f
        path[0] = emptyList()
        for (i in 1..n) {
            var best: Pair<Float, List<String>>? = null
            for (j in (i - 16).coerceAtLeast(0) until i) {
                val pre = score[j] ?: continue
                val piece = word.substring(j, i)
                val idOf = td.idOf
                val sc = if (piece in idOf) td.scores[idOf.getValue(piece)] else Float.NaN
                if (sc.isNaN()) continue
                val cand = pre + sc
                if (best == null || cand > best.first) {
                    best = Pair(cand, (path[j]!!).plus(piece))
                }
            }
            if (best == null) {
                val pre = score[i - 1]
                if (pre != null) best = Pair(pre + UNK_SCORE, (path[i - 1]!!).plus(word.substring(i - 1, i)))
            }
            if (best != null) {
                score[i] = best.first
                path[i] = best.second
            }
        }
        return path[n] ?: listOf(word)
    }

    fun tokenize(text: String): Encoded {
        val td = tok ?: return Encoded(longArrayOf(CLS_ID.toLong(), SEP_ID.toLong()), LongArray(2) { 1 })
        val norm = Normalizer.normalize(text, Normalizer.Form.NFKC).trim()
        val s = if (norm.startsWith(" ")) norm else " $norm"
        val ids = ArrayList<Int>(64)
        ids.add(CLS_ID)
        var done = false
        for (w in s.split(Regex("\\s+"))) {
            if (w.isEmpty()) continue
            for (piece in bestSegment("▁$w", td)) {
                val t = piece in td.idOf
                if (t && td.idOf.getValue(piece) != UNK_ID) {
                    ids.add(td.idOf.getValue(piece))
                } else {
                    if (ids.last() != UNK_ID) ids.add(UNK_ID)
                }
                if (ids.size >= MAX_LEN - 1) { done = true; break }
            }
            if (done) break
        }
        if (ids.size > MAX_LEN - 1) {
            // keep prefix, drop tail
            for (k in MAX_LEN - 1 until ids.size) ids.removeAt(MAX_LEN - 1)
        }
        ids.add(SEP_ID)
        val out = LongArray(ids.size)
        val mask = LongArray(ids.size) { 1 }
        for (i in ids.indices) out[i] = ids[i].toLong()
        return Encoded(out, mask)
    }

    // ── Inference ──────────────────────────────────────────────────────────
    fun embed(text: String): FloatArray? {
        if (ensureReady() != null) return null
        val e = env!!
        val s = session ?: return null
        val enc = tokenize(text)
        val inputIds = OnnxTensor.createTensor(e, java.nio.LongBuffer.wrap(enc.ids), longArrayOf(1, enc.ids.size.toLong()))
        val mask = OnnxTensor.createTensor(e, java.nio.LongBuffer.wrap(enc.mask), longArrayOf(1, enc.mask.size.toLong()))
        return try {
            val res = s.run(mapOf("input_ids" to inputIds, "attention_mask" to mask))
            try {
                val hidden = res.get(0).value as Array<Array<FloatArray>>
                val states = hidden[0] // [seq, 768]
                val n = states.size
                val dim = states[0].size
                val pooled = FloatArray(dim)
                for (i in 0 until n) {
                    for (d in 0 until dim) pooled[d] += states[i][d]
                }
                val cnt = n.toFloat().coerceAtLeast(1f)
                for (d in 0 until dim) pooled[d] = pooled[d] / cnt
                var norm = 0.0
                for (d in 0 until dim) norm += (pooled[d] * pooled[d]).toDouble()
                norm = kotlin.math.sqrt(norm)
                if (norm > 1e-9) for (d in 0 until dim) pooled[d] = (pooled[d] / norm).toFloat()
                pooled
            } finally {
                res.close()
            }
        } finally {
            inputIds.close()
            mask.close()
        }
    }
}