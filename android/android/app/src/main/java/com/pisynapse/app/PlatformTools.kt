package com.pisynapse.app

import android.app.Activity
import android.content.Context
import android.content.Intent
import android.net.Uri
import android.os.BatteryManager
import android.os.Build
import android.os.Environment
import android.provider.CalendarContract
import org.json.JSONArray
import org.json.JSONObject
import java.text.SimpleDateFormat
import java.util.Date
import java.util.Locale

class PlatformTools(private val ctx: Context) {

    fun composeEmail(params: JSONObject): JSONObject {
        val to = params.optString("to").takeIf { it.isNotBlank() } ?: ""
        val subject = params.optString("subject", "")
        val body = params.optString("body", "")
        val cc = params.optString("cc", "").takeIf { it.isNotBlank() }
        val uri = Uri.parse("mailto:${Uri.encode(to)}")
        val intent = Intent(Intent.ACTION_SENDTO, uri).apply {
            putExtra(Intent.EXTRA_SUBJECT, subject)
            putExtra(Intent.EXTRA_TEXT, body)
            cc?.let { putExtra(Intent.EXTRA_CC, arrayOf(it)) }
        }
        val chooser = Intent.createChooser(intent, "E-posta gönder")
        chooser.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
        ctx.startActivity(chooser)
        return JSONObject().put("ok", true).put("note", "E-posta uygulaması açıldı; gönderimi kullanıcı onaylar.")
    }

    fun addCalendarEvent(params: JSONObject): JSONObject {
        val summary = params.optString("summary")
        if (summary.isBlank()) return JSONObject().put("ok", false).put("error", "Etkinlik özeti boş.")
        val start = parseEpochSec(params.optString("start_time"))
        val end = parseEpochSec(params.optString("end_time")) ?: (start?.plus(3600))
        val intent = Intent(Intent.ACTION_INSERT).apply {
            setData(Uri.parse("content://com.android.calendar/time/${start?.times(1000) ?: System.currentTimeMillis()}"))
            putExtra(CalendarContract.Events.TITLE, summary)
            putExtra(CalendarContract.Events.DESCRIPTION, params.optString("description", ""))
            if (start != null) putExtra(CalendarContract.EXTRA_EVENT_BEGIN_TIME, start * 1000L)
            if (end != null) putExtra(CalendarContract.EXTRA_EVENT_END_TIME, end * 1000L)
            putExtra(CalendarContract.EXTRA_EVENT_ALL_DAY, params.optBoolean("all_day", false))
        }
        val chooser = Intent.createChooser(intent, "Takvime ekle")
        chooser.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
        ctx.startActivity(chooser)
        return JSONObject().put("ok", true).put("note", "Takvim uygulaması açıldı.")
    }

    fun mapOpen(params: JSONObject): JSONObject {
        val lat = params.optDouble("latitude", Double.NaN)
        val lon = params.optDouble("longitude", Double.NaN)
        val query = params.optString("query", "")
        val uri = if (!lat.isNaN() && !lon.isNaN()) {
            "geo:$lat,$lon?q=$lat,$lon"
        } else if (query.isNotBlank()) {
            "geo:0,0?q=${Uri.encode(query)}"
        } else {
            return JSONObject().put("ok", false).put("error", "Konum verisi yok.")
        }
        runCatching {
            val i = Intent(Intent.ACTION_VIEW, Uri.parse(uri))
            i.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
            ctx.startActivity(i)
            return JSONObject().put("ok", true).put("note", "Harita uygulaması açıldı.")
        }.onFailure {
            return JSONObject().put("ok", false).put("error", "Harita uygulaması bulunamadı.")
        }
        return JSONObject().put("ok", false)
    }

    fun deviceStatus(): JSONObject {
        val bm = ctx.getSystemService(Context.BATTERY_SERVICE) as? BatteryManager
        val level = bm?.getIntProperty(BatteryManager.BATTERY_PROPERTY_CAPACITY) ?: -1
        val charging = (bm?.getIntProperty(BatteryManager.BATTERY_PROPERTY_STATUS) ?: -1) == BatteryManager.BATTERY_STATUS_CHARGING
        val mem = (Runtime.getRuntime().totalMemory() - Runtime.getRuntime().freeMemory())
        val memTotal = try {
            Runtime.getRuntime().maxMemory()
        } catch (e: Exception) { 0L }
        val storageFree = try {
            val st = android.os.StatFs(Environment.getExternalStorageDirectory().path)
            st.availableBytes
        } catch (e: Exception) {
            0L
        }
        return JSONObject()
            .put("battery_level", level)
            .put("battery_charging", charging)
            .put("device_model", Build.MODEL)
            .put("manufacturer", Build.MANUFACTURER)
            .put("android", Build.VERSION.RELEASE)
            .put("app_memory_used_mb", mem / (1024 * 1024))
            .put("app_memory_max_mb", memTotal / (1024 * 1024))
            .put("storage_free_mb", storageFree / (1024 * 1024))
            .put("ok", true)
    }

    fun sensorsList(): JSONObject {
        val sm = ctx.getSystemService(Context.SENSOR_SERVICE) as? android.hardware.SensorManager
        val present = sm?.getSensorList(android.hardware.Sensor.TYPE_ALL).orEmpty().map { it.name }
        val known = listOf("accelerometer", "proximity", "light", "gyroscope", "magnetometer", "step_counter", "barometer")
        val out = JSONArray()
        for (k in known) {
            val n = when (k) {
                "accelerometer" -> android.hardware.Sensor.TYPE_ACCELEROMETER
                "proximity" -> android.hardware.Sensor.TYPE_PROXIMITY
                "light" -> android.hardware.Sensor.TYPE_LIGHT
                "gyroscope" -> android.hardware.Sensor.TYPE_GYROSCOPE
                "magnetometer" -> android.hardware.Sensor.TYPE_MAGNETIC_FIELD
                "step_counter" -> android.hardware.Sensor.TYPE_STEP_COUNTER
                "barometer" -> android.hardware.Sensor.TYPE_PRESSURE
                else -> -1
            }
            out.put(JSONObject().put("type", k).put("present", sm?.getDefaultSensor(n) != null))
        }
        return JSONObject().put("sensors", out).put("available_raw", present).put("ok", true)
    }

    private fun parseEpochSec(s: String): Long? {
        if (s.isBlank()) return null
        return try {
            s.trim().toLong()
        } catch (e: Exception) {
            try {
                SimpleDateFormat("yyyy-MM-dd'T'HH:mm", Locale.US).parse(s)?.time?.div(1000L)
            } catch (e2: Exception) {
                SimpleDateFormat("yyyy-MM-dd HH:mm", Locale.US).parse(s)?.time?.div(1000L)
            }
        }
    }
}