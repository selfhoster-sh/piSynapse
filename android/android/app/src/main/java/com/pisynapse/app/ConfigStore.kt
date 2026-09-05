package com.pisynapse.app

import android.content.Context
import org.json.JSONObject
import java.io.File

class ConfigStore(private val ctx: Context) {

    private val file: File = File(ctx.filesDir, "config.json")

    private fun defaults(): JSONObject = JSONObject()
        .put("LLM_MODEL", "")
        .put("LLM_BACKEND", "litert-lm")
        .put("LLM_BACKEND_TYPE", "cpu")
        .put("LLM_NUM_CTX", 6144)
        .put("LLM_MAX_OUTPUT_TOKENS", 512)
        .put("TEMPERATURE", 0.7)
        .put("TOP_P", 0.9)
        .put("TOP_K", 40)
        .put("DEFAULT_CITY", "")
        .put("NEXTCLOUD_URL", "")
        .put("NEXTCLOUD_USER", "")
        .put("NEXTCLOUD_PASSWORD", "")
        .put("LANGUAGE", "tr")
        .put("UI_THEME", "dark")
        .put("TTS_AUTO_REPLY", "off")
        .put("STT_SEND_ON_PAUSE", "off")

    fun load(): JSONObject {
        return try {
            if (file.exists()) JSONObject(file.readText()) else defaults()
        } catch (e: Exception) {
            defaults()
        }
    }

    fun save(o: JSONObject) {
        file.parentFile?.mkdirs()
        file.writeText(o.toString(2))
    }

    fun get(name: String): String = load().opt(name).toString()

    fun getInt(name: String, def: Int): Int = load().optInt(name, def)

    fun getFloat(name: String, def: Float): Float = try {
        load().optDouble(name, def.toDouble()).toFloat()
    } catch (e: Exception) {
        def
    }

    fun setValues(values: JSONObject) {
        val cur = load()
        values.keys().forEach { k -> cur.put(k, values.get(k)) }
        save(cur)
    }

    fun schema(): JSONObject {
        val out = JSONObject()
        fun add(name: String, value: Any, type: String, label: String, desc: String = "", group: String = "Genel", options: Array<String> = emptyArray()) {
            val e = JSONObject()
                .put("name", name)
                .put("value", value)
                .put("type", type)
                .put("label", label)
                .put("desc", desc)
                .put("group", group)
                .put("options", options.toList().joinToString("|"))
            out.put(name, e)
        }
        val cur = load()
        add("LLM_MODEL", cur.opt("LLM_MODEL"), "select", "Yerel Model (litertlm)", "Telefon içinde çalışan Gemma E2B modeli.", "Zeka",
            arrayOf("gemma-4-E2B-it", "gemma-3-1b-it", "gemma-3-270m"))
        add("LLM_BACKEND", cur.opt("LLM_BACKEND"), "select", "Motor", "Google LiteRT-LM (Gemma E2B için).", "Zeka",
            arrayOf("litert-lm"))
        add("LLM_BACKEND_TYPE", cur.opt("LLM_BACKEND_TYPE"), "select", "Donanım", "CPU / GPU / NPU. GPU hızı düşürür.", "Zeka",
            arrayOf("cpu", "gpu", "npu"))
        add("LLM_NUM_CTX", cur.opt("LLM_NUM_CTX"), "number", "Bağlam (tok), LLM_NUM_CTX", "Bağlam penceresi.", "Zeka")
        add("LLM_MAX_OUTPUT_TOKENS", cur.opt("LLM_MAX_OUTPUT_TOKENS"), "number", "Maks. çıktı (tok)", "Yanıt uzunluğu üst sınırı.", "Zeka")
        add("TEMPERATURE", cur.opt("TEMPERATURE"), "number", "Sıcaklık", "Üretim çeşitliliği.", "Zeka")
        add("DEFAULT_CITY", cur.opt("DEFAULT_CITY"), "text", "Şehir", "Hava durumu için varsayılan şehir.", "Hava")
        add("NEXTCLOUD_URL", cur.opt("NEXTCLOUD_URL"), "text", "Nextcloud adresi", "örn. nextcloud.sunucu.tld (https:// olmadan).", "Notlar")
        add("NEXTCLOUD_USER", cur.opt("NEXTCLOUD_USER"), "text", "Nextcloud kullanıcı", "Notlar hesabı kullanıcı adı.", "Notlar")
        add("NEXTCLOUD_PASSWORD", cur.opt("NEXTCLOUD_PASSWORD"), "password", "Nextcloud parola", "Uygulama parolası önerilir.", "Notlar")
        add("LANGUAGE", cur.opt("LANGUAGE"), "select", "Dil", "Arayüz dili.", "Arayüz", arrayOf("tr", "en"))
        add("UI_THEME", cur.opt("UI_THEME"), "select", "Tema", "Karanlık / aydınlık.", "Arayüz", arrayOf("dark", "light"))
        add("TTS_AUTO_REPLY", cur.opt("TTS_AUTO_REPLY"), "select", "Otomatik seslendirme", "Yanıt sonrası TTS.", "Arayüz", arrayOf("off", "on"))
        return out
    }
}