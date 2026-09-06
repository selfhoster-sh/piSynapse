package com.pisynapse.app

import android.content.Context
import org.json.JSONObject
import java.io.File

/**
 * ConfigStore — config.json (filesDir).
 *
 * Schema keys are the SAME names the web SPA uses (LLM_TEMPERATURE, LLM_TOP_P,
 * LLM_TOP_K, TTS_AUTO_REPLY, ...) so the in-app settings render every key.
 * Legacy Kotlin readers may still ask for TEMPERATURE/TOP_P/TOP_K — resolved
 * through [ALIASES]. Sync controls (SYNC_MODE / SERVER_URL / SYNC_ALWAYS) are
 * added here so phone-only, server-only and always-sync coexist in the UI.
 */
class ConfigStore(private val ctx: Context) {

    private val file: File = File(ctx.filesDir, "config.json")

    // JS/web key -> legacy Kotlin key (and vice-versa).
    private companion object {
        val ALIASES: Map<String, String> = mapOf(
            "LLM_TEMPERATURE" to "TEMPERATURE",
            "LLM_TOP_P" to "TOP_P",
            "LLM_TOP_K" to "TOP_K",
            "LANGUAGE" to "UI_LANGUAGE",
            // Server-aligned voice names read/write the legacy phone keys.
            "AUTO_TTS_ON_VOICE" to "TTS_AUTO_REPLY",
            "AUTO_SEND_ON_VOICE" to "STT_SEND_ON_PAUSE",
        )
    }

    private fun defaults(): JSONObject = JSONObject()
        .put("LLM_MODEL", "")
        .put("MODEL_URL", "")
        .put("LLM_BACKEND", "litert-lm")
        .put("LLM_BACKEND_TYPE", "cpu")
        .put("LLM_NUM_CTX", 6144)
        .put("LLM_MAX_OUTPUT_TOKENS", 512)
        // Web-aligned names (aliases: TEMPERATURE / TOP_P / TOP_K)
        .put("LLM_TEMPERATURE", 0.7)
        .put("LLM_TOP_P", 0.9)
        .put("LLM_TOP_K", 40)
        // Model preset / advanced
        .put("LLM_TITLE_ENRICHMENT", "off")
        .put("HISTORY_LIMIT", 50)
        .put("MEMORY_LIMIT", 10)
        .put("ASSISTANT_USER", "default")
        .put("DEFAULT_CITY", "")
        .put("MAIL_PROVIDER", "")
        .put("NEXTCLOUD_URL", "")
        .put("NEXTCLOUD_USER", "")
        .put("NEXTCLOUD_PASSWORD", "")
        // Sync mode (two separate controls, always visible in settings)
        .put("SYNC_MODE", "only-phone")
        .put("SYNC_ALWAYS", "off")
        .put("SERVER_URL", "")
        .put("SERVER_USER", "")
        .put("SERVER_API_KEY", "")
        // Voice (web names)
        .put("TTS_AUTO_REPLY", "off")
        .put("STT_SEND_ON_PAUSE", "off")
        // Model lifetime / semantic dedup (server-parity keys)
        .put("LLM_KEEP_ALIVE", "4h")
        .put("MEMORY_SIMILARITY_THRESHOLD", "0.68")
        .put("UI_LANGUAGE", "tr")
        .put("UI_THEME", "dark")

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

    fun get(name: String): String {
        val cur = load()
        val k = canonical(name, cur)
        if (cur.has(k) && cur.opt(k).toString().isNotBlank()) return cur.get(k).toString()
        val d = defaults()
        val dk = canonical(name, d)
        return if (d.has(dk) && d.opt(dk).toString().isNotBlank()) d.get(dk).toString() else ""
    }

    fun getInt(name: String, def: Int): Int {
        val cur = load()
        val k = canonical(name, cur)
        if (cur.has(k)) return cur.optInt(k, def)
        val d = defaults()
        return if (d.has(k)) d.optInt(k, def) else def
    }

    fun getFloat(name: String, def: Float): Float {
        val cur = load()
        val k = canonical(name, cur)
        return try {
            val v: Any = if (cur.has(k)) cur.get(k) else {
                val d = defaults()
                if (d.has(k)) d.get(k) else def
            }
            when (v) {
                is Number -> v.toFloat()
                is String -> v.toFloat()
                else -> def
            }
        } catch (e: Exception) {
            def
        }
    }

    /** Resolve a storage key either directly or through the alias map. */
    private fun canonical(key: String, cur: JSONObject): String =
        if (cur.has(key)) key else {
            ALIASES.entries.firstOrNull { it.value == key }?.key ?: key
        }

    fun setValues(values: JSONObject) {
        val cur = load()
        // Store under the canonical (web-aligned) key; readers resolve aliases.
        values.keys().forEach { k -> cur.put(k, values.get(k)) }
        // Keep legacy voice keys in sync so older readers never diverge.
        listOf(
            "AUTO_TTS_ON_VOICE" to "TTS_AUTO_REPLY",
            "AUTO_SEND_ON_VOICE" to "STT_SEND_ON_PAUSE"
        ).forEach { (new, legacy) ->
            if (values.has(new)) cur.put(legacy, values.get(new))
        }
        save(cur)
    }

    fun set(name: String, value: String) {
        val cur = load()
        cur.put(name, value)
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
        val def = defaults()
        fun v(name: String): Any {
            if (cur.has(name) && !cur.isNull(name) && cur.opt(name).toString().isNotBlank()) return cur.get(name) as Any
            val fromDef = if (def.has(name) && !def.isNull(name)) def.get(name) as Any else null
            if (fromDef != null) return fromDef
            val alias = ALIASES.entries.firstOrNull { it.key == name }?.let { cur.opt(it.value) }
            return alias ?: ""
        }

        // ── Telefon sekmesi ──
        add("LLM_MODEL", v("LLM_MODEL"), "select", "Yerel Model (litertlm)", "Telefon içinde çalışan Gemma E2B modeli.", "Telefon · Zeka",
            arrayOf("gemma-4-E2B-it", "gemma-3-1b-it", "gemma-3-270m"))
        add("MODEL_URL", v("MODEL_URL"), "text", "Model indirme adresi (opsiyonel)", "Boş bırakılırsa Hugging Face üzerinden ön tanımlı model çekilir. Kendı sunucundaki bir .litertlm dosyasının doğrudan URL'sini verebilirsin.", "Telefon · Zeka")
        add("LLM_BACKEND", v("LLM_BACKEND"), "select", "Motor", "Google LiteRT-LM (Gemma E2B için).", "Telefon · Zeka",
            arrayOf("litert-lm"))
        add("LLM_BACKEND_TYPE", v("LLM_BACKEND_TYPE"), "select", "Donanım", "CPU / GPU / NPU. Bu model ikilisi CPU'ya kilitli.", "Telefon · Zeka",
            arrayOf("cpu", "gpu", "npu"))
        add("LLM_TEMPERATURE", v("LLM_TEMPERATURE"), "number", "Sıcaklık", "Üretim çeşitliliği.", "Telefon · Üretim")
        add("LLM_TOP_P", v("LLM_TOP_P"), "number", "Top-P", "Çıktı çeşitliliği eşiği.", "Telefon · Üretim")
        add("LLM_TOP_K", v("LLM_TOP_K"), "number", "Top-K", "Her adımda değerlendirilen token sayısı.", "Telefon · Üretim")
        add("LLM_NUM_CTX", v("LLM_NUM_CTX"), "number", "Bağlam (tok)", "Bağlam penceresi (input+output toplam slot).", "Telefon · Üretim")
        add("LLM_MAX_OUTPUT_TOKENS", v("LLM_MAX_OUTPUT_TOKENS"), "number", "Maks. çıktı (tok)", "Yanıt uzunluğu üst sınırı.", "Telefon · Üretim")
        add("LLM_TITLE_ENRICHMENT", v("LLM_TITLE_ENRICHMENT"), "select", "Sohbet başlık üretimi", "Sohbet başlıklarını modelle zenginleştir.", "Telefon · Sohbet", arrayOf("off", "on"))
        add("LLM_KEEP_ALIVE", v("LLM_KEEP_ALIVE"), "select", "Modeli bellekte tut", "Son kullanımdan sonra yerel model bellekte ne kadar tutulur — belleği rahatlatmak için otomatik boşaltılır.", "Telefon · Zeka",
            arrayOf("10m", "30m", "1h", "2h", "4h", "12h", "24h", "0"))
        add("MEMORY_SIMILARITY_THRESHOLD", v("MEMORY_SIMILARITY_THRESHOLD"), "number", "Bellek benzerlik eşiği", "Yeni bir hafıza kaydı, ne kadar benzerlikte mevcut kayıtla birleştirilir (0-1; varsayılan 0.68).", "Telefon · Sohbet")
        add("HISTORY_LIMIT", v("HISTORY_LIMIT"), "number", "Geçmiş limiti", "Sohbette tutulan mesaj sayısı.", "Telefon · Sohbet")
        add("MEMORY_LIMIT", v("MEMORY_LIMIT"), "number", "Hafıza limiti", "Bağlama alınan hafıza kartı sayısı.", "Telefon · Sohbet")
        add("DEFAULT_CITY", v("DEFAULT_CITY"), "text", "Şehir", "Hava durumu için varsayılan şehir.", "Telefon · Hava")
        add("NEXTCLOUD_URL", v("NEXTCLOUD_URL"), "text", "Nextcloud adresi", "örn. nextcloud.sunucu.tld (https:// olmadan).", "Telefon · Notlar")
        add("NEXTCLOUD_USER", v("NEXTCLOUD_USER"), "text", "Nextcloud kullanıcı", "Notlar hesabı kullanıcı adı.", "Telefon · Notlar")
        add("NEXTCLOUD_PASSWORD", v("NEXTCLOUD_PASSWORD"), "password", "Nextcloud parola", "Uygulama parolası önerilir.", "Telefon · Notlar")
        add("AUTO_TTS_ON_VOICE", v("AUTO_TTS_ON_VOICE"), "select", "Otomatik seslendirme", "Yanıt sonrası TTS.", "Telefon · Ses", arrayOf("off", "on"))
        add("AUTO_SEND_ON_VOICE", v("AUTO_SEND_ON_VOICE"), "select", "Konuşmada duraklayınca gönder", "Sesli girişte duraklama algılanınca gönder.", "Telefon · Ses", arrayOf("off", "on"))
        add("UI_LANGUAGE", v("UI_LANGUAGE"), "select", "Arayüz dili", "Uygulama dili.", "Telefon · Uygulama", arrayOf("tr", "en"))
        add("UI_THEME", v("UI_THEME"), "select", "Tema", "Karanlık / aydınlık.", "Telefon · Uygulama", arrayOf("dark", "light"))

        // ── Sunucu sekmesi ──
        add("SYNC_MODE", v("SYNC_MODE"), "select", "Veri modu", "only-phone: hafıza/görev/geçmiş cihazda. only-server: veri sunucuda, LLM yine yerel.", "Sunucu · Senkron",
            arrayOf("only-phone", "only-server"))
        add("SYNC_ALWAYS", v("SYNC_ALWAYS"), "select", "Her zaman senkron", "Veri değişikliklerini otomatik olarak sunucuya it (yapılandırılmışsa).", "Sunucu · Senkron",
            arrayOf("off", "on"))
        add("SERVER_URL", v("SERVER_URL"), "text", "Sunucu adresi", "API ana sunucu adresi (https:// ile).", "Sunucu · Bağlantı")
        add("SERVER_USER", v("SERVER_USER"), "text", "Sunucu kullanıcı", "Sunucudaki kullanıcı kimliği.", "Sunucu · Bağlantı")
        add("SERVER_API_KEY", v("SERVER_API_KEY"), "password", "Sunucu API anahtarı", "Sunucuya erişim için API anahtarı (opsiyonel).", "Sunucu · Bağlantı")
        add("ASSISTANT_USER", v("ASSISTANT_USER"), "text", "Asistan kullanıcı adı", "Sunucu oturumlarında kullanılan kimlik.", "Sunucu · Kişisel")
        add("MAIL_PROVIDER", v("MAIL_PROVIDER"), "text", "E-posta sağlayıcı (sunucu)", "Sunucu tarafı e-posta bağlantısı için.", "Sunucu · Kişisel")
        return out
    }
}