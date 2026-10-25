# piSynapse — Bağımsız Değerlendirme (2026-10-25)

> **Metod:** tek ajan, salt-okuma, örnekleme. Tüm dosyalar satır satır okunmadı;
> iddiaların hepsi sayı, dosya:satır veya çalıştırılmış komutla desteklendi.
> **Kapsam:** `/home/user/piSynapse` (yerel ağaç, origin/main'in 51 commit önünde).
> **Durum:** bu bir kayıt dosyasıdır — **hiçbir kod değişikliği yapılmadı.**
> Kullanıcı yoğun bir dönemde; bu dosya 4 hafta sonra sıfırdan devam edilebilsin diye yazıldı.

---

## 0. Tek paragraf

Mühendislik kalitesi solo bir proje için üst çeyrekte: 1010 test, savunmacı kod,
gerçek güvenlik düzeltmeleri, tutarlı günlük disiplini. Sorun kod değil.
Sorun şu üçü: **(a) suite'in raf ömrü var — şu an kırmızı**, (b) ürün kimliği
"tek kullanıcı / çok kullanıcı sunucu" arasında sıkışmış, (c) dağıtım rampası yok.
Sıradaki en yüksek getirili iş yeni özellik değil, **30 saniyede denenen bir kurulum
ve 60 saniyelik bir demo**.

---

## 1. Ölçümler (yeniden üretilebilir)

```bash
find . -name '*.py' -not -path './.venv/*' -not -path './.git/*' -print0 | xargs -0 wc -l | tail -1
grep -rc 'def test_' tests/*.py | awk -F: '{s+=$2} END {print s}'
.venv/bin/python -m pytest -q
```

| Ölçüm | Değer |
|---|---|
| Python | **35.863 satır**, 130 dosya, 608 fonksiyon |
| Test | **1010 test fonksiyonu**, ~17.2k satır test kodu |
| Endpoint | 71 (`routers/*` + `main.py`) |
| Commit | 729, ilk 2026-05-24, son 2026-10-16, **origin'in 51 önünde** |
| Sürüm | pyproject 2.0.0 (2026-09-09) — yerel ağaç etiketsiz |
| Ortalama fonksiyon | 23.8 satır (sağlıklı) |
| >100 satır fonksiyon | 17 adet, hepsi LLM/stream/kurulum hattında |
| En büyük dosyalar | `db.py` 3859, `install.py` 1850, `routers/chat.py` 1066, `main.py` 994 |
| UI | `static/ui.js` 5183 satır (build yok), `ui.css` 1450 |
| Suite sonucu | **2 failed, 1014 passed** (122 sn) |

Not: `db.py` büyük ama god-object değil — 21 üst düzey tanım, içi küçük
fonksiyonlara bölünmüş (migrasyon DDL bloğu ~700 satır, normal).

---

## 2. R1 — BLOCKER: suite kırmızı (zaman bombası)

```
FAILED tests/test_audit_flywheel.py::test_failure_digest_clusters_and_counts
FAILED tests/test_audit_flywheel.py::test_overview_includes_digest
```

**Kök neden** — `tests/test_audit_flywheel.py:265`:

```python
r.get("created_at", "2026-10-16T00:00:00")
```

Sabit tohum tarihi + `db.py:1959` içindeki `created_at >= datetime('now', ?)`
penceresi (`-7 days`). Test yazıldığı gün (16 Ekim) geçti; **24 Ekim'de patladı**.
NOTES.md'deki "Suite: 1016 passed" ifadesi o gün doğruydu, bugün yanlış.

**Yaygınlık:** testlerde 56 sabit tarih var, `freezegun`/`time-machine` yok.
`tests/test_sync_lww.py` (23), `test_corpus_feeder.py` (13) aynı risk sınıfında.

**Neden CI yakalamadı:** son push 5 Ekim; CI o günden beri koşmadı.

**Düzeltme seçenekleri**
1. (küçük, bağımlılıksız) tohumu göreli yap:
   `(datetime.utcnow() - timedelta(days=1)).strftime("%Y-%m-%dT%H:%M:%S")`
2. (doğrusu) `time-machine` (dev bağımlılığı) ile saati dondur; pencere
   kenarlarını (6 gün / 8 gün) ayrıca test et.
3. (ucuz yama) iki testte `days=30` geç — kök nedeni gizler, önerilmez.

**Kural önerisi (R1'in asıl çıktısı):** NOTES'taki "test-quality audit" kuralı
vakum ve mutasyonu kontrol ediyor, **determinizmi** kontrol etmiyor. Eklenecek:
> Zaman/para/dosya sistemi/rassal davranışa bağlı her test ya saati dondurur ya da
> göreli zaman üretir. Mutlak tarih literali test kodunda yasak (migrasyon
> fixture'ları hariç). Her paket sonunda suite **temiz bir checkout'ta** bir kez
> daha koşulur.

---

## 3. Diğer bulgular (öncelik sırası)

### R2 — Ürün kimliği iki arada (yüksek etki, karar gerekiyor)
Çok kullanıcı + admin onay kuyruğu + kullanıcı başına şifreli kimlik bilgileri +
audit dashboard = **sunucu ürünü**. Ama auth düz HTTP, API key tel üzerinde açık,
`SESSION_COOKIE_SECURE` varsayılan kapalı, README "trusted home LAN" diyor.
Sonuç: çok kullanıcının bütün karmaşıklığı ödenmiş, sunucunun güvenliği alınmamış.
- Sunucu ise → TLS varsayılan (Caddy/nginx birincil kurulum yolu), `TRUSTED_HOSTS`
  ve `SESSION_COOKIE_SECURE` fail-closed.
- Tek kullanıcı ise → multi-user/admin/approval arkasında bayrak; varsayılan akış
  tek kullanıcı.
**Karar olmadan ne R3 ne R6 doğru yapılamaz.**

### R3 — Test dağılımı ters (yüksek etki, orta efor)
Kapsam %90 ama **`install.py` (1850 satır) kapsam dışı** — her kullanıcının ilk
çalıştırdığı, en kırılgan, en çok yarıda bırakılan kısım. 2.4 GB model indirme +
sudo + systemd burada. Kullanıcı kaybı sunucuda değil burada olur.
- İlk adım: `install.py`'nin saf karar fonksiyonlarını ayır (env yazımı, model
  seçimi, sürüm kontrolü) ve birim testle. Süreci uçtan uca test etmek gerekmez.

### R4 — LLM döngüsü dev fonksiyonlar (orta etki, orta efor)
`chat_with_ollama_stream` 541, `init_db` 377, `chat_with_ollama` 304,
`lifespan` 224, `chat_stream` 197. Hata raporlarının tamamı buraya düşer.
- Bölme önerisi: **taşıma** (SSE parse/emit) / **tool-loop** (seçim, yürütme,
  sınır) / **doğrulama** (verify + düzeltme). Her parça kendi birim testini alır.
- Bu bölme tek başına R1 tarzı regresyonları da azaltır (döngü guard'ları
  şu an e2e testlerle tutuluyor).

### R5 — Meta-özellik kayması (orta etki, stratejik)
Son 60 commit: 24 fix, 9 NOTES, 6 docs, 5 test, **4 feat — 3'ü audit**.
Son üç hafta "asistanın kendi araç çağrılarının" gözlemlenebilirliğine gitti
(NDJSON manifest, flywheel holdout, hata digest'i). İyi mühendislik; ama 3
kullanıcılı bir üründe kimsenin istemediği katman. Kullanıcının umursadığı:
cevap kalitesi, gecikme, kurulum.
- Kural önerisi: yeni "audit/meta" işi ancak bir kullanıcı şikayeti veya ölçülmüş
  bir kayıpla gerekçelenirse açılır.

### R6 — Dağıtım rampası yok (yüksek etki, düşük-orta efor)
3 yıldız, 0 fork. Kurulum: `git clone` → `install.py` → 2.4 GB model → systemd =
ilk "merhaba" için 30-60 dk. Docker/compose yok, demo GIF yok.
- En yüksek getirili tek saat: `docker compose up` + README'de 30 sn'lik gerçek
  demo ("yarın takvimimde ne var?" → CalDAV → cevap).
- Rakip başka bir self-hosted asistan değil; "ChatGPT'yi açarım".

### R7 — Günlük ikinci ürün oldu (düşük etki, bilinçli karar)
`NOTES.md` 2386 satır + `docs/` ~120 KB analiz. Kullanıcı+AI sürekliliği için
paha biçilmez; yeni gelen için sıfır değer ve kendi başına bakım yüzeyi.
- Öneri: dosyayı bölme. "Nasıl çalışılır" (READ FIRST) ayrı ve kısa kalsın;
  kronoloji arşive taşınsın. İçerik kaybı olmasın.

### R8 — "Collective learning" ismi gizlilik vaadiyle çelişiyor (düşük etki)
Lokal ve quorum kapılı olsa bile isim "kullanıcılar arası paylaşım" çağrıştırıyor.
Gizlilik ürününde isim bir güven yüzeyi. Yeniden adlandır veya README'de
"hiçbir şey cihazdan çıkmaz" cümlesinin hemen altında açıkça tanımla.

### R9 — Yayın durumu (düşük efor, yüksek görünürlük)
51 commit push edilmemiş, sürüm etiketi yok. Yereldeki en iyi hâl kimsenin
görmediği hâl.

### R10 — Küçük not (düşük etki)
Sunucu kodunda 54 `print(`, 36 `logging.` çağrısı. Bir kısmı CLI/kurulum için
meşru; kalanı log'a çevrilirse R4 bölmesi sırasında bedava gelir.

---

## 4. Önerilen yol haritası

| # | İş | Efor | Neden şimdi |
|---|---|---|---|
| 1 | R1 düzelt + determinizm kuralı | ~30 dk | Suite kırmızı; her şeyin önkoşulu |
| 2 | R9: push + `v2.1.0` etiketi | ~10 dk | Yerel iş görünür olsun |
| 3 | R6: compose + demo GIF | ~2-3 saat | En yüksek getiri/efor oranı |
| 4 | R2: tek kullanıcı / sunucu kararı | karar | R3 ve R6'yı şekillendirir |
| 5 | R4: stream döngüsünü böl + birim test | ~1 gün | Regresyon kaynağını kurutur |
| 6 | R3: install.py saf fonksiyonlarına test | ~yarım gün | İlk-kurulum kaybını azaltır |
| 7 | R5/R7/R8: süreç ve isimlendirme | küçük | Kültürel, acele değil |

**Yapılmaması gereken:** bu listeden önce yeni özellik. Özellikle yeni
entegrasyon, yeni audit katmanı, yeni UI sayfası.

---

## 5. Cevap bekleyen kararlar

1. **Tek kullanıcı mı, sunucu mu?** (R2 — diğer her şeyi etkiler)
2. **Hedef kitle:** sadece sen + birkaç arkadaş mı, yoksa yayın mı? (R5/R6)
3. **Docker kabul mü?** README'de "Docker kaldırıldı" notu var; bu kararın
   gerekçesi hâlâ geçerli mi? (R6)
4. **Android portu** (`/home/user/pisynapse-android`, Capacitor) bu dalgada
   kapsam içi mi? Değerlendirme dışı bırakıldı.

---

## 6. Kapsam dışı / doğrulanmayanlar

- `static/` UI ve `litert_serve/` satır satır okunmadı.
- Gerçek kurulum (temiz makinede `install.py`) denenmedi — R3 tam olarak bu
  yüzden "hipotez" sayılmalı, ölçüm değil.
- Model kalitesi/gecikme ölçülmedi (Pi 5 üzerinde cevap süresi iddiası README'den).
- Çok kullanıcı izolasyonu yalnızca test varlığı üzerinden değerlendirildi,
  sızma testi yapılmadı.

---

## 7. Dönüşte ilk 30 dakika

```bash
cd ~/piSynapse
git status && git log --oneline -5
.venv/bin/python -m pytest -q tests/test_audit_flywheel.py   # R1 hâlâ kırmızı mı?
# evet ise: tests/test_audit_flywheel.py:265 sabit tarihini göreli yap, tekrar koş
.venv/bin/python -m pytest -q                                 # tam suite yeşil olmalı
git push origin main                                          # R9
```

Sonra R6 (compose + demo) — kod yazmadan, sadece ambalaj.
