package com.pisynapse.app

import android.content.Context
import org.json.JSONObject
import java.io.File

/**
 * SessionSummaryStore — chat_summaries.json (filesDir).
 *
 * Per-session rolling summary with server parity to piServe's sessions table
 * (summary + summarized_until). Each entry stores the folded summary text and
 * the exclusive message-count boundary [until] of messages already folded.
 * [until] doubles as a monotonic revision: conversation reuse on the host side
 * is keyed off it, so a summary change forces conversation recreation (prefill).
 */
class SessionSummaryStore(private val ctx: Context) {

    private val file = File(ctx.filesDir, "chat_summaries.json")
    private val lock = Any()
    @Volatile private var cache: JSONObject? = null

    data class Entry(val summary: String = "", val until: Int = 0) {
        val isEmpty: Boolean get() = summary.isBlank() && until == 0
    }

    private fun load(): JSONObject = synchronized(lock) {
        cache ?: run {
            val o = try {
                if (file.exists()) JSONObject(file.readText()) else JSONObject()
            } catch (e: Exception) {
                JSONObject()
            }
            cache = o
            o
        }
    }

    fun get(sessionId: String): Entry {
        if (sessionId.isBlank()) return Entry()
        return synchronized(lock) {
            val o = load().optJSONObject(sessionId) ?: return Entry()
            Entry(o.optString("summary", ""), o.optInt("until", 0))
        }
    }

    /** Stores the folded summary; returns the new boundary (revision). */
    fun set(sessionId: String, summary: String, until: Int): Int {
        if (sessionId.isBlank()) return 0
        return synchronized(lock) {
            val o = load()
            val cur = o.optJSONObject(sessionId) ?: JSONObject()
            cur.put("summary", summary)
            cur.put("until", until)
            o.put(sessionId, cur)
            persist()
            until
        }
    }

    fun clear(sessionId: String) {
        if (sessionId.isBlank()) return
        synchronized(lock) {
            val o = load()
            if (o.has(sessionId)) {
                o.remove(sessionId)
                persist()
            }
        }
    }

    private fun persist() {
        try {
            file.parentFile?.mkdirs()
            file.writeText(load().toString(2))
        } catch (e: Exception) {
        }
    }
}