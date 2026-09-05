package com.pisynapse.app

import okhttp3.Call
import okhttp3.Callback
import okhttp3.OkHttpClient
import okhttp3.Request
import org.json.JSONObject
import java.io.IOException
import java.util.concurrent.TimeUnit

object HttpClient {
    val client: OkHttpClient by lazy {
        OkHttpClient.Builder()
            .connectTimeout(20, TimeUnit.SECONDS)
            .readTimeout(60, TimeUnit.SECONDS)
            .build()
    }
}

class WeatherClient(private val cfg: ConfigStore) {

    data class Wx(
        val city: String, val tempC: Double, val feelsC: Double, val condition: String,
        val wmo: Int, val kind: String, val humidity: Int, val windKmh: Double,
        val highC: Double, val lowC: Double, val units: String
    )

    fun fetch(cityArg: String?): Wx {
        val city = cityArg?.takeIf { it.isNotBlank() } ?: cfg.get("DEFAULT_CITY").takeIf { it.isNotBlank() }
            ?: throw IOException("Hava durumu için şehir ayarlanmamış (Ayarlar → Hava → Şehir).")
        val geoJson = getJson("https://geocoding-api.open-meteo.com/v1/search?name=${url(city)}&count=1&language=tr&format=json")
        val res = geoJson.optJSONArray("results")
        if (res == null || res.length() == 0) throw IOException("Şehir bulunamadı: $city")
        val hit = res.getJSONObject(0)
        val lat = hit.optDouble("latitude")
        val lon = hit.optDouble("longitude")
        val name = hit.optString("name", city)
        val wx = getJson(
            "https://api.open-meteo.com/v1/forecast?latitude=$lat&longitude=$lon&current=temperature_2m,apparent_temperature,weather_code,relative_humidity_2m,wind_speed_10m&daily=temperature_2m_max,temperature_2m_min&timezone=auto&forecast_days=1"
        )
        val cur = wx.getJSONObject("current")
        val daily = wx.optJSONObject("daily")
        val tempC = cur.optDouble("temperature_2m")
        val feelsC = cur.optDouble("apparent_temperature")
        val wmo = cur.optInt("weather_code")
        val humidity = cur.optInt("relative_humidity_2m")
        val wind = cur.optDouble("wind_speed_10m")
        val highC = daily?.optJSONArray("temperature_2m_max")?.optDouble(0) ?: tempC
        val lowC = daily?.optJSONArray("temperature_2m_min")?.optDouble(0) ?: tempC
        val (condition, kind) = wmoKind(wmo)
        return Wx(name, tempC, feelsC, condition, wmo, kind, humidity, wind, highC, lowC, "celsius")
    }

    fun fetchAsJson(cityArg: String?): JSONObject {
        val w = fetch(cityArg)
        return JSONObject()
            .put("city", w.city)
            .put("temp_c", w.tempC)
            .put("feels_c", w.feelsC)
            .put("condition", w.condition)
            .put("wmo_code", w.wmo)
            .put("kind", w.kind)
            .put("humidity", w.humidity)
            .put("wind_kmh", w.windKmh)
            .put("high_c", w.highC)
            .put("low_c", w.lowC)
            .put("units", w.units)
            .put("summary", "${w.city}: ${w.tempC.toInt()}°C, ${w.condition} (en yüksek ${w.highC.toInt()}°, en düşük ${w.lowC.toInt()}°)")
            .put("ok", true)
    }

    private fun wmoKind(code: Int): Pair<String, String> = when (code) {
        0 -> "Açık" to "sunny"
        in 1..2 -> "Az bulutlu" to "cloud"
        3 -> "Kapalı" to "cloud"
        in 45..48 -> "Sisli" to "fog"
        in 51..57 -> "Çiseleyen yağmur" to "rain"
        in 61..65 -> "Yağmur" to "rain"
        in 80..82 -> "Yağmur" to "rain"
        in 66..67 -> "Karla karışık yağmur" to "rain"
        in 71..77 -> "Kar" to "snow"
        in 85..86 -> "Kar" to "snow"
        in 95..99 -> "Gök gürültülü fırtına" to "thunder"
        else -> "Bilinmiyor" to "cloud"
    }

    private fun getJson(url: String): JSONObject {
        val req = Request.Builder().url(url).build()
        val resp = HttpClient.client.newCall(req).execute()
        resp.use {
            val body = it.body?.string() ?: throw IOException("HTTP ${it.code}")
            if (!it.isSuccessful) throw IOException("HTTP ${it.code}: $body")
            return JSONObject(body)
        }
    }

    private fun url(s: String): String = java.net.URLEncoder.encode(s, "UTF-8")
}