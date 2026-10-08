## piSynapse LLM Pipeline — Satır Satır Salt-Okuma Raporu

Kapsam: `llm/{chat,stream,intent,payload,utils}.py`, `prompt.py`, `routers/chat.py`, `retrieval.py`, `embedding.py`, `messages.py`, `litert_serve/server.py`, `static/{sw.js,ui.js}` (kod tarafı). Hiçbir dosya değiştirilmedi.

**Önce kural uyumları (doğrulandı):** WebSocket/yok (repo genelinde 0 eşleşme, kural 1 ✓) · `LLM_BACKEND=litert` aktif, ollama dalları pasif (kural 2 ✓) · loop guard'lar yerinde: `MAX_IDENTICAL_EXECUTIONS=2` (utils:118, create_*/send_email=1), finalize nudge, empty fallback, `strip_tool_leaks`, `allowed_names` reddi ✓ · escalation tek atımlık + single-group (stream:456-475, utils:344-390) ✓ · `request.state.user_id` (main:576) ✓ · `expected_until` + `FOLD_MAX_MESSAGES=30` (db:3008,3099-3123) ✓ · keepalive 15 sn (chat router:21,375) + UI `data:` dışı satır atlıyor (ui.js:2132) ✓ · reasoning olayı akış başlatıyor (chat router:411) + abort round/tool bazlı (stream:288,568) ✓.

---

### 1. GÜVENLİK

`[ÖNEMLİ: Yüksek] llm/stream.py:512-516,561-562` — Düz metinden `parse_leaked_tool_call` ile çıkarılan araç çağrısı, `allowed_names` `None` olduğu için (araçların kapalı olduğu saf-sohbet ve final-nudge turları) "hallüsinasyon reddi" guard'ı bypass edilip **çalıştırılıyor**; `create_note/create_task/create_calendar_event/save_memory` `CONFIRM_TOOLS` içinde olmadığından onay kartı da beklemez → e-posta/not gibi dış içerik "call:create_note{...}" içerip model alıntıladığında araç çalıştırma (prompt-injection gadget) — Öneri: `use_tools=False` iken leaked-call kurtarmayı kapat (yalnız escalation'a yönlendir) ve `allowed_names`'i boş küme say.

`[ÖNEMLİ: Yüksek] llm/intent.py:701-740 (732)` — LLM niyet fallback'i/Layer-1 kanıtlı çözümleme `client.post`'u **zaman aşımısız** çağırıyor; paylaşılan client `LLM_TIMEOUT=600` (config:106) kullanıyor → bahsedilen **10 sn'lik P3 guard'ı KODDA YOK** (yorum satırı:684 "adds ~15s delay" diyor, gerçek rakam 600 sn) — Öneri: `asyncio.wait_for(..., timeout=10)` ekle, yoksa `INTENT_LLM_FALLBACK=on` + taşma durumunda akış hiç başlamaz.

`[ÖNEMLİ: Yüksek] embedding.py:22-43` + `db.py:1664`, `routers/chat.py:154`, `intent.py:475,641` — Bilinen "model hiç yüklenmiyor" bug'ının devamı: `_model_lock` indirme sırasında **tutuluyor**, sarkma (0% takılma) exception üretmediği için circuit breaker **tri'e geçmiyor**; `save_message`/intent/memory embed'lerinde `asyncio.wait_for` **yok** (yalnız `retrieval.py:129` var) → bir sarkmış indirme tüm embed çağıran işleri askıya alır, SSE hiç başlamaz (504) — Öneri: embed çağrılarını 5-10 sn ile sınırla, timeout'u da `_model_error_ts`'e yaz.

`[ÖNEMLİ: Orta] config.py:20` + `embedding.py:8-12` — `HF_HUB_DOWNLOAD_TIMEOUT=30` **kodda mevcut** (`os.environ.setdefault`); ama `embedding.py` `fastembed`'i (satır 8) config'den (satır 12) önce import ettiği için env değişkeni geç geçerli olabilir (sunucu yolunda `main.py:17` config'i önce import ettiği için etkili). **Hüküm: yeterli değil** — yalnız HTTP fazı sınırı, sarkma + kilit senaryosuna çare değil (yukarıdaki madde).

`[ÖNEMLİ: Orta] llm/chat.py:124-138` — `_summary_transcript` yalnız asistan sızıntılarını temizliyor; kullanıcı mesajı sahte `assistant: ...` satırları yazıp transkripti zehirleyebilir, özet de `prompt.py:206` üzerinden SYSTEM promptuna kalıcı enjekte olur (çıkışta yalnız `strip_tool_leaks` var, chat.py:176) — Öneri: rol ayrımını kaçışlı formatla (fence/JSONL) kur ve özet bloğunu UNTRUSTED işaretiyle sar.

`[ÖNEMLİ: Orta] prompt.py:54` vs `prompt.py:199` — Kural "emails, calendar, notes" içeriğinin işaretli olduğunu söylüyor; oysa **sadece e-posta** `--- BEGIN UNTRUSTED ---` ile sarılıyor, not/görev/takvim işaretsiz geliyor → prompt kuralı ↔ kod uyuşmazlığı — Öneri: kuralı e-postayla sınırla ya da araç sonuçlarını da marker'la sar.

`[ÖNEMLİ: Düşük] routers/chat.py:462-470` + `:67` — `/chat/abort/{session_id}` kullanıcı kapsamı yok (`_validate_session_id` dışında kontrol yok), `_abort_events` yalnız `session_id` ile anahtarlanıyor; oturum kimliğini bilen başka kullanıcı başkasının akışını durdurabilir (kural 5 ruhuna aykırı) — Öneri: `_uid(request)` ile eşleştir.

`[ÖNEMLİ: Düşük] static/sw.js:40-41,61-73` + `main.py:656` — SW yalnız `/chat`,`/config`,`/widget`,`/health`'i hariç tutuyor; **`/users/*`, `/tools/*` gibi GET'ler stale-while-revalidate ile önbellekleniyor** ve `/static` mount'unda `Cache-Control` yok → refresh sonrası bayat shell/API yanıtı (bilinen "post-refresh login" bug'ının en güçlü backend/SW şüphelisi; cookie tarafı sağlam: httponly, samesite=lax, path=/, users.py:24-27) — Öneri: API yollarını SW'den çıkar + html/js'e `no-cache` ver.

---

### 2. TUTARSIZLIK (chat.py ↔ stream.py, prompt ↔ kod, i18n)

`[ÖNEMLİ: Orta] llm/stream.py:545` vs `llm/chat.py:327` — Dedup guard'ı stream'de tüm metin yerine yalnız boşaltılmış `buf`'a bakıyor (`not buf.strip()`), chat `raw_content`'e bakıyor: ≥8 karakter metin üretilmiş ve akıtılmış olsa bile stream yanlışlıkla finalize-nudge turu atıyor; nudge turu da aynı çağrıya düşerse **gerçek metnin sonuna** `empty_answer_fallback` ekleniyor — Öneri: `full_text.strip()` kullan (chat ile aynı semantik).

`[ÖNEMLİ: Orta] llm/stream.py:519-526,426-431,456-475` + `routers/chat.py:393,420-424` + `static/ui.js:2214-2217` — `gen_retry` (truncation/overflow/escalation/tool_leak) sonrası `reply_parts` ve UI `fullText` **temizlenmiyor**, kısmi metin de modele geri beslenmiyor → kullanıcıya ve DB'ye "kısmi liste + baştan üretilen tam liste" gibi mükerrer yanıt yazılır — Öneri: `gen_retry` yayınlandığında birikmiş token'ları geri çek (router'da `reply_parts=[]`, UI'da `fullText=''`) veya kısmi metni tekrar turuna ekle.

`[ÖNEMLİ: Orta] llm/stream.py:477` vs `llm/chat.py:282` — Think-mode yeniden deneme stream'de `iteration == 0` şartına bağlı değil → 5 tura kadar ekstra tam boyutlu non-stream LLM çağrısı (token/zaman israfı, parite farkı) — Öneri: stream'e de tek seferlik bayrak/`iteration==0` ekle.

`[ÖNEMLİ: Orta] llm/stream.py:485-500` ve `llm/chat.py:284-289` — Think-retry payload'ları `trim_messages_for_context`'ten geçirilmiyor (taşma riski) ve `_TOOL_ASK_HINT` yeniden enjekte edilmiyor → "araçların yok" bilgisi kayboluyor (1. maddedeki bypass yolunu açıyor) — Öneri: retry'yi normal tur gibi trim+hint ile kur.

`[ÖNEMLİ: Orta] llm/chat.py:262-264` (+ genel non-stream) — Non-stream'de truncation-retry, overflow-retry/`_shrink_tool_responses`, litert parse-recovery, `parse_leaked_tool_call` ve abort **yok**; ayrıca her hata türü (400 taşma dahil) `llm_unreachable` ("motora ulaşılamıyor") olarak yanlış etiketleniyor — Öneri: kurtarma mantığını ortak yardımcıya taşı, hata türünü ayırt et.

`[ÖNEMLİ: Orta] prompt.py:37,40-45` vs `llm/utils.py:319-324` — Saf-sohbet turunda sistem promptu hâlâ tüm araçları listeliyor ve "call the tool immediately" derken eklenen hint "You currently have NO tools available" diyor → çelişkili talimat, guard'lanmak istenen spurious `TOOL_NEEDED`/escalation gürültüsünü besliyor — Öneri: saf-sohbet varyantında `Available tools:` satırı ve kural 1-5'i kaldır.

`[ÖNEMLİ: Orta] llm/chat.py:482`, `llm/chat.py:412,417`, `llm/stream.py:655,662` — Sabit İngilizce kullanıcıya dönen string'ler: max-iteration mesajı, `[Rejected: 'x' is NOT available...]`, `validate_confirm_params` hataları (`definitions.py:471`) — kural 6'ya aykırı (UI bunları çevirmiyor) — Öneri: `messages.py`'ye key'ler ekle, model-facing metni kullanıcı-facing metinden ayır.

`[ÖNEMLİ: Düşük] llm/stream.py:302,424,434,444` — Hata metinleri sabit İngilizce; UI yalnız `connection error` ve `context too long`'u regex'le yerelleştiriyor (ui.js:2226-2229), "Internal error while preparing..." eşlenmiyor — Öneri: katalog key'ine taşı.

`[ÖNEMLİ: Düşük] llm/utils.py:23-25` — `EMPTY_ANSWER_FALLBACK` sabit Türkçe metni üretimde ölü (yalnız test karşılaştırması kullanıyor; üretim `empty_answer_fallback()`→katalog çağırıyor) — Öneri: sabiti kaldır.

`[ÖNEMLİ: Düşük] llm/chat.py:395` vs `llm/stream.py:635` — Non-stream `run_verification` dönüşünü yok sayıyor, router'da `link_audits_to_message` hiç çağrılmıyor → 👍/👎 ve düzeltme verisi non-stream turlarda mesaja bağlanamıyor — Öneri: audit_id'yi döndür ve bağla.

`[ÖNEMLİ: Düşük] llm/stream.py:450-451` vs `llm/chat.py:298-300` — Round sonu escalate kontrolünde `_bare_tool_name` yok (chat'de var); pratikte token seviyesinde yakalanıyor ama denge bozuk — Öneri: chat ile aynı üçlü şart.

`[ÖNEMLİ: Düşük] llm/stream.py:626` — `tool:start` olayındaki `max` her zaman `MAX_IDENTICAL_EXECUTIONS` (2) bildiriyor; oysa `create_*`/`send_email` için `max_exec=1` (satır 582) → UI "1/2" gösteriyor — Öneri: `max: max_exec`.

`[ÖNEMLİ: Düşük] routers/chat.py:289` — Sanitizasyondan sonra boş kalan yanıtta `result["reply"]` **ham** olarak istemciye döndürülüyor (`reply_text or result["reply"]`) — Öneri: boşsa katalog fallback'i ver.

---

### 3. DEĞİŞİKLİK GEREKSİNİMİ (NOTES'e aykırılık / bilinen bug bağlantısı)

`[ÖNEMLİ: Yüksek] routers/chat.py:314-341` — SSE response döndürülmeden **önce** tüm kurulum (`save_message`→embed, niyet, memory, retrieval, opsiyonel LLM çözümleme) çalışır; keepalive ping ancak `generate()` içinde (satır 375) başladığından bu fazdaki her takılma **hiçbir bayt gönderilmeden** proxy 504'e yol açar → NOTES 2026-10-05 "model never loads / churn" vakasıyla doğrudan bağlantılı — Öneri: kuruluma üst sınır (ör. 8-10 sn `wait_for`) ve embed çağrılarına kısa timeout koy.

`[ÖNEMLİ: Orta] llm/intent.py:687-695,866` — `INTENT_LLM_FALLBACK` default `off` (config:192) → **şu an kapalı risk**; açılırsa ek madde 2'deki 600 sn'lik kurulum-fazı bloğu devreye girer. P3 "timeout guard" **hâlâ implement edilmemiş** — Öneri: guard'ı yazmadan bu seçeneği açma.

`[ÖNEMLİ: Orta] routers/chat.py:237-239,310-312` — Oturum limiti (20/dk) kurulum başında tüketiliyor; başarısız/kopan istekler bütçeyi harcıyor ve 429'da `Retry-After` yok (genel limitte var, main:598) → bağlantı dalgalanmasında tekrarlanan 429 döngüsü; NOTES'teki "duplicate window'a girip takılma" davranışıyla uyumlu — Öneri: `Retry-After` ekle ve/veya limiti ilk başarılı byte'ta tüket.

`[ÖNEMLİ: Düşük] litert_serve/server.py:457-474` + `llm/payload.py:78-79` — `conversation_cache_max>0` iken istemci her turda tam geçmişi gönderirken sunucu eski conversation'ı yeniden kullanıp prelude'u/yeni araç setini yok sayar → escalation ve hint kaldırma sunucu tarafında etkisiz (varsayılan `0`, latent) — Öneri: araç listesi/prelude değiştiğinde cache'i invalidate et.

---

### 4. İYİLEŞTİRME (yarış / israf / hata yutma / event-loop)

`[ÖNEMLİ: Orta] llm/stream.py:91-94` + `:437-453,518-534` — `SSE_READ_IDLE_TIMEOUT` (300 sn) sonunda **hatayı `break` ile yutuyor**; `full_text` boşsa akış sessizce `done` ile kapanıyor → kullanıcı "boş yanıt" görüyor, motor zaman aşımı yalnız log'da — Öneri: idle timeout'ta `{"error": ...}` üret.

`[ÖNEMLİ: Orta] embedding.py:36-43` — İndirme `_model_lock` altında senkron yapıldığı için bekleyen her çağıran bir `asyncio.to_thread` worker'ını meşgul ediyor; havuz dolunca takvim/takvim-preview/başlık gibi diğer `to_thread` işleri de kilitlenir (event-loop dolaylı bloke) — Öneri: kilidi yalnız model atamasında tut, indirmeyi kilitsiz/tek-görevli yap.

`[ÖNEMLİ: Düşük] llm/intent.py:505-513` — Docstring "fire-and-forget … never delays routing" derken `await log_intent_audit(...)` ile her sınıflandırmada DB yazımı **bekletiliyor** (kurulum fazında ek gecikme) — Öneri: `asyncio.create_task` ile gerçekten async yap veya docstring'i düzelt.

`[ÖNEMLİ: Düşük] llm/utils.py:274-285` — Tek değerli `httpx.Timeout(LLM_TIMEOUT)` **connect** fazını da 600 sn'ye açıyor → ölü backend/siyah delikte 10 dk asılı kalma — Öneri: `httpx.Timeout(connect=10, read=LLM_TIMEOUT, ...)`.

`[ÖNEMLİ: Düşük] llm/stream.py:307,533,732` — `full_reasoning` her turda sıfırlanıyor; `done` yalnız **son** turun reasoning'ini taşıyor → önceki turların düşüncesini DB/ekran hiç görmüyor — Öneri: turlar arasında biriktir, `done`'da birleştir.

`[ÖNEMLİ: Düşük] llm/payload.py:176-181` — `FINALIZE_NUDGE` yeni "son user mesajı" olduğu için `mandatory` yalnız nudu kapsar; önceki asistan+tool üçlüleri kırpılabilir → nudge'in "sonuç yukarıda" iddiası geçersizleşip boş cevap/fallback üretir (uzun geçmişte) — Öneri: nudge'i user rolüyle değil tool/assistant olarak ekle veya tool üçlülerini zorunlu tut.

`[ÖNEMLİ: Düşük] llm/payload.py:263-272` — `_normalize_messages_for_backend` `fn["arguments"]` dict'ini **yerinde** string'e çevirerek paylaşılan mesaj nesnelerini değiştiriyor (çok turlu/çok çağrılu istekte yan etki riski) — Öneri: kopya üzerinde dönüştür.

`[ÖNEMLİ: Düşük] routers/chat.py:90-95` — `_uid` hiçbir yerde `HTTPException` yutup `"default"`'a düşüyor; chat uçları middleware sayesinde bunu tetiklemiyor ama tetiklerse istemci verisi "default" kullanıcısına yazılır (kural 5'nin sessiz istisnası) — Öneri: chat uçlarında sessiz fallback yerine 401 fırlat.

---

### Bilinen 3 bug — hüküm

1. **Embedding circuit breaker + `HF_HUB_DOWNLOAD_TIMEOUT=30`:** kodda doğrulandı (`embedding.py:33-34`, `config.py:20`) ama **yetersiz** — breaker yalnız exception'da tri'e geçiyor, sarkma/dönemsel takılma senaryosunda kilit ve timeout'suz `embed_async` çağrıları (db:1664, chat router:154, intent:475/641) akışı yine kilitleyebiliyor; ek madde 25'teki "SSE öncesi kurulum fazı" da 504'ü açıklıyor.
2. **LLM fallback 10 sn timeout guard (P3):** **YOK / pending** — `intent.py:732` doğrudan 600 sn'lik client'a bağlı; yalnız `INTENT_LLM_FALLBACK=off` olduğu için şu an görünmüyor.
3. **Post-refresh login:** cookie/middleware tarafı sağlam (users.py:24-27, main:555-577); asıl backend/ayar şüphelisi `static/sw.js:40-41,61-73` (API GET'lerinin önbelleklenmesi) + `main.py:656` (`/static` için `Cache-Control` yok) — madde 8.
