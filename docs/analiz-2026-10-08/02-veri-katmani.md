# VERİ KATMANI ANALİZ RAPORU — piSynapse (salt okuma)

Kapsam: `db.py`, `retrieval.py`, `embedding.py`, `reembed_all.py`, `corpus_feeder.py`, `textnorm.py` + tüketicileri (`routers/chat.py`, `main.py`, `llm/`, `tools/dispatcher.py`, `tool_verification.py`), kural kaynağı `NOTES.md`, testler `tests/`. Hiçbir dosya değiştirilmedi.

## A) BİLİNEN BUG DOĞRULAMALARI (2)

`[ÖNEMLİ: Yüksek] embedding.py:19-43 + config.py:20` — İddia edilen iki düzeltme kodda var (`_MODEL_RETRY_COOLDOWN = 600.0` 10 dk circuit breaker; `HF_HUB_DOWNLOAD_TIMEOUT=30` config.py:20'de `setdefault`), ama bug çözülmemiş: breaker yalnızca `TextEmbedding(...)` istisna fırlattığında `_model_error_ts` yazıyor, NOTES'taki "0% saatlerce asılı indirme" senaryosunda ise exception üretmediği için breaker hiç tetiklenmiyor, `_model_lock` içinde bekleyen tüm embed çağrıları süresiz bloke oluyor ve istek yolunda (`save_message` db.py:1659-1666, `embed_async` embedding.py:53-57) hiçbir timeout yok — Öneri: model yüklemeyi deadline'lı bir worker/`asyncio.wait_for` ile sarıp timeout'u da hata sayacak, istek yolundaki tüm embed çağrılarına süre sınırı koy.

`[ÖNEMLİ: Orta] db.py:1648-1657` — "Duplicate pencere" mekanizması aslında zaman penceresi değil, yalnızca "son satır aynı kullanıcı mesajı mı" kontrolü; kendisi sohbeti kilitlemiyor (yinelenen INSERT'i atlar, LLM çağrısı yine koşuyor) ayrıca kontrol `_write_lock` dışında (TOCTOU → iki eşzamanlı istek ikisi de geçer) ve önceki yanıt boşsa (routers/chat.py:283) meşru tekrar sessizce yutuluyor; asıl takılma asılı kalan embed — Öneri: dedup kontrolünü write-lock içine al ve yalnızca son ~30 sn / son ID aralığında uygula.

---

## 1) GÜVENLİK (multi-user sızıntı, PII, izinler)

`[ÖNEMLİ: Yüksek] db.py:1982-2003` — `search_sessions` FTS dalı scoping'i yalnızca `JOIN sessions s ... AND s.user_id = ?` üzerine kuruyor, FTS satırında `user_id` yok ve `conversations`'a join yok → başka kullanıcının benim session_id'me yazılmış mesajı (snippet = gerçek içerik) bana dönüyor — Öneri: `JOIN conversations c ON c.id = f.rowid AND c.user_id = ?` ekle, FTS satırına `user_id` kolonu taşı.

`[ÖNEMLİ: Yüksek] db.py:1684-1689` — `save_message`'daki `ON CONFLICT(id) DO UPDATE ... WHERE sessions.user_id = excluded.user_id` çakışmada sessizce no-op olurken `conversations` INSERT'i koşulsuz çalışıyor; session_id istemci seçimli (`ChatRequest.session_id` default'ü `default_session`, routers/chat.py:82; regex dışındaki tek koruma) → yabancı kullanıcı başkasının oturumuna satır yazabiliyor (üstteki sızıntının ön koşulu) — Öneri: INSERT öncesi oturum sahipliğini doğrula, sahip değilse 403 üret.

`[ÖNEMLİ: Orta] db.py:2114, 2173, 2231, 2365` — `clear_email_map/clear_notes_map/clear_tasks_map/clear_calendar_map` fonksiyonlarında hiç `user_id` parametresi yok (kural 2 aykırısı); şu an repo genelinde çağrıları yok (ölü kod) ama silme ucu açık — Öneri: `user_id` zorunlu kıl veya fonksiyonları sil.

`[ÖNEMLİ: Orta] corpus_feeder.py:166-180` — `_resolve_message_text` conversation_id → session_id → önceki kullanıcı mesajını kullanıcı filtresiz çekiyor, oysa db tarafındaki ayna `db._user_text_for_audit` (db.py:1042-1046) `user_id` filtresi koyuyor → db ve feeder aynası kaymış, başka kullanıcının cümlesi global `corpus_data/additions.jsonl` içine girebiliyor — Öneri: feeder'da audit satırındaki `user_id`'yi okuyup sorguyu onunla sınırla.

`[ÖNEMLİ: Orta] db.py:394-403, 926-931` — `intent_audit_log` şemasında `user_id` kolonu yok ve ham kullanıcı mesajı (`message[:500]`, PII) saklanıyor → kullanıcı bazlı tekilleştirme/silme yapılamıyor (kural 2 aykırısı) — Öneri: `user_id TEXT` ekle, MIGRATIONS'a sıralı kayıt yap ve geriye dönük doldur.

`[ÖNEMLİ: Orta] db.py:2754-2798` — `delete_user` docstring'i "privacy-complete wipe" dese de silinmeyenler var: `intent_audit_log` satırları, `audit_exports/*.csv` gün dosyaları ve `corpus_data/additions.jsonl` (ham metin) — Öneri: docstring'i dürüstleştir veya silme yoluna CSV/corpus temizliğini ekle.

`[ÖNEMLİ: Orta] tool_verification.py:191, 264` — `SELECT id FROM memories WHERE id = ?` ve `SELECT COUNT(*) FROM memories WHERE content = ?` sorgularında owner guard yok → başka kullanıcının bellek id/içeriği üzerinden çapraz kullanıcı varlık doğrulaması yapılabiliyor — Öneri: her iki sorguya `AND user_id = ?` ekle.

`[ÖNEMLİ: Orta] db.py:1414-1419` — `AUDIT_EXPORT_COLUMNS` `user_id` içermiyor (docstring "every audit column" diyor) → günlük audit CSV'lerinde çok kullanıcılı atıf kaybı ve kullanıcı bazlı silinemezlik — Öneri: kolonu listeye ekle, mevcut CSV'leri geriye dönük uyumlu işaretle.

`[ÖNEMLİ: Düşük] corpus_feeder.py:60-99` — `os.umask(0o077)` yalnızca db.py:26'da; standalone feeder `corpus_data/*.jsonl` dosyalarını varsayılan umask (0644, ham kullanıcı metni) ile yazıyor (ev dizini 750 olduğu için etkisi kısmi) — Öneri: feeder başlangıcında umask 077 kur ve mevcut corpus dosyalarını 0600'a düşür.

---

## 2) TUTARSIZLIK (şema ↔ migration ↔ consumer ↔ config)

`[ÖNEMLİ: Orta] db.py:3203 vs config.py:196` — `search_memories` benzerlik eşiği kod içi sabit `0.35`, `save_memory` dedup eşiği ise config'de `MEMORY_SIMILARITY_THRESHOLD=0.68`; config şemasında tek eşik anahtarı var, retrieval tarafı (retrieval.py:19) de "0.35 matches memories" diyerek aynı değeri config'siz tekrarlıyor — Öneri: arama ve dedup eşiklerini ayrı ayrı config anahtarlarına taşıyıp tek doğruluk kaynağı yap.

`[ÖNEMLİ: Orta] config.py:195 + db.py:3136, 3176, 3274, 3299` — `DEFAULT_USER = ASSISTANT_USER` (görünen ad, ör. "Ada") `user_id` fallback'i olarak kullanılıyor; `users.id` uuid hex / 'default' olduğu için böyle bir satır hiçbir kullanıcıya denk gelmez ve o kullanıcıya ait bellekler hiç kimseye görünmez — Öneri: fallback'i gerçek `user_id` olan `DEFAULT_USER_ID="default"` (db.py:2425) yap.

`[ÖNEMLİ: Orta] db.py:1536-1543 + 594-596` — günlük rollup summary satırları `INSERT ... SELECT` sırasında `user_id` yazılmıyor (NULL), açılıştaki NULL-normalizasyon ise `tool_audit_log.user_id = 'default'` yaptığı için tüm özetler 'default' kullanıcısına atanıyor; `delete_user('default')` (db.py:2785) tüm özet satırlarını silebiliyor — Öneri: özet satırlarında owner'ı koru ya da silme sorgusuna `AND is_summary = 0` koşulu ekle.

`[ÖNEMLİ: Orta] db.py:678-681` — retention süpürmesi `DELETE FROM sessions WHERE id NOT IN (SELECT DISTINCT session_id FROM conversations)` yazıyor; yaş filtresi yok → `CONVERSATION_RETENTION_DAYS>0` iken mesajsız TÜM oturumlar (yeni `POST /sessions` ile açılanlar dahil) günlük temizlikte silinip isimleri kayboluyor — Öneri: `AND last_active < datetime('now', ?)` ekle.

`[ÖNEMLİ: Orta] reembed_all.py:34-35, 41, 46-48, 57, 59-63` — (a) sorgular `WHERE embedding IS NOT NULL` olduğu için embed hatası düşenler ve `import_messages` satırları (db.py:1917) asla vektörleştirilmiyor; (b) conversations dalında dim kontrolü var, memories dalında yok; (c) `sqlite3.connect(db)` çağrısında `busy_timeout`/WAL ayarı yok → sunucu ayaktayken "database is locked" ile yarışıyor — Öneri: NULL vektörlü satırları ikinci bir geçişte işle, memories'e aynı dim kontrolünü ekle, `PRAGMA busy_timeout=10000` set et.

`[ÖNEMLİ: Orta] main.py:218-227` — dim drift koruması model adına göre (`minilm`→384, `mpnet`→768, diğerleri korumasız) ve tabloda tek satır örnekliyor → NOTES'taki `embeddinggemma-300m` gibi yeni modelde koruma tamamen devre dışı, karışıktan gelen kısmi drift görünmüyor — Öneri: beklenen boyutu indirmeden model yapılandırma/tokenizer'dan oku ve 3-5 satır örnekleyip warn-only karşılaştır.

`[ÖNEMLİ: Düşük] corpus_feeder.py:56-57, reembed_all.py:34` — her ikisi de `config.DB_PATH`'e düşüyor; test izolasyon fixture'i (tests/conftest.py:68) yalnızca `db.DB_PATH`'i patch'lediği için tek eksik `db_path` argümanı canlı `assistant.db`'ye yazabilir (kural 1 kırılganlığı; mevcut testler explicit path verdiği için şu an ihlal yok) — Öneri: fallback'i `db.DB_PATH`'e çevir veya fixture `config.DB_PATH`'i de patch'lesin.

---

## 3) DEĞİŞİKLİK GEREKSİNİMİ (NOTES.md kurallarına aykırılık)

`[ÖNEMLİ: Yüksek] db.py:1516-1569` — `rollup_tool_audit` `_write_lock` almadan `BEGIN IMMEDIATE` (1518) kullanıyor, oysa db.py:39-43 yorumu tam bu yüzden lock'u BEGIN IMMEDIATE yerine tercih ediyor: açık implicit transaction varsa "cannot start a transaction within a transaction" hatası ve `db.rollback()` (1554-1557) ile **eşzamanlı yazının yarım txn'inin geri alınması** (mesaj satırı + FTS yetimi) mümkün, ayrıca rollup o gün atlanıyor — kural 5 ihlali — Öneri: rollup'u `_write_lock` içine al ve BEGIN IMMEDIATE'i kaldır (veya rollup'a autocommit ayrı bağlantı ver).

`[ÖNEMLİ: Orta] db.py:3257-3267` — `search_memories` (her sohbet mesajında çağrılıyor) kilitsiz `UPDATE memories ...` yapıp **şartsız `_commit_with_retry`** çağırıyor; bu, fonksiyonun kendi yorumundaki uyarıyla (db.py:3226-3227, backfill nedeniyle ayrı bağlantı açılmış) çelişiyor → paylaşılan bağlantının başka görevin henüz bitmemiş transaction'ını commit'leyebilir (kural 5 ihlali; crash'te mesaj FTS/sessions satırlarından önce commit edilip drift yaratır) — Öneri: erişim-sayaç yazımını da write-lock içine al veya ayrı bağlantıya taşı.

`[ÖNEMLİ: Orta] db.py:2241-2276` — `upsert_sync_items` kilitsiz çok cümleli yazım (kural 5 ihlali) ve doküman "newer updated_at overwrites" (2242-2243) dese de `ON CONFLICT ... DO UPDATE` koşulsuz → gecikmeli eski cihaz yazısı yeni veriyi ezebiliyor, LWW yok; ayrıca `updated_at` serbest metin (ör. routers/chat.py:911) olduğu için `since` karşılaştırması leksikografik ve güvenilmez — Öneri: `WHERE excluded.updated_at > sync_items.updated_at` ekle ve yazımı `_write_lock` içine al.

`[ÖNEMLİ: Orta] db.py:883, 920, 936, 990, 1051, 1246, 1331, 1371, 1395, 2375, 2679, 3098, 3131, 3172, 3291` — write-lock disiplini tutarsız: kilitsiz yazarlar (lock alanlara karşılaştır: 1668, 1720, 1748, 1867, 1904, 2074, 2133, 2190, 2326, 2511, 2567, 2763) `_commit_with_retry` ile başkasının açık transaction'ını erken commit'leyebiliyor → kural 5 sistemik olarak yarım uygulanmış — Öneri: tek cümleli yazım olsa bile kilitsiz `commit` yasağı koy; her yazıcı ya lock alsın ya kendi bağlantısını kullansın.

`[ÖNEMLİ: Orta] db.py:526-539` — `sync_items` (2026-09-06'da eklendi; NOTES.md:546 kuralı 2026-09-05) `updated_at` ✓ ve `deleted` ✓ var ama **device origin kolonu yok** → doğrudan TECHNİK UYARI aykırılığı — Öneri: `origin TEXT DEFAULT ''` kolonunu MIGRATIONS'a sıralı ekle ve mevcut satırları `legacy` ile işaretle.

`[ÖNEMLİ: Orta] db.py:306-450` — 2026-09-05 kuralından sonra eklenen yedi tablo (`users`, `user_api_keys`, `user_sessions`, `user_settings`, `feedback_votes`, `pattern_approvals`, `user_credentials`) kurala uymuyor: hiçbirisinde `deleted`/origin yok, dördünde (`users`, `user_api_keys`, `user_sessions`, `feedback_votes`, `pattern_approvals`) `updated_at` de yok — Öneri: auth-only tablolar için NOTES'a istisna yaz, senkron adayı kalanlara `updated_at`/`deleted` ekle.

---

## 4) İYİLEŞTİRME (yarış, N+1, indeks, veri güvenliği)

`[ÖNEMLİ: Orta] db.py:1722, 1755, 1881` — FTS external-content "malformed" quirk koruması yalnızca iki yolda (610-617 dedupe, 2769-2776 user delete), oysa `delete_last_assistant`/`delete_branch`/`clear_history` FTS DELETE'leri korumasız → `save_message` FTS insert'i best-effort yutulmuşsa (1681-1683) regenerate/clear legacy DB'de 500 fırlatabilir (kural 7 yarım) — Öneri: üç yola da aynı non-fatal try/except'i ekle.

`[ÖNEMLİ: Orta] db.py:452-469 + 1843-1849` — `conversations` için `user_id` indeksi yok (`idx_conversations_session(session_id, timestamp)` ve partial `client_key` indeksi `WHERE user_id=?` koşulunu karşılamıyor), `get_all_history` tam tablo taraması yapıyor ve retention default `0` (config.py:206) yani tablo sınırsız büyüyor; ayrıca `tool_audit_log(user_id)` ve `feedback_votes(user_id)` indeksleri eksik — Öneri: `(user_id)`, `(session_id, user_id, id)`, `tool_audit_log(user_id)`, `feedback_votes(user_id)` indekslerini MIGRATIONS'a ekle.

`[ÖNEMLİ: Orta] db.py:1293-1324 + 1117-1143` — `get_review_queue` her imza için `get_pattern_decision`, her grup için `get_pattern_support`, her seçmen için `user_reputation` çağırıyor ve `user_reputation` her çağrıda tüm `feedback_votes` satırlarını yüklüyor → admin kuyruğu quadratik N+1, kalabalık kurulumda kilitli DB süresi uzuyor — Öneri: oyları tek sorguda çek ve itirazları Python'da tek geçişte hesapla.

`[ÖNEMLİ: Orta] corpus_feeder.py:66-72, 86-99, 108-111` — `_save_state`/`_append_jsonl` atomik değil (tmp+`os.replace` yok) ve `_load_jsonl` hatayı yutuyor: tek yarım satır (crash anında yazılan) `json.loads`'u patlatıp feeder'ı kalıcı kırabiliyor, state.json da aynı riski taşıyor — Öneri: yazım tmp+`os.replace` ile atomik yap, okumada satır-bazlı try/except ile bozuk satırı atla ve logla.

`[ÖNEMLİ: Düşük] db.py:3146-3154, 3187-3203` — `save_memory` ve `search_memories` kullanıcının tüm embedding'lerini yükleyip Python'da cosinüs benzerliği hesaplıyor (her sohbet mesajında O(n) tarama) → bellek sayısı arttıkça TTFT'yi yer — Öneri: sonuç önbelleği veya ön-filtre (önem skoru/son erişim) ile aday sayısını daralt.

`[ÖNEMLİ: Düşük] db.py:1911-1916` — `import_messages` kilit içinde mesaj başına `SELECT` + `INSERT` atıyor (2N sorgu); `idx_conversations_client_key` UNIQUE'i zaten var ve 1931-1936'daki UNIQUE ihlali idempotent yutuyor → SELECT gereksiz — Öneri: SELECT'i at, kilit içindeki süreyi yarıya indir.

`[ÖNEMLİ: Düşük] db.py:3025-3034` — `_repair_summary_boundaries` her delete yolunda tüm `sessions` tablosunu (2 tam tablo UPDATE'i) dolaşıyor ve `delete_last_assistant` her regenerate'te bunu tetikliyor — Öneri: onarımı yalnızca ilgili `session_id` için çalıştır.

`[ÖNEMLİ: Düşük] tests/test_user_isolation.py:129-144, 329-334 + tests/test_embedding_resilience.py:7-27` — kural 2'nin iki yönlü test şartı FTS yolu için sağlanmamış (arama testleri farklı session_id'ler kullanıyor, paylaşımı kapsıyor değil; bu yüzden A-madde sızıntısı görünmüyor) ve breaker testi yalnızca istisna yolunu deniyor, asılı indirme senaryosu yok — Öneri: aynı session_id'yi iki kullanıcıyla deneyen FTS testi ve zaman aşımında breaker'ın açıldığı asılı yükleme testini ekle.

---

## 5) KORUNMUŞ / DOĞRU BULUNANLAR

`[ÖNEMLİ: Düşük] db.py:221-242, 2006-2011, 1973` — SQL enjeksiyonu ve LIKE escape düzgün: tüm f-string'ler sabit kolon/`?` placeholder, `_safe_ident`/`_safe_ddl_definition` DDL metacharacter reddi, `LIKE ... ESCAPE '\'` ve FTS terimlerinin `[^\w\s]` temizliği yerinde.

`[ÖNEMLİ: Düşük] db.py:255-258, 212, 569-577` — migration disiplini doğru: sıralı `MIGRATIONS` + `PRAGMA user_version`, "duplicate column" toleransı sayesinde crash sonrası idempotent, `_DATA_BACKFILLS[21]` `users.is_approved` indeksini dolduruyor, FTS drift kontrolü + `rebuild` çalışıyor.

`[ÖNEMLİ: Düşük] tests/conftest.py:68 + db.py:1659-1668, 26, 728, 745` — kural 1 (testler canlı DB'ye dokunmaz) autouse tmp-DB fixture ile korunuyor; yazma bütünlüğü tarafında embed kilit dışında (kilit tutulmuyor), `_commit_with_retry`/`lastrowid` cursor üzerinden, backup atomic `os.replace` + 0600/0700, `os.umask(0o077)` + `_secure_db_files` yerinde.

`[ÖNEMLİ: Düşük] retrieval.py:19, 56-59, 129` — retrieval yolu iyi kurgulu: 1500 ms `TIME_BUDGET_MS` bütçesi, tüm sorgularda `user_id` filtresi, recall `RECENT_WINDOW`/`TOP_K`/`SIM_THRESHOLD` tek yerde toplanmış.

---

**Toplam: 30 bulgu** — Yüksek 3, Orta 20, Düşük 7 (+2 bilinen-bug doğrulaması, +4 korunmuş gözlem). Salt okuma: hiçbir dosyada değişiklik yapılmadı.
