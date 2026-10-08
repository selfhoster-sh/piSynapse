# TOOLS & ROUTERS KATMANI DENETİM RAPORU (32 BULGU)

[ÖNEMLİ: Yüksek] nextcloud_tasks.py:59 — `_get_task_calendar()` önbellek kontrolü credential kapısından önce gelir: `_task_calendar` bir kez ısındıktan sonra NC_CREDS/NC_SHARED_OK hiç sorgulanmadan döner, yani 2026-09-27'de kapatılan delik bu yoldan tamamen geri açılır (kişisel cred'si/hiç cred'si olmayan herkes admin'in görev listesini okuyup complete/delete edebilir) — `if _task_calendar is not None` bloğunu `_get_dav_client()` kapısının altına taşı.

[ÖNEMLİ: Yüksek] calendar_ops.py:87 — `_get_primary_calendar(client)` global `_dav_calendar`'ı client'tan bağımsız cache'ler; kullanıcı A'nın kişisel CalDAV oturumundan dönen nesne sıradaki kullanıcıya (admin dahil) aynen iade edilir, böylece kullanıcı B'nin delete_event/update_event'i A'nın event nesnesi üzerinde çalışır — cache'i client kimliğine göre key'le veya client değişince invalidasyon yap.

[ÖNEMLİ: Yüksek] calendar_ops.py:141 — `_find_events_cache` 5 sn boyunca global ve kullanıcı anahtarasız saklanır; delete_event (:441) / update_event (:462) bu cache üzerinden eşleşip `ev.delete()`/`ev.save()` yaptığı için kullanıcılar birbirinin etkinliğini silebilir/güncelleyebilir — cache anahtarına kullanıcı veya credential kimliği ekle.

[ÖNEMLİ: Yüksek] embedding.py:38 + db.py:1664 — bilinen "model yüklenmiyor → intent classification takılıyor" bug'ının kök nedeni: circuit breaker yalnızca `TextEmbedding(...)` raise ettiği için devreye girer (:41), model indirmesi asılı kalırsa `_model_lock` (:25) sonsuza dek tutulur ve `_model_error_ts` hiç yazılmaz; `embed_async` (`embedding.py:53-57`) sadece `asyncio.to_thread` olup hiçbir yerde `wait_for` yok, `chat.py:245` ayrıca gather'dan önce tek başına bekler — indirmeye 10-30 sn bütçe koy, asılı kalma sayacını da breaker'a ekle.

[ÖNEMLİ: Orta] nextcloud_tasks.py:207 — `_todos_cache` yalnız `include_completed` bayrağına göre key'lenir (kullanıcı/credential yok), 30 sn içinde kullanıcı A'nın görev listesi kullanıcı B'ye servis edilir — cache'e (creds veya user_id) ek anahtar ekle.

[ÖNEMLİ: Orta] routers/widgets.py:41 — `/widget/calendar` hiçbir yerde NC_CREDS/NC_SHARED_OK set etmez (set eden tek yer dispatcher.py:161-163), dolayısıyla `list_events_today → _get_calendar` daima "credentials missing" fırlatır ve calendar_ops.py:313 bunu `[]`'e yutar; widget 2026-09-27 fix'inden beri herkes için boş döner ve endpoint'te `_uid`/owner guard hiç yok — widget'ı kimlik bağlayıp owner-scoped hale getir.

[ÖNEMLİ: Orta] routers/chat.py:463 — `abort_generation` endpoint'inde `Request`/`_uid`/`current_user` hiç yok (fonksiyon imzası sadece `session_id`), herhangi bir authenticated kullanıcı bildiği session_id ile başkasının üretimini durdurabilir (kural 1 aykırılığı) — `uid = current_user(request)` + oturum sahipliği kontrolü ekle.

[ÖNEMLİ: Orta] routers/chat.py:729 — `/chat/reload-corpus` auth guard'sız (ne `_uid` ne `request` parametresi ne `require_admin`) ve global embedding corpus cache'ini sıfırlar; sıradan kullanıcı admin-seviye cache thrash'i tetikleyebilir — `require_admin(request)` ile gate'le.

[ÖNEMLİ: Orta] mail.py:42 / mail.py:111 / tools/dispatcher.py:506 — IMAP `mailbox` parametresi hiç sanitize edilmiyor, `imaplib.IMAP4._command` argümanları satır sonuyla ham birleştirir (CPython kaynağı ile doğrulandı) → `mailbox="INBOX\r\nA002 ..."` ile IMAP komut satırı enjeksiyonu mümkün — `mailbox`'ı INBOX/Sent/Trash gibi allowlist'inden geçir.

[ÖNEMLİ: Orta] tools/dispatcher.py:488 ↔ :950 — `/execute` ve `/sync` context'ine `_user_text` ve `_origin` hiç basılmaz; CLARIFY mesajlarındaki dil anchor'u (`The user's original message: "..."`, dispatcher :192/:338/:418/:541) bu yolda boş kalır ve chip guard'ları devre dışı kalır (kural 4 aykırılığı) — context'e `"_user_text": req.message, "_origin": req.origin` ekle.

[ÖNEMLİ: Orta] calendar_ops.py:445 / :467 — belirsiz eşleşme sonucu hiçbir prefix taşımaz (`"'X' matches multiple events..."`), dolayısıyla `is_tool_success` (dispatcher.py:43-44) bunu başarılı sayar (kural 6 aykırılığı); ayrıca mesaj "use the event UID" derken kural 7 gereği model yalnız sıra numarası kullanır — `"ERROR: "` prefix'i + "list number" ifadesi kullan.

[ÖNEMLİ: Orta] calendar_ops.py:442, :449, :464, :471 — hedef bulunamayınca `ERROR:` dönülür; buna karşılık notes/tasks aynı durumda `NOOP:` döndürür (nextcloud_notes.py:322, :341, :343; nextcloud_tasks.py:281, :303) → kural 6'nın NOOP disiplini takvimde uygulanmamış, denetimde "bulunamadı" hata olarak sayılır — bulamama durumlarını `NOOP:`'e çevir.

[ÖNEMLİ: Orta] tools/definitions.py:448 ↔ :105, :121 — `CONFIRM_TOOLS` içinde olan `delete_calendar_event` ve `update_calendar_event`'in şema açıklamasında "Requires user confirmation" yok; buna karşılık send_email (:183), delete_note (:302), complete_task (:363), delete_task (:377) bunu açıkça yazar → model onay diyaloğunu beklemediği için turu "işlem yapıldı" sanabilir — iki açıklamaya onay cümlesini ekle.

[ÖNEMLİ: Orta] tools/definitions.py:82 ↔ tools/dispatcher.py:185-192 — `create_calendar_event` şemada zorunlu tek parametre `summary` iken dispatcher `start_time` yoksa CLARIFY_REQUIRED döndürür (aynı şekilde create_note :254 ↔ dispatcher :335-341 `content` istiyor) → şema ile handler uyuşmadığı için her turda gereksiz clarify turu üretir — şemayı `required` alanlarıyla hizala.

[ÖNEMLİ: Orta] nextcloud_tasks.py:362, :370, :378 — kural 8 (30 sn bütçe) yalnız `list_tasks`'ta uygulanmış (:354), `complete_task`/`delete_task`/`search_tasks` içlerinde `cal.todos()` read'i varken `asyncio.to_thread` ile sınırsız çalışır — hepsine `wait_for(..., 30)` sarmalayıcı koy.

[ÖNEMLİ: Orta] nextcloud_notes.py:229, :263, :359 — `list_notes`/`get_note`/`search_notes` read yollarının hiçbirinde zaman bütçesi yok (`list_notes` 200 sayfalama x timeout'a kadar gidebilir), kural 8'in tool bazlı 30 sn kuralı bu dosyada uygulanmamış — tüm read çağrılarını 30 sn `wait_for` içine al.

[ÖNEMLİ: Orta] routers/chat.py:921 — `/chat/sync` komut listesinde boyut/kota yok: tek 30 rpm'lik istekte N tane CalDAV/IMAP/DB işlemi çalışır, kural 9 rate limit'i fiilen aşan bir çarpan üretir (session limiter sync'te hiç çağrılmıyor, sadece :237 ve :310) — komut başına da limiter veya batch cap uygula.

[ÖNEMLİ: Orta] tool_verification.py:178, :184, :197, :203, :276, :304 — her mutasyon sonrası doğrulama tam listeleme çağırır (`list_events(30)`, `list_notes()` tüm sayfalama, `list_tasks`) → yazma başına ikinci tam backend taraması (N+1 benzeri, CalDAV/NC yükü 2x ve list_events çağrılarını 5 sn'lik global cache'e takar) — doğrulamayı entity-id'li tek nokta okumaya indir.

[ÖNEMLİ: Orta] tools/dispatcher.py:498-499 — `get_user(user_id)` None döndürürse (silinmiş veya kimliği çözülemeyen kullanıcı) akış paylaşılan admin mailboxes'a düşer; kontrol yalnız `caller is not None and not caller.get("is_admin")` olduğundan `caller is None` tamamen geçer — `caller is None` durumunu da reddet.

[ÖNEMLİ: Orta] routers/config.py:104 ↔ :66 — `GET /config` model/llm_backend/stt/tts motorunu `request` parametresi olmadan tüm authenticated kullanıcılara açarken `GET /config/settings` aynı bilgiyi non-admin'den gizliyor (`if not is_admin and key not in PERSONAL_KEYS: continue`) → router parite aykırılığı — `get_config`'e `request` verip admin filtresi uygula.

[ÖNEMLİ: Orta] routers/widgets.py:19 + weather.py:89, :137 — hava widget'ı ve `get_weather` tool'u `city or config.DEFAULT_CITY` ile global env'e düşer; oysa `DEFAULT_CITY` PERSONAL_KEYS (config.py:166) ve prompt/payload kişisel değeri okur (prompt.py:21, llm/payload.py:118), şema ise "Omit to use the user's default city" (definitions.py:54) der → kullanıcının şehri tool/widget'ta kaybolur — `effective_setting(user_id, "DEFAULT_CITY")` kullan.

[ÖNEMLİ: Orta] nextcloud_notes.py:161 — arama sorgusu yalnız `query.replace(" ", "+")` ile hazırlanır; `&`, `#`, `?` ve Türkçe karakterler URL'yi bozar, `except: pass` bunu sessiz fallback'e yutar (UnicodeEncodeError dahil) — `urllib.parse.quote` kullan.

[ÖNEMLİ: Orta] nextcloud_notes.py:34 — kişisel client'ta `creds.get("password") or NEXTCLOUD_PASSWORD` (ve user tarafı :33) eksik kişisel credential'i yarıda paylaşılan admin şifresiyle tamamlar → fail-open karışımı, kişisel hesap yanlış parolayla auth olabilir — alanlardan biri eksikse shared fallback'i kapat.

[ÖNEMLİ: Orta] tools/definitions.py:158, :207 — `list_emails` ve `search_emails` limit'i `min_value=1` ile alt sınır içeriyor ama üst sınır yok; `_list_emails` `mail_ids[-limit:]` ile 100k mail'i tek çağrıda çeker (mail.py:45) — `le=50` gibi bir tavan koy.

[ÖNEMLİ: Orta] routers/chat.py:462 (abort) / :728 (reload-corpus) / :828 (upload) — bu üç endpoint'in hiçbiri `_uid` çağırmıyor: auth middleware'den geçiyorlar ama sahiplik/admin guard'ı yok (upload'ta sahiplik gerekmiyor, ikisinde gerekli) — her birine `request: Request` + `_uid`/`require_admin` ekle.

[ÖNEMLİ: Orta] routers/chat.py:237 / :310 — `_session_limiter` yalnız `session_id` ile key'lenir: kullanıcı B, A'nın bilinen session_id'siyle 429 yedirebilir ve yeni `session_id` açarak limiterden sıyrılır (kural 9'daki 30 rpm ayağı sağlam, session bucket'ı ne sahiplik ne bypass engelliyor) — bucket'ı `user:{uid}:{session_id}` yap.

[ÖNEMLİ: Düşük] mail.py:93 — `subject` CRLF için doğrulanmaz; stdlib `HeaderParseError` fırlatarak enjeksiyonu engelliyor ama `mail.py:102` bunu "Failed to send."a yutuyor (gizlenen neden belirsiz kalır) — `subject/to/cc/bcc` için tek satırlık `\r`/`\n` kontrolü ekle.

[ÖNEMLİ: Düşük] routers/chat.py:85-95 — `_uid` 401'ı yutup `"default"`'a düşer (fail-open); bugünkü exempt listesinde router yok ama yeni eklenen herhangi bir muaf path sessizce "default" kullanıcısına yazabilir — 401'ı middleware'e geri taşı.

[ÖNEMLİ: Düşük] litert_serve/server.py:287-290 — `PISERVE_ADMIN_TOKEN` boşken admin endpoint'leri herkese açık ve karşılaştırma `==` (timing açığı); `host` config ile 0.0.0.0'a çekilebilir — token yoksa `/v1/admin/*`'i kapatan kilit + `hmac.compare_digest`.

[ÖNEMLİ: Düşük] litert_serve/server.py:366-367 — `Content-Length` üst sınırı olmadan kabul edilip `rfile.read(length)` ile okunur (loopback servis ama bellek tıkanması mümkün) — okuma için maksimum boyut koy.

[ÖNEMLİ: Düşük] litert_serve/server.py:389 — `_reload_event.wait()` zamansızdır; yeniden yükleme asılı kalırsa iş parçacığı sonsuza kadar bloke olur — `wait(timeout=...)` + timeout'ta 503 dön.

[ÖNEMLİ: Düşük] tools/dispatcher.py:153 — tool parametreleri INFO log'a yazılır ve `_mask_params_for_log` yalnız anahtar adını maskeler; `send_email` için `to/subject/body`, `notes`/`summary` içerikleri 200 karakter olduğu gibi kalır (PII log'a sızar) — `body/content/notes` anahtarlarını da redact et.

[ÖNEMLİ: Düşük] routers/chat.py:955 ↔ :499 — sync yolu `run_verification`'a `error=result` geçirmiyor (`error=None if success else result` execute'ta var, sync'te yok), başarısız audit satırları `success=0, error=NULL` yazılır — execute ile aynı argümanı ver.

[ÖNEMLİ: Düşük] db.py:1999 ↔ :2014 — `/chat/search` FTS yolunda ~100 karakterlik `snippet` dönerken LIKE fallback yolu ham `content`'i aynı anahtara koyar; yanıt şekli ve boyutu tutarsız — fallback'i de snippet'e kırp.

[ÖNEMLİ: Düşük/Şüpheli] config.py:177-178 — yorum "Enabled by default" derken kod `TRUST_X_FORWARDED_FOR`'u açık değil (`""` → False); ayrıca değişken açık olsa dahi `main.py:583` ilk IP'yi spoof'lanabilir şekilde okur — yorumu/kodu hizala ve proxy yoksa açık bırakma.
