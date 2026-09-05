# piSynapse Android Port — Durum Dokümanı

> Durum: **CANLI (v0.12).** Kapaciter + Kotlin portu telefondaki `com.pisynapse.app` üzerinde çalışıyor; Gemma-4-E2B tamamen çevrimdışı, native tool-call döngüsünde. Bu dosya gerçekleşen mimariyi yansıtır (9/2025-09-05 güncel).
> Karar zinciri (geçmiş): native Yeniden derleme → UI mevcut SPA'dan (Capacitor) → LiteRT-LM + Gemma E2B.

## 0. Gerçekleşen durum özeti (2026-09-05)

- **UI:** `static/index.html` birebir paketlendi (Capacitor 8, WebView/Chromium; HW accel Android'de yerleşik açık). SW yok — asset pakette, model native'de. (Plan §7 onaylandı.)
- **Bridge:** tek `PiSynapseBridge` (Capacitor plugin); `window.PiSynapse.*`/`window.Capacitor.Plugins.PiSynapse`. `configGet/Set`, `invokeTool`, `modelStatus`, `chatStream` (SSE event kanalı), `deviceStatus`, `sensorsList`, `chatHistorySave/Load`, **`listMemory`/`deleteMemory`**, **`requestPermission`/`permissionStatus`**, `requestPermissions/checkPermissions` (Capacitor-standart).
- **LLM:** `com.google.ai.edge.litertlm:litertlm-android:0.12.0` (Google Maven; minSdk 23; arm64+x86_64). Gemma-4-E2B-it `.litertlm` (2.59GB) internal storage (`files/models/`). Streaming `Flow<Message>`, `automaticToolCalling=true` native tool döngüsü.
- **Tools (16):** datetime, weather, notes (Nextcloud), memory, tasks (lokalde JSON), email (intent), calendar (intent/ACTION_INSERT). Ortak dispatch tablosu `ToolRunner` (bridge + OpenApiTool aynı havuz). Ayrıca `save_memory`/`create_task`/`send_email`/`create_calendar_event` web tool'ları web tarafında.
- **Config:** `ConfigStore` → `filesDir/config.json`; schema `configGet`; yeni anahtarlar `HISTORY_LIMIT`, `MEMORY_LIMIT`, `LLM_TITLE_ENRICHMENT`, `ASSISTANT_USER`, `MAIL_PROVIDER`, `SERVER_URL`, `SERVER_USER`, `SYNC_MODE`, `SYNC_ALWAYS`; legacy `TEMPERATURE`/`TOP_P`/`TOP_K` alias'tır. Şema 2 sekme: **Telefon** (Zeka/Üretim/Sohbet/Hava/Notlar/Ses/Uygulama) + **Sunucu** (Senkron/Bağlantı/Kişisel) — `byGroup()` ile ayrılır.
- **İzinler:** manifest'e `WRITE_CALENDAR`, `READ_CALENDAR`, `RECORD_AUDIO`, `ACCESS_FINE_LOCATION`; JS ilk açılışta `requestPermission` ile tek seferlik sistem diyaloğu başlatır (`localStorage ps_perm_asked`).
- **Chat kalıcılığı:** `filesDir/chat_history.json` (native), JS `_nativeChatSave/Restore`; restart sonrası geri gelir. Gerçek-native geçişe hazır.
- **Hafıza:** native `listMemory`/`deleteMemory` → JS `_nativeApiRoute` `/chat/memories` GET/DELETE → `loadMem()` sidebar `#sidebar-mem-list .mem-card` render. `importance:5` varsayılan.
- **Kısıt/öğrenilmiş:** `.litertlm` ikilisi **CPU-only** (tüm bölümlerde `section_backend_constraint: cpu`) → GPU/NPU isteği reddedilir. `maxNumTokens` = **toplam context slot** (input+output); yetersizse `Status 3: input token ids too long` görülür, `max_tokens` artır.

## 1. Amaç & kapsam

- Projeyi Android cihazda (TECNO CM5 / 12GB RAM test cihazı; hedef sınıf Helio G100 / 6–8GB) **tam çevrimdışı** çalışan bir uygulamaya taşımak — gerçekleşti.
- Python'u gömmek yok: **native Kotlin/Java** + mevcut web UI'nin paketlenmesi (Capacitor).
- Mevcut UI kimliği (tema/glass/WCAG/mobil CSS) birebir korunacak; sıfır UI redizayn.

## 2. Mevcut mimari özeti (taşıma kaynağı)

| Katman | Mevcut | Android karşılığı |
|---|---|---|
| HTTP | FastAPI + uvicorn (SSE) | Kaldırılır → Capacitor bridge |
| LLM | `litert_serve/` (LiteRT-LM) | LiteRT Java API / llama.cpp |
| Embedding | fastembed (onnxruntime) | LiteRT tflite embed |
| STT | faster-whisper (ctranslate2) | whisper.cpp (JNI) |
| TTS | piper (onnxruntime) | piper-onnxruntime / Android TTS fallback |
| DB | aiosqlite | Room |
| Tools | nextcloud_notes/tasks, mail (IMAP/SMTP/CalDAV), weather | Kotlin port + OkHttp/dav4j |
| Config | config.py + .env | DataStore/Preferences |
| UI | static/index.html (SPA, SW, SSE) | Capacitor asset (birebir) |

Not: `litert_serve/server.py` bir **OpenAI-uyumlu mini HTTP sunucusu**; mantık (tool döngüsü, tool_calls nasıl beslenir) korunarak Kotlin'e taşınır.

## 3. Gerçekleşen mimari

```
piSynapse Android APK (Gradle, Kotlin 2.3.21)
├── Capacitor 8 çekirdeği
│   └── static/index.html + CSS/JS — WebView (Chromium, HW-accel yerleşik)
├── PiSynapseBridge (Capacitor plugin, coroutine-IO)
│   ├── LLM: LiteRT-LM 0.12.0 (Flow<Message>, automaticToolCalling=true, CPU-only)
│   ├── ConfigStore ↔ filesDir/config.json (bridge.get/set → JS config API)
│   ├── LocalStore: filesDir/tasks.json + memory.json
│   └── Engine loaded status → bridge.modelStatus (async modelBusyEmit)
├── LlmEngine (singleton, 30s loaded timeout, async prewarm)
├── PlatformTools (intent-based: ACTION_INSERT calendar, ACTION_SEND email)
├── PiTools (16 tool spec → OpenApiTool.invokeProviderFn + Definition kaydı)
├── ToolRunner (dispatch: notes↔NotesClient, calendar↔PlatformTools, memory/tasks↔LocalStore, weather↔WeatherClient)
├── WeatherClient (Yahoo unofficial API, OkHttp, API key gerektirmez)
├── NotesClient (Nextcloud WebDAV via OkHttp, kullanıcı web girişi)
└── MainActivity.java (Capacitor activity, değişmez)
```

## 4. Teknoloji kararları (gerçekleşen)

- **Capacitor (Tauri değil):** LiteRT/whisper/onnxruntime hepsi JVM/NDK native — Kotlin en doğal dil; Tauri Rust FFI ek yük.
- **LiteRT-LM 0.12.0 (Google Maven):** `com.google.ai.edge.litertlm:litertlm-android`. Jinja tool-call prompt desteği var (otomatik tool-call). Warm pace ~3.8 tps Helio G100'de kabul edilebilir.
- **DB:** `LocalStore` (tasks.json + memory.json); Room Henüz YOK — server tarafındaki sqlite (aiosqlite) hâlâ ana veri deposu, phone tarafı webDAV/intent tabanlı. **DB her zaman senkron edilebilir kalmalı** (kural), phone/server ayrımı şemada hazırlanacak (bkz. Sıradaki).
- **Config:** `ConfigStore` → `filesDir/config.json` (JSON encode/decode); `schema()` → `configGet` yanıtına şema koyar (sidebar ayar şeması JS'ten native'e geçecek — ŞU AN `_nativeApiRoute` /config sabit döndürüyor, güncelleme bekliyor). LLM parametreleri `LLM_NUM_CTX`(6144), `LLM_MAX_OUTPUT_TOKENS`(512), `TEMPERATURE`, `TOP_P`, `TOP_K`, `LLM_BACKEND_TYPE`(cpu/gpu/npu) vb. bridge.get/"configSet" üzerinden kontrol ediliyor.

## 5. Python → Kotlin eşleştirme tablosu (özet)

| Python | Kotlin sınıfı / kütüphane | Not |
|---|---|---|
| main.py (app + lifecycle) | `MainActivity` + `PiSynapseBridge` | bridge event yüzeyi |
| routers/chat.py (SSE + tool döngüsü) | `LlmEngine` (Flow<Message>, automaticToolCalling) | Native tool loop |
| routers/config.py | `ConfigStore` (`filesDir/config.json`) | `configGet/Set`, şema `schema()` |
| embedding.py / retrieval.py | — | Henüz taşınmadı (ileride) |
| mail.py | `PlatformTools` (ACTION_SEND intent) | Jakarta JIC değil — intent |
| calendar_ops.py | `PlatformTools` (ACTION_INSERT intent) | CalDAV JIC, intent kullanır |
| nextcloud_notes.py | `NotesClient` (WebDAV OkHttp) | |
| tasks.py | `LocalStore` (tasks.json) | |
| memory.py | `LocalStore` (memory.json) | |
| weather.py | `WeatherClient` (OkHttp) | |
| prompt.py | assett'teki prompt şablonları | i18n korunur |
| db.py | `LocalStore` (JSON) + server sqlite | Room yok; DB-her-zaman-sync kuralıyla |
| litert_serve/ | `LlmEngine` (LiteRT-LM API) | max_tokens mantığı taşındı |

## 6. Bridge API tasarımı (gerçekleşen)

- Tek `PiSynapseBridge` plugin (Capacitor). JS tarafında `window.Capacitor.Plugins.PiSynapse` + `window.PiSynapse` helper'ı.
- **Yöntemler:**
  - `configGet() → {schema, values}` • `configSet({values})` — ConfigStore (kısıt)
  - `invokeTool({name, args}) → {result}` — ToolRunner dispatch
  - `modelStatus() → {loaded, modelName, backend}` — LlmEngine durumu
  - `chatStream({purpose, messages, toolList}) → event` — token stream event, iki yönlü
  - `deviceStatus()`, `sensorsList()`, `requestPermission({type})` (rehber eklenecek)
  - `chatHistorySave({history})`, `chatHistoryLoad() → {history, sessions}` (native kalıcılık)
- **JS adapter:** SPA'nın `/api/*` fetch/SSE çağrıları `_nativeApiRoute` (native modda) + `window.__ANDROID_LLM__` kapısıyla bridge'e bağlanır; UI değişmez, gerçek-native geçiş noktaları `__PISYNAPSE__WS__` benzeri bayraklarla feature-detected.
- **Stream yönelimi:** yüksek frekanslı tokenlar tek yönlü plugin event (/chat/stream SSE yerine), request/response bridge'den ayrı.

## 7. UI uyarlamaları

- **SW devre dışı:** Capacitor Android local scheme'de SW kaydı güvenilmez (doğrulandı). Yüklü uygulamada gerek yok — asset pakette; model/corpus indirme native. `sw.js` kaydı sadece web build'de kalır.
- **SSE→bridge:** mevcut EventSource mantığı, plugin event listener ile değiştirilir (ayrı dosya, `window.__PISYNAPSE__WS__` feature-detect).
- **Tema/glass/WCAG işi:** aynen kalır. WebView render motoru Chromium = aynı emülasyon ortamı (problem: HW accel Android'de zaten açık — desktop'taki Brave sorunu yok).
- Sonuç: mobil CSS zaten Playwright mobil emülasyonunda doğrulandı.

## 8. Model & RAM hesabı (Helio G100 — 6–8GB)

| Model | Yaklaşık boyut (int8/Q4) | Not |
|---|---|---|
| 3–4B ctx 8K | ~2.8–3.7 GB + KV (birkaç yüz MB) | 8GB cihazda tamam; 6GB'ta zorlu trim |
| 8B | ~7.5 GB | Uygun değil (OOM riski) |

- TTS sesleri: ~20–60 MB; whisper: small ~460 MB (isteğe bağlı; zayıfsa cihaz STT'yi fallback).
- Pi5'ten aktarmak ya da ilk açılışta indirme: **açık karar**.

## 9. Faz durumu (dalda ilerleme)

- **Aşama 0 — İskelet:** ✅ Capacitor 8 + Kotlin projesi; SPA WebView'a paketlendi; UI birebir görünür.
- **Aşama 1 — Servis hattı:** ✅ Bridge'den weather/notes/memory/tasks/calendar/email; UI gerçek native veri kullanıyor (intent/WebDAV/JSON).
- **Aşama 2 — LLM çekirdek:** ✅ LiteRT-LM 0.12.0 + Gemma-4-E2B; streaming + native tool döngüsü; kalıcılık. (GPU/NPU reddedildi — model CPU-only.)
- **Aşama 3 — Ses:** ⏳ Henüz başlanmadı.
- **Aşama 4 — Gerçek-native / kalan:** ⏳ DB her-zaman-senkron, ayar sekmeleri (phone/server), only-phone/only-server sync modları, hafıza panosu native, runtime izin (WRITE_CALENDAR gibi).
- **Aşama 5 — Paketleme:** ⏳ model dağıtım akışı, ilk-açılış rehberi, manuel test.

## 10. Riskler & açık sorular (güncel 2026-09-05)

1. ✅ **LiteRT Java artifact:** `com.google.ai.edge.litertlm:litertlm-android:0.12.0` kararlı; CPU-only ikili (gpu/npu denendi → red).
2. ⚠️ **CalDAV/IMAP:** intent tabanlı (PlatformTools) çalışıyor, ancak tam CalDAV/İMAP (dav4j/jakarta) port edilmedi — kullanıcı ihtiyacına göre açık.
3. ⚠️ **STT/TTS:** henüz yok; olunca whisper.cpp JNI / Android TTS fallback.
4. ⚠️ **Refresh token / nextcloud oturum** WebDAV'da kalıcılık; şu an kullanıcının web girişi + token.
5. ⚠️ **RAM:** Helio G100 6GB'ta 4B model marjinal — trimi gerekiyorsa; Cihazki 12GB tamam.
6. ⚠️ **DB sync:** server sqlite ana depo; phone tarafında yerel JSON; DİKKAT: eşitleme katmanı (updated_at/deleted) henüz şemada yok — "DB her zaman senkron edilebilir" kuralı bunu zorunlu kılıyor (kullanıcı kararı, 2026-09-05).
7. ⚠️ **CalDAV kenar durumları** (invite, recurrence) intent tabanlı değil, ileride gerekirse.
8. ⚠️ **WebView vs desktop Chromium:** görsel karşılaştırma A0'da yapıldı, sorun yok.

## 11. Repo düzeni & senkron akışı

- Pi repo: `piSynapse/` (server + `static/` tek gerçek SPA kaynağı). Android iskeleti `piSynapse/android/` altında; build laptop'ta `pisynapse-android/` (gradle) üzerinden yapılır, APK telefona kurulur.
- **Build zinciri (güncel):** Pi'de `npx cap copy android` → `static/index.html`` + asset `android/android/app/src/main/assets/public/`'e → scp laptop `pisynapse-android/android/app/src/main/assets/public/` → gradle `assembleDebug` → APK.
- `static/` değişiklikleri (UI) Pi'de oturur; Kotlin kaynakları laptop'ta, Pi'deki kopyayla eşleştirilir (git'in single-source-of-truth olması için android/ klasörü repo'ya girmeli).
- **Senkron akışı (hedef):** `SYNC_MODE`: `only-phone` (tüm veri cihazda, server'a yazmaz) / `only-server` (server ana depo, cihaz aracı) — ayarlarda her zaman görünür; DB schema phone/server ayrımına göre `updated_at`+`deleted`+origin kolonlarıyla hazırlanır (çakışmalarda last-write-wins). Henüz UYGULANMADI (hedef).
- **Hafıza (bilinen sorun):** native modda `/chat/memories` route'u yok → JS `loadMem` server fetch'e düşüyor → "sunucuya ulaşılamadı". Düzeltilecek: native memory route (LocalStore memory.json) + JS'te native-first. (Kullanıcı raporu, 2026-09-05.)

## 12. Referanslar

- Capacitor 8 (2025-12), Android rehberi: https://capacitorjs.com/docs/android
- LiteRT (TFLite successor): Google AI Edge — https://ai.google.dev/edge/litert
- llama.cpp / llama-android: https://github.com/ggml-org/llama.cpp
- whisper.cpp: https://github.com/ggml-org/whisper.cpp
- onnxruntime-android AAR: https://onnxruntime.ai
- piper: https://github.com/rhasspy/piper
- dav4j (CalDAV/CardDAV), ical4j (iCal), jakarta.mail
- @capacitor-community/sqlite (web dev için; prod'da Room)