# piSynapse — Architecture Notes

## Son Değişiklikler — 13-08-2026

Denetim (A1-A10/B1-B5/C1-C8/D1-D6) + Faz 1 düzeltmeleri. Süreç: analiz → plan → uygulama, her madde ayrı commit + `py_compile` + `pytest` (27/27).

| # | Değişiklik | Detay |
|---|-----------|-------|
| **1** | **git init + baseline commit** | Proje artık git repo (`bcc7379`). Öncesinde tar yedeği: `backups/piSynapse-20260813-1917.tar.gz` (venv/db/.env/modeller hariç). |
| **2** | **.gitignore tamamlandı** | Eklendi: `venv/` (gerçek venv noktasız, önceden commit'lenebilirdi!), `*.db-wal`, `*.db-shm`, `*.db-journal`, `.pytest_cache/`, `.ruff_cache/`, `.mypy_cache/`, `*.egg-info/`, `dist/`, `build/`, `*.pyc`. |
| **3** | **A1** | `pyproject.toml` build-backend `setuptools.backends._legacy` (geçersiz) → `setuptools.build_meta`. `[project].dependencies`'e eksik `faster-whisper` eklendi. `[tool.setuptools]` paket/`py-modules` layout tanımı — `pip install -e .` artık çalışıyor. |
| **4** | **A2** | `llm/stream.py` — LiteRT stream'de tool_calls delta'ları üzerine yazılıyordu (id/name/arguments kayboluyor, çoklu tool call yok oluyordu). `_merge_tool_calls()` ile index'e göre birleştirme. Ollama tam-listeleri ayrıca ele alınıyor. |
| **5** | **A3** | `routers/media.py` — faster-whisper `transcribe` + 2× `subprocess.run(ffmpeg)` senkrondu (event loop blok). Hepsi `asyncio.to_thread`; lazy segment iterasyonu thread içinde. |
| **6** | **A4** | `llm/intent.py` — `model.embed()` senkron. `embed_async()` + yeni `embed_batch_async()` (embedding.py) kullanılıyor. |
| **7** | **A5** | `config.sync_config()` string listesi eksikti (DEFAULT_CITY, ASSISTANT_USER→DEFAULT_USER, MAIL_PROVIDER, LLM_KEEP_ALIVE yok). Dict eşlemesine çevrildi. `INTENT_LLM_FALLBACK` `RESTART_REQUIRED_KEYS`'ten çıkarıldı (çelişki). prompt.py/widgets.py/weather.py `DEFAULT_CITY`'yi çağrı anında okuyor (import-time binding kaldırıldı). |
| **8** | **A6** | `MEMORY_SIMILARITY_THRESHOLD` (0.68) ölü config'ti — db.py 0.85 hardcoded. Artık db.py dedup eşiğinde kullanılıyor + `SETTINGS_SCHEMA`'ya eklendi (UI'da ayarlanabilir). |
| **9** | **A7** | `routers/chat.py` — asistan yanıtı yalnızca `done` event'inde kaydediliyordu; disconnect/error'da kullanıcı mesajı sahipsiz kalıyordu. `finally` bloğu ile kısmi yanıt da kaydediliyor (`reply_saved` bayrağı). |
| **10** | **A8** | `calendar_ops.update_event` — ham iCal string `.replace()` (all-day VALUE=DATE eşleşmiyor, folded SUMMARY kırılıyor, yanlış damga değişebiliyordu) → vobject property manipülasyonu. All-day + timed test edildi. |
| **11** | **A9** | `mail.py` — boş MAIL_PROVIDER gmail'e düşüyordu (docs "empty = disable" diyor). Artık boş ise email devre dışı. |
| **12** | **A10** | `install.py` — `missing.append("ffmpeg"/"curl")` kurulum başarılı olsa da çalışıyordu; yalnızca gerçekten eksikse ekleniyor. |
| **13** | **B1** | `.gitignore` baseline'a girdi (satır 2). Kritik eksikler kapatıldı: `venv/`, `*.db-wal/shm/journal`, cache'ler, `dist/`/`build`/`*.egg-info`. |
| **14** | **B3** | `main.py` rate-limit IP'si `x-forwarded-for`'a koşulsuz güveniyordu (spoof ile bypass). Artık `request.client.host`; proxy arkasında çalışanlar `TRUST_X_FORWARDED_FOR=1` (PROTECTED_SETTINGS'e eklendi). |
| **15** | **B2/B4** | README'den yanlış "SSRF protection" iddiası kaldırıldı. "Security Notes" bölümü eklendi (TLS reverse-proxy, `.env` chmod 600, XFF). |

Durum: **Faz 1 (A1-A10) + Faz 2 (B1-B4) tamamlandı**, Faz 3 (mimari) başlıyor.

## Faz 3 (Mimari) — 13-08-2026

| # | Değişiklik | Detay |
|---|-----------|-------|
| **16** | **C8** | `f0179b1` — Ölü kod temizliği: `_AUTH_EXEMPT` (main.py), `_TOOL_TO_GROUP` (tools/definitions.py), `llm/__init__.py` re-export'ları (yalnızca `__all__`'dakiler kaldı), install.py `home`/`python_path` F841, `llm/payload.py` `tool_name`, f-string'ler + 42 otomatik F-hatası. Tüm F401/F841/F541 temiz (kalan 144 hata: E501/D-docstring stil, önceden vardı). |
| **17** | **C6** | `7780496` — `get_llm_model_options()` senkron subprocess(curl/ollama) çalıştırıyordu → async sarmalayıcı + `asyncio.to_thread`; bloklama event loop'tan çıktı. LiteRT canlı sorgu test edildi (gemma4-e2b, gemma4-e4b). |
| **18** | **C7** | `f224513` — `nextcloud_notes.list_notes()` tek istekle tüm notları çekiyordu → `page`/`itemsPerPage=100` sayfalama. Sunucu sayfalama parametresini yok sayarsa sonsuz döngü koruması (id dedupe). |
| **19** | **C3** | `0c3691e` — DB şema migrasyonu ad-hoc try/except → `PRAGMA user_version` tabanlı sıralı MIGRATIONS (images, name, summarized_until, embedding). Mevcut DB `user_version=4` doğrulandı. |
| **20** | **C2** | `807866c` — Opsiyonel veri saklama: `CONVERSATION_RETENTION_DAYS` / `MEMORY_RETENTION_DAYS` (varsayılan 0 = kapalı). `db.cleanup_expired_data()` başlangıçta çalışır. UI'da ayarlanabilir + `.env` PATCH ile canlı sync (restart gerekmez). |
| **21** | **C1** | `d13bd82` — SQLite `database is locked` hataları: `busy_timeout=10000` + `_write_with_retry()` (3 deneme, migrasyon/cleanup yazımlarında). Retry'ı simülasyonla test edildi. |
| **22** | **C4** | `b9e72d3` — `[project.optional-dependencies].dev` (pytest, pytest-asyncio, ruff, mypy). mypy gerçek bug'ı düzeltildi: `llm/chat.py` `msg2`/`message` None narrowing (188→154 hata; kalanlar eksik stub/generic, baseline). |

Durum: **Faz 3 (C1-C8) tamamlandı** — 22 madde işlendi, 27/27 test, smoke OK (/health 200, / 200, /chat/sessions 401). Sıradaki: Faz 4 (D1-D6, arayüz + README) + LiteRT systemd unit'i.

## Son Değişiklikler — 31-07-2026

| # | Değişiklik | Detay |
|---|-----------|-------|
| **1** | **Port 8765** | `pisynapse.service` portu 8000 → 8765. Eski 8765 process'i (PID 314732, manuel) durduruldu, systemd servisi güncellendi. |
| **2** | **install.py yeniden yazıldı** (453→654 satır) | LiteRT kurulumu: `uv tool install litert-lm` + `litert-lm import --from-huggingface-repo` ile model indirme (~2.4 GB) + `litert-lm serve --port 9379` başlatma + 60sn bekleme. Ollama: `curl install.sh | sh` + `ollama pull`. Model registry `_LITERT_MODEL_REGISTRY` dict'inde tanımlı. |
| **3** | **systemd çift servis** | `litert.service` (LiteRT server), `pisynapse.service` (After=litert.service varsa). `_create_litert_service()` ile kurulum. |
| **4** | **release.sh** | `rm -rf + bash release.sh` ile sıfırdan, kalıntısız release (912K, 49 dosya). exclude'lar: venv, __pycache__, *.db, models/, .env, .git, cache'ler. |
| **5** | **INTENT_LLM_FALLBACK** | `config.py` → `SETTINGS_SCHEMA`'da select kutusu. Varsayılan `off` (embedding+keywords yeterli). `on` olursa LLM fallback çağrısı (~+15s). `RESTART_REQUIRED_KEYS` + `sync_config()` string listesinde. |
| **6** | **get_llm_model_options() cache** | `_MODEL_OPTIONS_CACHE` (30s TTL, backend bazlı). LiteRT `/v1/models` ve `ollama list` tekrar çağrılmaz. |
| **7** | **Tüm dosyalara yorum satırları** | Her `.py` dosyasına kısa docstring + section/inline yorumlar eklendi. `embedding.py`, `llm/utils.py`, `llm/stream.py`, `llm/intent.py`, `llm/payload.py`, `llm/chat.py`, `tools/__init__.py`, `routers/config.py`. |
| **8** | **Avahi fix** | `/etc/avahi/avahi-daemon.conf` → `allow-interfaces=eth0`. `.local` çözümlemesi Docker bridge (`172.17.0.1`) yerine gerçek IP (`192.168.1.X`) döndürüyor. |
| **9** | **TTFT regresyonu — gürültü** | Ardışık 3 ölçüm: 14.5s / 13.3s / 13.6s. Önceki 18-21s değerleri LiteRT soğukken alınmış. Embedding+keywords intent ~50-100ms, gerisi LiteRT warmup. |
| **10** | **README baştan yazıldı** | Vision bölümü kaldırıldı. Hardware Requirements, Privacy & External Services tablosu, dual email (Proton/Gmail) kılavuzu eklendi. 52 env değişkeni senkronize edildi. |
| **11** | **install.py self-contained .env** | `step_env()` artık `example.env`'e ihtiyaç duymaz — tüm 52 değişkeni sıfırdan oluşturur. Email kurulumunda Proton/Gmail/none seçeneği sunar. |
| **12** | **example.env yenilendi** | Eksik 20+ değişken eklendi (LLM_NUM_CTX, SUMMARY_*, INTENT_LLM_FALLBACK, MEDIA_MAX_MB, etc.). config.py ile %100 uyumlu. |
| **13** | **GitHub push — v2 release** | `piSynapse-release` → `git init + add + commit + remote + pull --allow-unrelated-histories -X ours + push`. Eski 42 commit korundu, üzerine merge ile yeni kod eklendi. Toplam commit: 43 + merge. |

## ZORUNLU — HER SESSION/COMPACTION SONRASI ÖNCE BUNU OKU

- Proje ARTIK git repo (13 Ağustos 2026). Değişiklikler tek tek commit'lenir
  (kural: her madde tek commit + py_compile + pytest). Riskli mimari değişiklik
  öncesi yedek: `backups/piSynapse-*.tar.gz` (gitignore'da). Yedek alıp
  almadığını KULLANICIYA sor, kendiliğinden "yedek aldım" diye varsayma.
- Kullanıcının onayı olmadan mimari değişiklik yapma (yeni klasör/
  paket ekleme, Docker/WebSocket gibi yeni altyapı ekleme, framework
  değiştirme). Kapsamı kendi inisiyatifinle genişletme.
- "Kullanıcı onayladı / kabul etti" diye BİR ŞEY YAZMADAN önce, o
  onayın bu konuşmada gerçekten, açıkça verildiğinden emin ol. Emin
  değilsen "kullanıcı onaylamadı, ben varsaydım" diye dürüstçe yaz,
  asla olmayan bir onayı var gibi gösterme.
- services/ katmanı KALDIRILDI (30 Temmuz 2026) — db.py, llm/,
  tools/, embedding.py gibi eski modüller tüm işi yapıyor. Yeniden
  bir DI/service katmanı önerme, kullanıcı özellikle istemedikçe.
- Docker, WebSocket (/chat/ws) kaldırıldı — frontend sadece SSE
  (/chat/stream) kullanıyor, gelecekte tekrar eklenmesin.
- Ollama servisi durduruldu, devre dışı bırakıldı — LLM_BACKEND=litert
  aktif. Ollama'yı tekrar başlatma/bağımlılık ekleme, kullanıcı
  özellikle istemedikçe.
- Test kapsamı düşük (~%7) — calendar_ops.py, mail.py, llm/, tools/
  dispatcher hiç test edilmiyor. Bu bilinen bir eksik, ayrı bir
  oturumda ele alınacak, "prod kalitesinde" iddiası şu an bu yüzden
  tam doğru değil.
- calendar_ops.py'de hata yönetimi eksik (try/except yok) — bilinen
  bir sorun, henüz düzeltilmedi.

## Vision

Tek makineden dağıtık kişisel asistana evrim.

## Three Layers

| Layer | State | Description |
|-------|-------|-------------|
| **1. Current** | ✅ Live | Single server + web UI, her şey local |
| **2. Queue / Sync** | 🔜 Next | Phone stores plain-text commands offline, `/sync` endpoint on reconnect |
| **3. Distributed** | 🔭 Far | Every device contributes at its capacity, LiteRT on mobile, optional sync-only server |

## Key Decisions

- **Device discovery:** Manual (login / domain / VPN) — no auto-discovery
- **Conflict resolution:** Merge semantics — last-write-wins is not acceptable
- **Queue format:** `{ "command": str, "timestamp": str, "session_id": str }` — JSONL locally
- **Offline tool policy:** `OFFLINE_SAFE_TOOLS` set in `tools.py` — low-risk commands run offline, `CONFIRM_TOOLS` are queued only
- **Mobile model:** LiteRT-LM (eski TFLite üzerine LLM orkestrasyon katmanı) — not mature yet, tracking
- **Sync transport:** Tailscale-like P2P or user-defined relay
- **Sync-only server:** Optional — for users who want cloud sync without LLM on server

## Open Questions

- Queue persistence format (JSONL? SQLite?)
- `/sync` endpoint design — batch vs streaming
- Conflict resolution algorithm for calendar/alarm overlap scenarios
- LiteRT integration timeline

---

## LiteRT-LM Detay

> 13 Temmuz 2026 — mobil offline model araştırması için teknoloji notu.

### Nedir

LiteRT-LM, LiteRT (eski TFLite) üzerine kurulu, LLM'lere özgü karmaşıklıkları (KV-cache yönetimi, session state, multi-turn context, prompt caching) yöneten bir orkestrasyon katmanı. Gemini Nano'nun Chrome ve Pixel Watch'taki dağıtımını güçlendiren üretim altyapısı.

### Cross-Platform

Android, iOS (Swift + Metal), Web (JS + WebGPU), Desktop (Linux/macOS/Windows), Raspberry Pi dahil IoT. Erken aşamada topluluk destekli Flutter binding.

### Tool-Use / Function Calling

Native constrained decoding ile tool-call doğruluğu artırılıyor. Mevcut `run_tool()` akışına benzer: model duraklatıp yapılandırılmış tool-call isteği döndürüyor, sonuç alınınca devam ediyor.

### Entegrasyon

- CLI + Python API (`uv`/`pip`)
- OpenAI-uyumlu yerel sunucu modu → `llm.py`'de sadece base URL değişir
- Android: `com.google.ai.edge.litertlm:litertlm-android` (Gradle, Kotlin API). Engine sınıfı, hatalar `LiteRtLmJniException` / `IllegalStateException`

### Model Desteği

Gemma, Llama, Phi-4, Qwen, Gemma4 12B

### Pi 5'te Beklenti (TEST EDİLDİ — 29 Temmuz 2026)

CPU-only ~2-5 token/sn (E2B). Ollama+gemma4:e2b ile token/sn, bellek, tool-call doğruluğu kıyaslandı.

### Karşılaştırma Sonuçları (Raspberry Pi 5, 8 GB RAM) — 29 Tem 2026

**Metodoloji:** Aynı system prompt ve tool şeması kullanıldı (get_current_time + create_task, 3-turn multi-step).

**Ollama testi:** Temiz başlangıç: `swapoff -a && swapon -a && echo 3 > /proc/sys/vm/drop_caches` sonrası. Hiçbir runtime process'i çalışmıyordu. 3 kez çalıştırılmak istendi ama 1. run tamamlandı, 2. run'un ilk turn'ü 129.6s'de timeout'a takıldı, 3. run başlayamadı.

**LiteRT-LM testi:** Ollama testinin hemen ardından yapıldı. Ollama process'leri `killall -9` ile öldürüldü ama **swap yeniden sıfırlanmadı** (free -h ~1.3 GiB swap used gösteriyordu). Bu nedenle LiteRT-LM test ortamı %100 temiz değildi — ancak LiteRT-LM swap kullanmadığı için sonuçları etkilemedi. RAM kıyaslamasında Ollama'nın swap kullanımı dramatik farkın ana kaynağı.

**Notlar:**
- Ollama API'si `tool_calls.function.arguments`'ı **dict** döndürür; LiteRT-LM ise **string** döndürür. İlk test script'inde bu fark TypeError'a yol açmıştı — test tekrarı değil, API farkıydı.
- Ollama'nın 150s ölçümü model loading içeriyor; LiteRT-LM'in 17s'si de öyle.

#### Cold start (model yükleme dahil ilk inference)

| Ölçüt | LiteRT-LM (gemma4-e2b) | Ollama (gemma4:e2b) |
|-------|------------------------|---------------------|
| **Turn 1** (load + get_current_time) | **16.9 s** | 137.7 s |
| **Turn 2** (create_task) | **16.7 s** | 70.7 s |
| **Turn 3** (final answer) | **14.5 s** | 197.9 s |
| **Toplam** | **48.1 s** | 406.3 s |
| Warm simple query (3-req avg) | **2.4 s** | (ölçülemedi — swap thrashing) |

#### Warm runs (model yüklü, 2. ve 3. denemeler)

| Ölçüt | LiteRT-LM (gemma4-e2b) | Ollama (gemma4:e2b) |
|-------|------------------------|---------------------|
| Run 2 total | **44.7 s** | (test 129.6s'de timeout) |
| Run 3 total | **43.6 s** | — |
| n | 3 (tam) | 1 (tam) + 1 (yarım) |
| Not | Model yüklü, stabil | Her turn ~100-140s, 2. run timeout |
| Warm latency | ~2.4s (simple) | Ölçülemedi — swap thrashing |

#### Memory (model yüklüyken)

| Ölçüt | LiteRT-LM (gemma4-e2b) | Ollama (gemma4:e2b) |
|-------|------------------------|---------------------|
| **RAM kullanımı** | **+1.7 GB** (3.7 GB total) | +5.4 GB (7.5 GB total) |
| **Swap kullanımı** | 0 (sadece zram) | 6.5 GB (zram + swapfile) |
| **Model loading** | Lazy (ilk inference'da) | Eager (ilk inference'da) |

#### Özet

- **Inference hızı:** LiteRT-LM ~8× daha hızlı (cold), ~5-8× (warm)
- **RAM verimliliği:** LiteRT-LM ~3× daha az RAM, swap kullanmıyor
- **Tool call formatı:** LiteRT-LM OpenAI string (`"{\"due\":...}"`) vs Ollama native dict (`{"due":...}`) — ikisi de doğru, sadece parse farkı
- **Multi-step doğruluk:** İkisi de doğru prompt'la çalışıyor

**Sonuç:** LiteRT-LM Pi 5'te açık ara daha iyi. Geçişe değer.

### E2B vs E4B Tool-Call Doğruluğu (LiteRT-LM)

| Mod | E2B | E4B |
|-----|-----|-----|
| `litert-lm run` (preset/constrained decoding) | ✅ 5/5 PASS (~30s) | ✅ 5/5 PASS (~30s) |
| `litert-lm serve` (OpenAI API, doğru prompt) | ✅ multi-step (~15s/turn) | ✅ multi-step (~35s/turn) |
| RAM (serve modu, model yüklü) | ~3.2 GB | ~4.9 GB |
| Warm latency (simple) | ~2.4s | ~5.9s |

**Not:** Daha önce E4B server'ın `<|tool_call|>` döndürdüğü rapor edilmişti. Bunun sebebi system prompt'ta `get_current_time` talimatının olmamasıydı — doğru prompt'la E4B server da düzgün JSON `tool_calls` döndürüyor.

---

## Bilinen Sınırlamalar

### LAN HTTPS / Mikrofon Erişimi

**Sorun:** LAN üzerinden (`http://10.X.Y.Z:8765`) erişildiğinde tarayıcı `getUserMedia` API'sini bloke eder çünkü HTTP + non-localhost origin "güvenli olmayan bağlam" (insecure context) sayılır. Sonuç: sesli konuşma (mikrofon) çalışmaz. `localhost` veya `127.0.0.1`'den erişimde sorun yok.

**Çözüm A — VPS üzerinden NPM proxy (önerilen):**
Mevcut Nginx Proxy Manager'a (VPS'te, Docker `npm-app-1`) yeni bir proxy host eklenir:
- Domain: `pi.example.com`
- Forward: `10.X.Y.Z:8765` (Pi5'in AWG IP'si)
- SSL: Mevcut Let's Encrypt sertifikası (`*.example.com` wildcard veya yeni cert)
- Telefon `https://pi.example.com` ile erişir → VPS 443 → AWG tunnel → Pi5:8765
- **Artı:** Sıfır ek yapılandırma, mevcut cert geçerli, her yerden erişim
- **Eksi:** Tüm trafik VPS üzerinden geçer (ek gecikme ~5-10ms AWG üzerinden)
- **Kurulum:** NPM admin panel → Add Proxy Host → domain + forward IP/port → SSL sekmesinden cert seç → Save

**Çözüm B — Pi5'te Caddy ile otomatik HTTPS:**
- Pi5'e Caddy kurulur (`apt install caddy`)
- DNS provider API (Cloudflare, etc.) ile DNS-01 challenge kullanılır
- `pi.example.com` DNS kaydı Pi5 LAN IP'sini (veya AWG IP'sini) gösterecek şekilde ayarlanır
- **Artı:** Tam otomatik Let's Encrypt, yerel HTTPS
- **Eksi:** DNS zone'da A kaydı LAN IP'sini göstermeli (public erişim yok, sadece LAN/WG için)
- Cloudflare proxied mode (orange cloud) ile kullanılamaz — DNS-only (gri cloud) gerekir

**Çözüm C — Self-signed cert + mkcert (tam yerel):**
- Pi5'te `mkcert` kurulur (`apt install mkcert` veya `go install filippo.io/mkcert`)
- Yerel CA oluşturulur (`mkcert -install`)
- `mkcert 10.X.Y.Z 192.168.x.x localhost` ile cert imzalanır
- Telefona/laptop'a yerel CA'nın public key'i yüklenir (iOS: profile, Android: CA cert)
- Caddy/nginx ile cert+key kullanılarak Pi5'te HTTPS sunulur
- **Artı:** Tamamen LAN'a bağımlı, internet gerekmez
- **Eksi:** Her cihaza CA trust'ı manuel eklenmeli

**Çözüm D — nginx-proxy-manager (NPM) Pi5'te:**
- Pi5'e Docker + NPM kurulur
- NPM üzerinden self-signed cert veya DNS-01 Let's Encrypt ile HTTPS sunulur
- Artı: Mevcut NPM bilgisi kullanılır, web UI ile yönetim
- Eksi: Pi5'te ek Docker container, NPM'nin kendisi 80/443 ister

**Mevcut yaklaşım (index.html'deki `isSecureContext` kontrolü):**
LAN HTTP'de "Mikrofon HTTPS gerektirir" hatası gösterilir. Bu bir çözüm değil, sadece kullanıcıyı bilgilendirir. Gerçek çözüm için yukarıdaki seçeneklerden biri uygulanmalı.

---

## Kod Tabanı İyileştirmeleri — 29 Temmuz 2026

> Aşağıdaki değişiklikler piSynapse'in kod kalitesi, güvenlik ve bakım kolaylığını artırmak için yapıldı.

### ✅ Altyapı

| Değişiklik | Açıklama |
|---|---|
| **pyproject.toml** | Proje yapılandırma dosyası eklendi — pytest, mypy, ruff ayarları |
| ~~Alembic migrations~~ | ~~`alembic/` dizini + ilk migration~~ — KALDIRILDI (30 Temmuz 2026). Veritabanı schema'sı doğrudan `db.py` içinde. |
| ~~Dockerfile + docker-compose.yml~~ | ~~Multi-stage Docker build~~ — KALDIRILDI (30 Temmuz 2026). Kullanılmıyordu, container çalışmıyordu. |

### ✅ Mimari

| Değişiklik | Açıklama |
|---|---|
| ~~services/ katmanı + DI helpers~~ | ~~`DatabaseService`, `LLMService`, `EmbeddingService` + `main.py` DI helpers~~ — KALDIRILDI (30 Temmuz 2026). Hiçbir router bağlanmamıştı, eski modüller tüm işi yapıyordu. |
| **Lazy loading** | FastEmbed (~470MB) artık sadece embedding gerektiğinde yüklenir (startup'ta eager load yok) |

### ✅ Modül Yapısı

| Dosya | Yeni Yapı |
|---|---|
| `llm.py` → `llm/` | `payload.py`, `chat.py`, `stream.py`, `intent.py`, `utils.py` |
| `tools.py` → `tools/` | `definitions.py`, `dispatcher.py` |
| `routers/chat.py` | Sadece chat, session, memory endpoint'leri |
| `routers/media.py` (yeni) | Transcription (Whisper/Gemma4) + TTS (Piper) endpoint'leri |

### ✅ Güvenlik

| Değişiklik | Açıklama |
|---|---|
| **ProtonMail SSL** | Localhost'ta bypass, remote'ta sertifika doğrulaması zorunlu (`mail.py`) |
| **X-Forwarded-For** | Rate limiter proxy arkasında da doğru client IP'sini görür |

### ✅ Tip Güvenliği

| Değişiklik | Açıklama |
|---|---|
| **`_safe_int()`** | Artık `int \| str` union döndürmek yerine `ValueError` fırlatır — tüm çağıranlar `except ValueError` ile yakalar |
| **retry decorator** | `utils.py`'deki `@retry` dekoratörü IMAP/SMTP işlemlerinde kullanılmaya başlandı |

### ✅ Streaming

| Değişiklik | Açıklama |
|---|---|
| **LiteRT SSE streaming** | LiteRT-LM için gerçek SSE streaming eklendi (önceden non-streaming fallback vardı) |
| **Ollama + LiteRT ortak stream** | Tek `chat_with_ollama_stream()` fonksiyonu iki backend'i de SSE ile çalıştırır |

### ✅ WebSocket

| Değişiklik | Açıklama |
|---|---|
| **`/chat/ws`** | WebSocket chat endpoint'i — session_id ve user_id query param ile, JSON mesaj alışverişi |

### ✅ Test

| Değişiklik | Açıklama |
|---|---|
| **pytest** | 20 test (`test_utils.py`, `test_tools.py`) — utility fonksiyonları, tool definitions, `_safe_int`, arg parser |

---

## Tool İyileştirmeleri — 30 Temmuz 2026

> Modelin tool kullanma yeteneği ve içerik hakimiyeti geliştirildi. Ana hedef: modelin tereddüt etmeden tool çağırması, email/note/task verilerini bağlamda tutması ve kullanıcıya ID sormaması.

### ✅ Tool Definitions — Kesinlik ve Doğrudanlık

| Değişiklik | Detay |
|---|---|
| **`"Only use when the user explicitly asks"` kaldırıldı** | Tüm email/notes/tasks tool'larından — modelin tereddüt sebebiydi |
| **Imperative description'lar** | "Call this when...", "Use this when..." formatı — model ne yapacağını net bilir |
| **list_emails** | "Returns a list you can use to answer questions" — model veriyi kullanabileceğini bilsin |
| **search_emails** | "Searches subject, sender, AND body" — model kapsamı bilir |
| **read_email** | "Use this when the user asks for DETAILS of a specific email" — net kullanım koşulu |

### ✅ System Prompt — 10 Kural

| # | Kural | Hedef |
|---|---|---|
| 1 | Tool'u hemen çağır, tarif etme | Tereddüt kırıcı |
| 2 | Varsayılan değerlerle çağır, "kaç tane" diye sorma | Proaktiflik |
| 3 | Seyrek sonuç gelirse genişlet | Proaktiflik |
| 4 | List verisiyle takip sorularını yanıtla | Kullanıcıya ID/konu sorma |
| 5 | "Yapamam" deme — tool'un var | Tereddüt kırıcı |
| 6 | save_memory sadece kalıcı bilgiler için | Hafıza kirliliğini önleme |
| 7 | Relative dates → get_datetime | Tarih doğruluğu |
| 8 | ISO 8601 formatı | Standardizasyon |
| 9 | Kısa cevaplar | Context ekonomisi |
| 10 | Doğal ve sıcak ton | Kullanıcı deneyimi |

### ✅ Email İçerik Zenginliği

| Değişiklik | Dosya |
|---|---|
| **Body preview 200→300 karakter** | `mail.py:_list_emails()` |
| **Cache preview 100→200 karakter** | `prompt.py:cache_email_context()` |
| **Email context'te Preview satırı** | `prompt.py:build_context()` — model read_email çağırmadan cevap verebilsin |
| **search_emails artık body'de de arar** | `mail.py:_search_emails()` IMAP `TEXT` anahtarı eklendi |
| **search_emails de cache'ler** | `tools/dispatcher.py:search_emails` → `cache_email_context()` çağırır |
| **search_emails çıktısı list_emails ile aynı formatta** | ID + Preview + From/Subject aynı düzende |

### ✅ Calendar/Notes/Tasks Önizleme

| Tool | Yeni Özellik | Dosya |
|---|---|---|
| **list_calendar_events** | Description varsa 100 karakter alt satır | `calendar_ops.py:85` |
| **list_notes** | Her not için 80 karakter content preview | `nextcloud_notes.py:149` |
| **list_tasks** | Her task için 120 karakter description preview | `nextcloud_tasks.py:185-186` |

### ✅ Email ID Takibi — Kritik Düzeltme

**Sorun:** Model `list_emails` çağırıp sonuç alıyor, context'ten düşünce kullanıcıya "hangi ID?" diye soruyordu.

**Çözüm:**
1. `search_emails` artık kullanıcının bahsettiği içeriği bulmak için kullanılır — model kullanıcıya sormak yerine `search_emails(query="Netdata")` çağırır
2. `search_emails` sonuçları da `cache_email_context()` ile cache'lenir — "Recent Emails Context" güncel kalır
3. System Prompt Kural 4: "Do NOT ask the user 'which one' or 'what ID' — just pick the right email from the data you already have"
4. System Prompt CRITICAL bölümü: "If you don't have the data anymore, call search_emails — don't ask the user for an ID"

---

## Gelecek Planı

| Öncelik | Ne Yapılacak |
|---|---|
| 🔴 Yüksek | **Tool call indicator** — chat'te modelin tool çağırdığını gösteren UI ("Takvime bakıyorum..." gibi) |
| 🔴 Yüksek | **Onboarding ekranı** — ilk kurulumda "API key'in bu, şöyle kullan" rehberi |
| 🔴 Yüksek | **Hata mesajları** — net kullanıcı mesajları ("Model yükleniyor, 20sn bekle", "Nextcloud bağlantısı yok") |
| 🟡 Orta | **Nextcloud'suz kullanım** — sohbet + hafıza en azından çalışmalı, email/takvim opsiyonel |
| 🟡 Orta | Test coverage artırma (özellikle dispatcher + mail) |
| 🟡 Orta | FastAPI DI → dependency_overrides ile mock test altyapısı |
| 🟡 Orta | Docker image'i optimize etme (Pi 5'te multiarch) |
| 🟡 Orta | **HTTPS/mikrofon** — Caddy self-signed veya NPM ile çözüm |
| 🟡 Orta | **Performans** — NUM_CTX/batch optimizasyonu ile 13-15s → 10-12s |
| 🟢 Düşük | Session management için Redis cache (opsiyonel) |
| 🟢 Düşük | Observability: Prometheus metrikleri, structured logging |
| 🟢 Düşük | Multi-user authentication (JWT) |
| 🟢 Düşük | Daha fazla dil desteği |
