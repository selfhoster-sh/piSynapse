package com.pisynapse.app

import android.content.Context
import okhttp3.OkHttpClient
import okhttp3.Request
import java.io.File
import java.io.RandomAccessFile
import java.io.InterruptedIOException
import java.util.concurrent.atomic.AtomicBoolean
import java.util.concurrent.TimeUnit
import org.json.JSONObject

/**
 * ModelDownloader — downloads a .litertlm model file into files/models/ with
 * HTTP Range resume support and progress callbacks.
 *
 * Resolvable targets (each yields an id + url + a model name to configure):
 *   1. ConfigStore MODEL_URL — a direct .litertlm URL (e.g. your own Pi server).
 *   2. A Hugging Face litert-community preset for the configured LLM_MODEL.
 *   3. The default preset (gemma-4-E2B-it) when nothing else matches, so a
 *      first-run download always has something to offer.
 */
class ModelDownloader(private val ctx: Context, private val cfg: ConfigStore) {

    private val client = OkHttpClient.Builder()
        .connectTimeout(30, TimeUnit.SECONDS)
        .readTimeout(60, TimeUnit.SECONDS)
        .followRedirects(true)
        .followSslRedirects(true)
        .build()

    val cancelFlag = AtomicBoolean(false)

    data class Target(val id: String, val url: String, val modelName: String)

    data class Progress(val bytesRead: Long, val bytesTotal: Long, val state: String)

    data class Result(val path: String?, val cancelled: Boolean)

    fun status(): JSONObject {
        val f = targetFile()
        return JSONObject()
            .put("exists", f.exists() && f.length() > 0)
            .put("size", if (f.exists()) f.length() else 0)
            .put("downloading", cancelFlag.get())
            .put("model", cfg.get("LLM_MODEL"))
    }

    fun cancel() {
        cancelFlag.set(true)
    }

    fun targets(): List<Target> {
        val out = mutableListOf<Target>()
        val custom = cfg.get("MODEL_URL").trim()
        if (custom.isNotEmpty()) {
            out.add(Target("custom", custom, ""))
        }
        val preset = presetFor(cfg.get("LLM_MODEL").trim())
        if (preset != null) {
            out.add(preset.first)
        } else {
            // Fall back to the recommended default so first-run download works
            // even with LLM_MODEL unset.
            PRESETS[DEFAULT_MODEL]?.let { (file, repo) ->
                out.add(Target(hfId(file), hfUrl(repo, file), DEFAULT_MODEL))
            }
        }
        return out
    }

    /**
     * Blocking download with chunks surfaced to [onProgress]. Returns the final
     * model file path, or null on failure/cancel.
     */
    fun download(targetId: String?, onProgress: (Progress) -> Unit): Result {
        val all = targets()
        val target = all.firstOrNull { it.id == targetId } ?: all.firstOrNull()
            ?: return Result(null, false)
        val file = targetFile()
        val r = downloadTo(target.url, file, onProgress)
        if (r.path != null && target.modelName.isNotEmpty() && cfg.get("LLM_MODEL") != target.modelName) {
            cfg.set("LLM_MODEL", target.modelName)
        }
        return r
    }

    /** Download the mpnet embedding model (ONNX) into files/models/ for EmbeddingEngine. */
    fun downloadEmbedding(onProgress: (Progress) -> Unit): Result {
        val f = File(File(ctx.filesDir, "models"), EmbeddingEngine.MODEL_NAME)
        val remote = "model_qint8_arm64.onnx"
        val base = "https://huggingface.co/sentence-transformers/paraphrase-multilingual-mpnet-base-v2"
        return downloadTo("$base/resolve/main/onnx/$remote?download=true", f, onProgress)
    }

    private fun downloadTo(url: String, file: File, onProgress: (Progress) -> Unit): Result {
        val tmp = File(file.parentFile, ".${file.name}.part")
        file.parentFile?.mkdirs()
        cancelFlag.set(false)

        val existing = if (tmp.exists() && tmp.length() > 0) tmp.length() else 0L
        try {
            val start = existing
            val req = Request.Builder().apply {
                this.url(url)
                if (start > 0) header("Range", "bytes=$start-")
                header("User-Agent", "piSynapse-model-downloader/0.16")
            }.build()

            client.newCall(req).execute().use { resp ->
                val code = resp.code
                if (code != 200 && code != 206) return Result(null, false)
                // If we asked for a range but the server ignored it (200), the
                // body is the whole file — fall back to a clean start.
                val effectiveStart = if (start > 0 && code == 200) 0L else start
                val body = resp.body ?: return Result(null, false)
                val declaredTotal = if (code == 206) {
                    resp.header("Content-Range", "")
                        ?.substringAfterLast('/')
                        ?.trim()
                        ?.toLongOrNull()
                } else {
                    body.contentLength()
                }
                val total = declaredTotal ?: -1L

                val raf = RandomAccessFile(tmp, "rw")
                if (effectiveStart == 0L) raf.setLength(0L)
                raf.seek(effectiveStart)
                body.source().use { src ->
                    val buf = ByteArray(128 * 1024)
                    var read: Int
                    var done = effectiveStart
                    while (true) {
                        if (cancelFlag.get()) {
                            cancelFlag.set(false)
                            raf.close()
                            return Result(null, true)
                        }
                        read = src.read(buf, 0, buf.size)
                        if (read == -1) break
                        raf.write(buf, 0, read)
                        done += read
                        onProgress(Progress(done, total, "downloading"))
                    }
                }
                raf.close()
            }

            if (!cancelFlag.get()) {
                tmp.renameTo(file)
                onProgress(Progress(if (file.exists()) file.length() else 0L, if (file.exists()) file.length() else 0L, "done"))
                return Result(if (file.exists()) file.absolutePath else null, false)
            }
        } catch (e: InterruptedIOException) {
            cancelFlag.set(false)
            return Result(null, false)
        } catch (e: Exception) {
            cancelFlag.set(false)
            return Result(null, false)
        }
        cancelFlag.set(false)
        return Result(null, false)
    }

    private fun presetFor(model: String): Pair<Target, Pair<String, String>>? {
        if (model.isEmpty()) return null
        val p = PRESETS[model] ?: return null
        val (file, repo) = p
        return Pair(Target(hfId(file), hfUrl(repo, file), model), p)
    }

    private fun hfId(file: String) = "hf-$file"
    private fun hfUrl(repo: String, file: String) = "https://huggingface.co/$repo/resolve/main/$file?download=true"

    private fun targetFile(): File = File(File(ctx.filesDir, "models"), modelFileName())

    private fun modelFileName(): String {
        val custom = cfg.get("MODEL_URL").trim()
        if (custom.isNotEmpty()) {
            return custom.substringAfterLast('/').substringBefore('?').ifBlank { "model.litertlm" }
        }
        val preset = cfg.get("LLM_MODEL").trim().takeIf { it.isNotEmpty() }
        if (preset != null && PRESETS.containsKey(preset)) return PRESETS.getValue(preset).first
        return PRESETS.getValue(DEFAULT_MODEL).first
    }

    companion object {
        const val DEFAULT_MODEL = "gemma-4-E2B-it"

        // model name -> (file name, HF repo)
        val PRESETS: Map<String, Pair<String, String>> = mapOf(
            "gemma-4-E2B-it" to ("gemma-4-E2B-it.litertlm" to "litert-community/gemma-4-E2B-it-litert-lm"),
            "gemma-3-1b-it" to ("gemma-3-1b-it.litertlm" to "litert-community/gemma-3-1b-it"),
            "gemma-3-270m" to ("gemma-3-270m-it.litertlm" to "litert-community/gemma-3-270m-it"),
        )
    }
}