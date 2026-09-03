# piSynapse — Tool-escalation / SSE Bug: Durum ve Kaldığımız Yer

Tarih: 2026-09-04 (orijinal teşhis: 2026-09-03)
Amaç: Bu dosya, bug'ın tam teşhisi, çözüm planı ve **uygulanan çözümün** tam
durumunu içerir. Farklı bir oturumda bu dosyayı okuyarak kaldığımız yerden devam
edebilirsin. **DURUM: Adım 1-2-3'ün tamamı tamamlandı, test edildi ve canlı
doğrulandı** (2026-09-04). Değişiklikler çalışma ağacında duruyor, **commit edilmedi**.

---

## ✅ SON DURUM ÖZETİ (2026-09-04)

Bug'ın kök nedeni (gereksiz tool-escalation) **çözüldü ve canlı doğrulandı**.
Yapılanlar özetle:

1. **Adım 1** — `_TOOL_ASK_HINT` sadece gerçek tool sinyali (keyword/`_hit_groups`
   dolu) varsa enjekte ediliyor; `hint_armed=False` iken escalation tamamen kapalı.
   → Saf sohbet ("uykum var ama uyuyamıyorum") artık asla gereksiz "GEREKLİ ARAÇLAR
   ETKİNLEŞTİRİLİYOR" üretmiyor.
2. **Adım 2** — escalation artık `combined (23 tool)` değil, ilgili **tek gruba**
   daralıyor (TTFT ~49s → ~13s); `combined` yalnız gerçek multi-domain isteklerde.
3. **Adım 3** — frontend `data.error` dalı artık her hatayı `connErr` ("Sunucuya
   ulaşılamadı") ile damgalamıyor; bağlantı vs. uygulama hatası ayrıştırıldı.

Test: tam suite **560 passed** (+3 yeni `_escalation_tools` birim testi), frontend
`node --check` geçti, canlı doğrulama başarılı. Detaylar için §8 kontrol listesine bak.

---

## 1. ÇÖZÜLECEK SORUN (belirtiler)

Kullanıcı sohbetteyken:
1. Gereksiz "GEREKLİ ARAÇLAR ETKİNLEŞTİRİLİYOR" (tool escalation) uyarısı çıkıyor.
2. Ardından "Sunucuya ulaşılamadı" hatası; retry ölü görünüyor.
3. Aynı session'da sonraki mesajlar da hemen başarısız; diğer session'lar çalışıyor.
4. Kullanıcı bu bug'ı D-EMB-UPGRADE migration'ından (768-dim, `b35bf64`, 2026-09-02)
   GÜNLER ÖNCE fark etmişti.

## 2. ASIL KÖK NEDEN (kanıtlandı — migration'dan bağımsız)

**Not: Bu, D-EMB-UPGRADE / 384/768 shape-mismatch ile İLGİSİZ.** İlk `Hatch escalating`
logu **2026-08-31 00:54** — yani 768-dim migration'dan (02 Eyl) 2 gün önce, tüm
embedding'ler 384-dim ve tek tipti. O dönem shape mismatch FİZİKSEL OLARAK İMKÂNSIZDI.

**Kök neden zinciri:**
1. `intent == "question"` ve `tool_group is None` olan her tura `_TOOL_ASK_HINT`
   sistemi-prompt'u enjekte ediliyordu (`llm/stream.py:321`).
2. Bu hint küçük modele "gereksinim tool gerektiriyorsa TOOL_NEEDED ile başla"
   diyor. Model saf sohbet sorusunda bile ("uykum var ama uyuyamıyorum") bunu
   gereksiz üretiyordu (tool-call hallucination).
3. `_wants_tools_hint` / `_check_tool_leak` / `_bare_tool_name` bu marker'ı yakalayıp
   Hatch'ı ateşliyor: `Hatch escalating: scope=combined (23 tools)` → TTFT ~49s.
4. `combined (23 tool)` ağır yükü + SSE kesilmesi → "Sunucuya ulaşılamadı".

**Migration öncesi log kanıtı (384-dim aktifken, 2026-08-31 00:54):**
```
00:54:16 Intent=question via LLM (raw='question')     ← sınıflandırma DOĞRU
00:54:16 Pure chat (question+None) — tools disabled    ← _TOOL_ASK_HINT enjekte edildi
00:54:44 Hatch armed — aborting pure-chat round        ← +28s sonra marker yakalandı
00:54:44 Hatch escalating: scope=combined (23 tools)
```

**Tarihsel bağlam (neden TOOL_NEEDED eklenmişti):** commit `1fdc11f` (2026-08-23):
> "Measurements killed always-tools on this hardware (7 tools 2x latency, full set >45s)."

Yani öncesinde her turda TÜM araçlar yüklüydü (always-tools) → ölümcül latency.
Bunu kırmak için tool'ları `question` dalında kapattılar ve modelcik isterse
TOOL_NEEDED marker'ıyla yükseltme eklediler. Sonuç: karar modele bırakıldı →
küçük model yanlış karar veriyor (hem gereksiz escalation hem bazı gerekli
tool'u açmıyor). İkilem: *always-tools = ölümcül latency* vs *tools-none + model
kararı = yanlış karar*.

## 3. İKİNCİL / EK FAKTÖR (384-768, migration sonrası)

- MPNet 768-dim'e geçildikten sonra DB'de hâlâ 384-dim saklı embedding satırları var.
- `cosine_similarity` (`embedding.py:78`) hata yakalayıp 0.0 döndürüyor →
  `retrieval.py:110` `>= threshold` filtresinde bu satırlar sessizce eleniyor →
  model bağlam bulamayınca da tool isteyebiliyor. Bu, asıl kök DEĞİL ama semptomu
  besleyen ikincil katkı. NOTES'taki "tüm vektörler re-embed edildi" iddiası
  sorgulanmalı/doğrulanmalı.

## 4. FINE-TUNE İÇİN VERİ ANALİZİ (ölçüldü)

- DB: `/home/salih/piSynapse/assistant.db` (çalışma dizini — NOT `/home/salih/assistant.db`, o 4096B boş placeholder).
- `INTENT_LLM_FALLBACK=on` (.env) → Katman 1 (LLM+kanıt fallback) ASLINDA AÇIK ve çalışıyor.
- `intent_audit_log = 658` örnek / 9 gün (25 Ağu–02 Eyl), günde ~70 artıyor.
- Dağılım (çok dengesiz): weather 398, email 83, notes 54, tasks 37, memory 27,
  calendar 9; `question/None` negative 39.
- Source: keyword_fallback 425, context_keyword 70, thin_margin 47,
  context_dependent_deferred 39, llm_verified 33, llm_rejected_evidence 33,
  multi_domain_combined 11.
- **Yorum:** 658 labeled örnek, dengeli bir sınıflayıcı fine-tune'u için YETERSİZ
  (özellikle calendar 9 örnekle, negative 39). Veri birikimi sürsün; şimdilik
  fine-tune YAPMA.

## 5. GRUP TESPİTİ ARAÇLARI (zaten mevcut)

- `_hit_groups(message)` (`llm/intent.py:549`): deterministic keyword + reminder
  ile grupları bulur (6 grup: weather/calendar/email/tasks/notes/memory).
- `_KEYWORD_CHECKS` (`llm/intent.py:516`): Türkçe+İngilizce kelime tablosu.
- `reminder_group` (`llm/intent.py:173`): "X saati hatırlat" → calendar.
- `_escalation_tools(full_text, user_message)` (`llm/stream.py:169`): escalation
  için scope seçer; hiçbir şey bulamazsa `combined`'a düşer.
- Çözüm için yeni model lazım DEĞİL; bu deterministic araçlar yeterli.

## 6. ÇÖZÜM PLANI (3 adım — sıralı, küçük, geri-alınabilir)

### ADIM 1 (YARDIM — KÖK): `_TOOL_ASK_HINT`'i sadece gerçek tool sinyali varsa enjekte et
- Durum: **✅ TAMAMLANDI** (2026-09-04). Test + canlı doğrulama yapıldı.
- Yapılan: `question+None` dalında hint yalnızca `_hit_groups(context["_user_text"])`
  doluysa enjekte ediliyor; `hint_armed` bayrağı `True/False` olarak loglanıyor.
  `_hit_groups` boşsa (saf sohbet: "uykum var...") hint yok → model `TOOL_NEEDED`
  üretmez → gereksiz escalation olmaz.
- TAMAMLAYICI KISIM: `hint_armed` artık escalation gate'lerine bağlandı:
  - mid-stream hatch: `hatch_armed = intent_no_tools and hint_armed and not tools_escalated and not think`
  - end-of-round escalate: `if not escalate_now and intent_no_tools and hint_armed and ...`
  Böylece "hint enjekte etmediğim turda escalation olamaz" garantisi sağlandı.
- **Yol boyunca düzeltilen bug'lar (yarı-yapılmış diff'ten):**
  - `_user_text` değişken DEĞİLDİ, `context` sözlüğünün anahtarıydı → `_user_text`
    yazımı `NameError` veriyordu; `context["_user_text"]` yapıldı.
  - `_hit_groups` import'u hiç eklenmemişti → dal başında `try/except` ile import
    edildi (hata olursa `_hit_groups=None` → hint_armed=False → escalation kapalı).
  - Test `test_marker_aborts_round_before_it_finishes` mesajı "bunu halleder misin"
    (keyword'suz) idi; yeni davranışta bu escalation yapmaz → "not oluşturur musun"
    (notes grubu, hint_armed=True) yapıldı.

### ADIM 2: Escalation'ı `combined` yerine ilgili tek gruba daralt
- Durum: **✅ TAMAMLANDI** (2026-09-04). `_escalation_tools` güncellendi.
- `_escalation_tools(full_text, user_message)` artık `_hit_groups(user_message)`
  kullanarak scope'u seçiyor:
  - `len(groups) == 1` → `get_tools_for_group(g)` (≤7 araç, ~13s TTFT)
  - `len(groups) > 1` (gerçek multi-domain: "hava durumunu maille gönder") →
    `get_combined_tools()` (~49s) — iki intent de yanlış yönlenmesin diye
  - `len(groups) == 0` → eski `_keyword_group` (ilk eşleşen) fallback; o da yoksa
    `combined` (son çare)
- Böylece gereksiz `combined (23 tool)` → ilgili tek gruba iniyor; `combined`
  yalnız gerçekten multi-domain ya da hiçbir ipucunun olmadığı uç durumda kalıyor.
- Test: 3 yeni birim test eklendi — `test_escalation_tools_single_group`,
  `test_escalation_tools_multidomain_falls_back_to_combined`,
  `test_escalation_tools_no_group_falls_back_to_combined`.

### ADIM 3 (opsiyonel): SSE sağlamlığı
- Durum: **✅ TAMAMLANDI** (2026-09-04).
- `static/index.html` `data.error` dalı (@~2947) artık her hatayı `connErr`'a
  ("Sunucuya ulaşılamadı") düşürmüyor. Ayrıştırma:
  - gerçek bağlantı kopması (`connection error`) → `errConnLost` mesajı + `connErr` toast
  - `context too long` → `errContextTooLong` mesajı + o mesajın toast'u
  - diğer uygulama hataları → backend'in gönderdiği spesifik `data.error` görülüyor
    (toast'ta da aynı spesifik mesaj)
- `catch` bloğu (gerçek ağ kopması / stream kesilmesi) olduğu gibi `connErr`
  göstermeye devam ediyor — orası doğru.
- `node --check` doğrulandı: ana script (1347-4476) + i18n (1329-1338) geçti.

## 7. UYGULANAN KOD DEĞİŞİKLİKLERİ (çalışma ağacında — commit edilmedi)

Değişen dosyalar (tam diff için `git diff` çalıştır):

1. **`llm/stream.py`**
   - `_escalation_tools` (@~169): `_hit_groups` kullanılarak scope seçimi
     (Adım 2) — tek grup → o grubu, multi-domain → combined, boş → keyword/combined.
   - `chat_with_ollama_stream` intent_no_tools dalı: hint koşullu enjeksiyon +
     `hint_armed` bayrağı (Adım 1).
   - `hatch_armed` (@~460) ve end-of-round escalate (@~535) koşullarına
     `hint_armed` eklendi (Adım 1 tamamlayıcı kısım).
2. **`static/index.html`**
   - `data.error` dalı (@~2947): connection/context/other ayrımı + toast düzeltmesi
     (Adım 3).
3. **`tests/test_tool_escalation.py`**
   - `test_marker_aborts_round_before_it_finishes`: mesaj "bunu halleder misin" →
     "not oluşturur musun" (yeni davranışla uyum).
   - `test_marker_without_hints_falls_back_to_combined` → `test_multi_domain_marker_falls_back_to_combined`
     (eski senaryo yeni mimaride imkânsızlaştı; multi-domain davranışını test ediyor).
   - +3 yeni birim test (`test_escalation_tools_*`).

Değişiklikler çalışma ağacında duruyor, **commit edilmedi.** Yedekler:
`/tmp/opencode/stream.py.bak-*`, `/tmp/opencode/test_tool_escalation.py.bak-*`.

---

## 8. YAPILAN İŞİN DETAYLI DÖKÜMÜ (her adımda ne yapıldı)

1. [x] Adım 1'i TAMAMLA: `hint_armed`'ı `hatch_armed` (@~446) ve `escalate_now`
      koşuluna (@~521-522) bağla. NOT: bu iki noktanın tam satır numaraları,
      hint koşullandırma eklenince kaymış olabilir; `grep -n "hatch_armed\|escalate_now"`
      ile bul. YAPILDI (2026-09-04):
      - `hatch_armed = intent_no_tools and hint_armed and not tools_escalated and not think`
      - end-of-round `if not escalate_now and intent_no_tools and hint_armed and ...`
      - `_hit_groups` import'u dalın başına eklendi (try/except → None fallback).
      - DÜZELTİLEN BUG: yarı-yapılmış diff `_user_text` kullanıyordu ama o sadece
        `context` sözlüğünün ANAHTARI, değişken değil → `context["_user_text"]` yapıldı.
      - Test test_marker_aborts... 'bunu halleder misin' (keyword'suz) kullanıyordu;
        yeni davranışta bu escalation yapmaz → mesaj 'not oluşturur musun' yapıldı.
2. [x] Test: `venv/bin/pytest` → **557 passed** (tam suite); `tests/test_tool_escalation.py` 11/11.
      2026-09-04'te gerçekleştirildi.
3. [x] Adım 2: escalation'ı tek gruba daralt (TTFT iyileştirmesi). YAPILDI (2026-09-04):
      `_escalation_tools` (@~169) artık `_hit_groups` kullanıyor:
      - tek grup bulunursa → `get_tools_for_group(g)` (≤7 araç, ~13s)
      - 2+ grup (gerçek multi-domain: "hava durumunu maille gönder") → `combined`
      - hiçbiri bulunamazsa → `_keyword_group` fallback, o da yoksa `combined` (son çare)
      Test: 3 yeni birim test eklendi (`test_escalation_tools_*`); suite → **560 passed**.
4. [x] Adım 3 (opsiyonel): SSE mesaj netleştirme (frontend `index.html`). YAPILDI (2026-09-04):
      `data.error` dalı (@~2947) artık her hatayı `connErr`'a düşürmüyor:
      - gerçek bağlantı kopması (`connection error`) → `errConnLost` + `connErr` toast
      - context overflow → `errContextTooLong` + o mesajın toast'u
      - diğer uygulama hataları → ham spesifik `data.error` mesajı (toast'ta da o mesaj)
      Yani backend'in gönderdiği spesifik hata artık kullanıcıya gerçek haliyle gösteriliyor.
5. [x] Frontend değişikliği olursa: `node --check` (index.html'den çekilen script).
      YAPILDI: ana script (1347-4476) + i18n (1329-1338) → node --check ikisi de geçti.
6. [x] Canlı doğrulama: "uykum var ama uyuyamıyorum" tarzı saf sohbet sorusunda
      artık `Hatch escalating` logu gelmemeli; yanıt normal akmeli.
      2026-09-04'te gerçekleştirildi (servis restart edildi → yeni kod aktif):
      - SENARYO 1 (saf sohbet) "uykum var ama uyuyamıyorum, ne önerirsin":
        log `Pure chat ... (hint_armed=False)`; `Hatch escalating`/`Hatch armed` YOK;
        yanıt normal üretildi (done event + message_id). ASIL SEMPTOM ÇÖZÜLDÜ.
      - SENARYO 2 (tool domain) "bugün hava nasıl olacak":
        `Intent=action group=weather via embedding (sim=0.92)` → 2 araçla doğrudan
        çalıştı (escalation yolu hiç girmedi); get_weather çağrıldı, yanıt geldi.
      - NOT: escalation'ın tek-gruba daralması canlıda modelin marker üretmesine
        bağlı olduğu için deterministik olarak canlı tetiklenmedi; bu scope
        daralması birim test test_escalation_tools_single_group ile garanti altında.

7. [x] Geliştirme sürecinde karşılaşılan ve düzeltilen test hataları
      (gelecekte aynı tuzağa düşmeyi önlemek için kayıt):
      - İlk `venv/bin/pytest tests/test_tool_escalation.py` çalışması: 7 test
        `NameError: '_hit_groups' is not defined` ile fail → `_hit_groups` hiç
        import edilmemişti. `_escalation_tools` içindeki import, üst seviyedeki
        kullanımı kapsamıyordu → dal başına `try/except` import eklendi.
      - Aynı 7 test ikinci denemede `NameError: '_user_text' is not defined` ile
        fail → `_user_text` değişken değil, `context` sözlüğünün ANAHTARI;
        difft'teki `_user_text` yazımı yanlıştı → `context["_user_text"]` yapıldı.
      - `test_marker_without_hints_falls_back_to_combined` (eski ad;
        yeni adı `test_multi_domain_marker_falls_back_to_combined`): `_hit_groups`'u
        `set()` yapınca escalation HİÇ olmadı (çünkü `hint_armed=False`) → bu senaryo yeni
        mimaride imkânsız ("keywords yok ama marker var"). Test yeniden yazıldı:
        çoklu-domain (`{"email","weather"}`) → `combined` davranışını test ediyor.
      - `test_marker_aborts_round_before_it_finishes`: "bunu halleder misin"
        (keyword'suz) artık escalation yapmıyor → "not oluşturur musun" yapıldı.
      - `test_escalation_tools_single_group` içindeki `get_weather` iddiası: weather
        grubu tool isimleri `get_tools_for_group` davranışına göre değişebildiği
        için brittle; scope + araç sayısı iddiası yeterli → get_weather iddiası kaldırıldı.

## 9. ÖNEMLİ DOSYA / SATIR REFERANSLARI

- `llm/stream.py`: `_TOOL_ASK_HINT` @144; `_wants_tools_hint` @152; `_bare_tool_name` @157;
  `_escalation_tools` @169 (Adım 2); `intent_no_tools` dalı @329; hint koşullu enjeksiyon
  @344-345; mid-stream hatch `hatch_armed` @463; end-of-round escalate @538-539.
- `llm/intent.py`: `reminder_group` @173; `_KEYWORD_CHECKS` @516; `_hit_groups` @549;
  `_classify_intent` @573; `llm_resolve_with_evidence` @~860 (Katman 1, açık).
- `llm/utils.py`: `_check_tool_leak` @~125 (tool tag/JSON/leak regresi).
- `static/index.html`: `data.error` dalı @~2947 (Adım 3); in-line script 1329-1338 (i18n),
  1346-4477 (ana uygulama).
- `tests/test_tool_escalation.py`: Adım 1/2'nin tüm escalation testleri; `_drain` helper @30.
- `config .env`: `INTENT_LLM_FALLBACK=on`, `DB_PATH=assistant.db`.
- DB: `/home/salih/piSynapse/assistant.db` — `intent_audit_log` (658), `tool_audit_log` (215).
- Servisler: `pisynapse.service` (uvicorn), `piserve.service` (litert gemma4-e2b).
- Rapor önceki (kök analiz, daha kapsamlı log): `/home/salih/bug_teşhis_raporu.md`.
