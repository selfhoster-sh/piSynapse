# 06 — Installer / Test / CI / Docs Analizi (install.py, pyproject, requirements, ci.yml, playwright, README, NOTES.md, CHANGELOG)

**Yöntem:** salt-okunur statik analiz (1714 satır install.py, 56 test dosyası/767 test, ci.yml, pyproject, requirements*, README/CHANGELOG/docs). Ortamda fastapi/pytest/ruff yüklü olmadığı için suite **çalıştırılamadı**; bulgular grep/python-parse ile doğrulandı, uydurma yok.

## 1) GÜVENLİK

- `[ÖNEMLİ: Orta] install.py:1318-1324 — cryptography import'u düşerse MAIL_CREDS_KEY için `secrets.token_urlsafe(32)` yazılıyor; bu değer Fernet'te "Incorrect padding" hatası verir (5/5 denemede), anahtar .env'e girip rerun'da korununca tüm kimlik bilgisi kaydı sessizce `False` döner — fallback'i Fernet-uyumlu üret (veya üretilemiyorsa .env'e yazmadan hata ver).`
- `[ÖNEMLİ: Orta] install.py:1442-1446 — .env önce `write_text` (umask 022 → 0644) ile yazılıp sonra chmod 0600 yapılıyor, chmod `except OSError: pass` ile yutuluyor; API_KEY/MAIL_CREDS_KEY hem yazım penceresinde hem hata durumunda dünya-okunur kalabilir (NOTES kural 2 ihlali) — `os.open(..., O_CREAT|O_WRONLY, 0o600)` ile yaz ve başarısızlığı kullanıcıya göster.`
- `[ÖNEMLİ: Orta] install.py:858-863 ve 1612-1614 — üniteler öngörülebilir `/tmp/piserve.service` / `/tmp/pisynapse.service`'a yazılıp `sudo cp` ile kopyalanıyor; yazımdan cp'ye kadar içerik değiştirilirse root yetkisiyle keyfi systemd unit'i kurulur — geçici dosyayı `mkstemp` ile üret ya da `sudo tee` ile doğrudan yaz.`
- `[ÖNEMLİ: Orta] install.py:490,1012,1088 — get-pip.py, ollama install.sh ve Piper sesleri checksumsiz indiriliyor (repoda `sha256/hashlib/checksum` hiç yok) → fix-plan-2026-09-09.md:139'daki K7 "checksum doğrulamalı indirme" hâlâ karşılanmamış — her indirilen artefakt için SHA256 doğrula.`
- `[ÖNEMLİ: Orta] install.py:545-547 — `_run()` timeout almadan `subprocess.run` sarmalayıcısı; 977 (`litert-lm import`) ve 1028 (`ollama pull`) bunu çağırdığı için ölü bağlantıda kurulum süresiz asılı kalır — `_run`'a varsayılan `timeout=900` ekle.`
- `[ÖNEMLİ: Orta] install.py:1012,1088 — `curl -fsSL` / `curl -fSL` çağrılarında `--max-time` yok (667/680/1059'da var) — tüm curl çağrılarına mutlak süre sınırı koy.`
- `[ÖNEMLİ: Orta] install.py:1480 ve 1634 — hem systemd `ExecStart` hem de özet komutu `--host 0.0.0.0:8765` sabit; port .env'de yok, firewall adımı yok → docs/server-audit-2026-09-09.md:319 (A-Y2) ve fix-plan:139 "default 127.0.0.1" uygulanmamış — host/port'u .env'e taşı, default'u 127.0.0.1 yapıp LAN'ı bilinçli aç.`
- `[ÖNEMLİ: Orta] install.py:132-146 + 321/339 — `_pkg_install` her paketleyicide `sudo` kullanıyor, `-n` yok; `ask_yesno` default'u True olduğu için BATCH_MODE'da bile (321, 339) sudo'ya girer ve parola sorulamayan ortamda kurulum askıda kalır — batch'te `sudo -n` kullan, başarısızsa açık hata ver.`
- `[ÖNEMLİ: Orta] credstore.py:21-38 — `MAIL_CREDS_KEY` eksikken canlı `ENV_PATH` dosyasına append ediliyor; yalnızca test_credentials.py ve test_provision_owner.py anahtarı set ettiği için şu an kurtuluyor, unutulan tek test repo .env'ini kirletir — conftest'e MAIL_CREDS_KEY default'u ekle veya ENV_PATH patch'ini zorunlu kıl.`
- `[ÖNEMLİ: Düşük] install.py:779-790 — `litert-server.log` varsayılan umask ile (0644) açılıyor, non-systemd `Popen` yolunda unit'teki `UMask=0077` geçerli değil — log dosyasını 0600 aç veya o yola da umask uygula.`

## 2) TUTARSIZLIK

- `[ÖNEMLİ: Orta] pyproject.toml:10-25 — `dependencies` listesinde `bcrypt` ve `cryptography` yok (requirements.txt:6-7'de var; db.py:2561/2581 `import bcrypt`) → `pip install .` eksik bağımlılıkla kurulur — pyproject'i requirements.txt ile senkronla.`
- `[ÖNEMLİ: Orta] pyproject.toml:33-34 — `py-modules` 12 modüllü, repoda 22'si var; retrieval, messages, auth, tool_verification, credstore, textnorm, title, corpus_feeder, provision_owner, reembed_all eksik (routers/chat.py:42 `from retrieval`, llm/chat.py:14 `from messages`) → `pip install .` ImportError üretir — listeyi tamamla veya paketlemeyi iptal et.`
- `[ÖNEMLİ: Orta] .github/workflows/ci.yml:26,34 — CI `requirements.txt` (`>=` aralıklar) ile kuruyor; `requirements-lock.txt` hiçbir yerde install edilmiyor (yalnız tests/test_install_template.py:138 adları kontrol ediyor) ve pip-audit sadece lock:4'teki yorum → NOTES "lock pin enforcing" yarıya inmemiş — CI'ı lock ile kur, pip-audit job'ı ekle.`
- `[ÖNEMLİ: Düşük] .github/workflows/ci.yml:30 — compileall listesi auth.py, corpus_feeder.py, credstore.py, messages.py, provision_owner.py, reembed_all.py, textnorm.py, title.py ve litert_serve/ içermiyor — listeyi `*.py` taramasıyla otomatikleştir.`
- `[ÖNEMLİ: Düşük] .github/workflows/ci.yml:4-5,32-35 — push+pull_request PR'da çift koşu, `ruff format --check` ve mypy hiç çalışmıyor (pyproject.toml:62 "E501 ruff format ile zorlanıyor" iddiası fiilen uygulanmıyor) — koşulları ayıkla ve format/mypy adımı ekle.`
- `[ÖNEMLİ: Düşük] .github/workflows/ci.yml:21,27,34 — tek Python 3.11 (requires-python >=3.10), pytest/ruff pinlenmemiş, pip cache yok — 3.10+3.12 matrix, pinli test araçları ve cache koy.`
- `[ÖNEMLİ: Orta] docs/port-contract.md:109-118 — "test_user_isolation (9)", "test_write_integrity (5)" ve "648 passed at freeze" bayat; gerçek 16, 6 ve 767 test / 56 dosya — kabul listelerini güncel sayılarla güncelle (diğer satır ref'ı :31 `llm/chat.py:98` → gerçek llm/chat.py:105).`
- `[ÖNEMLİ: Orta] docs/tool_intent_analysis.md:21 — embedding modeli `paraphrase-multilingual-MiniLM-L12-v2` (384-dim) gösteriliyor; config.py:208 default'u mpnet-base-v2 (768-dim) ve NOTES Phase 2a bunu zaten değiştirmiş (artı :10 satır 389-396 → definitions.py:411, :13 satır 418 → :448, :44-47 grup 4/4/6 → 6/5/7, :228 "P3 upgrade path") — dokümanı gerçek değerlerle yenile.`
- `[ÖNEMLİ: Düşük] NOTES.md:368,1064,1415 — üstü çizilmemiş "test_install_template (9 tests)" (gerçek 12), "27 tools" ve "22 tools" (gerçek 23) iddiaları duruyor — düzelt veya tarihleyip çiz.`
- `[ÖNEMLİ: Orta] docs/fix-plan-2026-09-09.md:128,139 — "`==` pin + lockfile + pip-audit gating (Y18)" ve "checksum doğrulamalı indirme (K7)" karşılanmamış (hiçbir yerde `==` pin yok, checksum yok, pip-audit hiç çalışmıyor) — Faz 7/Y18 kalemlerini kapatana kadar açık tut.`
- `[ÖNEMLİ: Düşük] docs/server-audit-2026-09-09.md:319-323 — A-Y2/A-Y3 satır ref'ları (install.py:1346,1377,1255) bayat ve A-Y2 hâlâ çözüm değil (port 0.0.0.0 sabit) — satır numaralarını güncelle ve maddeyi işaretle.`
- `[ÖNEMLİ: Orta] README.md:299-303 — `/chat/memories?user_id=default` + "Delete all memories" örnekleri yanlış: routers/chat.py:788-796 `list_memories` client user_id'yi yok sayar, DELETE `/memories?id=...` kullanır — README API bölümünü canlı router'lardan yeniden üret.`
- `[ÖNEMLİ: Düşük] README.md:126,149,221 — "installer generates config.json from config.example.json" (gerçek: install.py:715 inline dict yazıyor), `static/piSynapse_Icon.svg` (dosya repo kökünde) ve quickstart `--host 0.0.0.0` (fix-plan'ın 127.0.0.1 kararıyla çelişiyor) — README ağacını ve komutunu gerçekle hizala.`
- `[ÖNEMLİ: Düşük] CHANGELOG.md:24-42 — [2.0.0] altında `### Security` (24, 39) ve `### Fixed` (29, 42) ikişer kez tekrar (Keep a Changelog aykırı) — birleştir.`
- `[ÖNEMLİ: Düşük] docs/mail-accounts-2026-09-09.md:36 — "test_credentials.py (6 tests)" gerçek 9 — dokümanı düzelt.`

## 3) DEĞİŞİKLİK GEREKSİNİMİ

- `[ÖNEMLİ: Orta] NOTES.md:19 (kural 7: pre-push secret tarama) — kural hiçbir yerde uygulanmamış: `.git/hooks/` yalnızca `.sample`, CI'da gitleaks yok, repoda secret-scan betiği yok — pre-push hook + CI adımı ekle.`
- `[ÖNEMLİ: Orta] NOTES.md:26,321 — "requirements-lock.txt + pin-enforcing test" ve "pip-audit networked gate" deniyor; test yalnızca lock↔requirements **ad** kapsamasını, sürüm drift'ini değil doğruluyor ve pip-audit hiç çalışmıyor — sürüm eşitliği assertion'ı + pip-audit job'ı ekle.`
- `[ÖNEMLİ: Orta] tests/test_install_template.py:25-163 — 12 test seçilmiş anahtarları ve 2 korunan anahtarı denetliyor; tam `template ≡ example.env` anahtar-kümesi/çift yönlü eşitlik ve .env 0600 eşitliği test edilmiyor (statik karşılaştırmam tuttuğu için bug yok, regresyon koruması yok) — tam key-set + mode assertion'ı ekle.`
- `[ÖNEMLİ: Orta] playwright.config.js:23-28 — webServer `python -m uvicorn main:app --port 8765` (ortam python'u, venv değil), `DB_PATH` override yok ve `reuseExistingServer: true` → e2e canlı `assistant.db`'ye yazar (NOTES kural 4/7 ihlali) — e2e'yi tmp DB + venv python ile başlat.`
- `[ÖNEMLİ: Düşük] package.json:11-12 — `@playwright/test`/`playwright` 1.40.0 (lock'ta "deprecated" yazıyor) sabit ve e2e CI'da hiç koşmuyor — sürümü güncelle ve CI'a e2e job'ı ekle.`

## 4) İYİLEŞTİRME

- `[ÖNEMLİ: Orta] install.py:310,366-367 — `step_system_deps` `missing` listesi topluyor ama doluysa ne özet uyarı basıyor ne de kalıcı sorunu raporluyor; venv/build-tools kurulumları hiç `missing`'e girmiyor (350-366) — sonunda "N eksik: ..." özeti ver ve tüm adımları listeye kat.`
- `[ÖNEMLİ: Orta] install.py:896-927 — `_predownload_ml_models` tek deneme, `capture_output=True` (kullanıcı neden başarısız göremiyor), retry/geri bildirim yok; bilinen model-indirme bug'ının ilk temas noktası — stderr'i göster, 2 deneme + basit backoff ekle.`
- `[ÖNEMLİ: Düşük] install.py:583 ve 599-601 — `Path(os.path.dirname("~/Library/Python/3.*/bin/x")).glob(basename)` asla eşleşmez (dizinde `*` literal), macOS'ta pip ile kurulan uv/litert-lm adayları ölü kod — glob desenini `Path(...).parent` üzerinden yap.`
- `[ÖNEMLİ: Düşük] install.py:1412 (preserved_keys) — yeniden çalıştırmada template'de olup korunmayan (elle eklenmiş) .env anahtarları sessizce siliniyor — bilinmeyen anahtarları koru ya da en azından özette listele.`
