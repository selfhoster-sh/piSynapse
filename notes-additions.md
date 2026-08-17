## Altıncı Round (2026-08-17)

### Yapılan Değişiklikler

1. **Cursor trail kaldırıldı** — Welcome pseudo-element + JS tamamen silindi. Kullanıcı fikrinden vazgeçti.

2. **Mobil input bar şeffaflığı düzeltildi** — `#input-container` mobilde `backdrop-filter:none` ile birlikte `background-color:var(--surface)` eklendi, böylece mesajlar alttan görünmüyor.

3. **Gönder butonu renklendirildi** — Tamamen şeffaf cam bilye yerine hafif accent gradient (`--accent 18%`) + border + hover glow. Abartmadan, temiz.

4. **WCAG contrast düzeltmesi** — `--text3` #5e5e72 → #7e7e96 (surface'te 4.76:1, AA PASS). `--text4` #404056 → #626276 (surface'te 3.16:1, dekoratif/large text PASS). CSS'te WCAG notu eklendi.

5. **sendMsg() emptyReply bug'ı düzeltildi** — `emptyWarningShown` yerine `terminated` flag kullanıldı. `data.confirm`, `data.error` ve `data.done` dallarının hepsi `terminated=true` yapıyor. finally bloğu sadece bu bayrağa bakıyor. Böylece onay modalı açılırken veya hata oluşurken gereksiz "boş yanıt" mesajı eklenmiyor.

6. **pollHealth .ok class** — CSS'e `.status-dot.ok` kuralı eklendi (base .status-dot ile aynı yeşil).

7. **freshEvents comment** — Fonksiyonun "sadece bugünün etkinlikleri" varsayımına dayandığı belirtildi.

### Manuel Test Senaryoları

1. **Onay gerektiren tool testi** — Sohbete "bir not sil" veya "e-posta gönder" komutu ver. Onay modalı açılırken sohbette "⚠️ Boş yanıt" mesajı **çıkmamalı**. Modal kapatılıp tekrar denenebilir.

2. **Stream hata testi** — Geçersiz/başarısız bir istek gönder (örn. çok uzun bir mesaj veya bağlantı kesintisi simüle et). Sadece **tek ve doğru** hata mesajı görünmeli, "boş yanıt" mesajı **eklenmemeli**.

3. **Mobil input bar** — Glass modda mobilde sohbet sırasında input bar'ın altından mesaj metni **görünmemeli**. Arka plan opak olmalı.

4. **Gönder butonu** — Glass modda hafif accent tonlamalı, hover'da parlaklık artışı + glow, active'de basit basma hissi.

5. **WCAG contrast** — `--text3` (label, timestamp, placeholder) ve `--text4` (timestamp) renkleri yeterli kontrasta sahip olmalı.

---

## Yedinci Round (2026-08-17)

### Yapılan Değişiklikler

1. **Üçüncü görünüm modu: Klasik** — Sade/Cam/Klasik olarak üç mod. Body class: `body.classic-mode`. Keskin köşeler (`--r:8px`), animasyonlar tamamen kapalı (`animation:none!important`), font-weight400, düz/opak yüzeyler. Accent rengi korunuyor (tema seçiminden bağımsız).

2. **Ayarlar > Görünüm sekmesi** — Eski glass-toggle (checkbox/switch) kaldırıldı, yerine 3 seçenekli radio liste (`#mode-list > .mode-option`). Seçili olan `.active` class'ı alır (sol kenar accent çizgisi + arka plan). Tema rengi seçimi bağımsız kaldı.

3. **localStorage migration** — Eski `ps_glass === '1'` → yeni `ps_appearance: 'glass'`. Sıfır/X → `'plain'`. Migration tek seferlik çalışır, eski veri silinmez.

4. **sendMsg() catch bloğu düzeltmesi** — `terminated=true` catch bloğuna da eklendi (network/fetch hatası durumunda). `try` başına yorum satırı: "Yeni bir son durum dalı eklersen `terminated=true` ekle".

5. **STRINGS güncellendi** — `appearanceLabel`, `modePlain`, `modeGlass`, `modeClassic` (tr+en). Eski `glassLabel`, `glassHint`, `glassHintOff` kaldırıldı.

6. **CSS eklentileri** — `.mode-list` / `.mode-option` stilleri. `body.classic-mode` override'ları (sharp corners, no anim, muted surfaces). `.status-dot.ok` kuralı. `freshEvents` varsayım notu.

### Manuel Test Senaryoları

1. **Mevcut kullanıcı (ps_glass=true)** → Sayfayı aç, "Cam" modu seçili gelmeli (migration).
2. **Sade mod** → Ayarlar > Görünüm > Sade → Düz görünüm, animasyonlar var.
3. **Cam mod** → Cam seç → Buzlu cam efektleri, gradient arka plan.
4. **Klasik mod** → Klasik seç → Keskin köşeler, animasyon yok, sakin görünüm.
5. **Tema rengi** → Üç modda da tema rengini değiştir, renk sorunsuz geçmeli.
6. **Dil** → TR/EN değiştir, mod isimleri doğru çevrilmeli.
7. **Sayfa yenileme** → `ps_appearance` localStorage'da saklanmalı, aynı modda kalmalı.
8. **Network hatası** → Bağlantıyı kes, mesaj gönder → Sadece tek hata mesajı, "boş yanıt" eklenmemeli.

---

## Sekizinci Round (2026-08-17)

### Yapılan Değişiklikler

1. **Klasik mod tamamen yeniden tasarlandı** — Kurumsal/ciddi bir karakter: Claude'dan ilham alınmış ama piSynapse'e uyarlanmış. Keskin köşeler (`--r:6px`), animasyonlar tamamen kapalı, düz yüzeyler, ince border'lar, gölge yok. Profesyonel tipografi hiyerarşisi (regular weight body, semibold headings). Flat send button (accent renk solid, glow yok).

2. **Ayarlar düzeni düzeltildi** — `settings-appearance` dikey flex'e çevrildi (`flex-direction:column`). 3 grup (Tema, Dil, Görünüm) alt alta düzgün sığıyor.

3. **Kapsamlı override'lar** — Topbar/sidebar backdrop-filter Klasik modda devre dışı. Tüm hover transform'lar kaldırıldı. Modal/settings box gölgeleri sadeleştirildi. List items, table, code, link stilleri eklendi.

### Klasik Mod vs Sade Mod Farkları

| Özellik | Sade | Klasik |
|---|---|---|
| Köşe radiusu | 16px | 6px |
| Animasyonlar | Aktif (subtleGlow, msgSlideIn, bounce) | Tamamen kapalı |
| Gölgeler | Var (shadow-sm/md) | Yok, sadece border |
| Tipografi | 500 weight | 400 weight |
| Gönder butonu | Accent gradient + glow | Flat solid, no glow |
| Topbar | backdrop-filter blur | Düz solid border |
| Hover | Transform + background | Sadece background |
| Sidebar items | Gölge + active glow | Border + active accent |

### Manuel Test Senaryoları

1. **Sade vs Klasik** → İkisi arasında geçiş yap, fark hemen görünmeli: köşeler keskinleşmeli, animasyonlar durmalı, gölgeler kaybolmalı
2. **Klasik modda tema rengi** → Accent rengi değişmeli ama genel ciddi his korunmalı
3. **Klasik modda mobil** → Temiz ve okunabilir olmalı, border'lar sade görünmeli
4. **Klasik modda sohbet** → Mesaj bubble'ları border ile ayrılmalı, glow olmamalı
5. **Klasik modda ayarlar** → Modal temiz, professional görünmeli

---

## Dokuzuncu Round (2026-08-17)

### Yapılan Değişiklikler

1. **Klasik mod tamamen sıfırdan yeniden yazıldı** — Sade moddan bağımsız, tamamen farklı bir görsel kimlik. Yeni renk paleti, yeni yüzey hiyerarşisi, yeni tipografi, yeni border sistemi.

### Klasik Mod Yeni Renk Paleti

| Değişken | Sade (varsayılan) | Klasik |
|---|---|---|
| `--bg` | `#0a0a0f` | `#08080e` (daha koyu) |
| `--surface` | `#111116` | `#0e0e16` (daha koyu) |
| `--surface2` | `#1a1a22` | `#15151f` (daha koyu) |
| `--border` | `#1e1e2a` | `#252536` (daha parlak) |
| `--accent` | `#f0943a` (turuncu) | `#6e8efb` (mavi) |
| `--text` | `#e2e2e8` | `#d8d8e4` (hafif soluk) |
| `--user-bg` | `#1a1a22` | `#131320` (mavi tonlu) |
| `--r` | `16px` | `8px` |
| `--r-sm` | `10px` | `6px` |
| `--r-chat` | `18px` | `10px` |

### Klasik Mod Görsel Kimlik

- **Renk paleti**: Tamamen farklı — turuncu accent yerine mavi (`#6e8efb`), daha koyu yüzeyler, daha parlak border'lar
- **Tipografi**: Daha sıkı letter-spacing, daha net hierarchy
- **Yüzeyler**: Border ile ayrışma, gölge yok (sadece modal'da)
- **Sidebar**: Item'lar border ile çevrelenmiş, active state accent border
- **Gönder butonu**: Flat solid mavi, opacity efekti
- **Linkler**: Underline + offset, professional
- **Tablolar**: Temiz grid, uppercase header
- **Ayarlar/modal**: Daha derin gölge, backdrop yok

### Manuel Test Senaryoları

1. **Sade → Klasik** → Renk paleti tamamen değişmeli (turuncu → mavi), köşeler keskinleşmeli, animasyonlar durmalı
2. **Klasik → Cam** → Tamamen farklı his (mavi → turuncu, cam efektleri geri gelmeli)
3. **Klasik modda tema rengi** → Mavi accent yerine farklı renk seç, renk değişmeli
4. **Klasik modda sohbet** → Mesaj bubble'ları mavi tonlu user-bg ile ayrılmalı
5. **Klasik modda sidebar** → Item'lar temiz border ile, active state accent border
