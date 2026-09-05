package com.pisynapse.app

import org.json.JSONObject
import java.text.SimpleDateFormat
import java.util.Date
import java.util.Locale

class ToolRunner(
    private val store: ConfigStore,
    private val weather: WeatherClient,
    private val notes: NotesClient,
    private val local: LocalStore,
    private val platform: PlatformTools
) {

    fun run(group: String, name: String, params: JSONObject): JSONObject = run(name, params)

    fun run(name: String, params: JSONObject): JSONObject {
        val handler: (JSONObject) -> JSONObject = when (name) {
            "get_datetime" -> {
                val now = SimpleDateFormat("yyyy-MM-dd HH:mm:ss", Locale.US).format(Date())
                val trTime = SimpleDateFormat("HH:mm", Locale.getDefault()).format(Date())
                val wd = when (SimpleDateFormat("EEEE", Locale("tr")).format(Date()).lowercase()) {
                    "pazartesi" -> "Pazartesi"
                    "salı" -> "Salı"
                    "çarşamba" -> "Çarşamba"
                    "perşembe" -> "Perşembe"
                    "cuma" -> "Cuma"
                    "cumartesi" -> "Cumartesi"
                    else -> "Pazar"
                }
                { _: JSONObject -> JSONObject().put("datetime", now).put("time", trTime).put("weekday", wd).put("ok", true) }
            }
            "get_weather" -> { p -> weather.fetchAsJson(p.optString("city").takeIf { it.isNotBlank() }) }
            "list_notes" -> { _ -> notes.list() }
            "read_note" -> { p -> notes.get(p.optInt("note_id")) }
            "create_note" -> { p ->
                notes.create(p.optString("title", "Not"), p.optString("content", ""), p.optString("category", null))
            }
            "update_note" -> { p ->
                if (!p.has("note_id")) JSONObject().put("ok", false).put("error", "note_id gerekli")
                else notes.update(p.optInt("note_id"), p.optString("title", "Not"), p.optString("content", ""), p.optString("category", null))
            }
            "delete_note" -> { p -> notes.delete(p.optInt("note_id")) }
            "search_notes" -> { p -> notes.search(p.optString("query", "")) }
            "save_memory" -> { p -> local.saveMemory(p.optString("content", ""), p.optString("category", null)) }
            "create_task" -> {
                { p -> local.createTask(p.optString("summary", ""), p.optInt("priority", 0), p.optString("status", "open"), p.optString("due", null)) }
            }
            "list_tasks" -> { _ -> local.listTasks() }
            "complete_task" -> { p -> local.completeTask(p.optInt("task_id", -1)) }
            "delete_task" -> { p -> local.deleteTask(p.optInt("task_id", -1)) }
            "search_tasks" -> { p -> local.searchTasks(p.optString("query", "")) }
            "send_email" -> { p -> platform.composeEmail(p) }
            "create_calendar_event" -> { p -> platform.addCalendarEvent(p) }
            else -> {
                { _ -> JSONObject().put("ok", false).put("error", "Bilinmeyen araç: $name") }
            }
        }
        return handler(params)
    }
}