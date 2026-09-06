package com.pisynapse.app

import android.content.Context
import org.json.JSONArray
import org.json.JSONObject
import java.io.File
import java.text.SimpleDateFormat
import java.util.Date
import java.util.Locale
import java.util.UUID

class LocalStore(ctx: Context) {

    private val tasksFile = File(ctx.filesDir, "tasks.json")
    private val memoryFile = File(ctx.filesDir, "memory.json")

    private fun read(file: File): JSONArray = try {
        if (file.exists()) JSONArray(file.readText()) else JSONArray()
    } catch (e: Exception) {
        JSONArray()
    }

    private fun write(file: File, arr: JSONArray) {
        file.parentFile?.mkdirs()
        file.writeText(arr.toString(2))
    }

    private fun now(): String = SimpleDateFormat("yyyy-MM-dd'T'HH:mm:ssXXX", Locale.US).format(Date())

    // Attach idempotent client metadata (stable uuid + updated_at) to any item.
    private fun ensureMeta(o: JSONObject): JSONObject {
        if (!o.has("_uuid") || o.isNull("_uuid") || o.optString("_uuid").isBlank()) {
            o.put("_uuid", UUID.randomUUID().toString())
        }
        if (!o.has("_updated_at") || o.isNull("_updated_at") || o.optString("_updated_at").isBlank()) {
            o.put("_updated_at", now())
        }
        return o
    }

    fun metaOf(o: JSONObject): Pair<String, String> =
        Pair(ensureMeta(o).optString("_uuid"), ensureMeta(o).optString("_updated_at"))

    private fun fileItems(type: String): JSONArray = when (type) {
        "tasks" -> read(tasksFile)
        "memory" -> read(memoryFile)
        else -> JSONArray()
    }

    private fun writeFileItems(type: String, arr: JSONArray) = when (type) {
        "tasks" -> write(tasksFile, arr)
        "memory" -> write(memoryFile, arr)
        else -> {}
    }

    // Generic two-way merge target used by the sync engine.
    val entityTypes = listOf("tasks", "memory")

    fun replaceAll(type: String, items: JSONArray) {
        writeFileItems(type, items)
    }

    fun upsertLocal(type: String, o: JSONObject) {
        val arr = read(when (type) { "tasks" -> tasksFile; else -> memoryFile })
        val uuid = o.optString("_uuid")
        for (i in 0 until arr.length()) {
            if (arr.getJSONObject(i).optString("_uuid") == uuid) {
                arr.put(i, o)
                write(when (type) { "tasks" -> tasksFile; else -> memoryFile }, arr)
                return
            }
        }
        arr.put(ensureMeta(o))
        write(when (type) { "tasks" -> tasksFile; else -> memoryFile }, arr)
    }

    fun deleteLocalByUuid(type: String, uuid: String): Boolean {
        val f = when (type) { "tasks" -> tasksFile; else -> memoryFile }
        val arr = read(f)
        val out = JSONArray()
        var found = false
        for (i in 0 until arr.length()) {
            if (arr.getJSONObject(i).optString("_uuid") == uuid) found = true else out.put(arr.getJSONObject(i))
        }
        write(f, out)
        return found
    }

    fun allEntities(type: String): JSONArray = fileItems(type)

    // ── Tasks ──────────────────────────────────────────────────────────────
    fun createTask(summary: String, priority: Int, status: String, due: String?): JSONObject {
        if (summary.isBlank()) return JSONObject().put("ok", false).put("error", "Görev özeti boş.")
        val arr = read(tasksFile)
        val id = (0 until arr.length()).maxOrNull()?.let { arr.getJSONObject(it).optInt("id") }?.plus(1) ?: 1
        val t = JSONObject()
            .put("id", id)
            .put("title", summary)
            .put("priority", priority)
            .put("status", status)
            .put("due", due ?: JSONObject.NULL)
            .put("created_at", now())
        ensureMeta(t)
        arr.put(t)
        write(tasksFile, arr)
        return JSONObject().put("id", id).put("ok", true)
    }

    fun listTasks(): JSONObject {
        val arr = read(tasksFile)
        return JSONObject().put("tasks", arr).put("ok", true)
    }

    fun completeTask(id: Int): JSONObject {
        val arr = read(tasksFile)
        for (i in 0 until arr.length()) {
            if (arr.getJSONObject(i).optInt("id") == id) {
                arr.getJSONObject(i).put("status", "done").put("completed_at", now())
                write(tasksFile, arr)
                return JSONObject().put("id", id).put("ok", true)
            }
        }
        return JSONObject().put("ok", false).put("error", "Görev bulunamadı (id $id).")
    }

    fun deleteTask(id: Int): JSONObject {
        val arr = read(tasksFile)
        val out = JSONArray()
        var found = false
        for (i in 0 until arr.length()) {
            if (arr.getJSONObject(i).optInt("id") == id) found = true else out.put(arr.getJSONObject(i))
        }
        write(tasksFile, out)
        return JSONObject().put("ok", found).put("id", id)
    }

    fun searchTasks(q: String): JSONObject {
        val out = JSONArray()
        for (i in 0 until read(tasksFile).length()) {
            val o = read(tasksFile).getJSONObject(i)
            if (o.optString("title").lowercase().contains(q.lowercase())) out.put(o)
        }
        return JSONObject().put("tasks", out).put("ok", true)
    }

    // ── Memory ─────────────────────────────────────────────────────────────
    fun saveMemory(content: String, category: String?): JSONObject {
        if (content.isBlank()) return JSONObject().put("ok", false).put("error", "İçerik boş.")
        val arr = read(memoryFile)
        val id = (0 until arr.length()).maxOrNull()?.let { arr.getJSONObject(it).optInt("id") }?.plus(1) ?: 1
        val m = JSONObject()
            .put("id", id)
            .put("content", content)
            .put("category", category ?: "general")
            .put("created_at", now())
        ensureMeta(m)
        arr.put(m)
        write(memoryFile, arr)
        return JSONObject().put("id", id).put("memories", arr.length()).put("ok", true)
    }

    fun listMemory(): JSONObject =
        JSONObject().put("memories", read(memoryFile)).put("ok", true)

    fun deleteMemory(id: String): Boolean {
        val arr = read(memoryFile)
        val out = JSONArray()
        var found = false
        for (i in 0 until arr.length()) {
            val o = arr.getJSONObject(i)
            if (o.optString("id") == id || o.optString("id") == "" && o.optInt("id").toString() == id) {
                found = true
            } else {
                out.put(o)
            }
        }
        write(memoryFile, out)
        return found
    }
}