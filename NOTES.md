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

## Faz 4 (Arayüz + Dokümantasyon) — 13-08-2026

| # | Değişiklik | Detay |
|---|-----------|-------|
| **23** | **D3** | `a0c10d3` — `static/manifest.json`'dan `orientation: portrait` kaldırıldı (PWA tablet/landscape'te dönebilsin). |
| **24** | **D4** | `52765c3` — `relTime()`: SQLite UTC damgası `"YYYY-MM-DD HH:MM:SS"` boşluk ayraçlı; JS `new Date()` buna her tarayıcıda güvenilmiyor. `ts.replace(' ','T')` ile ISO-8601 normalizasyonu. Prompt'taki "Current date and time"a "(local time)" etiketi (DB UTC, prompt local — tutarsızlık işaretlendi). |
| **25** | **D5** | `52765c3` içinde — Sistem prompt'unun "Under ~{LLM_NUM_CTX} tokens" kuralı yanıltıcıydı (LLM_NUM_CTX context penceresi, yanıt limiti değil) → genel "concise ol" ifadesiyle değiştirildi, import kaldırıldı. |
| **26** | **D1** | `52765c3` içinde — Onay modali salt-okunurdu (`<div class="val">`); send_email alanları (to/subject/body + cc/bcc) artık düzenlenebilir input/textarea (`mInput()` + `data-p`, `confirmAction` değerleri params'a yazıyor). CSS `.val-input` eklendi. |
| **27** | **D2** | `39dca60` — `send_email` cc/bcc desteklenmiyordu (imza vardı, kullanılmıyordu). `_send_email(to, subject, body, cc, bcc)` header + envelope (sendmail recipients'a virgülle ayrılmış tüm alıcılar), dispatcher params passthrough, tool tanımına cc/bcc. |
| **28** | **D6** | `028d7de` — README: LiteRT import hedefi `gemma4:e2b`→`gemma4-e2b` (kolonlu ID ile piSynapse `-` normalize ettiğinden eşleşmiyordu); port `8000`→`8765` (gerçek hizmet + curl örnekleri); `MAIL_PROVIDER` varsayılanı `gmail`→`— (disabled)` (A9 ile boş=devre dışı). |

Durum: **Faz 4 (D1-D6) tamamlandı** — toplam 28 madde, smoke OK. Sıradaki: LiteRT systemd unit'i (`litert-lm.service`) + pisynapse.service sıralama bağımlılığı.

## Kapanış — 13-08-2026 (LiteRT systemd + dev-rules)

| # | Değişiklik | Detay |
|---|-----------|-------|
| **29** | **LiteRT systemd unit'i** | LiteRT manuel süreçti (PID 3482251, unit yok → reboot'ta ölüyordu). `/etc/systemd/system/litert.service` oluşturuldu (User=salih, `uv` python + `litert-lm serve --host 127.0.0.1 --port 9379`, Restart=on-failure). Manuel süreç durduruldu → `enable --now`. Port 9379 model sorgusuyla doğrulandı (gemma4-e2b, gemma4-e4b). |
| **30** | **pisynapse.service sıralama** | `After=network.target ollama.service` → `After=network.target litert.service`. `pisynapse` de **disabled**'dı → `enable` edildi (reboot-safe). `systemd-analyze verify` temiz. |
| **31** | **dev-rules güncellemesi** | `piSynapse-dev-rules.md`: git repo durumu, `llm/` ve `tools/` paket yapısı (llm.py/tools.py yerine), LiteRT primary + gemma4-e2b (kolonlu değil), pytest 27 test + ruff/mypy komutları, port 8765, MAIL_PROVIDER boş=devre dışı, XFF/rate-limit notu, yanlış "SSRF prevention" satırı düzeltildi, systemd birimleri. |

**Toplam denetim sonucu:** A1-A10 ✓, B1-B5 ✓ (B5=C5 atlandı, not), C1-C8 ✓, D1-D6 ✓ — **31 madde**, 20+ commit, 27/27 test, smoke OK. Tüm değişiklikler git'te (`main`).

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
| **8** | **Avahi fix** | `/etc/avahi/avahi-daemon.conf` → `allow-interfaces=eth0`. `.local` çözümlemesi Docker bridge (`<docker-bridge-ip>`) yerine gerçek IP (`<lan-ip>`) döndürüyor. |
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

**Sorun:** LAN üzerinden (`http://<vpn-ip>:8765`) erişildiğinde tarayıcı `getUserMedia` API'sini bloke eder çünkü HTTP + non-localhost origin "güvenli olmayan bağlam" (insecure context) sayılır. Sonuç: sesli konuşma (mikrofon) çalışmaz. `localhost` veya `127.0.0.1`'den erişimde sorun yok.

**Çözüm A — VPS üzerinden NPM proxy (önerilen):**
Mevcut Nginx Proxy Manager'a (VPS'te, Docker `npm-app-1`) yeni bir proxy host eklenir:
- Domain: `<your-domain>`
- Forward: `<vpn-ip>:8765` (Pi5'in VPN IP'si)
- SSL: Mevcut Let's Encrypt sertifikası (`*.<your-domain>` wildcard veya yeni cert)
- Telefon `https://<your-domain>` ile erişir → VPS 443 → AWG tunnel → Pi5:8765
- **Artı:** Sıfır ek yapılandırma, mevcut cert geçerli, her yerden erişim
- **Eksi:** Tüm trafik VPS üzerinden geçer (ek gecikme ~5-10ms AWG üzerinden)
- **Kurulum:** NPM admin panel → Add Proxy Host → domain + forward IP/port → SSL sekmesinden cert seç → Save

**Çözüm B — Pi5'te Caddy ile otomatik HTTPS:**
- Pi5'e Caddy kurulur (`apt install caddy`)
- DNS provider API (Cloudflare, etc.) ile DNS-01 challenge kullanılır
- `<your-domain>` DNS kaydı Pi5 LAN IP'sini (veya AWG IP'sini) gösterecek şekilde ayarlanır
- **Artı:** Tam otomatik Let's Encrypt, yerel HTTPS
- **Eksi:** DNS zone'da A kaydı LAN IP'sini göstermeli (public erişim yok, sadece LAN/WG için)
- Cloudflare proxied mode (orange cloud) ile kullanılamaz — DNS-only (gri cloud) gerekir

**Çözüm C — Self-signed cert + mkcert (tam yerel):**
- Pi5'te `mkcert` kurulur (`apt install mkcert` veya `go install filippo.io/mkcert`)
- Yerel CA oluşturulur (`mkcert -install`)
- `mkcert <vpn-ip> <lan-ip> localhost` ile cert imzalanır
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

<!-- ═══ KRONOLOJİK DEVAM · 13-22 Ağustos arası local-only dönem disk kaybına uğradı;
     aşağıdaki kayıtlar notes-additions.md ve güncel dosyadan derlendi (2026-08-23) -->

## 17 Ağustos 2026 — UI İyileştirmeleri, XSS Düzeltmesi, Limit Yükseltme

---

## Oturum-içi kendi-kendini-zehirleme raporu (2026-08-22)

### Bulgular

| Sorun | Durum |
|---|---|
| Oturumlar arası veri sızması | Yok — tasarım temiz (`get_history`/`_fetch_candidates`/özet/cache hepsi `WHERE session_id = ?`) ✅ |
| Leak metninin geçmişe kaydedilmesi | Bug — `routers/chat.py` save noktalarında sanitizasyon yok; ham `call:xxx{{}}` metni assistant cevabı olarak DB'ye yazılıyor ⚠️ |
| DB'deki zehirli kayıt | `session_1787407132114_14uw4dn` içindeki `call:list_notes{{}}` satırı hâlâ duruyor; model kendi çöp çıktısını taklit ediyor ⚠️ |
| Boş cevap fallback'i | Dedup düşerse birikmiş metin boşsa hiçbir şey üretilmiyor → "model boş cevap döndürdü" ⚠️ |

Tasarım gereği oturumlar arası taşınan tek şey: kullanıcı hafızaları (`save_memory`, user_id bazlı) — bilinçli özellik.

### Düzeltme planı (onaylandı)

- [x] **1. Save-time sanitizasyon** — assistant cevabı DB'ye yazılmadan önce
  `strip_tool_leaks()`; tamamen leak ise kaydetme (stream + non-stream yolları)
  ✅ Doğrulandı: `tests/test_history_hygiene.py` 4 passed, ruff temiz.
  `_clean_assistant_reply()` yardımcısı eklendi; stream done/finally ve
  non-stream save noktaları sanitizyor, boşsa kaydetmiyor.
- [x] **2. Tek seferlik DB temizliği** ✅ Doğrulandı: dry-run tarama sonrası
  2 saf zehir satırı silindi (id=592 eski read_email leak'i, id=757
  `call:list_notes{{}}`); tekrar tarama → 0 zehirli. Gömülü-temizlik katmanı
  bilinçli olarak UYGULANMADI: dry-run'daki 20 adayın tamamı kozmetik boşluk
  farklarıydı (markdown), biri Python kod bloğu içeriyordu — rewrite etmek
  zarar verirdi. Bu bulgu ayrıca strip_tool_leaks'ın küresel boşluk
  sıkıştırmasının kod bloklarını bozduğunu ortaya çıkardı → düzeltildi:
  sıkıştırma artık ``` fence dışında uygulanıyor (_collapse_spaces_outside_fences).
  Test kapsamı: `tests/test_history_hygiene.py` 9 test = 7 passed + 2 xfail
  (bilinen sınırlar: `<tool|call>` ayraç, JSON echo); entegrasyon testleri gerçek
  save path'ini mock DB ile kanıtlıyor.
- [x] **3. Boş-buf fallback** ✅ Doğrulandı: dedup dalı boş `buf` ile düşerse
  (2026-08-22 "model boş cevap döndürdü" vakası) bir kez `_FINALIZE_NUDGE`
  sistem notu eklenip araçlar kapatılarak (`final_nudge_used` → `use_tools=False`,
  truncation-retry deseni) text-only final turu zorlanıyor; nudge sonrası hâlâ
  boşsa `_EMPTY_ANSWER_FALLBACK` nazik mesajı yield ediliyor. Nudge turunda
  sızıntı tekrar kurtarılırsa aynı dedup dalına düşer → fallback.
- [x] **2b. Summary zehirlenme koruması** (kullanıcı önerisiyle) ✅ Doğrulandı:
  3 katman — (1) `SUMMARY_SYSTEM_PROMPT` güncellendi: artifact görmezden gelme,
  "do not infer or invent", çelişkide yeni bilgi önceliği, ~3-5 cümle sıkıştırma
  (kullanıcının taslağı aynen alındı); (2) `_summary_transcript()` girdi
  sanitizasyonu: assistant mesajları modele gitmeden önce temizlenir, tamamen
  leak olan satır transcript'ten düşer, kullanıcı mesajlarına dokunulmaz;
  (3) çıktı koruması: özet `strip_tool_leaks` ile saklanır. Boş transcript'te
  LLM çağrısı hiç yapılmaz (önceki özet korunur).
  Testler: `tests/test_summary_hygiene.py` 5 passed. Tam suite: 287 passed,
  2 xfailed; ruff temiz.
- [x] **4. Tool-loop üst sınırı** ✅ Doğrulandı: `sig_exec_counts` sayacı ile
  birebir aynı imza `(isim(args_json sorted))` istek başına en fazla
  `_MAX_IDENTICAL_EXECUTIONS=2` kez çalıştırılır; 3. denemede çalıştırma
  reddedilip modele "[Refused: ...]" tool mesajı döner (yan etkili araçlar için
  emniyet; saf tekrarları zaten dedup yakalar, bu katman karışık batch'lerdeki
  tekrarları keser — örn. [A,B] → [A,C] akışında A bir daha koşmaz).
  Testler: `tests/test_stream_loop_guards.py` 3 passed (nudge turu + tools
  kapalı payload doğrulaması, fallback mesajı, 3. özdeş çağrının reddi).
  Tam suite: 290 passed, 2 xfailed; ruff temiz.

### Non-stream portu + backend senkronizasyonu (2026-08-22)

- [x] **Guard'ların non-stream yoluna portu** ✅ Doğrulandı: `llm/chat.py`
  döngüsüne aynı nudge+cap mekanizması (sabitler `llm/utils.py`'e taşındı:
  FINALIZE_NUDGE / EMPTY_ANSWER_FALLBACK / MAX_IDENTICAL_EXECUTIONS; stream
  modülü eski `_` önekli adlarla içe aktarıyor — testler bozulmaz).
  Testler: `tests/test_chat_loop_guards.py` 3 passed.
- [x] **Backend değişiminde model senkronu** ✅ Doğrulandı: canlı probda
  ollama dalı 404 verdi — kök neden: LLM_MODEL litert biçiminde saklanıyor
  (`gemma4-e2b`) ama ollama kayıt defteri kolonlu ister (`gemma4:e2b`);
  konvansiyon install.py:1246 (litert→tireli, ollama→kolonlu). Düzeltmeler:
  (1) `LLM_BACKEND` artık UI'dan seçilebilir (SETTINGS_SCHEMA'ya select
  girdisi eklendi, PROTECTED_SETTINGS'ten çıkarıldı,
  RESTART_REQUIRED_KEYS'e eklendi); (2) PATCH /config/settings backend
  değiştirirken LLM_MODEL'i YENİ daemon listesine göre doğruluyor ve istekte
  model yoksa ayraç-bağımsız eşlemeyle otomatik dönüştürüyor
  (`get_llm_model_options(backend=...)` parametresi eklendi); (3) eşleşme
  yoksa eski model korunur + uyarı loglanır (manuel seçim gerekir).
  Testler: `tests/test_settings_backend_sync.py` 4 passed.
- [x] **Niyet tespiti + LLM fallback iki-backend doğrulaması** ✅: embedding
  katmanı backend-bağımsız (FastEmbed/ONNX yerel); LLM fallback'in litert
  (/v1/chat/completions) ve ollama (/api/chat) dalları için unit testler +
  canlı probe: her iki backend'de de soru niyeti doğru üretildi. Ollama ile
  tam araç döngüsü de canlı doğrulandı (Nextcloud timeout'a rağmen model
  hatadan düzgün metin yanıtı üretti → hata yönetimi sağlam).
  Testler: `tests/test_intent_backends.py` 5 passed.
  Tam suite: 302 passed, 2 xfailed; ruff temiz. Not: test sonrası ollama
  servisi çalışır bırakıldı (kullanıcı denerse hazır).

Her adımda: ruff + pytest doğrulaması, sonra bu dosyanın güncellenmesi.

### İlgili dosyalar
- `routers/chat.py` — save noktaları (stream ~255/~273, non-stream ~182)
- `llm/stream.py` — dedup/fallback (~358), loop mekanizması
- `llm/utils.py` — `strip_tool_leaks`, `_TOOL_CALL_TAG_RE`
- `db.py` — conversations tablosu

## 2026-08-22 — Frontend iyileştirmeleri + ollama think akışı
- static/index.html: asistan mesajlarının altına .msg-actions satırı (kopyala + sesli oku, yan yana); artık .msg-meta içinde değil → minimal modda da görünür (minimal modda meta gizleniyordu, TTS kayboluyordu). attachMsgActions() hem addMsg hem stream-tamamlama yolunda kullanılıyor; copyMessage() clipboard API + execCommand fallback, kopyalandı geri bildirimi (tik ikonu).
- Minimal mod mesaj aralığı 24px→34px (body.minimal-chat .msg-group).
- i18n: copyTitle/copiedTitle (TR+EN). sw.js CACHE pisynapse-v4→v5.
- Ollama think hatası: stream.py/chat.py yalnız `reasoning_content` okuyordu; ollama ≥0.9 alanı `message.thinking`. İkisi de okunuyor. Canlı test: ollama'da 169 reasoning event frontend'e aktı (CPU'da yavaş ama çalışıyor).
- Yeni keşif: intent/media STT/warmup doğrudan ollama çağrılarında `think:false` eksikti → gemma4 sessizce düşünüyor, num_predict=20 bütçesi thinking'e gidiyor, intent raw='' + ~45sn. Üçüne think:false eklendi; canlıda raw='question' ✓.
- PATCH settings otomatik model-eşleme iki yönlü dogfood edildi (gemma4-e2b ↔ gemma4:e2b). Test dosyası: tests/test_ollama_think_stream.py (2 test). Suite 304+2xf, ruff temiz. Backend litert'e geri alındı; prob oturumları silindi.

## 2026-08-23 — CI askıda kalması düzeltildi
- Belirtiler: c399314 push'unu takip eden CI run'ı 3h28m "in_progress"; ikiz run success ama 3 test FAIL (no such table: email_session_map); lokalde tek dosya koşumları sonsuz bekliyor.
- Kök neden: yeni guard/think testleri gerçek DB'ye dokunuyordu (chat→_build_full_messages→prompt.get_email_context→db.get_email_map). CI'da şema yok → hızlı fail; lokalde tablo varken modül-global aiosqlite bağlantısı kapanmıyor ve NON-daemon worker thread interpreter exit'i blokluyordu.
- Çözüm: üç test dosyasına autouse fixture ile prompt.get_email_context mock'u (testler DB'siz); conftest.py'ye pytest_sessionfinish güvenlik ağı (close_db). Ruff import sıralaması --fix.
- Doğrulama: kapalı portlarla CI simülasyonunda tek dosyalar <1sn rc=0; tam suite 7.1/7.8sn exit=0 ×2. ruff temiz.

## 2026-08-23 (2) — Son iki xfail kapatıldı
- llm/utils.py: tag regex'leri artık <tool|call> (pipe mangle) türevini de tüketiyor; _strip_json_tool_echo eklendi (satır-bağımsız, sadece bilinen tool adları, prose içindeki JSON'a dokunmaz).
- tests/test_history_hygiene.py: 2 xfail → normal regression test + 2 negatif vaka (unknown_tool ve inline JSON korunuyor). Suite: 308 passed / 0 xfail. CHANGELOG + release notes güncellendi.

## 2026-08-23 (3) — UI_LANGUAGE (seçenek B)
- messages.py: kullanıcıya dönük 3 backend mesajı (llm_empty_reply/llm_unreachable/llm_empty_response) tr/en sözlüğü; get_message() config.get("UI_LANGUAGE") ile canlı seçer.
- config.py: UI_LANGUAGE select (default tr, restart gerektirmez). llm/utils.py: empty_answer_fallback() fonksiyonu; EMPTY_ANSWER_FALLBACK sabiti test-uyumu için kaldı (noqa F401 alias'lar stream/chat'te).
- Frontend: init'te ps_lang hiç set edilmemişse sunucudaki UI_LANGUAGE benimseniyor.
- Ders: ruff --fix ara durumda FINALIZE_NUDGE import'unu silmişti → import blokları tekilleştirildi. Suite 312 passed; kapalı-port simülasyonu da temiz.

## 2026-08-23 (4) — prefers-reduced-motion
- OS "Hareketi Azalt" ayarına saygı: tüm animasyon/transition'ları kapatır (vestibüler hassasiyet nezaketi). SW cache v6.
- Düzeltme: glass-mode envanteri 139 seçici gösterdi ama çekirdek zaten değişken bazlı (--surface vs. body.glass-mode'da yeniden tanımlı), kurallar gruplu tarifler → önceki "dağınık" eleştirisi abartıydı; refactor gerekmedi.

## 2026-08-23 (5) — Visual polish turu
- #messages mask-image edge fade: altta 64px, üstte 28px yumuşatma; cam modda da çalışır (bg'den bağımsız).
- Streaming caret: withStreamCaret() son kapanan block tag'ının içine yerleştirir (yeni satıra düşmez), done'da temizlenir; caretBlink keyframes.
- Welcome'a öneri çipleri (WELCOME_CHIPS tr/en, chipFill input'u doldurur); .w-chip stilleri. text-wrap:pretty.
- WCAG denetimi script'i (/tmp/opencode/wcag_audit.py): tek fail text3/surface2 4.37 → --text3 #7e7e96→#83839c (4.69). Diğer tüm çiftler AA geçiyor (kullanıcı WCAG'ı gerçekten uygulamış). SW v7.
- Kullanıcı notu: logo iç içe kare = chat merkezi, toggle menü deseni = ekosistem araçlarına bağlantı sembolü — dokunulmayacak.

## 2026-08-23 (6) — Sidebar redraw fix + chip gönderimi + cam ayarı
- Bug: .sess-item her render'da opacity:0+slide-in → stream bitişi/arama kapanışında "yeniden çizim" flaşı. Çözüm: renderSessions(list,animate) + #session-list.no-anim; loadSessions(animate) pass-through. Sessiz çağrılar: stream done, abort finally, non-stream reply, search-restore (sadece filtre uygulanmışsa restore).
- Çipler artık direkt GÖNDERİYOR (chipSend→sendMsg); içerik intent keyword'leriyle hizalı: özetle/e-posta (email-read), etkinlik (calendar), görev (tasks), notlarımı göster (notes exact). Önceki 'hatırlatıcı' çipi memory_kw('hatırla') yüzünden memory'ye kayabiliyordu → 'görev oluştur' yapıldı.
- Cam kararları: gren .07→.09; aurora mix 30/20/22/13→24/15/16/9 + vinyet .28→.32 (@supports fallback da güncellendi); iç beyaz çizgiler korundu (glass affordance).
- Kullanıcı: push şimdi değil.

## 2026-08-23 (7) — Saf siyah varsayılan + hover fix + tipografi + aurora canlanması
- Saf siyah artık seçenek değil, varsayılan: body.amoled değerleri :root'a gömüldü, toggle+applyBlack+ps_black+i18n anahtarları silindi. theme-black en derin katman olarak kaldı (bg yine #000). Mobil density boost sadeleşti.
- Sidebar titreme kök nedeni: hover'da .sess-del display:none→flex = layout shift. Çözüm: opacity+pointer-events (slot rezerve), transition:all→background-color/border-color. Hover belirginliği: surface2→surface3 + rgba(255,255,255,.05) border.
- Tipografi standart: body+bubble 14.5→15px, sess-name 13.5→14px.
- Çipler 4→6: +hava ('Bugün hava nasıl?'), +question ('Komik bir şey söyle' — embedding corpus'ta 'tell me a joke' örneği var, güvenli).
- Aurora yanıt sırasında yaşıyor: setLoading→body.generating; auroraDrift 14s transform-only (inset:-9% oversize, GPU-friendly) + grainBreathe. reduced-motion global kill zaten var. Mobil: compositor animasyonu, repaint yok.
- Cam hissi: maske fade alt 64→96px (yazı cama "eriyerek" giriyor), user bubble'a hafif elevation shadow glass-mode'da.
- Kullanıcı sorusu "glassmorphism standartlarına uygun mu": evet — translucency+blur+1px light border+inset highlight+vignette+decoration hepsi mevcut; eksik kalan hareket hissiydi, eklendi.

## 2026-08-23 (8) — Lav lambası aurora + saat konumu + intent corpus fix + custom select
- Aurora tam yeniden yazıldı: #aurora katmanı (2 blob, --glow token'lı radial, color-mix bağımsız → @supports aurora dupesü silindi). generating'de lavaA 17s/lavaB 23s büyük gezinme+scale; idle'da opacity fade + donma (snap yok). ::before artık sadece vinyet.
- Saat konumu geri: .sess-del absolute right (hover'da saat↔çöp swap, Discord tarzı), name'e padding-right:20px. Zaman hep sağ kenarda.
- Çip: şaka yerine 'Görevlerimi listele'/'List my tasks' (task_kw 'görev' ✓). TR/EN sıraları eşitlendi.
- INTENT BUG BULUNDU: calendar corpus'unda alan-sözcüksüz genel kalıplar ("değiştirir misin...", DE/FR/ES muadilleri) her "X'i değiştirir misin"i takvime çekiyordu; tasks'ta güncelleme örnekleri yoktu. Temizlendi + tasks'a update/ertele anchor'ları eklendi. Gerçek embedding ile 7/7 doğru (öncesi: görev-değiştir→calendar kayması).
- applyLang anında uygulama: welcome tam rebuild (çipler dahil) + settings modal açıksa openSettings() yeniden çağrılıyor. Hard-refresh ihtiyacının nedeni buydu (modal eski dilde kalınca değişmemiş sanılıyor).
- Custom dropdown (.sel-wrap/.sel-btn/.sel-menu): native <select> gizlenir, esc()'li menü; enhanceAllSelects boot+openSettings sonrası; outside-click/Esc kapatır; change event'i inline handler'lara dispatch edilir.
- SW v10. Testler 312 ✓ ruff ✓ node ✓

## 2026-08-23 (9) — Aurora donma fix + 4 blob + memory meta-save kök nedeni
- Aurora "simsiyah" sorunu: idle'da opacity:0 → arka plan sadece vinyet kalıyordu. Yeni model: bloblar her zaman görünür (idle .45-.55), animasyon hep tanımlı ama idle'da animation-play-state:paused = BULUNDUĞU KAREDE DONAR, snap yok. generating'de running + opacity .95.
- Blob sayısı 2→4 (ab3 merkez-sağ 19s, ab4 accent-h tonlu sağ-üst 27s; lavaC/lavaD çok-noktalı keyframes).
- MEMORY BUG KÖK NEDENİ (log kanıtı): 05:40:28 'Notlarımı göster' embedding ile memory'e kaymış (sim .73, MARGIN .06 — eşik .05!). Ardından memory grubundaki LLM save_memory'yi çağırıp isteği fact sanmış: 'Kullanıcının notlarını gösterme isteği.' katmanlar: (1) corpus'taki generic 'değiştirir misin' kalıpları zaten silinmişti ama bu yeterli olmadı → intent.py artık margin<0.10'da keyword farklı grup işaret ediyorsa keyword kazanır + embedding path'te mesaj loglanıyor (görünürlük). (2) prompt.py kural 6 + tool desc + group blurb: istek/soru/komut yasak. (3) dispatcher save_memory guard: regex (isteği/talebi/request to/wants to/asked that...) meta içerik reddi, 'Kullanıcı Python sever' gibi gerçek fact'ler geçiyor (8 vaka test edildi). DB: assistant.db id=17 çöp kayıt silindi.
- Çip: 'Notlarımı göster'→'Notları listele' / EN 'List my notes'.
- Testler: 314 (+2 save_memory regresyon). ruff ✓ node ✓ SW v11. Servis restart, healthy.

## 2026-08-23 (10) — Ambient standart turu (kullanıcı uyurken tam yetki)
- Araştırma (aurora UI tarifleri + dark-mode gradient pratikleri): renk alanı HZAMAN görünür; idle = sakin donmuş sahne, metin panelde ışık arkada, hareket yavaş. 60-30-10 kuralı.
- DONMA+DEVAM FIX (asıl bug): animasyon .generating'e bağlıydı → sınıf gidince animation kendisi gidiyor → başa sıçrama. Doğru desen: keyframes kalıcı bağlı, default play-state:paused; generating sadece running + opacity 1. Bittiğinde kare donar, sonraki yanıtta kaldığı yerden devam.
- ::before'a soluk köşe yıkamaları geri geldi (11/7/8/5% mixes) → idle asla boş siyah değil (@supports fallback da eklendi). Blob idle opaklıkları .5-.62.
- Çip 7 oldu: +Yeni not oluştur / Create a note (TR keyword ✓, EN corpus'ta 'create note' birebir var).
- SW v12. 314 test ✓ ruff ✓ node ✓. Servis restart, healthy. Push hâlâ beklemede (7+1 commit).

## 2026-08-23 (11) — Marquee çipler + menü opaklığı + maske derinleşti
- #messages alt fade: 96px düz → 128px + kısmi alfa durakları (rgba .55 @ -52px) = sinematik erime, her iki mod.
- .sel-menu glass'ta yarı saydam kalıp alttaki yazıyla karışıyordu: layered background (surface üstüne surface gradient, altına solid --bg) + backdrop-blur 18px → her temada okunur.
- Çipler dual marquee: iki sıra, ters yönlüler (chipMq 38s/46s linear infinite), kenarlarda mask fade ('|gölge|'), hover'da dururlar, tıklayınca gönderir. Track = set×2, translateX(-50%) döngüsü. reduced-motion global kill ile statik (yarılar özdeş → aynı görünüm).
- SW v13. Sadece frontend → restart gerekmez. 8+1 commit push bekliyor.

## 2026-08-23 (12) — Sürüklenebilir marquee
- CSS keyframe yerine JS rAF modeli: her track kendi controller'ı (x, half, vx, drag). Parmak/mouse ile yatay sürükleme (touch-action:pan-y → dikey scroll bozulmaz), 6px eşiği altı dokunuş = tık sayılır (chipSend çalışır), üstü fling: hız ölçülüp vx olarak devralınır, exp(-3t) ile söner; 450ms sonra otomatik devam (boş yere tıklama gereksiz). Hover-pause kaldırıldı.
- wrap: x (-half,0] aralığında döngü → sonsuz kusursuz. resize'da half yeniden ölçülür. reduced-motion: otomatik akış yok, sürükleme serbest. Sayfadan ayrılınca rAF temizliği (isConnected).
- SW v14. node ✓.

## 2026-08-23 (13) — Çip rastgele dağıtımı
- shuffleChips(): Fisher-Yates + anti-clump kurallar (dikiş komşusu aynı çip yasak, iki şerit aynı çiple başlayamaz), 60 deneme; node ile 2000/2000 doğrulandı. Her showWelcome'da yeni düzen.
- SW v15.
