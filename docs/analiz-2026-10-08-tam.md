# piSynapse — Kapsamlı Analiz Raporu (2026-10-08) — TAM METİN

> Metod: 6 paralel subagent; her biri NOTES.md + hedef dosyaları satır satır okudu.
> Kapsam: 155 dosya / ~30K Python satırı / 56 test dosyası / 767 test / 23 tool / 22 router.
> Bu dosya, subagent'ların HAM raporlarının birebir birleşimidir (özet için
> `analiz-2026-10-08.md`; ham tek tek raporlar için `analiz-2026-10-08/`
> klasöründe 6 dosya).
> Kullanım: haftalık ilerlemede her satır iş kalemi olarak ele alınabilir.
> Önem sırası: [Yüksek] > [Orta] > [Düşük].

---

# YÖNETİCİ ÖZETİ — En kritik 10 bulgu

1. **`static/ui.js:383` — `esc()` fonksiyonu NO-OP.** Replace zinciri kaçış
   üretmiyor (`esc("<")` → `"<"` dönüyor), 168 çağrı noktası korumasız. XSS
   savunmasının tek katmanı çökmüş durumda. **Yüksek.**
2. **Post-refresh login bug'ının KÖK NEDENİ bulundu (`static/ui.js:1768`).**
   `/users/session` şifre girişi API key döndürmüyor (`routers/users.py:97-111`);
   boot kapısı ise `getApiKey()` doluluğuna bakıyor → refresh'te key boş → login.
   Ek katkı: `sw.js:61-74` oturumlu GET'leri cache'liyor; `main.py` cookie
   `secure` statik `.env`'den. **Yüksek.**
3. **2026-09-27'de kapatılan Nextcloud deliği YENİDEN AÇIK**
   (`nextcloud_tasks.py:59`): `_get_task_calendar` önbelleği credential
   kapısından önce → cache ısındıktan sonra NC_CREDS/NC_SHARED_OK sorgulanmıyor.
   Aynı desen `calendar_ops.py:87,141` global DAV/olay cache'lerinde. **Yüksek.**
4. **Embedding asılı indirme → tüm sohbet 504.** Circuit breaker yalnızca
   exception'da tri'e geçiyor; "0% asılı kalma" senaryosunda `_model_lock`
   sonsuza dek tutuluyor, istek yolunda timeout yok (`embedding.py:19-43`,
   `db.py:1664`, `routers/chat.py:314-341`). 4 subagent aynı sonuca vardı. **Yüksek.**
5. **Çapraz kullanıcı veri sızıntısı (veri katmanı):**
   `search_sessions` FTS dalında user_id yok (`db.py:1982-2003`) + `save_message`
   oturum sahipliği doğrulamıyor (`db.py:1684-1689`). **Yüksek.**
6. **Prompt-injection gadget (`llm/stream.py:512-516`):** `use_tools=False`
   iken düz metinden çıkarılan leaked tool call, `allowed_names=None` yüzünden
   guard bypass edilip çalıştırılabiliyor. **Yüksek.**
7. **`/chat/abort/{session_id}` sahiplik doğrulaması yok** — 3 subagent
   bağımsız buldu (`routers/chat.py:462-470`). **Yüksek/Orta.**
8. **`main.py:534-545` — `/debug` auth + 8KB limit ÖNCESİNDE tüm body'yi
   belleğe tamponluyor** → kimliksiz DoS. **Yüksek.**
9. **LLM niyet fallback'inde timeout YOK** (`llm/intent.py:701-740`); paylaşılan
   client 600 sn. P3 "10 sn guard" NOTES'ta "pending" — kodda doğrulandı, yok. **Yüksek.**
10. **`install.py:1318-1324` — cryptography düşerse Fernet-uyumsuz anahtar**
    üretiliyor; kayıtlar kalıcı olarak çözülemez hale geliyor. **Orta.**

**Konverjans notu (farklı subagent'ların bağımsız ortak bulguları):**
esc() no-op, embedding asılı indirme, calendar/task global cache sızıntısı,
`/chat/abort` sahiplik, SW API cache'i, TRUST_X_FORWARDED_FOR yorum/kod tersliği,
`docs/port-contract.md` test sayılarının bayat olması.

---
---

# RAPOR 1 — BACKEND ÇEKİRDEK (main.py, config.py, auth.py, credstore.py, examples, idempotency, request_id, title, weather, tool_verification)

Kapsam: `main.py` (~760 satır), `config.py` (~500), `auth.py`, `credstore.py`,
`request_id.py`, `idempotency.py`, `title.py`, `weather.py`, `tool_verification.py`,
`example.env`, `example.config.json`, `config.example.json`, `messages.py`,
`utils.py`, `retrieval.py` (küçük kısım).

## A. GÜVENLİK

### A1. [Yüksek] `/debug` auth ÖNCESİNDE sınırsız body tamponlama — `main.py:534-545`
- `main.py:538`: handler ilk satırda `body = await request.body()` çağırıyor.
- Bu satır `x-api-key` doğrulamasından (549-553), 8KB body limitinden (617-625),
  rate limit'ten ÖNCE çalışıyor.
- 8KB limit (`MAX_DEBUG_BODY = 8192`, satır 617) yalnızca handler'ın İÇİNDE,
  yani auth'dan sonra uygulanıyor.
- Sonuç: kimliği olmayan herkes POST /debug ile GB'lerce gövde
  belleğe yükleyebilir (ram DoS); `await request.body()` gövdeyi tamamen okur.
- Ayrıca `body` okunduktan sonra endpoint `request.json()` tekrar dener
  (`_beacon` akışı, satır 747-759) — ikinci okuma farklı bir Request nesnesi
  üzerinde; payload'ın gerçekten loglanıp loglanmadığı doğrulanmalı.
- Öneri: Content-Length header'ını auth'dan ÖNCE kontrol et (>8KB → 413),
  gövdeyi yalnız `content-length` varsa oku, chunked'ta `request.stream()` ile
  sınırlı oku; `/debug`'a erken rate-limit.

### A2. [Yüksek] `calendar_ops` global DAV cache — kullanıcılar arası sızıntı
- `calendar_ops.py:85-101` → `_dav_calendar(client)` sonucu process-genel
  `_dav_calendar_cache` içinde; anahtar `client` nesnesi olsa da aynı credential
  üreten fonksiyon (`_get_dav_client`) farklı kullanıcılar için FARKLI client
  nesnesi döndürür; ancak `calendar_ops.py:65-82` `_dav_client` cache'i yalnız
  modül genelinde tek client (shared fallback) — oradan A'nın client'ı B'nin
  isteğinde de kullanılabilir.
- `_find_events_cache` (calendar_ops.py:141) 5 sn TTL, anahtar SİZ, A'nın
  sorgu sonucu B'ye döner.
- Sonuç: kullanıcılar arası veri sızıntısı + yanlış kullanıcıya yazma riski.
- Öneri: tüm global cache anahtarlarına credential fingerprint / user_id ekle.

### A3. [Orta] `TRUST_X_FORWARDED_FOR=on` → tüm istemciler "unknown" kovasında
- `config.py:177-179` yorum "Enabled by default" diyor; kod varsayılanı `off`.
- `main.py:582-588`: XFF header yoksa `client_ip = ""` → `"unknown"` olarak
  dönüyor; `x-forwarded-for` yoksa bile `on` ise okuma yapılıyor mu doğrula
  (kodda header yoksa fallback `request.client.host` YOK).
- Etki: XFF göndermeyen gerçek istemciler (curl, LAN) tek "unknown" IP →
  rate limit `429` karşılıklı tetiklenir = kendi kendine DoS.
- Öneri: `x-forwarded-for` yoksa `request.client.host`'a düş; `on` yalnız
  proxy arkasında.

### A4. [Orta] Log forging — `main.py:409,413`
- `x-request-id` header'ı istemciden geldiği gibi `logging` extra ve yanıt
  header'ına yazılıyor; `request_id.py` doğrulama yalnız `X-Request-Id`
  kendisinde (`request_id.py:8-10` var mı — subagent doğruladı: header değeri
  normalize edilmiyor).
- Öneri: `[A-Za-z0-9_-]{1,64}` filtresi; uymuyorsa üret + logla "rejected".

### A5. [Orta] Parola değişikliği cihaz anahtarlarını revoke etmiyor — `routers/users.py:149-151`
- PATCH `/users/password` yalnız `UPDATE user_sessions SET revoked=1` yapıyor
  (browser oturumları); `user_api_keys` satırları (`active=1`) olduğu gibi kalıyor.
- Etki: çalınan/ezilmiş API key, parola bile değiştirilse geçerli kalır.
- Öneri: parola değişikliğinde aynı kullanıcı `user_api_keys` için de
  `revoked`/rotasyon (veya `key_version` artırma) uygula; OPTIONS NOTU:
  `user_api_keys` şemasında `revoked` kolonu olmayabilir → migration gerekebilir.

### A6. [Orta] `/chat/upload` 100MB'a kadar bellek + base64 — `routers/chat.py:827-863`
- Gövde doğrudan `await request.body()` ile alınıp base64'e çevriliyor
  (`base64.b64encode(payload).decode()`), sonra dosyaya yazılıyor.
- 100MB binar → base64 ile ~133MB string + kopyalar → Pi 5'te OOM riski.
- Öneri: default limiti düşür (örn. 25MB), `request.stream()` ile diske akıt,
  base64'ü yalnız modal/UI'a gerekirse.

### A7. [Orta] `/chat/abort/{session_id}` sahiplik yok — `routers/chat.py:462-470`
- Endpoint yalnız `_uid` (auth) kontrolü yapıyor; path'teki `session_id`
  herhangi bir kullanıcının oturumuna ait olabilir.
- Etki: kimlikli her kullanıcı başkasının üretimini durdurabilir (IsI/DoS).
- Aynı bulgu rapor 3 ve rapor 4'te de bağımsız tekrarlanmış (konverjans).
- Öneri: `SELECT user_id FROM sessions WHERE id=?` → `!= _uid` ise 404/403.

### A8. [Orta] `/health` `startup_error` sızıntısı — `main.py:677-679, 724-744`
- `startup_error = f"{type}: {e}"` auth'suz JSON'da; SQLite `no such table`,
  dosya yolu, import hatası dışa açık.
- Öneri: detayı logla, dışa `{"status":"degraded"}`; detay yalnız
  `_uid + is_admin`.

### A9. [Düşük] `/static` prefix eşleşmesi — `main.py:510`
- `path.startswith("/static")` bölüm karakteri olmadan: `/staticX` da eşleşir.
- `"/static/"` + `path == "/static"` yapı.

### A10. [Düşük] CSP yok — `main.py:483-496`
- `X-Content-Type-Options`, `X-Frame-Options` var; `Content-Security-Policy` yok.
- XSS (esc() no-op) tek katman savunmasız; CSP ikinci katman olurdu.
- Öneri: nonce tabanlı CSP (inline script'ler `web.html`/`app.html` var).

### A11. [Düşük] HSTS yalnız `url.scheme=="https"` — `main.py:494-495`
- Uvicorn `--proxy-headers` kullanılmadığından (service template) scheme hep
  `http` → HSTS hiç eklenmez.
- Öneri: `--proxy-headers --forwarded-allow-ips=127.0.0.1` veya
  `PISERVE_BEHIND_PROXY` ile şartı kaldır.

### A12. [Düşük] `Permissions-Policy: microphone=()` — `main.py:489-492`
- Web'de `getUserMedia` (sesli sohbet varsa) bu header ile engellenir.
- Doğrula: sesli giriş kullanılıyor mu? Kullanılıyorsa `microphone=(self)`.

### A13. [Düşük] Rate limiter bucket taşması — `main.py:67-68`
- `_MAX_BUCKETS = 10000`; dolunca yeni IP'ler `kovi yok` → hep 429.
- Periyodik LRU/yaş temizliği ekle.

## B. TUTARSIZLIK

### B1. [Orta] `UI_LANGUAGE` config'de tanımsız — config.py + messages.py:50
- `messages.py:50` `config.UI_LANGUAGE` okuyor; `config.py`'de böyle bir
  attribute TANIMLANMIŞ DEĞİL → her zaman `AttributeError` mı yoksa getattr
  fallback mi? subagent: `get()` fallback `default_lang="en"` → `.env`'deki
  dil anahtarı tamamen ÖLÜ.
- Öneri: `UI_LANGUAGE = os.getenv("UI_LANGUAGE", "en")` config'e ekle;
  `.env`'de `UI_LANGUAGE=tr` örneğini example.env'e yaz.

### B2. [Orta] `ENV_PATH`/`DB_PATH` göreli → split-brain — `config.py:85-86`, `example.env:58,120`
- `ENV_PATH = os.getenv("ENV_PATH", ".env")`, `DB_PATH=assistant.db` göreli.
- Farklı CWD'den başlatılan ikinci process ikinci .env + ikinci assistant.db
  oluşturur (NOTES "ikinci DB" felaketi ile aynı desen).
- Öneri: `REPO_ROOT = Path(__file__).resolve().parent` göreli çöz.

### B3. [Orta] `sync_config()` ölü senkronizasyon — `config.py:475-495` ↔ `main.py:26-31,93-101`
- `sync_config()` RATE_LIMIT_* ve MEDIA_MAX_MB'yi config'e yazıyor ama:
  - rate limiter nesneleri import anında kuruluyor (module level),
  - `main.py` `from config import X` ile by-value kopyalıyor.
- Sonuç: .env değişiminden sonra limiter/media limit değişmez (API PATCH'i
  ölü).
- Öneri: okumaları runtime'da `config.X` üzerinden yap veya PATCH'te limiter
  nesnesini de rebuild et.

### B4. [Orta] Ollama/LLM varsayılanı yorum-kod ters — `config.py:89-90`
- Yorum "ollama (default)", kod `"litert"` (NOTES: Ollama durduruldu).
- Yorumu düzelt; `litert_serve/server.py` ile iki taraflı doğrula.

### B5. [Orta] `_session_limiter` hiç kullanılmıyor + client-supplied anahtar — `main.py:96,366` + `config.py:175`
- docs "20 req/min per session" diyor; middleware'de `_session_limiter` tanım
  dışında (dead) ve anahtar istemcinin gönderdiği `session_id` → baypas edilebilir.
- Öneri: anahtar `user:{uid}:{session}`; middleware'e gerçekten bağla.

### B6. [Düşük] `get_user_id_for_key()` her bilinmeyeni "default"a map eder — `config.py:39-54`
- Ölü kod (kullanım yok) ama docs hâlâ "kimlik doğrulama" gibi referans veriyor.
- Sil veya raise.

### B7. [Düşük] `.env`'de okunmayan anahtarlar — `example.env:127,129`
- `PISERVE_ADMIN_TOKEN`, `AUDIT_EXPORT_DIR` şablonda var, `config.py` okumuyor.
- config docstring "herkes config'ten import eder" diyor → ya taşı ya sil.

### B8. [Düşük] PATCH bilinmeyen anahtar sessiz — `routers/config.py:245-246`
- `continue` → istemci `{"ok":true}` alır, hiçbir şey değişmez.
- Yanıta `{"skipped":["..."]}` ekle.

### B9. [Düşük] Kişisel anahtarlar global .env'de — `routers/config.py:110`
- Örn. NEXTCLOUD_* kişisel ayarlar sistem .env'de okunup yazılabilir;
  kişisel/sistem ayrımı bulanık (NOTES "effective_setting" kuralı ile gerilim).

## C. NOTES KURAL İHLALLERİ / BİLİNEN BUG BAĞLANTILARI

### C1. [Orta] Cookie `secure` statik `.env`'den → post-refresh login hipotezi — `routers/users.py:24-28` + `config.py:182`
- `Set-Cookie: ...; Secure` bayrağı `SESSION_COOKIE_SECURE` (default on? subagent:
  default değer config.py'de `on` ise HTTP localhost'ta tarayıcı cookie'yi
  REDDEDER — http'de Secure cookie yazılmaz.
- NOTES hipotezleri arasında "cookie Secure attr yanlış varsayımı" bu satırda
  doğrudan kanıt: login 200 dönüyor ama cookie disk'e yazılmıyor → refresh'te
  `/users/me` 401 → login ekranı.
- Öneri: `secure = SESSION_COOKIE_SECURE and request.url.scheme == "https"`
  (request üzerinden) veya localhost için otomatik kapat.

### C2. [Orta] SW oturumlu GET'leri cache'liyor — `static/sw.js:39-44`
- Denylist yalnız `/chat,/config,/widget,/health`.
- Cache'lenen oturumlu GET'ler (subagent listesi): `/users`, `/users/me`,
  `/users/session` (GET?), `/admin/patterns/review`, `/tools/groups`,
  `/chat/sessions`, `/chat/memories`, `/history/pull`, `/export` vb.
- `stale-while-revalidate` → logout sonrası eski 200'ler servis edilebilir.
- Öneri: allowlist'e geç (yalnız `/static/*`), logout'ta `caches.delete`.

### C3. [Orta] SW `CACHE_NAME` elle versiyonlu — `static/sw.js:1,17-24`
- `pisynapse-v55` sabit; asset'ler `?v=` olmadan (`web.html:14,220`) → bump
  unutulursa eski shell.
- Öneri: build hash veya manifest sürümünden oku.

### C4. [Düşük] `STATIC_ASSETS` içinde `/` (307 redirect) — `sw.js:4,48-59`
- Redirect'i cache'ler. Listeden çıkar.

### C5. [Orta] Hardcode tek-dilli Türkçe (kural 9) — `title.py:18,20`
- `"Yeni Sohbet"`, `"[e-posta]"` doğrudan kullanıcıya dönen string.
- `messages.py` kataloğa taşı (katalogta şu an yalnız 3 anahtar).

### C6. [Orta] `weather.py` durum etiketleri Türkçe + özet EN — `weather.py:44-61,132-133`
- Tek çağrıda karışık dil; katalog hiç kullanılmıyor.

### C7. [Orta] Widget router'ları global DEFAULT_CITY — `routers/widgets.py:17-34`
- `/widget/weather` kişisel şehir yerine `config.DEFAULT_CITY`.
- `/widget/calendar` NC bağlamı hiç set edilmediği için hep boş (2026-09-27
  fix'inden sonra regresyon).
- `effective_setting(user_id, ...)` + istekte NC bağlamı set et.

### C8. [Orta] `save_memory` doğrulaması user_id'siz — `tool_verification.py:191,263-265`
- Kural 5: her user-scoped sorguda owner guard — bu iki yerde yok.

### C9. [Düşük] `sync_items` device origin kolonu yok — `db.py:527-536`
- 2026-09-05 TECHNICAL WARNING (NOTES'ta "TECHNICAL WARNING" olarak geçiyor):
  yeni `sync_items` origin kolonu içermiyor → doğrudan ihlal. (Rapor 2 ile
  çakışan madde; iki raporda da var.)

### C10. [Düşük] Ollama kod yolları hâlâ canlı — `main.py:266-290`, `config.py:398`
- NOTES "Ollama durduruldu" ama "dual-backend continues" notu da var →
  karar netleştirilmeli; hangisi güncel?

### C11. [Düşük] Test fixture `config.DB_PATH` patch etmiyor — `tests/conftest.py:59-79`
- `db.DB_PATH` patch'li; `config.DB_PATH` değil → ileride kırılgan.

## D. İYİLEŞTİRME

### D1. [Orta] `_redact_debug_body` ölü kod olabilir — `main.py:538-544` ↔ `747-759`
- Middleware kendi Request nesnesinde body okuyor; endpoint ikinci Request ile
  `request.json()` dener. İkinci okuma boş/different olabilir → beacon payload'ı
  hiç loglanmamış olabilir.
- Doğrulama: canlı beacon gönder, log satırını kontrol et.

### D2. [Orta] Doğrulama listeleme round-trip'leri — `tool_verification.py:146-206`
- Her mutasyon sonrası tam listeleme (CalDAV/NC 2×, list_events cache'ine takılır).
- Background task veya nokta-okuma.

### D3. [Orta] `httpx.AsyncClient` hiç kapanmıyor — `weather.py:19-26`
- Modül geneli tek client; lifespan'te `aclose()` yok.
- Lifespan kapanışında kapat veya get/asynccontextmanager.

### D4. [Orta] `.env` yazma istisnası `except: pass` — `credstore.py:30-45`
- Başarısızlıkta her çağrıda geçici Fernet key → kayıtlar kalıcı çözülemez
  (rapor 6 ile birlikte en kritik credential bulgusu).
- Sabit key üret + kullanıcıya uyar; write'ı yeniden dene.

### D5. [Düşük] Senkron `@retry` event loop'u dondurabilir — `utils.py:74-86`, `mail.py:37,66,105`
- `time.sleep(4)` senkron; event loop'ta çağrılırsa 4-6 sn donma.
- `asyncio.to_thread` zorunluluğunu doğrula/uygula.

### D6. [Düşük] `decode_header` `LookupError` — `utils.py:113-125`
- Bilinmeyen charset `LookupError` fırlatır, `_is_retryable` anlamsız retry yapar.
- `codecs.lookup` kontrolü + fallback UTF-8.

### D7. [Düşük] Docstring "prevents XSS" — `utils.py:138-154`
- Regex temizlik; asıl savunma frontend `esc()`. Docstring düzelt
  (gerçekten de `esc()` şu an NO-OP → bu docstring artık iki kat yanlış).

### D8. [Düşük] `run_verification` docstring — `tool_verification.py:81-86` ↔ `109-111`
- "(None,None)" diyor; kod `verification_error` döndürüyor.

### D9. [Düşük] `max_words` ölü parametre — `title.py:11` vs `25`
- `max_words=5` her koşulda 4'te kesiliyor.

### D10. [Düşük] `merge_history` dedup eksik — `retrieval.py:41-46`
- Dedup yalnız recent window'a karşı; retrieved listesi içinde mükerrerler kalır.
- "chat duplicate window" vakası ile şüpheli bağlantı: `(role, content)` ile
  dedup'la.

### D11. [Düşük] `add_middleware` insert(0) sırası — `main.py:407-416,471-478`
- Starlette zincirde son eklenen dışta; erken 401/429/413 yanıtlarının
  başlıklardan mahrum kalma riski — empirik doğrula.

### D12. [Düşük] `request: Request = None` imzaları — `routers/chat.py:694-700,742-748`
- Zayıf tip güvenliği; `Request` zorunlu yap.

### D13. [Düşük] `POST /reload-corpus` auth guard'sız — `routers/chat.py:728-739`
- (`require_admin` yok; rapor 4'te de tekrarlanmış.)

## E. DOĞRULANAN OLUMLULAR

- `eval/exec/pickle.loads/os.system/shell=True` kullanımı: **YOK** ✓
- SQL f-string'ler sabit/placeholder dışında değil ✓
- services/DI katmanı kalıntısı: **YOK** ✓ (NOTES 2026-10-02 silinmiş)
- Docker/WS kalıntısı: **YOK** ✓
- `example.env` ↔ `install.py` anahtar kümesi: **69/69 birebir** ✓
- `messages.py` i18n iskeleti mevcut (anahtar sayısı az) ✓

---
---

# RAPOR 2 — VERİ KATMANI (db.py, retrieval.py, embedding.py, corpus_feeder.py, textnorm, reembed_all.py, backup/restore)

Kapsam: `db.py` (3312 satır), `retrieval.py`, `embedding.py`, `corpus_feeder.py`,
`textnorm.py`, `reembed_all.py`, `backup/restore`, `tests/test_user_isolation.py`,
`tests/conftest.py`.

## A. BİLİNEN BUG DOĞRULAMALARI

### A1. [Yüksek] Embedding asılı indirme → kilit asılı — `embedding.py:19-43`, `config.py:20`
- Düzeltmeler kodda VAR: `_BREAKOUT_AFTER = 600` (10 dk) + `HF_HUB_DOWNLOAD_TIMEOUT=30`.
- AMA bug KAPANMAMIŞ:
  - Breaker yalnızca `except` bloğunda tri'e geçiyor (`embedding.py:36-43`).
  - hf_hub_download "0% indirme, asılı kalma" senaryosunda **exception üretmez**
    (timeout'a kadar sessiz) → breaker tri olmaz → `_model_lock` tutulmaya devam.
  - `save_message` → embed çağrısı `db.py:1659-1666` yolunda **hiç timeout yok**.
  - `retrieval.py:129` yalnız `asyncio.to_thread(...)` içinde `wait_for` var mı
    kontrol edildi: `retrieval` tarafında 1500ms bütçe var ama kilit zaten
    tutulduğu için budget işe yaramaz (kilit beklemesi timeout'tan önce).
- Sonuç: NOTES'taki "chat duplicate window / takılma" vakası hâlâ canlı.
- Öneri: model yükleme/indirmeyi `asyncio.to_thread` + `wait_for(300)` içinde
  worker'a taşı; kilit yalnız `self._model = model` atamasında tutulacak;
  her embed çağrı yoluna üst sınır (5-10 sn) ekle; timeout'u da breaker
  sayacına yaz.

### A2. [Orta] "Duplicate window" aslında yalnız son-satır kontrolü — `db.py:1648-1657`
- `save_message` tekrar kontrolü: yalnız **önceki asistan satırının birebir
  aynısı mı** bakıyor; `_write_lock` DIŞINDA (TOCTOU); boş önceki yanıt
  (`""`) meşru tekrarı yutabiliyor.
- Öneri: dedup'u write-lock içine al; pencereyi ~30 sn / son N ID aralığıyla
  sınırla; boş yanıtları hariç tut.

## B. GÜVENLİK

### B1. [Yüksek] FTS çapraz kullanıcı sızıntısı — `db.py:1982-2003`
- `search_sessions(query, user_id)`:
  - FTS dalı: `SELECT ... FROM sessions_ftf f JOIN ...` — yalnız `sessions` join'i
    user_id filtresi uygulanıyor; **FTS satırının kendisi user_id taşımıyor** ve
    `conversations` üzerinden user_id kısıtı yok.
  - `LIKE` dalı (2014+) filtreli.
- Etki: A, B'nin yazdığı mesajın FTS snippet'ini kendi oturumunda görebilir
  (`save_message`'de B'nin session'ına yazabildiğini varsayarsan — B2 ile birleşir).
- Öneri: FTS sonucunu `JOIN conversations c ON c.id = f.rowid AND c.user_id = ?`
  ile süz (FTS rowid = conversations.id mi doğrula) veya FTS tablosuna user_id
  kolonu + index.

### B2. [Yüksek] `save_message` oturum sahipliği yok — `db.py:1684-1689`
- `sessions` upsert korumalı (`ON CONFLICT` + owner), ama `conversations`
  INSERT'i **şartsız**: `session_id` istemci seçimli → yabancı kullanıcı
  başkasının oturumuna satır yazabilir.
- Öneri: INSERT öncesi `SELECT user_id FROM sessions WHERE id=?` → 403/raise.

### B3. [Orta] `clear_*_map` fonksiyonlarında user_id yok — `db.py:2114,2173,2231,2365`
- Şu an çağrılmıyor olabilir (ölü kod) ama silme ucu açık: çağrılırsa tüm
  kullanıcıların map'ini siler.
- `user_id` parametresi + `WHERE user_id=?` ekle ya da fonksiyonları sil.

### B4. [Orta] Audit → corpus'ta kullanıcı filtresiz cümle — `corpus_feeder.py:166-180`
- `audit → session → önceki kullanıcı mesajı` sorgusu **user_id filtresiz**;
  db aynası `db._user_text_for_audit` filtreli → iki taraf çelişiyor.
- Etki: başka kullanıcının cümli corpus'a (global öğrenme) girebilir.
- Öneri: sorguya `user_id` ekle; feeder'ı per-user çalıştır.

### B5. [Orta] `intent_audit_log` user_id'siz + ham mesaj — `db.py:394-403,926-931`
- Tabloda `user_id` kolonu YOK; `raw`/prompt özeti saklanıyor (PII).
- Kullanıcı bazlı silme (GDPR benzeri wipe) imkânsız.
- Öneri: migration ile `user_id` ekle; `delete_user`'a bu tabloyu da al.

### B6. [Orta] `delete_user` "privacy-complete wipe" iddiası — `db.py:2754-2798`
- Silinmeyenler: `intent_audit_log` (zaten user_id yok), `audit_exports/*.csv`,
  `corpus_data/additions.jsonl`.
- Docstring'i dürüstleştir veya temizliği ekle.

### B7. [Orta] Memories doğrulamasında owner guard yok — `tool_verification.py:191,264`
- `SELECT id/content FROM memories WHERE id=?` user_id'siz → başka
  kullanıcının varlığını "doğrulayabilir" (id tahmini).
- `AND user_id = ?` ekle. (Rapor 1/C8 ile aynı madde — iki bağımsız tespit.)

### B8. [Orta] Audit export kolon listesi user_id içermiyor — `db.py:1414-1419`
- `AUDIT_EXPORT_COLUMNS` docstring "every audit column" diyor, user_id yok.

### B9. [Düşük] Feeder umask'siz — `corpus_feeder.py:60-99`
- `corpus_data/*.jsonl` 0644 (ham kullanıcı metni).
- `os.umask(0o077)` + 0600.

## C. TUTARSIZLIK

### C1. [Orta] Eşikler üç yerde farklı — `db.py:3203` / `config.py:196` / `retrieval.py:19`
- `search_memories` eşik kod içi **0.35**; `save_memory` dedup eşiği config'de
  **0.68**; retrieval'da tekrar **0.35** hardcode.
- Öneri: ayrı config anahtarları (`MEMORY_SEARCH_MIN_SIM`, `MEMORY_DEDUP_MIN_SIM`),
  tek doğruluk kaynağı.

### C2. [Orta] `DEFAULT_USER` user_id fallback'i — `config.py:195` + `db.py:3136,3176,3274,3299`
- `DEFAULT_USER` bir **görünen ad** (`"Ada"`); `user_id` fallback'i olarak
  kullanılıyor → o id hiçbir gerçek kullanıcıya denk gelmez → o kullanıcının
  bellekleri/ayarları **hiç kimseye görünmez** (sessiz veri kaybı).
- Öneri: `DEFAULT_USER_ID = "default"` ayrı sabit; fallback'i ona çevir.

### C3. [Orta] Rollup summary satırları user_id'siz — `db.py:1536-1543` vs `594-596`
- `insert_or_replace` kullanıcı yazımında owner'ı koruyor; rollup INSERT owner'sız
  (NULL → default norm) → `delete_user("default")` tüm özetleri silebilir.
- Owner'ı koru ya da `delete_user`'da `AND is_summary = 0`.

### C4. [Orta] Retention yaş filtresiz — `db.py:678-681`
- `DELETE FROM sessions WHERE id NOT IN (recent N)` → mesajsız TÜM oturumlar
  (yaşlı + genç, boş) silinir; ayrıca `conversations` cascade'ini doğrula.
- `AND last_active < datetime('now','-X days')` ekle.

### C5. [Orta] `reembed_all.py` üçlü hata — `reembed_all.py:34-63`
- (a) `WHERE embedding IS NOT NULL` → **NULL vektörler hiç re-embed edilmiyor**
  (tam tersi olması gereken filtre!);
- (b) memories dalında dim kontrolü yok;
- (c) `busy_timeout` yok → canlı sunucuyla yazma yarışı.
- Öneri: `(embedding IS NULL OR embedding != ?)` gibi yeniden hesapla; timeout ekle.

### C6. [Orta] Dim drift koruması model adı eşleşmesine bağlı — `main.py:218-227`
- Beklenen boyutu sabit map'ten okuyor (`minilm→384`, `mpnet→768`); yeni model
  (`embeddinggemma`) map'te yoksa koruma **devre dışı**, karışık drift görünmüyor.
- Öneri: tokenizer/`model.config` boyutunu oku; 3-5 örnekleyip warn-only doğrula.

### C7. [Düşük] Standalone script fallback'i canlı DB'ye yazabilir — `corpus_feeder.py:56-57`, `reembed_all.py:34`
- `config.DB_PATH` fallback'i: tek eksik argümanda canlı `assistant.db`.
- Test fixture yalnız `db.DB_PATH` patch'liyor → kırılganlık.

## D. NOTES KURAL İHLALLERİ (yazma bütünlüğü / sync)

### D1. [Yüksek] `rollup_tool_audit` lock'suz `BEGIN IMMEDIATE` — `db.py:1516-1569`
- `BEGIN IMMEDIATE` kullanıyor ama `_write_lock` **almamış**.
- Açık implicit transaction varsa: `BEGIN IMMEDIATE within transaction` hatası →
  `db.rollback()` çağrısı (subagent: `conn.rollback()` hatadan sonra) → **başkasının
  yarım transaction'ını geri alabilir**; rollup o gün atlanır.
- Kural 5 (her user-scoped yazımda `_write_lock` + retry) doğrudan ihlali.
- Öneri: fonksiyonu `_write_lock` içine al; `BEGIN IMMEDIATE`'i kaldır
  (PRAGMA already set).

### D2. [Orta] `search_memories` kilitsiz UPDATE + şartsız commit — `db.py:3257-3267`
- Kilitsiz `UPDATE memories SET ... WHERE id=?` + `_commit_with_retry(conn)`
  → başkasının açık transaction'ını erken commit'leyebilir.
- Fonksiyonun kendi yorumundaki uyarımla bile çelişiyor.
- Öneri: `_write_lock` içine al veya `commit=False` bırak (yalnız kendi tx).

### D3. [Orta] `upsert_sync_items` kilitsiz + LWW yok — `db.py:2241-2276`
- Doc "newer `updated_at` overwrites" dese de `DO UPDATE` **koşulsuz** →
  gecikmeli eski yazı yeni veriyi ezebilir.
- `updated_at` serbest metin (ISO format doğrulanmış değil) → `since` karşılaştırması
  leksikografik/güvensiz.
- Öneri: `WHERE excluded.updated_at > sync_items.updated_at`; timestamp'i
  normalize + `CHECK`/format doğrulama.

### D4. [Orta] Write-lock disiplini tutarsız — db.py: 15 nokta (883…3291)
- Kilitsiz yazarlar (`UPDATE`/`DELETE`/`INSERT`) `_commit_with_retry` ile
  başkasının transaction'ını erken commit edebiliyor.
- Liste (subagent): satır aralıkları `883, 926, 1117, 1414, 1516, 1684, 1911,
  2114, 2241, 2365, 2754, 3025, 3069, 3136, 3257` civarı.
- Kural 5 sistemik olarak yarım uygulanmış → tek seferlik "lock audit" işi.

### D5. [Orta] `sync_items` origin kolonu yok — `db.py:526-539`
- 2026-09-05 TECHNICAL WARNING: yeni oluşturulan `sync_items` şemasında
  device origin kolonu yok (yeni tablolar sync-uyumlu olmalı: updated_at + deleted + origin).
- `origin TEXT NOT NULL DEFAULT ''` + migration ekle. (Rapor 1/C9 ile ortak.)

### D6. [Orta] Kural sonrası 7 tablo sync disiplini dışı — `db.py:306-450`
- `users`, `user_api_keys`, `user_sessions`, `user_settings`, `feedback_votes`,
  `pattern_approvals`, `user_credentials`:
  - 5'inde `updated_at` YOK,
  - hiçbirinde `deleted`/`origin` YOK (auth-only'ler hariç — NOTES'a istisna yaz).
- Öneri: senkron adaylarına (`feedback_votes`, `pattern_approvals`, `user_settings`)
  tam set; auth-only'lere NOTES'ta istisna kaydı.

## E. İYİLEŞTİRME

### E1. [Orta] FTS "malformed" koruması 2/5 yolda — `db.py:1722,1755,1881` vs `delete_last_assistant/delete_branch/clear_history`
- Non-fatal `except` yalnız iki FTS DELETE yolunda; üç yolda yok → legacy DB'de
  `malformed match expression` ile 500 riski.
- Üç yola da try/except + log.

### E2. [Orta] Eksik indeksler — `db.py:452-469` şema
- `conversations.user_id` İNDEKSİ YOK → `get_all_history` tam tablo taraması.
- `tool_audit_log(user_id)`, `feedback_votes(user_id)` indeksleri yok.
- Retention default 0 → `conversations` sınırsız büyür (disk dolusu NOTES vakası
  ile aynı aile).

### E3. [Orta] N+1 sorgular — `db.py:1293-1324`, `1117-1143`
- `get_review_queue`: her imza/grup/seçmen için ek sorgu (quadratik).
- `user_reputation`: tüm oyları belleğe yüklüyor.

### E4. [Orta] Feeder atomik değil — `corpus_feeder.py:66-111`
- `_save_state`/`_append_jsonl` doğrudan `open(...,"a")` → yarım satır riski.
- `_load_jsonl` satır bazlı hatayı **yutuyor** → tek bozuk satır feeder'ı
  kalıcı kırabilir (sessiz).
- `tmp + os.replace` + satır bazlı try/except (bozuk satırı atla + logla).

### E5. [Düşük] Python cosinüs taraması — `db.py:3146-3203`
- `save_memory`/`search_memories` tüm embedding'leri yükleyip Python'da
  hesaplıyor → O(n) her mesajda.
- sqlite-vec/FAISS yoksa bile numpy batch + indeks.

### E6. [Düşük] `import_messages` kilit içinde 2N — `db.py:1911-1916`
- Mesaj başına SELECT+INSERT; UNIQUE ihlali zaten yutuluyor → SELECT'i at.

### E7. [Düşük] `_repair_summary_boundaries` tam tarama — `db.py:3025-3034`
- Her delete'de tüm `sessions` dolaşılıyor; yalnız ilgili `session_id` için
  çalıştır.

### E8. [Düşük] Test boşlukları — `tests/test_user_isolation.py:129-144`
- FTS çapraz-user testi YOK (paylaşımlı session_id denenmiyor — B1 regresyon koruması yok).
- Breaker testi yalnız istisna yolunu deniyor; **asılı indirme senaryosu yok**
  (A1 için regresyon testi yazılmamış).

## F. DOĞRULANAN KORUNANLAR

- SQL/LIKE/FTS tamamı parametreli; string birleştirme yok ✓
- Migration disiplini: `_migrate()` tek kapı, versiyonlu, transaction ✓
- Test fixture: geçici DB + `tmp_path`, canlı `assistant.db'ye` yazma ✓
- Retry: `_commit_with_retry` + `lastrowid` taşıma ✓
- Backup: atomic temp+replace, 0600 ✓
- `retrieval.py`: user_id filtreleri + 1500ms bütçe ✓ (ama kilit sorununu çözmüyor)

---
---

# RAPOR 3 — LLM PIPELINE (llm/*, prompt.py, litert_serve, streaming, abort)

Kapsam: `llm/stream.py`, `llm/chat.py`, `llm/intent.py`, `llm/utils.py`,
`llm/payload.py`, `prompt.py`, `litert_serve/server.py`, `routers/chat.py`
(akış tarafı), `embedding.py` (ilgili kısım).

## A. GÜVENLİK

### A1. [Yüksek] Leaked tool call bypass — `llm/stream.py:512-516, 561-562`
- `parse_leaked_tool_call()` düz metinden `tool:{...}` çıkarabiliyor.
- `allowed_names` parametresi `None` geldiğinde hallüsinasyon reddi guard'ı
  (`allowed_names` kontrolü) **çalışmıyor** → çağrı `execute_tool`'a gidiyor.
- `use_tools=False` iken bile (chat saf-sohbet dalı) bu yol açık kalıyor.
- `create_note/task/event`, `save_memory` **CONFIRM_TOOLS içinde değil** →
  onay kartı da yok → tek adımda yazma.
- Saldırı: dış içerik (e-posta/notes/web) `"call:create_note{...}"` içerirse
  LLM bunu metne sızdırır, kurtarma kodu çalıştırır → prompt injection gadget.
- Öneri:
  1. `use_tools=False` iken leaked-call kurtarmayı tamamen kapat;
  2. `allowed_names=None` yerine **boş küme** (her şey reddedilir) yap;
  3. CONFIRM_TOOLS kontrolünü kurtarma yoluna da uygula.

### A2. [Yüksek] Fallback çözümleme timeout'suz — `llm/intent.py:701-740, 732`
- LLM fallback (`INTENT_LLM_FALLBACK`) ve `Layer-1 çözümleme` `client.post(...)`
  çağırıyor; **zaman aşımı yok**; paylaşılan client'ın timeout'u `config.LLM_TIMEOUT`
  = 600 sn (`llm/utils.py:274-285`).
- NOTES P3 maddesi "10 sn guard" → kodda doğrulandı, **YOK** (Notes'ta "pending" doğru).
- Şu an fallback default **off** → görünmüyor; açılmadan önce guard şart.
- Öneri: `asyncio.wait_for(client.post(...), timeout=10)` (veya geçici client
  `timeout=10`).

### A3. [Yüksek] Embedding asılı indirme + istek yolunda timeout yok (3 rapor konverjansı)
- `embedding.py:22-43` (bkz. Rap2 A1), `db.py:1664`, `routers/chat.py:154`,
  `intent.py:475,641` embed çağrıları: `wait_for` YOK.
- `retrieval.py:129` yalnız retrieval yolunda.
- Sonuç zinciri: kilit asılı → `save_message` embed'i asılı → fonksiyon dönmez →
  `generate()` hiç başlamaz → keepalive gönderilemez → **proxy 504**.
- Öneri: her embed yoluna 5-10 sn `wait_for`; timeout tri breaker'a.

### A4. [Yüksek] SSE öncesi kurulum fazı sınırsız — `routers/chat.py:314-341`
- `generate()` çağrılmadan önce: `save_message` (embed dahil), niyet sınıflandırma,
  memory save, retrieval, LLM çözümleme — hepsi senkron (asenkron ama sıralı)
  ve **keepalive bunların içinde değil**.
- Bu fazdaki her takılma: **hiç bayt göndermeden** proxy 504 →
  NOTES 2026-10-05 vakasıyla doğrudan bağlantılı (en güçlü aday).
- Öneri: kurulum fazına toplam üst sınır (örn. 8-10 sn); aşarsa warn + akışa geç;
  mümkünse keepalive'i Response dönmeden önce başlat (starlette ile zor — o yüzden
  faz bütçesi gerçekçi).

### A5. [Orta] Özet transkripti zehirlenebilir — `llm/chat.py:124-138`
- `_summary_transcript` yalnız **asistan** sızıntılarını temizliyor
  (regex `^assistant:` satırları vs); kullanıcı sahte `assistant: ...` satırı
  yazarsa transkript zehirlenir → özet SYSTEM promptuna kalıcı enjekte olur.
- Öneri: rol ayrımını kaçışlı biçimde (JSONL/fence) kur; kullanıcı satırlarını
  `UNTRUSTED` işaretiyle özetle.

### A6. [Orta] UNTRUSTED fence tutarsız — `prompt.py:54` vs `199`
- Kural: "emails, calendar, notes" işaretle (NOTES'ta bu yazıyor).
- Uygulama: yalnız e-posta `--- BEGIN UNTRUSTED ---` ile sarılıyor
  (`prompt.py:199`); takvim/notes içeriği işaretsiz.
- Öneri: üçü de fence'le veya kuralı değiştir + NOTES'u güncelle.

### A7. [Düşük] Abort sahiplik yok (konverjans) — `routers/chat.py:462-470`
- (Rap1 A7 ile aynı.)

### A8. [Düşük] SW API cache + `/static` Cache-Control (konverjans)
- `static/sw.js:40-41,61-73` + `main.py:656` — post-refresh login'in en güçlü
  backend/SW şüphelisi.
- Cookie tarafı **sağlam**: `httponly`, `samesite=lax`, `path=/`
  (`routers/users.py:24-27`) → Secure dışında hipotez kuvvetli.

## B. TUTARSIZLIK (chat ↔ stream PARİTE)

### B1. [Orta] Dedup guard'ı farklı — `stream.py:545` vs `chat.py:327`
- Stream: `not buf.strip()` — `buf` **boşaltılmış** olabilir (yield edilmiş);
- Non-stream: `raw_content` dolu.
- Etki: stream'de ≥8 karakter metin + boşalmış buf → finalize-nudge atlanabilir;
  nudge ikinci kez çağrılırsa gerçek metnin sonuna fallback eklenir (kırpma/tekrar).
- Öneri: `full_text.strip()` üzerinden tek guard.

### B2. [Orta] Retry sonrası mükerrer yanıt — `stream.py:519-526, 426-431` + `routers/chat.py:393,420-424` + `ui.js:2214-2217`
- `gen_retry` sonrası `reply_parts` (server) ve `fullText` (client) **TEMİZLENMİYOR**;
- Kısmi metin modele geri beslenmiyor.
- Sonuç: kullanıcıya + DB'ye mükerrer yanıt yazılır ("duplicate window" ailesi).
- Öneri: retry'da birikimi geri çek **veya** kısmi metni tekrara ekle; client'ta
  `fullText` sıfırla.

### B3. [Orta] Think-retry şartı farklı — `stream.py:477` vs `chat.py:282`
- Non-stream `iteration == 0` şartlı; stream şartsız → 5 tura kadar ekstra
  tam boyutlu çağrı (maliyet + gecikme).

### B4. [Orta] Retry payload'ı eksik — `stream.py:485-500`, `chat.py:284-289`
- Think-retry payload'ları `trim_messages_for_context`'ten geçmiyor
  (bağlam taşma riski);
- `_TOOL_ASK_HINT` yeniden enjekte edilmiyor → "araçların yok" bilgisi kaybolur
  → A1 bypass yolunu besler.

### B5. [Orta] Non-stream yol eksikleri — `llm/chat.py:262-264`
- Yok olanlar: truncation-retry, overflow-retry, litert parse-recovery,
  leaked-call kurtarma, abort kontrolü.
- Her hata türü (400 taşma dahil) → `llm_unreachable` etiketi (yanlış ölçüm).
- Öneri: parite tablosu + tek yardımcı fonksiyona taşıma.

### B6. [Orta] Saf-sohbet sistemi çelişkili — `prompt.py:37,40-45` vs `llm/utils.py:319-324`
- Saf-sohbet turunda sistem promptu tüm araçları listeliyor + "call the tool
  immediately" derken eklenen hint **"NO tools available"** diyor.
- Etki: spurious TOOL_NEEDED/escalation gürültüsü.
- Öneri: saf-sohbet varyantında araç listesi + kural 1-5 kaldırılacak;
  yalnız mod + kural 6-10 + safety.

### B7. [Orta] Sabit EN kullanıcıya dönen metinler (kural 9) — `chat.py:412,417,482`, `stream.py:655,662`
- `"max-iteration"` mesajı, `[Rejected: ...]` tool sonucu,
  `validate_confirm_params` hataları — UI bunları çevirmiyor; birebir kullanıcıya
  gidiyor (örn. İngilizce arayüzde Türkçe değil, tam tersi: EN kalıyor).
- `messages.py`'ye key + frontend çevirisi.

### B8. [Düşük] Hata metinleri sabit EN — `stream.py:302,424,434,444`
- UI yalnız `connection error` / `context too long` regex'liyor (`ui.js`).
- Diğerleri callback'e düşüyor, kullanıcıya ham EN.

### B9. [Düşük] `EMPTY_ANSWER_FALLBACK` ölü — `llm/utils.py:23-25`
- Türkçe metin; üretimde hiç kullanılmıyor (yalnız test).
- Kaldır veya gerçek fallback yap.

### B10. [Düşük] `run_verification` non-stream'te yok sayılıyor — `chat.py:395` vs `stream.py:635`
- Non-stream `run_verification` dönüşünü yok sayıyor; `link_audits_to_message`
  non-stream'te hiç çağrılmıyor → **👍/👎 non-stream turlarda mesaja bağlanamıyor**.

### B11. [Düşük] `_bare_tool_name` stream'de yok — `stream.py:450-451` vs `chat.py:298-300`
- Escalate kontrolünde isim normalizasyonu eksik → farklı imleyle yazılmış
  escalate tool'ları yakalanamayabilir.

### B12. [Düşük] `tool:start` yanlış `max` — `stream.py:626`
- `max` her zaman 2; `create_*`/`send_email` için 1 → UI "1/2" gösterir.
- `max: max_exec` kullan.

### B13. [Düşük] Sanitized boş yanıtta ham `reply` — `routers/chat.py:289`
- Sanitizasyondan boş kalan yanıtta `reply` istemciye ham dönüyor.

## C. DEĞİŞİKLİK GEREKSİNİMİ / BİLİNEN BUG

### C1. [Orta] `INTENT_LLM_FALLBACK` off + açık risk — `intent.py:687-695, 866`
- Default off (doğru); A2 guard'ı yazılmadan açma. NOTES'a "guard şart" notu ekle.

### C2. [Orta] Oturum limiti kurulum başında + 429 `Retry-After` yok — `routers/chat.py:237-239,310-312`
- Başarısız istekler bütçeyi harcıyor (limit kurulum başında düşülüyor).
- 429 yanıtında `Retry-After` yok (genel limitte var) → istemci backoff yapamaz
  → dalgalanmada 429 döngüsü; "duplicate window" senaryosuna girme davranışıyla uyumlu.
- Öneri: limiti yalnız başarıda düş; 429'a `Retry-After` header'ı ekle;
  hata/fallback'te geri iade et.

### C3. [Düşük] Tool cache invalidation — `litert_serve/server.py:457-474` + `llm/payload.py:78-79`
- `conversation_cache_max > 0` iken araç seti/prelude değişimi cache'i invalidate
  etmiyor (varsayılan 0 → latent ama tehlikeli).
- Cache key'e araç-seti hash'i ekle.

## D. İYİLEŞTİRME

### D1. [Orta] SSE idle timeout hatayı yutuyor — `llm/stream.py:91-94, 437-453`
- `SSE_READ_IDLE_TIMEOUT` (300 sn) `break` ile sessiz sonlanıyor; `full_text`
  boşsa akış `done` ile biter → kullanıcı **boş yanıt** görür, hata görmez.
- Idle timeout'ta `{"error": ...}` event üret.

### D2. [Orta] Kilit altında senkron indirme — `embedding.py:36-43`
- İndirme `_model_lock` altında `to_thread` ile senkron; bekleyen her çağıran
  thread havuzunu meşgul eder → havuz dolunca dolaylı **event-loop bloke**
  (tüm SSE'ler dahil).
- Kilidi yalnız `self._model = model` atamasında tut; indirmeyi kilitsiz yap.

### D3. [Düşük] Docstring "never delays routing" — `intent.py:505-513`
- `await log_intent_audit` her sınıflandırmada DB yazımı bekletiyor.
- Fire-and-forget (`asyncio.create_task`) veya docstring düzelt.

### D4. [Düşük] `httpx.Timeout` tek değer — `llm/utils.py:274-285`
- Tek değer `connect` dahil her faza uygulanır → ölü backend'de 10 dk asılı
  connect bekler. `httpx.Timeout(LLM_TIMEOUT, connect=10)`.

### D5. [Düşük] Reasoning turlarda kayboluyor — `stream.py:307,533,732`
- `full_reasoning` tur başında sıfırlanıyor; `done` yalnız son turu taşır.
- Turlar arasında biriktir veya `reasoning_delta`'ları kümülatif gönder.

### D6. [Düşük] Nudge yalnız son user mesajını kapsar — `llm/payload.py:176-181`
- Uzun geçmişte önceki "üçlü" (user/assistant/tool) kırpılıp boş cevap üretilebilir.
- Nudge'ı kırpma sonrası bağlama göre yeniden konumlandır.

### D7. [Düşük] Yerinde mutation — `llm/payload.py:263-272`
- `_normalize_messages_for_backend` `arguments` dict'ini yerinde string'e
  çeviriyor → yan etki riski. Kopya üzerinde çalıştır.

### D8. [Düşük] `_uid` fail-open — `routers/chat.py:90-95`
- 401'ı yutup `"default"` fallback'i → chat uçları fail-open.
- Uçlarda 401 fırlat; middleware'e geri taşı.

## E. DOĞRULANAN KORUNANLAR

- WebSocket: **YOK** ✓ (SSE-only, NOTES uyumlu)
- Loop guard'lar: identical-cap=2, finalize nudge, empty fallback, strip leaks,
  allowed_names reddi — `stream.py` içinde ✓ (ama A1 bypass yolu bunun dışında)
- Escalation: tek-atım + single-group ✓
- `request.state.user_id` setter'ı var ✓
- Summary: conditional write + fold bounds ✓
- Keepalive: `generate()` içinde + UI non-data atlama ✓
- Abort: round/tool kontrolü ✓ (sahiplik hariç)

---

# RAPOR 4 — TOOLS & ROUTERS

Kapsam: 23 tool (`tools/`, `calendar_ops.py`, `nextcloud_tasks.py`,
`nextcloud_notes.py`, `mail.py`, `weather.py`), 22 router (`routers/*`),
`tools/dispatcher.py`, `tools/definitions.py`, `tool_verification.py`.

## A. GÜVENLİK

### A1. [Yüksek] Nextcloud görev cache'i credential kapısını bypass — `nextcloud_tasks.py:59`
- `_get_task_calendar()` önce `_todos_cache` kontrolü, **sonra**
  `NC_CREDS/NC_SHARED_OK` gate.
- Cache ısındıktan sonra gate hiç çalışmaz → 2026-09-27'de kapatılan delik
  (credential'sız okuma) **bu yoldan tamamen geri açılır**.
- Öneri: cache kontrolünü `_get_dav_client()`/gate'in ALTINA taşı
  (gate önce, cache sonra).

### A2. [Yüksek] `_get_primary_calendar` global cache — `calendar_ops.py:87`
- Client'tan bağımsız global `_dav_calendar` cache'i → B'nin delete/update
  **A'nın event nesnesi** üzerinde çalışır (yanlış kullanıcıya yazma).
- Öneri: anahtara credential fingerprint / user_id ekle.

### A3. [Yüksek] `_find_events_cache` anahtarsız global — `calendar_ops.py:141`
- 5 sn TTL, anahtar **SİZ**; A'nın sorgu sonucu B'ye döner.
- `delete_event(:441)` / `update_event(:462)` üzerinden başka kullanıcı
  silebilir/güncelleyebilir.
- Aynı zamanda arama cache'i → sızıntı + yanlış eşleşme.

### A4. [Yüksek] Embedding asılı indirme (konverjans) — `embedding.py:38` + `db.py:1664`
- (Rap2 A1 / Rap3 A3 ile aynı madde — üç rapor aynı kök neden.)

### A5. [Orta] Todos cache'i anahtarsız — `nextcloud_tasks.py:207`
- `_todos_cache` anahtarı yalnız `include_completed` → 30 sn içinde A'nın görev
  listesi B'ye.
- Öneri: creds/user_id + `include_completed` key.

### A6. [Orta] `/widget/calendar` NC bağlamı yok + owner guard yok — `routers/widgets.py:41`
- 2026-09-27 fix'inden beri bağlam hiç set edilmediği için **hep boş** dönüyor
  (işlevsel regresyon);
- Kullanıcı filtresi de yok.

### A7. [Orta] `/chat/abort` sahiplik yok (konverjans) — `routers/chat.py:463`
- (Rap1 A7 / Rap3 A7.)

### A8. [Orta] `/chat/reload-corpus` auth guard'sız — `routers/chat.py:729`
- Ne `_uid` ne `require_admin` → sıradan kullanıcı cache thrash + CPU.
- `require_admin` ekle. (Rap1 D13 ile aynı.)

### A9. [Orta] IMAP komut enjeksiyonu — `mail.py:42,111` + `tools/dispatcher.py:506`
- `mailbox` parametresi sanitize edilmiyor; `imaplib._command` satır sonuyla
  ham birleşir (CPython kaynağı doğrulandı) →
  `mailbox = "INBOX\r\nA002 APPEND ..."` ile IMAP komut enjeksiyonu mümkün
  (command injection seviyesi değil, IMAP protokol seviyesi — yine de ciddi).
- Öneri: `INBOX`, `Sent`, `Drafts`, `Trash` allowlist + `re.fullmatch(r"[A-Za-z0-9_/-]+")`.

### A10. [Orta] Context'e `_user_text`/`_origin` basılmıyor — `tools/dispatcher.py:488` ↔ `950`
- `/execute` ve `/sync` path'lerinde context CLARIFY dil anchor'u içermiyor →
  `chat.py` `setorigin` dışındaki CLARIFY ayarları devre dışı (kural 4 aykırılığı).
- Context'e ekle.

### A11. [Orta] `caller is None` → admin mailboxes — `dispatcher.py:498-499` / `mail.py:498-501`
- Kontrol yalnız `caller is not None and not is_admin`; `caller=None` durumunda
  akış **paylaşılan admin mailboxes**'a düşüyor.
- `caller is None` durumunu da reddet (fail-closed).

### A12. [Orta] `/config` parite aykırılığı — `routers/config.py:104` ↔ `66`
- `GET /config` model/llm_backend/stt/tts motorunu **tüm** authenticated
  kullanıcılara açıyor;
- `GET /config/settings` non-admin'den gizliyor.
- İkisi aynı veriyi farklı yetkiyle sunuyor → router parite hatası.
- `/config`'i de `require_admin`'a bağla veya settings ile hizala.

### A13. [Orta] Widget/tool global DEFAULT_CITY — `routers/widgets.py:19` + `weather.py:89,137`
- `DEFAULT_CITY` PERSONAL_KEYS (NOTES: kişisel); prompt kişisel değeri okur
  ama tool/widget global default'a düşer → kullanıcının şehri tool'da kaybolur.
- `effective_setting(user_id, "DEFAULT_CITY", ...)` kullan.

### A14. [Orta] Uçlarda `_uid` çağrılmıyor — `routers/chat.py:462,728,828`
- abort + reload-corpus: auth yok (upload'ta gerekli değil).
- (Tekrar: A7/A8.)

### A15. [Orta] Session limiter yalnız `session_id` — `routers/chat.py:237/310`
- B, A'nın session_id'siyle 429 yedirebilir; yeni id ile sıyrılır.
- `user:{uid}:{session}` anahtarı. (Rap1 B5 ile aynı.)

### A16. [Düşük] Subject CRLF — `mail.py:93`
- Doğrulanmıyor; stdlib `smtplib` engelliyor ama `"Failed to send."`a yutuluyor
  (yanlış hata mesajı). `\r`/`\n` kontrolü + net hata.

### A17. [Düşük] `_uid` fail-open (konverjans) — `routers/chat.py:85-95`
- (Rap3 D8.)

### A18. [Düşük] `PISERVE_ADMIN_TOKEN` boşken açık + `==` — `litert_serve/server.py:287-290`
- Token yoksa admin endpoint'leri **açık**; karşılaştırma `==` (timing).
- Token yoksa kapatan kilit (503) + `hmac.compare_digest`.

### A19. [Düşük] Body boyut sınırı yok — `litert_serve/server.py:366-367`
- `Content-Length` kontrolü yok → `rfile.read(length)` bellek tıkanması.
- Maks boyut (örn. 8MB) + 413.

### A20. [Düşük] `_reload_event.wait()` zamansız — `litert_serve/server.py:389`
- Timeout + 503.

### A21. [Düşük] Tool parametreleri log'a — `tools/dispatcher.py:153`
- `extra={params}`; maskeler yalnız anahtar **adını** (`api_key`) →
  `to/subject/body/content/notes` PII log'a sızar.
- Alan bazlı redact listesi.

## B. TUTARSIZLIK (NOOP/ERROR disiplini, şema ↔ handler)

### B1. [Orta] Takvim çoklu eşleşme ERROR'suz — `calendar_ops.py:445,467`
- `"matches multiple... metin"` → `is_tool_success` **başarılı** sayar
  (kural 6: belirsizlik `ERROR:` olmalı);
- Ayrıca "use the event UID" derken kural 7 (sıra no. kullanılmalı) ile çelişiyor.
- `"ERROR: "` prefix + "list number" talimatı.

### B2. [Orta] NOOP disiplini takvimde yok — `calendar_ops.py:442,449,464,471`
- Bulunamama `ERROR:` döner; notes/tasks **`NOOP:`** döndürür → tutarsızlık.
- Takvimde de NOOP'ye çevir (kural 6).

### B3. [Orta] CONFIRM şeması eksik — `tools/definitions.py:448` ↔ `105,121`
- `delete_calendar_event` / `update_calendar_event` CONFIRM_TOOLS **içinde**,
  şemada `"Requires user confirmation"` **YOK** (diğerlerinde var).
- Model onay diyaloğu beklemeden çağırabilir → kullanıcı onayı bypass.
- Şemaya onay notu ekle.

### B4. [Orta] Şema ↔ handler CLARIFY tutarsızlığı — `definitions.py:82` ↔ `dispatcher.py:185-192`
- `create_calendar_event` şemada zorunlu tek `summary`;
- dispatcher `start_time` yoksa **CLARIFY** döner.
- `create_note`'da `summary/content` aynı durumda CLARIFY **yok**.
- → Model gereksiz clarify turu / eksik parametre hatası alır.
- Şemayı handler'a hizala (zorunlu alanları şemada belirt).

### B5. [Orta] Mail limiti üst sınır yok — `definitions.py:158,207`
- `list_emails`/`search_emails` `limit` min var **max YOK** → `mail_ids[-limit:]`
  100k maili çeker (payload patlaması).
- Şemaya `le=50` ekle.

### B6. [Düşük] Sync doğrulama `error` geçirmiyor — `routers/chat.py:955` ↔ `499`
- Execute path `error` alanını `run_verification`'a veriyor; sync path vermiyor
  → başarısız audit satırları `error=NULL`.

### B7. [Düşük] `/chat/search` yanıt biçimi — `db.py:1999` vs `2014`
- FTS dalı `snippet ~100` krtr; LIKE fallback ham `content` → yanıt şekli/boyutu
  uçlar arasında tutarsız.

## C. İYİLEŞTİRME

### C1. [Orta] Read'lerde zaman bütçesi yok — `nextcloud_tasks.py:362,370,378`
- `complete_task`/`delete_task`/`search_tasks` iç read'lerinde 30 sn bütçe yok
  (kural 8 yalnız `list_tasks`'ta uygulanmış).
- `asyncio.wait_for(..., 30)` ekle.

### C2. [Orta] NC notes read'lerinde bütçe yok — `nextcloud_notes.py:229,263,359`
- `list_notes`/`get_note`/`search_notes`: 200 sayfalama × timeout → uçurum.
- 30 sn `wait_for`.

### C3. [Orta] `/chat/sync` batch sınırı yok — `routers/chat.py:921`
- Tek istekte N CalDAV/IMAP/DB işlemi → rate limit çarpanı + timeout.
- Batch cap (örn. 20) + `Retry-After`.

### C4. [Orta] Doğrulama sonrası tam listeleme — `tool_verification.py:178-304`
- Her mutasyon sonrası 2. backend taraması (CalDAV/NC 2×; 5 sn'lik
  `list_events` cache'ine takılır → doğrulama cache'ten eski okuyabilir).
- Entity-id'li nokta okuma (GET event by uid).

### C5. [Orta] Arama URL encode — `nextcloud_notes.py:161`
- `query.replace(" ", "+")`; `&/#/?` ve TR karakterler URL'yi bozar;
  `except: pass` → sessiz fallback.
- `urllib.parse.quote(query, safe="")`.

### C6. [Orta] Kişisel eksik cred → paylaşılan şifre — `nextcloud_notes.py:34`
- `creds.get("password") or NEXTCLOUD_PASSWORD` → kişisel `username` var
  `password` yoksa **paylaşılan şifreyle** kendi kullanıcısında login
  (fail-open karışımı).
- Bir alan eksikse shared fallback'i kapat (tam/hiç).

### C7. [Düşük] `TRUST_X_FORWARDED_FOR` yorum/kod + spoof (konverjans) — `config.py:177-178`, `main.py:583`
- (Rap1 B1/A3.)

---

# RAPOR 5 — FRONTEND (static/*)

Kapsam: `static/ui.js` (~5000+ satır), `static/web.html`, `static/app.html`,
`static/index.html`, `static/sw.js`, `static/ui.css`, `static/manifest.json`,
STRINGS/i18n, vendor (marked, DOMPurify), `main.py` static mount.

## A. GÜVENLİK

### A1. [Yüksek] `esc()` NO-OP — `static/ui.js:383`
- Kod:
  ```js
  function esc(s){return String(s).replace(/&/g,'&amp;').replace(...)}
  ```
  — subagent doğrulaması: zincir **üretemiyor**; `esc("<")` → `"<"` dönüyor
  (escape sıralaması/regex bozuk; örn. `&amp;` üretip sonra tekrar `&`'e
  çeviriyor veya replace pattern'i yanlış).
- 168 çağrı noktası bu fonksiyona güveniyor.
- Regresyon: `7609519` (2026-09-03).
- XSS savunmasının **tek katmanı**; DOMPurify yalnız markdown'da.
- Öneri: doğru replace sırası (`&` → `&lt;` → `>` → `"` → `'`) +
  **bozulmayı yakalayan birim test** (`esc("<b>") !== "<b>"`).

### A2. [Yüksek] Oturum adı/snippet `innerHTML` — `ui.js:1887`, `1945-1946`
- Session listesi: oturum adı ham `innerHTML`; `patchRow` aynı.
- `esc()` no-op + `<b>` dönüşümü (highlight) bilinçli ham HTML açıyor.
- Öneri: `textContent` + DOM ile `<b>` ekle veya DOMPurify.

### A3. [Yüksek] Takvim/hava durumu `innerHTML` — `ui.js:4823, 4799-4818, 4869`
- Harici takvim (CalDAV) olay başlıkları + hava durumu özeti no-op `esc` ile
  `innerHTML` → dış kaynaklı depolanmış XSS (ve A1 ile tüm sink'ler).
- Öneri: `textContent` veya DOMPurify.sanitize.

### A4. [Yüksek] SW oturumlu GET cache (konverjans) — `static/sw.js:61-74`
- Cache'lenen oturumlu GET'ler: `/users`, `/users/me`, `/admin/patterns/review`,
  `/tools/groups`, `/chat/sessions`, `/chat/memories`, `/history/pull`, `/export`.
- `stale-while-revalidate` → logout sonrası eski kimlik/hassas liste servis edilir.
- Öneri: denylist → **allowlist** (yalnız `/static/*`); logout'ta `caches.delete()`.

### A5. [Orta] Tek 401 anahtar siliyor — `ui.js:1669, 1686`
- `api()` içinde tek geçici 401 bile localStorage API key'i siliyor →
  ağ hatasında kullanıcı istemeden çıkış.
- Anahtarı yalnızca `/users/session` **doğrulama başarısızlığında** sil.

### A6. [Orta] Maskelenmiş key geri geliyor — `ui.js:1308`
- Sunucu maskedelenmiş `'********'` döndürüyor; client bunu API key sanıp
  her istekte `X-API-Key: ********` gönderiyor (boş yere 401 riski).
- `getApiKey()`'da maskeleri yok say.

### A7. [Orta] Inline event + CSP yok — `ui.js:3324` + `main.py:483-496`
- Ayar satırları `${key}` ile `oninput/onclick` inline üretiyor; CSP yok.
- Öneri: `data-key` + `addEventListener`; CSP ekle (Rap1 A10).

## B. BİLİNEN BUG: POST-REFRESH LOGIN

### B1. [Yüksek] Boot gate yanlış anahtara bakıyor — `static/ui.js:1768` — KÖK NEDEN
- Boot:
  ```js
  if (getApiKey()) { ...app start... } else { showLogin() }
  ```
- `/users/session` şifre girişi **API key DÖNDÜRMEZ** (`routers/users.py:97-111`
  — yalnız session cookie + user nesnesi).
- Böylece: şifre girişi → key localStorage'a YAZILMAZ → refresh → gate
  `getApiKey()` boş → login ekranı. Cookie olsa bile gate cookie'ye bakmıyor.
- Öneri: kapıyı `/users/me` (401/403 → login, 200 → app) testine çevir;
  VEYA `/users/session` yanına key döndüren bir boot-check endpoint'i.

### B2. [Orta] SW sürüm bayat — `static/sw.js:1` + `web.html:14,220`
- `CACHE_NAME` hâlâ `pisynapse-v55`; 25+ commit ui.js, 6+ commit ui.css
  değiştirdi; asset'ler `?v=` olmadan → SW eski shell hipotezi destekleniyor.
- Öneri: sürüm bump veya build hash parametresi.

### B3. [Orta] Boot 401'de aynı çağrı tekrarlanıyor — `ui.js:1711`
- Boot'ta başarısız `/config` çağrısı tekrarlanıyor, config varsayılana
  düşürülüp sessiz devam → kullanıcı login ekranında kalmıyor ama veri yok.
- 401'de doğrudan login akışına geç.

### B4. [Orta] `/static` Cache-Control yok (konverjans) — `main.py:656`
- Eski asset servis edilme riski (eski boot kodu = login bug'ı taklit eder).

## C. TUTARSIZLIK (i18n, dead code)

### C1. [Orta] Tek-dilli sabit metinler (kural 9) — `ui.js:855,1846,1848,1869,3063,3084,3387,4828`
- Örnekler: `"Max 5 images"`, sunucu toast'ları (`"Saved"`, `"Failed"`),
  `"Yeni Sohbet"`, `"Eşleşen etkinlikler"`, `"Sistem"`, `"Confirm"`,
  `"Memory Active"` — bunlar STRINGS'e taşınmamış, doğrudan kullanıcıya gidiyor.
- `messages.py` backend anahtarları da var ama frontend'de karşılığı yok.

### C2. [Orta] Erişilebilirlik metinleri karışık dil — `web.html:28,44,54,60,80,105,125,131` + `app.html:86`
- `aria-label`/`alt`/`title` İngilizce sabit; arayüz TR olabiliyor.
- `data-i18n` veya JS `t()` ile hizala.

### C3. [Orta] Dinleyici sızıntısı — `ui.js:1926`
- `renderSessions()` her tam yeniden çizimde yeni click dinleyicisi ekliyor
  (`_hasDelegation` korumasının dışında — 1899'daki koruma yalnız另一 kolda).
- Event delegation'a geç veya `clone()` ile temizle.

### C4. [Orta] 429 backoff yok + tek kova — `ui.js:1689`
- `api()` 429'u bilmiyor; tüm oturumlu çağrılar + `/debug` beacon'ları
  **30 rpm tek kova** (main.py limiter).
- `Retry-After` tabanlı duraklatma; `/debug` ayrı limiter (Rap1 D/I).

### C5. [Orta] `/debug` beacon cookie auth'suz — `ui.js:2147`? (main.py:545)
- Web beacons yalnızca `X-API-Key` kontrolü; şifre ile giren (key'siz) kullanıcıda
  telemetri sessiz 401 → veri kaybı.
- Cookie fallback'i ekle (middleware'de).

### C6. [Orta] Markdown O(n²) — `ui.js:2147, 2277`
- Her token'da tüm metin yeniden `marked` + `DOMPurify` → uzun sohbette
  tırmanma.
- rAF / 60 ms throttle.

### C7. [Orta] Çağrı fırtınası — `ui.js:1806`
- Her yanıtta iki kez `/chat/sessions`; arama 150 ms debounce →
  dakikada 30+ istek → 30 rpm limiter'i tetikler (duplicate/429 döngüsü ile
  bağlantılı).
- Birleştir + önbellek (yalnız odak kaybında yenile).

### C8. [Düşük] Ölü DOM/CSS — `ui.js:695` + `ui.css:521-545`
- `#think-split`, `#think-chev` DOM'da yok → bağlı CSS ölü.
- Temizle.

### C9. [Düşük] `'|'.repeat(0)` + shadowing — `ui.js:3284`, `1914`
- `const t = setTimeout(...)` yerel `t` i18n `t()` fonksiyonunu gölgeliyor.
- İkisini de kaldır.

### C10. [Düşük] STRINGS'te ölü anahtarlar — `ui.js:54`
- `obName`, `obAsync`, `setSrvHint`, `loginNeedKey`, `amoledLabel` → 0 kullanım.
- Taramayla sil.

### C11. [Düşük] manifest vs HTML — `manifest.json:7` vs `index.html:6`
- `background #000000` vs `theme-color #0a0a0f`; `lang: "en"` (uygulama TR).
- HTML ile hizala.

### C12. [Düşük] Loader metni + `lang` — `index.html:27`, `web/app.html:2`
- Loader Türkçe sabit; tüm HTML'ler `<html lang="en">`.
- `applyLang` ile senkronize.

### C13. [Düşük] Hardcode renkler — `ui.css:148, 1357`
- Sabit mor `rgba(...)` / turuncu glow → `var(--accent)`.

### C14. [Düşük] Z-index çakışması — `web.html:190`
- `#toast` (z:300) `#onboard` (z:300) ile eşit → onboarding açıkken toast arkada.
- Toast 310.

### C15. [Düşük] Açık tema toast — `ui.css:883`
- `#toast.err` sabit koyu palet; açık temada uyumsuz → danger değişkenleri.

### C16. [Düşük] `/static` rate limit — `main.py:510`
- Soğuk yüklemeler 120 rpm paylaşımlı IP kovasında → NAT arkası 429 riski
  (sayfa hiç yüklenmez). Static'ten rate limit'i çıkar.

### C17. [Düşük] SW precache eksik — `sw.js:4`
- `STATIC_ASSETS`: `/` + ikonlar; `ui.js`, `ui.css`, `web.html` **YOK** →
  çevrimdışı ilk açılış eksik. Shell asset'lerini ekle.

### C18. [Düşük] Login açıkken arka plan çağrıları — `ui.js:4134`
- `showLogin` açıkken `loadSessions`/ticker devam ediyor → gereksiz 401 gürültüsü.
- Login iken durdur.

## D. DOĞRULANAN OLUMLULAR

- i18n: `tr`/`en` STRINGS **294 anahtar tam eşitlik** ✓
- `eval` / `new Function` / `document.write` / `WebSocket(` / `?k=` /
  `insertAdjacentHTML` **YOK** ✓
- `isSecureContext` kapıları (getUserMedia vb.) ✓
- `prefers-reduced-motion` ✓
- `web.html` vs `app.html`: fark tam 1 satır ✓
- Vendor'lar yerel + güncel: DOMPurify **3.1.6**, marked **12.0.2** ✓
- Markdown çıkışı DOMPurify'dan geçiyor ✓
- **Tek zayıf halka: `esc()`** (A1).

---

# RAPOR 6 — INSTALLER / TEST / CI / DOCS

Kapsam: `install.py` (1714 satır), `pyproject.toml`, `requirements*.txt`,
`*.service`, `scripts/`, `tests/` (56 dosya, 767 test), `.github/workflows/ci.yml`,
`playwright.config.js`, `package.json`, `README.md`, `docs/*`, `NOTES.md`,
`CHANGELOG.md`, `example.env`, `credstore.py` (ilgili kısım).

## A. GÜVENLİK

### A1. [Orta] Fernet-uyumsuz yedek anahtar — `install.py:1318-1324`
- `cryptography` import'u düşerse `MAIL_CREDS_KEY = "piss:" + token_urlsafe(32)`
  yazılıyor; `credstore.py` bunu Fernet key'i sanıp decode edince
  **"Incorrect padding"** (subagent 5/5 deneme) → tüm kimlik bilgisi kaydı
  sessizce `False`.
- Öneri: Fernet-uyumlu üret (`base64.urlsafe_b64encode(os.urandom(32))`) veya
  hiç yazma + kullanıcıya açık hata.

### A2. [Orta] `.env` 0644 penceresi — `install.py:1442-1446`
- Önce `write_text` (umask 022 → **0644**), sonra `chmod 0600`; chmod istisnası
  `except: pass` ile yutuluyor.
- Pencere: API_KEY üretildikten sonra, chmod başarısızsa **kalıcı** dünya-okunur.
- Öneri: `os.open(path, O_WRONLY|O_CREAT|O_TRUNC, 0o600)` ile baştan 0600;
  `SECRET` yazımını bunun içine al.

### A3. [Orta] `/tmp/piserve.service` TOCTOU — `install.py:1442? 1480?` (1442-1446 area; 1612-1614)
- Üniteler öngörülebilir `/tmp/piserve.service`'a yazılıp `sudo cp` ile
  kopyalanıyor → `/tmp` symlink saldırısı ile root unit'i değiştirilebilir.
- Öneri: `tempfile.mkstemp` (0600) veya doğrudan `sudo tee` pipe.

### A4. [Orta] Checksumsiz indirme — `install.py:490, 1012, 1088`
- `get-pip.py`, `ollama install.sh`, Piper ses arşivleri **SHA256'sız** iniyor
  ve (get-pip) doğrudan çalıştırılıyor.
- Repoda hiyerarşik doğrulama (K7) **hiç yok** (`sha256` dosyası repo genelinde 0).
- Öneri: bilinen hash'leri sabitle + doğrula (fix-plan K7 tamamlanmadı).

### A5. [Orta] `timeout` yok — `install.py:545-547, 977, 1028`
- `_run()` subprocess'te timeout yok → `litert-lm import`, `ollama pull` ölü
  bağlantıda **süresiz asılı** (kurulum kilitlenir).
- `timeout=900` + SIGKILL sonrası özet.
- İlgili: `curl` çağrılarının birçoğunda `--max-time` yok (667/680/1059'da var).

### A6. [Orta] `0.0.0.0` sabit + firewall yok — `install.py:1480, 1634`
- `--host 0.0.0.0:8765` hardcoded; port .env'de **yok**; firewall adımı yok.
- fix-plan / server-audit kararı: **default 127.0.0.1** → uygulanmamış.
- Öneri: `PISERVE_HOST` .env anahtarı (default 127.0.0.1), `0.0.0.0` opt-in,
  isteğe bağlı UFW kuralı.

### A7. [Orta] Batch'te `sudo` ( `-n` yok) — `install.py:132-146, 321, 339`
- `_pkg_install` her paketleyicide `sudo` çağırıyor; `-n` yok → parola
  sorulamayan ortamda (CI/batch) askıda kalır.
- BATCH_MODE'da `sudo -n` + önyükleme kontrolü.

### A8. [Orta] `.env` append + test kirliliği — `credstore.py:21-38`
- `MAIL_CREDS_KEY` eksikken canlı `ENV_PATH`'e append (umask 0644 riski A2 ile
  aynı aile);
- Tek unutan test repo `.env`'ini kirletir → conftest'e default key ekle.

### A9. [Düşük] Log dosyası 0644 — `install.py:779-790`
- `litert-server.log` umask'siz; non-systemd yolda `UMask=` geçerli değil.
- `0o600` ile aç.

## B. TUTARSIZLIK

### B1. [Orta] `pyproject` eksik bağımlılıklar — `pyproject.toml:10-25`
- `dependencies`'te **`bcrypt`**, **`cryptography`** YOK (`requirements.txt:6-7`
  var; `db.py:2561` `import bcrypt`).
- `pip install .` → eksik kurulum → ImportError.

### B2. [Orta] `py-modules` eksik — `pyproject.toml:33-34`
- Listelenen: 12 modül; repoda **22** Python modülü.
- Eksik (subagent listesi): `retrieval`, `messages`, `auth`, `tool_verification`,
  `credstore`, `textnorm`, `title`, `corpus_feeder`, `provision_owner`,
  `reembed_all`.
- `pip install .` ile kurulan pakette bu modüller **olmaz** → ImportError.
- Öneri: listeyi tamamla **veya** paketlemeyi (pip install .) tamamen iptal et
  (uygulama repo-root'tan çalışıyor).

### B3. [Orta] CI lock'u hiç kullanmıyor — `.github/workflows/ci.yml:26,34`
- CI `pip install -r requirements.txt` (>= aralık) → **lock hiçbir adımda
  install edilmiyor**;
- `pip-audit` yalnız lock **yorumu** okuyor → NOTES "lock pin enforcing"
  maddelesi yarıya inmemiş.
- Öneri: `pip install -r requirements.lock` + gerçek `pip-audit` job.

### B4. [Düşük] Compile listesi bayat — `ci.yml:30`
- 8 dosya sayesinde; `litert_serve` yok, yeni eklenen modüller unutulur.
- `compileall .` veya `**/*.py` taraması.

### B5. [Düşük] ruff format/mypy hiç çalışmıyor — `ci.yml:4-5, 32-35` + `pyproject:62`
- `pyproject.toml:62` format/mypy iddiası; CI'da ne `ruff format --check` ne
  `mypy` adımı var.
- push+PR **çift koşu** (duplicate).
- Öneri: koşulları ayıkla + format/mypy job'ı ekle (veya pyproject'ten iddiayı sil).

### B6. [Düşük] Tek Python + pin yok — `ci.yml:21,27,34`
- 3.11 tek; `pytest`/`ruff` pinlenmemiş (lock disipliniyle çelişiyor); cache yok.

### B7. [Orta] `port-contract.md` kabul listesi bayat — `docs/port-contract.md:109-118`
- "test_user_isolation (9)" → **gerçek 16**;
- "648 passed at freeze" → **gerçek 767 / 56 dosya**;
- satır referansı `llm/chat.py:98` → şu an **105**.
- Öneri: kabul listelerini canlı `pytest --collect-only -q` ile üret.

### B8. [Orta] Tool analizi dokümanı bayat — `docs/tool_intent_analysis.md:21`
- Embedding "MiniLM-L12 (384)" gösteriliyor; config default **mpnet-base-v2 (768)**
  ve NOTES Phase 2a bunu değiştirmiş;
- Ayrıca `:10, :13, :44-47` grup/sayılar, `:228` P3 durumu bayat.

### B9. [Düşük] NOTES içi bayat sayılar — `NOTES.md:368, 1064, 1415`
- Üstü çizilmemiş "test_install_template (9)" → **gerçek 12**;
- "27 tools" / "22 tools" → **gerçek 23**.
- Düzelt veya `~~çiz~~ + 2026-10-08` notu ekle.

### B10. [Orta] Fix-plan maddeleri karşılanmamış — `docs/fix-plan-2026-09-09.md:128, 139`
- **Y18**: `==` pin + lockfile üretimi + pip-audit → yarı uygulanmış (B3).
- **K7**: checksum ile indirme → uygulanmamış (A4).
- Açık tut / iş kalemi olarak işaretle.

### B11. [Düşük] Server-audit satır ref'ları bayat — `docs/server-audit-2026-09-09.md:319-323`
- A-Y2/Y3 bayat; **A-Y2 hâlâ çözüm değil** (host 0.0.0.0 sabit — A6).

### B12. [Orta] README API örnekleri yanlış — `README.md:299-303`
- `GET /chat/memories?user_id=default` → router **client user_id'yi yok sayıyor**;
- `DELETE ...?id=` → gerçek router `?id=` mi `path` mi doğrula (subagent:
  DELETE `?id=` kullanıyor ama auth bağlamı farklı);
- Öneri: API bölümünü canlı router'lardan yeniden üret.

### B13. [Düşük] README diğer bayatlıklar — `README.md:126, 149, 221`
- "installer generates config.json from config.example.json" → gerçek: **inline dict**
  (`install.py` içinde);
- ikon yolu bayat;
- quickstart `--host 0.0.0.0` → fix-plan kararıyla (127.0.0.1) çelişiyor.

### B14. [Düşük] CHANGELOG biçimi — `CHANGELOG.md:24-42`
- `[2.0.0]` altında `### Security` ve `### Fixed` **ikişer kez**
  (Keep a Changelog aykırı). Birleştir.

### B15. [Düşük] Mail doc bayat — `docs/mail-accounts-2026-09-09.md:36`
- "test_credentials (6)" → **gerçek 9**.

## C. NOTES KURAL İHLALLERİ

### C1. [Orta] Pre-push secret tarama HİÇ uygulanmamış — `NOTES.md:19`
- `.git/hooks/` yalnızca **`.sample`** dosyaları (hiç aktif hook yok);
- CI'da **gitleaks yok**;
- Repo'da secret-scan betiği yok.
- Kural metni "pre-push'ta secret/şifre/IP tara" — uygulanmadan push yapılmış.
- Öneri: aktif `pre-push` hook (NOTES + creds + IP regex) + CI `gitleaks`.

### C2. [Orta] "pin-enforcing test" zayıf — `NOTES.md:26, 321`
- Mevcut test yalnız `requirements.lock` ↔ `requirements.txt` **ad** kontrolü;
  sürüm drift'ini doğrulamıyor; pip-audit hiç çalışmıyor (B3).
- Öneri: her `pkg>=x` için lock'ta `pkg==y` assertion'ı + pip-audit job.

### C3. [Orta] Template ≡ example.env testi yok — `tests/test_install_template.py:25-163`
- Tam **anahtar-kümesi eşitliği** (template ↔ example.env ↔ install.py) +
  `.env 0600` eşitliği test edilmiyor → regresyon koruması yok
  (install.py template'i inline değiştirse kimse anlamaz).

### C4. [Orta] Playwright canlı DB'ye yazar — `playwright.config.js:23-28`
- `webServer.env`: `python` **sistem** (venv değil), `DB_PATH` override **yok**,
  `reuseExistingServer: true`.
- Etki: e2e canlı `assistant.db'ye` yazar → NOTES kural 4/7 ihlali
  (testler canlı DB'ye dokunmaz).
- Öneri: `webServer.command` venv python + `DB_PATH=<tmp>` +
  `reuseExistingServer: false`.

### C5. [Düşük] Playwright bayat — `package.json:11-12`
- `@playwright/test` **1.40.0** (deprecated); e2e CI'da **hiç koşmuyor**.
- Yükselt + CI'a ekle (yalnız e2e job).

## D. İYİLEŞTİRME

### D1. [Orta] Eksik paket özeti yok — `install.py:310, 366-367`
- `step_system_deps` eksik listesi topluyor ama **uyarı özet yok**; venv/build
  tools hiç listeye girmiyor.
- "N paket eksik: ... (sudo ile kurulacak)" + devam onayı.

### D2. [Orta] Model ön-indirme tek deneme + gizli hata — `install.py:896-927`
- `_predownload_ml_models`: tek deneme, `capture_output=True` → kullanıcı
  **neden başarısız göremiyor**, retry yok.
- Bu, NOTES'taki model-indirme bug'ının **ilk temas noktası**.
- Öneri: stderr'i göster + 2 deneme + exponential backoff + "modeli sonra
  `python -m ...` ile indir" çıktısı.

### D3. [Düşük] macOS adayları ölü kod — `install.py:583, 599-601`
- `Path("~/Library/Python/3.*/bin/x").glob(...)` → dizinde `*` **literal**
  (expanduser sonrası) → asla eşleşmez.
- `glob`'u home dışında dene veya tamamen sil (macOS desteklenmiyorsa).

### D4. [Düşük] Rerun'da .env temizliği — `install.py:1412`
- Template'de olmayan, elle eklenen .env anahtarları **sessizce siliniyor**.
- Koru ya da özetle: "3 anahtar taşındı: ...".

## E. DOĞRULANAN OLUMLULAR

- `example.env` ↔ `install.py` şablon anahtarları **69/69 birebir** ✓
- Test fixture geçici DB; canlı `assistant.db'ye` yazma yok (playwright hariç) ✓
- 56 test dosyası / 767 test toplanıyor (ci.yml compile adımı dışında) ✓
- `requirements.lock` mevcut (ama CI kullanmıyor) ✓

---
---

# SONRAKİ ADIM ÖNERİLERİ (öncelik sırası — haftalık plan için)

1. **Kritik güvenlik paketi (1. hafta):** esc() onarımı + unit test;
   calendar/task/todo global cache'lerine user/credential anahtarı;
   FTS + save_message owner guard'ları; leaked-call bypass (`use_tools=False`
   iken kapat); `/debug` body limiti (auth öncesi); `/chat/abort` sahiplik;
   `/reload-corpus` require_admin; `nextcloud_tasks.py:59` gate sırası.
2. **Post-refresh login (2. hafta):** ui.js boot gate → `/users/me` testi;
   sw.js allowlist + logout cache temizliği; cookie `secure` scheme bağlı;
   SW sürüm bump; `/static` Cache-Control.
3. **Embedding takılması (2-3. hafta):** kilitsiz indirme + `wait_for`;
   breaker'a timeout sayacı; SSE öncesi kurulum fazı bütçesi; retry'da
   `reply_parts`/`fullText` sıfırlama.
4. **NOTES ihlalleri (3-4. hafta):** sync tablo origin kolonu + LWW;
   `rollup_tool_audit` lock; pre-push secret tarama + gitleaks; i18n
   hardcode temizliği; playwright tmp DB; port-contract/test sayıları.
5. **Kurulum/kalite (5. hafta):** pyproject tamamlama (veya paketleme iptali);
   CI lock + pip-audit + format/mypy; install.py checksum + timeout +
   0600-at-write + `sudo -n` + host default 127.0.0.1.

# EK — Dosya referans dizini (hızlı arama)

| Konu | Dosya:S satır |
|---|---|
| esc() no-op | static/ui.js:383 |
| Boot gate / login bug | static/ui.js:1768, 1711; routers/users.py:97-111 |
| SW cache | static/sw.js:1, 39-44, 61-74 |
| Cookie secure | routers/users.py:24-28; config.py:182 |
| NC task cache bypass | nextcloud_tasks.py:59 |
| Takvim global cache | calendar_ops.py:65-82, 85-101, 141, 441-471 |
| Todos cache | nextcloud_tasks.py:207 |
| Embedding breaker | embedding.py:19-43; config.py:20; db.py:1664 |
| SSE kurulum fazı | routers/chat.py:314-341 |
| FTS sızıntısı | db.py:1982-2003 |
| save_message sahiplik | db.py:1684-1689 |
| rollup lock | db.py:1516-1569 |
| sync origin | db.py:526-539; 2241-2276 |
| leaked tool call | llm/stream.py:512-516, 561-562 |
| intent timeout | llm/intent.py:701-740 |
| retry mükerrer | llm/stream.py:426-431, 519-526; routers/chat.py:393 |
| /debug DoS | main.py:534-545, 617-625 |
| abort sahiplik | routers/chat.py:462-470 |
| reload-corpus auth | routers/chat.py:728-739 |
| IMAP injection | mail.py:42,111; tools/dispatcher.py:506 |
| Fernet fallback | install.py:1318-1324; credstore.py:30-45 |
| .env 0644 | install.py:1442-1446 |
| /tmp unit TOCTOU | install.py:1612-1614 |
| pyproject eksik | pyproject.toml:10-25, 33-34 |
| CI lock | .github/workflows/ci.yml:26, 34 |
| playwright DB | playwright.config.js:23-28 |
