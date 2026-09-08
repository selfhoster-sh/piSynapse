# piServe Sunucu Denetimi — 2026-09-09

Kapsam: `/home/salih/piSynapse` içindeki sunucu tarafı Python (`main.py`, `config.py`,
`db.py`, `routers/*`, `llm/*`, `tools/*`, entegrasyonlar, `install.py`, `litert_serve/`,
testler; `android/` ve `static/` UI hariç).
Yöntem: 4 paralel uzman ajan (veri katmanı / chat boru hattı / güvenlik+konfig / ölü kod-tutarlılık),
salt-okuma; kritik iddialar spot-check ile doğrulandı.
Ham bulgu: 81 + ek denetimler 44 → tekilleştirme sonrası **106 benzersiz bulgu**
(Kritik: 14, Yüksek: 31, Orta: 44, Düşük: 17).

> Not: `.env` içindeki gerçek secret değerleri bu rapora alınmamıştır.

## Yönetici özeti

1. **Kullanıcı izolasyonu sistematik olarak eksik (en ağır tema).** `user_id`
   filtresi `get_messages_to_summarize`, `retrieval._fetch_candidates`,
   `search_sessions` (semantic yol), `sessions` upsert'i ve FTS temizliğinde yok.
   Tek kullanıcılı ev kurulumunda pratik risk düşük, ama çok kullanıcılı/yanlış
   `session_id` senaryosunda veri sızıntısı + özet kirlenmesi olur. Port öncesi
   düzeltilmeli.
2. **`search_emails(..., mailbox)` şu an kesin patlıyor** — dispatcher 4 argüman
   geçiyor, `mail.search_messages` 3 argüman alıyor (TypeError).
3. **Non-stream `/chat/` ile `/chat/stream` ikiz implementasyon ayrışmış**
   (hint/escalation, chip guard) — aynı niyet iki endpointte farklı davranır.
4. **Özetleme üstten sınırsız:** `SUMMARY_BATCH_SIZE` yalnızca eşik; ilk fold'da
   tüm pending satırlar özetleyiciye gider (Android'de gördüğümüz 15595-token
   patlamasının server'daki karşılığı).
5. **Operasyonel güvenlik:** `install.py` içinde `curl|sh`, TRUSTED_HOSTS=`*`,
   CORS `*`+credentials kombosu, `/config/settings` GET ile secret iadesi,
   `?k=` URL anahtarı, pinsiz bağımlılıklar, log rotasyonu yokluğu.
6. **Testler kritik yolları mock'luyor:** retrieval SQL'i, summary boundary,
   mail imzası, middleware sırası gerçekte hiç çalıştırılmıyor.

---

## KRİTİK (9)

### K1. `mail.search_messages` imza uyuşmazlığı — mailbox'lı arama her zaman düşer
- Dosya: `mail.py:146` vs `tools/dispatcher.py:490`
- Kanıt: `async def search_messages(self, account_id: int, query: str, limit: int = 10)`
  çağrısı `mc.search_messages(account_id, q, limit, mailbox_id)` (4 argüman).
- Etki: Mailbox parametreli her `search_emails` TypeError ile düşer.
- Öneri: İmzaya `mailbox_id` ekleyip `_search_emails` içine ilet.

### K2. Non-stream chat'te hint/escalation yok, stream'de var
- Dosya: `llm/chat.py:194-197` vs `llm/stream.py:343-346,463,538`
- Kanıt: non-stream `if intent=="question"... use_tools=False` + log; stream
  `hint_armed`/`hatch_armed` ile escalate eder.
- Etki: Aynı niyet iki endpointte farklı davranır.
- Öneri: Kararı tek helper'a taşı, iki yoldan çağır.

### K3. `get_messages_to_summarize`'da `user_id` filtresi yok
- Dosya: `db.py:1636-1663` (iki sorgu da `WHERE session_id = ?` only)
- Etki: Çakışan `session_id`'de bir kullanıcının mesajı diğerinin özetine girer.
- Öneri: İki sorguya `AND user_id = ?` ekle.

### K4. `sessions` upsert'i kullanıcıyı doğrulamıyor
- Dosya: `db.py:207,1669-1676` (+ `save_message` içi `ON CONFLICT(id)` 962-966)
- Kanıt: `ON CONFLICT(id) DO UPDATE SET summary=?, summarized_until=?` —
  `UPDATE` kolunda `user_id` koşulu yok.
- Etki: Aynı `session_id`'yi bilen ikinci kullanıcı özeti ezer.
- Öneri: PK `(id, user_id)` veya tüm session yazmalarına `WHERE id=? AND user_id=?`.

### K5. `search_sessions` semantic yolunda kullanıcı filtresi yok
- Dosya: `db.py:1265-1270`
- Kanıt: `... WHERE c.embedding IS NOT NULL ... LIMIT 200` — `c.user_id` yok.
- Etki: FTS yolu filtreliyken semantic yol başka kullanıcının içeriğini sızdırır.
- Öneri: `c.user_id = ?` + `JOIN ... AND s.user_id=?` ekle.

### K6. Paylaşımlı bağlantıda `SELECT last_insert_rowid()` yarışı
- Dosya: `db.py:956-957,1161-1162` (+ tek global `_db`, 88-110)
- Etki: Eşzamanlı yazmada FTS satırı/audit yanlış mesaja bağlanır.
- Öneri: `cursor.lastrowid` kullan.

### K7. Installer `curl|sh` ile imzasız uzak script çalıştırıyor
- Dosya: `install.py:925-927`
- Kanıt: `curl -fsSL https://ollama.com/install.sh` çıktısı `sh`'ye veriliyor.
- Etki: MITM/kaynak ele geçirilirse kurulum hostunda tam RCE.
- Öneri: Paket yöneticisi/imza doğrulamalı kuruluma geç.

### K8. Canlı secret'lar `.env`'de plaintext
- Dosya: `.env:1,9,23` (API_KEY, GMAIL_APP_PASSWORD, NEXTCLOUD_PASSWORD)
- Etki: Yedek/log sızıntısında Gmail + Nextcloud tamamen ele geçer.
- Öneri: Secret'ları rotasyona sok, dosya dışı yönetime taşı. (Değerler rapora alınmadı.)

### K9. `clear_*_context` dörtlüsü ölü kod
- Dosya: `prompt.py:243,266,289,312`
- Kanıt: Tanımlı ama repo genelinde çağrı yok.
- Etki: Session silinince list-no→ID eşleşmelerinin temizlendiği sanılır, kalır.
- Öneri: Sil veya `clear_history`/`delete_session` yoluna bağla.

---

## YÜKSEK (22)

### Y1. `SUMMARY_BATCH_SIZE` üst sınır değil, yalnızca eşik
- `db.py:1650-1666` — dönüş sorgusu TÜM pending satırlar; 10 bin mesaj
  birikirse özetleyiciye 10 bin satır gider. `ORDER BY id ASC LIMIT ?` + boundary
  ilerletme ekle.

### Y2. Cleanup/retention `summarized_until`'i düzeltmiyor
- `db.py:981-1035,427-456` — `delete_branch`/`cleanup_expired_data` sonrası
  boundary bayat kalır: özetleme sonsuza dek boş döner, silinmiş içeriğin özeti
  prompt'a girmeye devam eder. `MIN(summarized_until, MAX(id))` düzeltmesi ekle.

### Y3. Tek bağlantıda gruplu yazma girişimi
- `db.py:88-110,951-977` — tek global `_db`'de çok ifadeli yazma + sonda commit;
  eşzamanlı istekler aynı transaksiyona karışır. `BEGIN IMMEDIATE` kısa
  transaksiyon veya havuz kullan.

### Y4. `_update_summary` kilitsiz read-modify-write
- `routers/chat.py:150-160` (+ çağrılar 258-259, 389-390) — iki background görev
  aynı session'da çakışırsa bayat boundary yeni özeti ezer. Session başına
  `asyncio.Lock` veya koşullu `UPDATE ... WHERE summarized_until=?` ekle.

### Y5. `retrieval._fetch_candidates`'ta `user_id` filtresi yok
- `retrieval.py:48-52` — çakışan session'da başkasının mesajları LLM bağlamına
  girer. `WHERE session_id=? AND user_id=?` yap.

### Y6. EMBED_MODEL varsayılan üçlü çelişki
- `embedding.py:13-16` (mpnet 768) vs `config.py:169` (MiniLM 384) vs
  `install.py:1055` template (MiniLM) vs `example.env:47` (mpnet);
  üstelik `embedding.py` `load_dotenv` çağırmadan `os.getenv` okur. Boyut
  karışınca cosine sessizce `0.0` döner, retrieval boşalır. Tek sabit
  (`config.EMBED_MODEL`) + startup boyut kontrolü ekle.

### Y7. Mail liste çıktısında numara yok
- `tools/dispatcher.py:442-448` vs `prompt.py:51,59` + `read_email` beklentisi —
  model `read_email("3")` dayanağı olmadan numara uydurur. `enumerate(...,1)` ekle.

### Y8. `create_event` RRULE ham string ile iCal'e gömülüyor
- `calendar_ops.py:232` + `tools/dispatcher.py:151` — model girdisiyle iCal
  yapısına satır enjekte edilebilir. Allowlist regex + CRLF reddi ekle.

### Y9. Indexsiz LiteRT chunk'ları merge'de eziliyor
- `llm/stream.py:106-109` vs `litert_serve/server.py:522` (index yok) —
  çok parçalı tool argümanı yarım kalır, yanlış/eksik tool çalışır. String-concat
  birikimi veya server'a index ekle.

### Y10. Sadece email UNTRUSTED işaretli
- `prompt.py:190` email bloğu sanitize edilirken `calendar_ops:271`,
  `nextcloud_tasks:250`, `nextcloud_notes:237` ham enjekte ediliyor. Tüm tool
  çıktılarını aynı UNTRUSTED+santize hattından geçir.

### Y11. `send_email` alıcı doğrulaması yok
- `tools/dispatcher.py:470-479` + `mail.py:95` — halüsinasyon/enjekte adrese tek
  onayla veri sızar. Email regex + confirm-preview zorunlu kıl.

### Y12. `_normalize_messages_for_backend` LiteRT yolunda `tool_name` düşürüyor
- `llm/payload.py:200-236` — çok turlu akışta tool sonucu ayırt edilemez.
  `tool_name`'i koru veya OpenAI `name` alanına eşle.

### Y13. TRUSTED_HOSTS=`*` Host kontrolünü kapatıyor
- `main.py:367-368` — host-header poisoning'e açık. `*` reddedilip allowlist
  zorunlu kılınmalı.

### Y14. CORS `allow_credentials=True` + `*` filtresi yok
- `main.py:279-285` — operatör `*` yazarsa credential'lı istekler genişler.
  Startup'ta `*` reddedilmeli.

### Y15. `/health,/,/static` auth+rate-limit'ten muaf
- `main.py:406,449` — kimliksiz sınırsız tarama/L7 DoS. Exempt yollara gevşek
  ayrı limit uygula.

### Y16. `GET /config/settings` secret döndürüyor
- `routers/config.py:81-85` + `config.py:361,374` — `PROTECTED_SETTINGS`
  yalnız PATCH'i engeller; GET `NEXTCLOUD_PASSWORD` dahil her şeyi verir.
  Password alanlarını maskele.

### Y17. `/chat/upload` tip/MIME doğrulamasız, RAM'de biriktiriyor
- `routers/chat.py:742-763` — magic kontrolü yok; 100MB×N istekte OOM + %33
  base64 şişmesi. MIME/magic kontrolü + diske stream et.

### Y18. Bağımlılıklar pinsiz (`>=` her yerde)
- `requirements.txt:1-14` + `pyproject.toml:10-25` — tedarik zinciri kayması
  riski. `==` pin + lockfile + `pip-audit` gating ekle.

### Y19. `/debug` tüm body'yi stdout'a basıyor
- `main.py:601-611` — PII loglara sızar. Prod'da kapat veya redact+örnekleme.

### Y20. Stream abort iç döngüyü kırmıyor
- `routers/chat.py:331-333` + `llm/stream.py:706,374` — "Durdur" sonrası tool
  arka planda çalışmaya devam eder, terminal `done` yok. Abort bayrağını
  `chat_with_ollama_stream` içine taşı + iptal olayı yayınla.

### Y21. Doküman sayısı/tool adı uyuşmazlıkları
- `docs/tool_intent_analysis.md:9` (27 tool iddiası, kodda 23),
  `:42` (OpenWeatherMap iddiası, kod Open-Meteo),
  `README.md:131` (`routers/tools.py` eksik), `README:124-125` (tek `index.html`
  iddiası; gerçekte index+web+app+ui.js+ui.css). Dokümanı koddan üret.

### Y22. CHANGELOG'da düzeltildi denilen `?k=` leak'i canlı
- `main.py:419` hâlâ `query_params.get("k")` kabul ediyor; `CHANGELOG.md:41`
  düzeltildi diyor; `tests/test_security.py:74-76` bunu sabitliyor. Dalı kaldır
  veya kalıcılığı güvenlik notuyla belgele.

---

## ORTA (34)

**Veri/bellek:** FTS temizliğinde `user_id` yok (`db.py:1127`);
`_enrich_title` `COUNT(*)==2` katı eşitliği kalıcı skip üretir (`routers/chat.py:182-185`);
RAKE başlık e-postayı verbatim saklar (`title.py:10-21`, test bile pinliyor);
`reembed_all` busy_timeout/retry ve memories dim kontrolünden yoksun;
`update_session_summary` retry'siz commit + `last_active` güncellemiyor
(`db.py:1669-1676`); `import_messages` TOCTOU, `client_key` UNIQUE değil
(`db.py:1136-1160`); `get_all_history` limitsiz, `search_memories` tüm vektörleri
çeker, retention default `0`, `audit_exports/*.csv` hiç silinmiyor
(`db.py:1096-1121,1736-1741`, `config.py:167-168`);
`SUMMARY_EARLY_TRIGGER` UI şemasında yok, `CONFLICT_COSINE` canlı okunmuyor
(`config.py:287-301,384`, `corpus_feeder:408`);
`corpus_feeder._llm_resolve` httpx client sızdırıyor (`:484,518`).

**Chat boru hattı:** non-stream chip fast-path yok (`llm/chat.py:172-182`,
`routers/chat.py:202`); prompt grup stringleri `TOOL_GROUPS`'tan türemiyor,
`get_datetime` grup listelerinde eksik (`prompt.py:78-124` vs
`tools/definitions.py:413`); `trim_messages_for_context` tool üçlülerini
ortadan bölebilir (`llm/payload.py:163-188`); `parse_tool_args` bozuk JSON'da
sessiz `{}` döner (`tools/definitions.py:481-485`); CalDAV/inference drain
süresiz bekler (`calendar_ops.py:127-130`, `nextcloud_tasks.py:202-204`,
`litert_serve/server.py:186-189`); `merge_history` pencere ortasını sessizce
atar (`retrieval.py:40-48`).

**Konfig/güvenlik:** `install.py` template vs `example.env` vs `config.py`
(`install.py:1055`, `example.env:47`, `config.py:169` — bkz. Y6);
`CONFLICT_COSINE` example.env/`_NUMERIC_KEYS` dışında (`config.py:165,377-393`);
`UI_LANGUAGE` default üçlemesi (`messages.py:32-34`, `config.py:308`,
`.env:43`, `example.env` — tek default'a indir);
`ASSISTANT_USER`/`DEFAULT_USER` default çelişkisi (`config.py:156,322`);
media upload suffix filtresiz (`routers/media.py:128,206`);
log rotasyonu yok (`main.py:42-45`, `install.py:777-782`);
göreli yol + hardcoded host/port (`config.py:75-76`, `install.py:1346`);
her açılışta tam sayım + koşullu VACUUM (`db.py:386-392,406-424`).

**Test/ölü kod:** `reembed_all.main` hiç import edilmiyor + testsiz;
`install.py` (~1300 satır) için doğrudan test yok;
`CONFIRM_REQUIRED` ölü export (`tools/definitions.py:454`);
`EARLY_BUFFER_CHARS` ölü export (`llm/stream.py:53`);
`generate_title_first4`/`generate_rake_title` çift isim (`title.py:10`);
`_SessionRateLimiter` gereksiz alt sınıf (`main.py:94`);
mock'lar gerçek davranışı gizliyor (`test_health:12`, `test_security:18-21`,
`conftest:14`); `routers/chat.py:652` olmayan `--commit` flag'ine referans;
intent "5 tokens" iddiası kodla tutmuyor (`README:62` vs `llm/intent.py:688,878`);
`EARLY_TRIGGER`/`user_id` kapsamı title testlerinde yok;
`resume_context` seed'i `user_id` yazmıyor, çapraz-kullanıcı testi yok.

---

## DÜŞÜK (12)

`generate_rake_title` ölü `max_words` parametresi (`title.py:24`);
`_old/` izole ölü dizin (canlı import yok);
widget/tool weather formatı iki yerde kopya (`routers/widgets.py:28` vs
`weather.py:132-134`); `sanitize_external_text` kapsamı belgelenmemiş
(`utils.py:127`); tool param logu + audit DB ham PII saklıyor
(`tools/dispatcher.py:91-114`, `db.log_tool_call`);
`messages.py:33` dil default'u (`UI_LANGUAGE` ile tekilleştir — bkz. Orta);
`test_security`/`test_dispatcher` kritik yolları mock'luyor (mail imzası,
normalize/tool_name, merge-index, abort, chip-parity testi yok);
`piSynapse.db` 644 (dünya-okunur) — startup'ta `*.db*` için 600 enforce et;
`MEDIA_MAX_MB` parse `_safe_int` kullanmıyor (`routers/chat.py:748`);
`cat .env | grep API_KEY` yönergesi secret'ı shell-history'e düşürür
(`install.py:1401-1402`).

---

## Port kararı için çıkarımlar

1. Python tarafı **mimari olarak sağlam ama izolasyon + sınırlandırma
   katmanında delikleri var** — porta başlamadan önce K1–K6 + Y1–Y5
   düzeltilmeli; yoksa aynı delikler Kotlin'e taşınır.
2. Port kontratı için dondurulması gereken davranışlar: `get_messages_to_summarize`
   boundary formülü **+ gerçek cap** (Y1 fix'li hali), `_update_summary` kilit
   semantiği (Y4 fix'li hali), session PK/`user_id` kapsamı (K3–K5 fix'li hali),
   tool JSON şeması + retry/intent akışı, SSE olay şekilleri (`done` terminal
   olayı dahil — bkz. Y20).
3. Test boşlukları (mock'lanan retrieval SQL, boundary, mail imzası) portun
   kabul testleri olmalı — önce server'da gerçek test yazılmalı.

---

## Ek A — İlk kurulum denetimi (2026-09-09)

Kapsam: `install.py`, `example.env`+template+`config.py` üçlüsü, gereksinimler,
`main.py` startup, model indirme, systemd, dizin/izinler, üç DB dosyası, ilk
çalıştırma. Ana rapordaki Y6 (EMBED_MODEL), ikiz-DB ve `grep API_KEY` bulgularıyla
çakışanlar tekrar sayılmadı; tamamlayıcı notlar en altta.

### Kritik (4)

**A-K1. `--yes` menülerde yok, headless kurulum asılı kalır**
- `install.py:246` — `menu()` BATCH_MODE kontrolü yapmaz (kontroller yalnız
  222/230/238/1426'da); `step_llm_backend/step_tts_voices/step_env` hep `menu()`
  çağırır. `menu()` başına `if BATCH_MODE: return default` ekle.

**A-K2. Piper yarım indirme zehirlenmesi, resume/yoklama yok**
- `install.py:984-991` — `if exists: continue` + `curl -o` (boyut/hash yok,
  `-C -` yok). Kesilen indirme "var" sayılıp atlanır; TTS runtime 503 verir
  (`routers/media.py:467-471`). `.tmp` + boyut kontrolü + `os.replace` kullan.

**A-K3. `backups/*.tar.gz` dünya-okunur (644)**
- `backups/` — `.env`/`assistant.db` 600 iken yedek arşivler 644; mail/Nextcloud/
  API secret içeren arşivler her local kullanıcıya açık. Yedek yazımında 0600 +
  `UMask=0077` uygula, eskileri `chmod 600` yap.

**A-K4. Canlı systemd üniteleri installer şablonundan sapmış**
- Canlı `piserve.service`: `WorkingDirectory=/home/salih/litert_serve` +
  `ExecStart=... /home/salih/litert_serve/server.py` (repo değil, yetim kopya);
  canlı `pisynapse.service`: `After=... litert.service` (ölü isim; doğrusu
  `piserve.service`). Boot'ta yanlış/ölü kod veya sıralama yarışı (`:9379`).
  Üniteleri installer'dan yeniden üret, yetim dizini kaldır. (Doğrulandı.)

### Yüksek (8)

**A-Y1. piserve şablonunda WorkingDirectory/UMask/EnvironmentFile yok**
- `install.py:817-832` (pisynapse şablonunda var: 1343-1344). CWD `/` olur,
  `PISERVE_ADMIN_TOKEN` systemd altında geçemez (`server.py:37`). Üçünü ekle.

**A-Y2. Port sabit `0.0.0.0:8765`, firewall adımı yok** — `install.py:1346,1377`;
port `.env`'de yok. Portu `.env`'e al, default `127.0.0.1` + `ufw` önerisi sun.

**A-Y3. TRUSTED_HOSTS tekrar-çalıştırmada değiştirilemez** —
`install.py:1255,1284-1290`; `preserved_keys` eski değeri sorulanın üstüne yazar.
Sorulan anahtarları preserve listesinden çıkar.

**A-Y4. STT `browser` şema dışı** — installer/example `whisper/gemma4/browser`
sunar (`install.py:1235`), şema yalnız `gemma4/whisper` (`config.py:338`).
Şemaya `browser` ekle veya installer'dan kaldır. (Doğrulandı.)

**A-Y5. Embedding (~470MB) ve Whisper (~75MB) kurulumda indirilmez** —
installer'da adım yok; ilk yük lazy, warmup yalnız `try` içinde
(`main.py:192-222`). "Modelleri ön-indir + df/RAM kontrolü" adımı ekle.

**A-Y6. `max_num_tokens` üçlü uyumsuz** — installer `8192` (`:725`) vs
`config.example.json`/`canlı config.json` `6144` vs `config.py:87`
`DEFAULT_LLM_NUM_CTX=8192`. Tek kaynağa bağla.

**A-Y7. Canlı anahtarlar template/preserve dışında, rerun'da silinir** —
`CONFLICT_COSINE`, `PISERVE_ADMIN_TOKEN`, `AUDIT_EXPORT_DIR` ne `_ENV_TEMPLATE`'te
ne `preserved_keys`'te. Üçünü template + preserve + example.env'e ekle.

**A-Y8. `init_db()` korumasız, startup tek hata noktası** —
`main.py:123` `try` dışı (warmup'lar try içinde). Bozuk/kilitli DB `/health`
dahil her şeyi indirir. Yakala + degraded `/health` veya net hata ver.
(Doğrulandı.)

### Orta (5)

**A-O1. Gerekli dizinler kurulmaz** — tek `makedirs` `models/piper` (`:980`);
`models/`, `corpus_data/`, `audit_exports/`, `backups/` lazy oluşur. Kurulumda
`0700` ile oluştur.

**A-O2. `litert-lm` bağımlılık dışı ama piServe ona muhtaç** — iki listede de
yok; `--skip-llm` + litert default'ta `ImportError`. Opsiyonel bağımlılık +
kurulum kontrolü ekle.

**A-O3. Manuel kurulum `API_KEY` üretmez, fail-closed olur** —
`README.md:180-194` + `example.env:108` vs `main.py:434-439` (boş key → 503).
Manuel bölüme key-üretim + doğru sıra ekle.

**A-O4. TTS skip'i `.env`'de sahte hazır görünür** — skip'te voice yine defaulta
setlenir (`:1008-1012,1242`); dosya yoksa ilk TTS 503. Skip'te `TTS_ENGINE=browser`
yaz veya boş bırak + uyar.

**A-O5. Model indirme tek deneme, resume yok** — `litert-lm import`/`ollama pull`
tek subprocess (`:897-904,935-939`). Retry + `list` doğrulaması ekle.

### Düşük (3)

**A-D1. Disk/RAM ön-kontrolü yok** (`:865-868`); **A-D2. `.env` yokluğu
davranışı belgeli değil** (`config.py:12`, `main.py:108-114`); **A-D3. litert shim
`0o755`** (`:634-639`, `0750` yap).

### Tamamlayıcı notlar (ana raporla birleşen)
- EMBED_MODEL tutarsızlığı **dörtlü**: installer template (MiniLM) de dahil (bkz. Y6).
- Üç DB dosyası: `pisynapse.db`/`piSynapse.db` 0-byte 644 hayaletler + split-brain
  riski (bkz. Düşük ikiz-DB); hayaletleri sil.
- `cat .env | grep API_KEY` yönergesi shell-history'e sızar (bkz. Düşük).

---

## Ek B — DB yönetimi denetimi (2026-09-09)

Kapsam: `db.py` (1-1862) yaşam döngüsü — şema/migration, pragma, bağlantı,
concurrency, retention, yedek, kurtarma, silme kaskadları, testler. Ana rapordaki
K3–K6, Y1–Y4, Orta-büyüme bulgularıyla çakışanlar tekrar sayılmadı. Not: DB ajanı,
ana raporda Orta sayılan `import_messages` TOCTOU/`client_key` UNIQUE eksikliğini
**Kritik** görüyor (paralel re-sync'te çift yazma kanıtlı) — yükseltme önerilir.

### Kritik (1)

**B-K1. Bozulma kurtarma yok, otomatik yedek yok, geri yükleme prosedürü yok**
- `db.py:88` + `main.py:123` — `integrity_check/quick_check` repo `*.py`'de
  sıfır eşleşme; `backups/`'a kod referansı sıfır (içerik manuel tar.gz).
  Corrupt DB açılışta exception'a düşer, veri kaybı kalıcı olur. Startup
  `PRAGMA quick_check` + SQLite online-backup ile günlük otomatik yedek ekle.

### Yüksek (1)

**B-Y1. `save_message` FTS hatası tüm mesajı kaybettirir (asimetri)**
- `db.py:958-961` try'sız `INSERT conversations_fts`; hata sonraki commit'i
  engeller. `import_messages` aynı insert'i best-effort sarar (`:1163-1170`).
  `save_message` FTS insert'ini de best-effort yap, drift-rebuild'e bırak.

### Orta (5)

**B-O1. Büyüme sorgularını vuran eksik indeksler** — yok:
`conversations(client_key)`, `memories(created_at)`,
`tool_audit_log(conversation_id)`, `substr(created_at,1,10)` expression.
(Mevcutlar `db.py:281-354`.) Dördüne indeks ekle.

**B-O2. FK hiç yok, migration yalnız `ADD COLUMN`** — `FOREIGN KEY` sıfır
eşleşme; `MIGRATIONS` 15× `ADD COLUMN` (`:137-174`); FTS-dışı rebuild yok.
Yetim satırlar kalır, tip/PK evrimi elle müdahale ister. FK + `ON DELETE
CASCADE` veya silme yollarında manuel cascade'i zorunlu tut.

**B-O3. WAL limitsiz, checkpoint politikası yok** — pragma setinde
(`:101-107`) `journal_size_limit/mmap_size/auto_checkpoint` yok; canlı
`-wal` ~4MB gözlendi. `journal_size_limit` + periyodik `wal_checkpoint(PASSIVE)` ekle.

**B-O4. `save_*_map` DELETE+INSERT atomik değil** — önce `DELETE WHERE
session_id`, sonra satır başına commit'li yazma (`:1302-1321,1354-1373,
1404-1424,1531-1549`). Ortada crash'te map yarım kalır, model no→ID'yi yanlış
çözer. Tek transaksiyonda topla, sonda tek commit yap.

**B-O5. PII/secret'lar şifresiz + yedek politikasıyla birleşince sızıntı büyür**
- `conversations/memories/map` içerikleri plaintext; audit CSV 20 kolonla
  arşivlenir (`:713-751`). Secret'ları dosya dışına taşı, yedekleri şifrele,
  CSV retention ekle.

### Düşük (2)

**B-D1. `ALTER TABLE`/`PRAGMA user_version` f-string ile** (`:167,172`) —
bugün sabit listeden beslendiği için güvenli; tablo/kolon adlarını allowlist +
quoting ile sabitle.

**B-D2. Migration/concurrency/bozulma testi yok** — `init_db`'yi vuran testler
var (`test_audit`, `test_retry`) ama `user_version` adımı, eski-DB migration,
`BEGIN IMMEDIATE` concurrency testi yok. Ekle.
