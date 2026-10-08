# piSynapse Frontend Denetim Raporu (salt okuma, 26 bulgu)

## Yüksek

- `[ÖNEMLİ: Yüksek] static/ui.js:383 — esc() birebir no-op: replace(/&/g,'&').replace(/</g,'<')... gövde metnini kaçışlamıyor, 168 çağrı noktası korumasız kaldı (regresyon: 7609519, 2026-09-03) — kaçışları &amp;/&lt;/&gt;/&quot;/&#39; olarak geri koy ve bozulmayı yakalayan birim test ekle.`
- `[ÖNEMLİ: Yüksek] static/ui.js:1887 — oturum adı/snippet'i innerHTML'e ham giriyor (esc() no-op + &lt;b&gt; dönüşümü bilinçli ham HTML açıyor), 1945-1946 patchRow da aynı — bu sink'lerde textContent veya DOMPurify kullan.`
- `[ÖNEMLİ: Yüksek] static/ui.js:1768 — NOTES:24 "yenileme sonrası giriş" bug'ının kesin nedeni: /users/session şifre girişi anahtar döndürmez (routers/users.py:97-111), boot kapısı ise getApiKey() doluluğuna bakıyor — kapıyı /users/me 401/403 testine çevir.`
- `[ÖNEMLİ: Yüksek] static/sw.js:61-74 — stale-while-revalidate oturumlu GET'leri (/users, /users/me, /admin/patterns/review, /tools/groups) Cache Storage'a yazıyor: çıkıştan sonra eski kimlik anında servis edilir, hassas liste önbellekte kalır — /users|/admin|/tools|/debug'ı atlama listesine ekle, logout'ta caches'leri sil.`
- `[ÖNEMLİ: Yüksek] static/ui.js:4823 — harici takvim olay başlıkları ve hava durumu özeti (4799-4818) no-op esc ile 4869'da innerHTML'e giriyor: dış kaynaklı depolanmış XSS — ticker metnini textContent ile bas veya DOMPurify'dan geçir.`

## Orta

- `[ÖNEMLİ: Orta] static/sw.js:1 — CACHE_NAME hâlâ 'pisynapse-v55' ama 25+ commit ui.js'yi, 6+ commit ui.css'i değiştirdi; web.html:14/220 asset'leri sorusuz (?v=) yüklüyor — sürümü bump et veya build hash'li query ekle.`
- `[ÖNEMLİ: Orta] static/ui.js:1689 — api() 429'ı bilmiyor (backoff yok); tüm oturumlu çağrılar + /debug beacon'ları tek 30 rpm kullanıcı kovasında (main.py:589, config.py:174) — 429 için Retry-After tabanlı duraklatma ekle, /debug'ı ayrı kovaya al.`
- `[ÖNEMLİ: Orta] main.py:545 — /debug beacon'ları yalnızca X-API-Key kontrolü yapıyor, cookie fallback'i yok (web.html:208 / app.html:209): şifre ile giren kullanıcıların tüm telemetrisi sessizce 401 — session cookie fallback'i ekle.`
- `[ÖNEMLİ: Orta] static/ui.js:1669 — tek bir geçici 401 bile localStorage anahtarını siliyor (setApiKey('')), 1686 da aynısı yapıyor — anahtarı yalnızca /users/session doğrulaması düşerse sil.`
- `[ÖNEMLİ: Orta] static/ui.js:1926 — renderSessions() her tam yeniden çizimde (1882 erken dönüşü yoksa; mesaj sonrası, arama, online/offline) #session-list ve document'e yeni click dinleyicisi ekliyor — 1899'daki _hasDelegation korumasının içine al.`
- `[ÖNEMLİ: Orta] static/ui.js:2147 — her token'da tüm birikmiş metin yeniden marked+DOMPurify'dan geçiriliyor (O(n²)), 2277'de de aynı — render'ı rAF/60 ms throttle ile toplu yap.`
- `[ÖNEMLİ: Orta] static/ui.js:855 — tek dilli sabit metinler (855 'Max 5 images', 1846/1848 Sunucu toast'ları, 1869 "Yeni Sohbet", 3063 'Eşleşen etkinlikler', 3387 Sistem, 3084 'Confirm', 4828 'Memory Active') — STRINGS'e taşı ve t() kullan.`
- `[ÖNEMLİ: Orta] static/web.html:28 — erişilebilirlik metinleri karışık dilde sabit (28 Settings, 44 Search, 54/60 Ara/Sohbetler, 80 Toggle menu, 105/125/131 Think/Upload/Voice; app.html aynı + 86 Türkçesi) — data-i18n veya JS ile t() ile bas.`
- `[ÖNEMLİ: Orta] static/ui.js:1308 — sunucudan maskedelenen '********' (routers/config.py:117) API anahtarı olarak geri geliyor ve her istekte X-API-Key: ******** olarak gönderiliyor — maskeyi getApiKey()'da yok say.`
- `[ÖNEMLİ: Orta] static/ui.js:1806 — her yanıtta iki kez /chat/sessions çağrılıyor (2168 + 5,5 sn sonra 2172), ayrıca arama 150 ms debounce ile (4905-4938) dakikada 30+ istek üretebiliyor — 30 rpm kovasını aşan tekrarları birleştir/önbellekle.`
- `[ÖNEMLİ: Orta] static/ui.js:1711 — boot 401 verince aynı başarısız /config çağrısını bir kez daha yapıyor (1723) ve config'i varsayılana düşürüp sessizce devam ediyor — 401'de tekrar yerine login akışına geç.`
- `[ÖNEMLİ: Orta] static/ui.js:3324 — ayar satırları ${key} ile inline oninput/onclick üretiyor (3295-3324) ve main.py:483-496'da hiç CSP yok — anahtarı dataset+addEventListener ile kur ve CSP başlığı ekle.`

## Düşük

- `[ÖNEMLİ: Düşük] static/ui.js:695 — #think-split/#think-chev hiç yok (web.html:104-108'de yok), buna bağlı ui.css:521-545 ve lv0-lv5 kuralları ölü — referansları ve ölü CSS'i temizle.`
- `[ÖNEMLİ: Düşük] static/ui.js:3284 — '|'.repeat(0) anlamsız no-op; 1914'teki const t=setTimeout i18n t() fonksiyonunu gölgeliyor — ikisini de kaldır.`
- `[ÖNEMLİ: Düşük] static/ui.js:54 — STRINGS'te kullanılmayan çok sayıda anahtar var (obName, obAsync, setSrvHint, loginNeedKey, amoledLabel = 0 kullanım) — taramayla bul ve sil.`
- `[ÖNEMLİ: Düşük] static/manifest.json:7 — background_color/theme_color #000000 iken index.html:6 theme-color #0a0a0f, manifest:24 lang "en" — değerleri HTML ile hizala.`
- `[ÖNEMLİ: Düşük] static/index.html:27 — loader metni Türkçe sabit ("piSynapse yükleniyor…") ve tüm HTML'ler <html lang="en"> (web.html:2, app.html:2) — metni JS'e taşı, dili applyLang ile senkronize et (ui.js:626).`
- `[ÖNEMLİ: Düşük] static/ui.css:148 — .sess-item.active kenarı sabit eski mor rgba(124,108,240,.25), 1357'de ayrıca sabit turuncu glow var — var(--accent) türevine çevir.`
- `[ÖNEMLİ: Düşük] static/web.html:190 — #toast (ui.css:880, z:300) DOM'da #onboard'dan (web.html:193, ui.css:1390, z:300) önce geldiği için onboarding açıkken toast'lar arkada kalır — toast z-index'ini 310'a çıkar.`
- `[ÖNEMLİ: Düşük] static/ui.css:883 — #toast.err koyu paleti sabit (#2a0f0f/#fca5a1), açık temada uyumsuz — danger yüzey değişkenlerine bağla.`
- `[ÖNEMLİ: Düşük] main.py:510 — /static asset istekleri auth muaf ama 120 rpm'lik paylaşımlı IP kamuya açık kovaya giriyor; soğuk yüklemelerde (ui.css/ui.js dahil ~6 istek) NAT arkası kullanıcılar 429 görebilir — /static'i rate limit'ten tamamen çıkar.`
- `[ÖNEMLİ: Düşük] static/sw.js:4 — STATIC_ASSETS '/' ve ikonları içeriyor ama ui.js/ui.css/web.html yok; ilk yüklemede doküman network-first, asset SWR olduğu için yeni HTML + eski JS karışması bir tur sürer — shell asset'lerini precache'e ekle.`
- `[ÖNEMLİ: Düşük] static/ui.js:4134 — showLogin() giriş katmanını açarken arkada loadSessions()/ticker devam ediyor (1771), çıkış yapmış kullanıcıda gereksiz 401 üretir — login açıkken periyodik/arka plan çağrılarını durdur.`

## Olumlu doğrulananlar (kural uyumu)

i18n tr/en 294 anahtar tam eşitlik, 0 eksik/tekrar, tüm `t()` çağrıları mevcut; `eval/new Function/document.write/WebSocket/?k=/insertAdjacentHTML` yok; isSecureContext mikrofon kapıları yerinde (ui.js:935, 1093); `@media (prefers-reduced-motion)` (ui.css:623) ve `#tab-hidden` marquee durdurma var; web/app farkı tam 1 satır (app.html:86); vendor'lar yerel ve güncel (DOMPurify 3.1.6, marked 12.0.2); `/sw.js` main.py:671'den servis ediliyor, kaydı doğru (ui.js:5090); markdown çıktısı DOMPurify'dan geçiyor (ui.js:393/544) — tek zayıf halka, ham string şablonlara giren `esc()`.
