package com.pisynapse.app

import com.google.ai.edge.litertlm.OpenApiTool
import com.google.ai.edge.litertlm.ToolProvider
import com.google.ai.edge.litertlm.tool
import org.json.JSONObject

class PiTools(private val runner: ToolRunner) {

    private data class Param(val type: String, val desc: String)

    private class Spec(
        val name: String,
        val desc: String,
        val props: List<Pair<String, Param>> = emptyList(),
        val required: List<String> = emptyList()
    )

    fun providers(): List<ToolProvider> {
        val defs = specs()
        return defs.map { d ->
            val descJson = JSONObject()
                .put("name", d.name)
                .put("description", d.desc)
                .put("parameters", schema(d))
            tool(object : OpenApiTool {
                override fun getToolDescriptionJsonString(): String = descJson.toString()
                override fun execute(arguments: String): String {
                    return try {
                        runner.run(d.name, JSONObject(arguments)).toString()
                    } catch (e: Exception) {
                        JSONObject().put("ok", false).put("error", e.message ?: e.toString()).toString()
                    }
                }
            })
        }
    }

    private fun schema(s: Spec): JSONObject {
        val properties = JSONObject()
        s.props.forEach { (n, prm) ->
            properties.put(n, JSONObject().put("type", prm.type).put("description", prm.desc))
        }
        return JSONObject()
            .put("type", "object")
            .put("properties", properties)
            .put("required", s.required.toTypedArray())
    }

    private fun specs(): List<Spec> = listOf(
        Spec("get_datetime", "Şu andaki tarih, saat ve gün bilgisini döndürür."),
        Spec("get_weather",
            "Belirtilen şehir için güncel hava durumunu döndürür.",
            listOf("city" to Param("string", "Şehir adı (Türkçe)")),
            listOf("city")),
        Spec("list_notes", "Nextcloud'da kayıtlı tüm notları listeler."),
        Spec("read_note",
            "Not içeriğini ID ile okur.",
            listOf("note_id" to Param("integer", "Notun kimliği")),
            listOf("note_id")),
        Spec("create_note",
            "Yeni bir not oluşturur.",
            listOf(
                "title" to Param("string", "Not başlığı"),
                "content" to Param("string", "Not içeriği"),
                "category" to Param("string", "Kategori")
            ),
            listOf("title", "content")),
        Spec("update_note",
            "Notun başlığını ve içeriğini kategoriyle günceller.",
            listOf(
                "note_id" to Param("integer", "Not kimliği"),
                "title" to Param("string", "Yeni başlık"),
                "content" to Param("string", "Yeni içerik"),
                "category" to Param("string", "Kategori")
            ),
            listOf("note_id")),
        Spec("delete_note",
            "Notu kalıcı olarak siler.",
            listOf("note_id" to Param("integer", "Not kimliği")),
            listOf("note_id")),
        Spec("search_notes",
            "Notları arama sorgusuyla filtreler.",
            listOf("query" to Param("string", "Arama terimi")),
            listOf("query")),
        Spec("save_memory",
            "İlgili bir bilgiyi hafızaya (kalıcı) kaydeder.",
            listOf(
                "content" to Param("string", "Hatırlanacak bilgi"),
                "category" to Param("string", "Kategori")
            ),
            listOf("content")),
        Spec("list_tasks", "Yerel görev listesini döndürür."),
        Spec("create_task",
            "Yeni bir görev oluşturur.",
            listOf(
                "summary" to Param("string", "Görev özeti"),
                "priority" to Param("integer", "Öncelik (0-3)"),
                "status" to Param("string", "Durum: open,in_progress,completed"),
                "due" to Param("string", "Bitiş tarihi (YYYY-MM-DD)")
            ),
            listOf("summary")),
        Spec("complete_task",
            "Görevi tamamlandı olarak işaretler.",
            listOf("task_id" to Param("integer", "Görev kimliği")),
            listOf("task_id")),
        Spec("delete_task",
            "Görevi siler.",
            listOf("task_id" to Param("integer", "Görev kimliği")),
            listOf("task_id")),
        Spec("search_tasks",
            "Görevleri arama sorgusuyla filtreler.",
            listOf("query" to Param("string", "Arama terimi")),
            listOf("query")),
        Spec("send_email",
            "Kullanıcının e-posta uygulamasını taslakla açar (göndermez).",
            listOf(
                "to" to Param("string", "Alıcı e-posta adresi"),
                "subject" to Param("string", "Konu"),
                "body" to Param("string", "İçerik"),
                "cc" to Param("string", "CC adresleri"),
                "bcc" to Param("string", "BCC adresleri")
            )),
        Spec("create_calendar_event",
            "Takvim uygulamasına etkinlik ekleme ekranını açar.",
            listOf(
                "title" to Param("string", "Etkinlik başlığı"),
                "description" to Param("string", "Açıklama"),
                "location" to Param("string", "Konum"),
                "start" to Param("string", "Başlangıç (YYYYMMDDTHHMMSS VEYA YYYYMMDD)"),
                "end" to Param("string", "Bitiş (aynı biçim)")
            ),
            listOf("title"))
    )
}