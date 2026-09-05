package com.pisynapse.app

import android.content.Context
import org.json.JSONArray
import org.json.JSONObject
import java.io.File
import java.text.SimpleDateFormat
import java.util.Date
import java.util.Locale

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
        arr.put(JSONObject()
            .put("id", id)
            .put("content", content)
            .put("category", category ?: "general")
            .put("created_at", now()))
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