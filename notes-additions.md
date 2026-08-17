## Bu Bölüm NOTS.md'ye Yapıştırılacak

---

## 17 Ağustos 2026 — UI İyileştirmeleri, XSS Düzeltmesi, Limit Yükseltme

### Frontend (static/index.html)

**XSS Güvenlik:**
- 50 innerHTML assignment incelendi (27 statik, 18 `esc()`-korumalı, 1 low-risk, 1 açık)
- Açık: ticker/marquee'de `item.text` escape edilmeden insert ediliyordu → `esc(item.text)` ile düzeltildi
- `renderMd()` safe-by-construction (tüm content path'leri `esc()`'den geçiyor)
- `eval()`, `Function()`, `document.write()`, `outerHTML` kullanımı yok — temiz

**Mobil İyileştirmer:**
- Swipe gesture: scroll-edilebilir alanlarda (`code-wrapper`, `pre`, `textarea`, `#msg-input`, `.sess-list`) tetiklenmiyor (`_swipeInScrollable` flag)
- Input bar glass blur: `blur(16px) saturate(150%)`, `rgba(17,17,22,.88)` — opak ama cam hissi korunuyor
- Sidebar toggle: 90ms gecikme + `btn-press` animasyonu (scale .88) + `navigator.vibrate(12)` haptic feedback
- Buton CSS: `#logo-btn.btn-press .logo-icon{transform:scale(.88);filter:brightness(.85)}`

**Glass Toggle Fix:**
- Cam efekti toggle'ına `<span class="track">` eklendi — toggle artık düzgün render ediliyor (checkbox yerine)

### Backend (config.py)

**Limit Yükseltme:**
- `LLM_NUM_CTX`: default 6144 → **8192**, UI max 6144 → **32768**
- `LLM_MAX_OUTPUT_TOKENS`: default 2048 → **4096**, UI max 6144 → **16384**
- piServe `config.json`: `max_num_tokens` 6144 → **8192**
- Pi `.env`: `LLM_NUM_CTX=8192`, `LLM_MAX_OUTPUT_TOKENS=4096`
- piServe servisi yeniden başlatıldı (8192 context aktif)

**Rate Limiting:**
- 30 RPM rate limiter aktif kaldı (muafiyet eklenmedi)
- Sayfa yüklemesindeki 429'lar servis restart'ı ile çözüldü

### Güvenlik Audit Sonucu

| Kategori | Adet | Durum |
|---|---|---|
| innerHTML — statik HTML | 27 | Güvenli |
| innerHTML — `esc()` korumalı | 18 | Güvenli |
| innerHTML — low-risk (yerel data URI) | 1 | Kabul edilebilir |
| innerHTML — açık (ticker `item.text`) | 1 | **DÜZELTİLDİ** |
| eval/Function/document.write | 0 | Temiz |
| Hardcoded secret/API key | 0 | Temiz |
| .env .gitignore'da | — | Doğru |

### Değişen Dosyalar

- `static/index.html`: XSS fix, mobil iyileştirmeler, glass toggle fix, blur artırma
- `config.py`: limit default'ları ve UI max değerleri
- `notes-additions.md`: bu dosya

### Test Senaryoları

1. **XSS**: Ticker'da takvim etkinliği varsa, `<script>` tag'i metin olarak görünmeli, çalıştırılmamalı
2. **Mobil swipe**: Kod bloğunda veya uzun mesajda yatay kaydırma → sidebar açılmamalı
3. **Mobil input bar**: Glass modda sohbet sırasında input bar arkasındaki metin okunabilir ama çok belli olmamalı
4. **Sidebar butonu**: Mobilde logo butonuna bas → hafif gecikme + görsel press efekti + titreşim
5. **Context window**: Ayarlar'dan bağlam penceresi 8192'ye kadar artırılmalı
6. **Max output**: Ayarlar'dan maksimum çıktı 16384'e kadar artırılmalı
