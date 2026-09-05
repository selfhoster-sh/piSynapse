package com.pisynapse.app

import okhttp3.MediaType.Companion.toMediaType
import okhttp3.Request
import okhttp3.RequestBody.Companion.toRequestBody
import org.json.JSONArray
import org.json.JSONObject
import java.io.IOException
import java.util.Base64

class NotesClient(private val cfg: ConfigStore) {

    private fun base(): String {
        val url = cfg.get("NEXTCLOUD_URL").trim().removePrefix("https://").removePrefix("http://").trimEnd('/')
        if (url.isEmpty()) throw IOException("Nextcloud adresi ayarlanmamış (Ayarlar → Notlar).")
        return "https://$url/index.php/apps/notes/api/v1"
    }

    private fun authHeader(): String {
        val u = cfg.get("NEXTCLOUD_USER")
        val p = cfg.get("NEXTCLOUD_PASSWORD")
        if (u.isEmpty() || p.isEmpty()) throw IOException("Nextcloud kullanıcı/parola ayarlanmamış.")
        return "Basic " + Base64.getEncoder().encodeToString("$u:$p".toByteArray(Charsets.UTF_8))
    }

    private fun req(method: String, path: String, bodyJson: String? = null): String {
        val b = base()
        val rb = bodyJson?.toRequestBody("application/json".toMediaType())
        val req = Request.Builder()
            .url("$b$path")
            .method(method, rb)
            .header("Authorization", authHeader())
            .header("Accept", "application/json")
            .build()
        HttpClient.client.newCall(req).execute().use { r ->
            val body = r.body?.string() ?: ""
            if (!r.isSuccessful) throw IOException("Nextcloud HTTP ${r.code}: ${body.take(200)}")
            return body
        }
    }

    private val notesBase = ""

    fun list(): JSONObject {
        val raw = req("GET", "/notes")
        val arr = JSONArray(raw)
        val out = JSONArray()
        for (i in 0 until arr.length()) {
            val o = arr.getJSONObject(i)
            out.put(JSONObject()
                .put("id", o.optInt("id"))
                .put("title", stripTitle(o.optString("title")))
                .put("category", o.optString("category"))
                .put("modified", o.optLong("modified"))
                .put("etag", o.optString("etag")))
        }
        return JSONObject().put("notes", out).put("ok", true)
    }

    fun search(q: String): JSONObject {
        val base = list()
        val arr = base.getJSONArray("notes")
        val out = JSONArray()
        for (i in 0 until arr.length()) {
            val o = arr.getJSONObject(i)
            if (o.optString("title").lowercase().contains(q.lowercase())) out.put(o)
        }
        return JSONObject().put("notes", out).put("ok", true)
    }

    fun get(id: Int): JSONObject {
        val o = JSONObject(req("GET", "/notes/$id"))
        return JSONObject()
            .put("id", o.optInt("id"))
            .put("title", o.optString("title"))
            .put("content", o.optString("content"))
            .put("category", o.optString("category"))
            .put("modified", o.optLong("modified"))
            .put("ok", true)
    }

    fun create(title: String, content: String, category: String?): JSONObject {
        val payload = JSONObject()
            .put("title", title)
            .put("content", content)
        if (!category.isNullOrBlank()) payload.put("category", category)
        val o = JSONObject(req("POST", "/notes", payload.toString()))
        return JSONObject()
            .put("id", o.optInt("id"))
            .put("title", o.optString("title"))
            .put("category", o.optString("category"))
            .put("ok", true)
    }

    fun update(id: Int, title: String, content: String, category: String?): JSONObject {
        val payload = JSONObject()
            .put("title", title)
            .put("content", content)
        if (!category.isNullOrBlank()) payload.put("category", category)
        val o = JSONObject(req("PUT", "/notes/$id", payload.toString()))
        return JSONObject().put("id", o.optInt("id")).put("ok", true)
    }

    fun delete(id: Int): JSONObject {
        req("DELETE", "/notes/$id")
        return JSONObject().put("id", id).put("ok", true)
    }

    private fun stripTitle(t: String): String {
        var s = t
        for (line in s.lines()) {
            val l = line.trimStart()
            if (l.startsWith("#") || l.isNotBlank()) {
                s = l
                break
            }
        }
        return s.trim().take(120)
    }
}