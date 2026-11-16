# "Beni tanı" — hafızaya yükleme şablonu (deneysel)

piSynapse'in `save_memory` aracıyla kalıcı hafıza kayıtları oluşturur. Aşağıdaki mesajı sohbete yapıştır; asistan her maddeyi **ayrı bir `save_memory` çağrısıyla** kaydeder. Kayıt bittikten sonra "beni tanı" testi yap.

> **Not:** Hafıza kayıtları yerel `assistant.db`'de tutulur (git/journal'a girmez). `MEMORY_LIMIT` (Ayarlar → Intelligence, varsayılan 10, max 30) tek istekte enjekte edilen kayıt sayısını belirler — çok kayıt girersen en benzer 10'u gelir, bu yüzden madde sayısını makul tut veya limiti yükselt.

## Mesaj (yapıştır)

```
Aşağıda benim hakkımda kalıcı bilgiler var. Her birini save_memory aracıyla kaydet.

Kurallar:
- Her madde için AYRI bir save_memory çağrısı yap (birden fazla maddeyi tek kayıtta birleştirme).
- content: kısa, tek cümle, bağımsız (başka bağlam olmadan anlamlı olmalı).
- category: personal / preference / habit / work / general — en uygun olanı seç.
- importance: 1 (trivial) – 10 (kritik). Kimlik/temel tercihler 9-10, alışkanlıklar 5-7, trivia 2-4.
- Benim zaten söylediğim veya Core Memories'de zaten olan bir şeyi tekrar kaydetme.
- Tüm maddeler bitince "X adet hafıza kaydedildi" de ve listele.

### Kimlik
- Adım: [adın]
- Yaş/cinsiyet: [...]
- Meslek/rol: [...]
- Konum: [...]
- Eğitim: [...]

### Tercihler
- Tercih ettiğim dil: [...]
- Çalışma saatleri: [...]
- İletişim tarzı: [...]
- Favori araçlar/teknolojiler: [...]
- Favori yemek/içecek: [...]

### Alışkanlıklar
- Günlük rutin: [...]
- Uyku düzeni: [...]
- ...

### İş / Proje
- Şu an üzerinde çalıştığım proje: [...]
- Hedefler: [...]
- Bağlı olduğum ekipler/topluluklar: [...]

### İlişkiler (isteğe bağlı)
- [...]

### Diğer
- [...]
```

## Doğrulama (kayıt bittikten sonra)

1. **"Beni tanı" testi:** "Ben kimim? Ne biliyorsun benim hakkımda?" → asistan Core Memories'den yanıt vermeli.
2. **Retrieval testi:** "Tercih ettiğim programlama dili ne?" → ilgili kayıt getirilmeli (benzerlik ≥ 0.68).
3. **UI kontrolü:** Hafıza panelinden (sidebar → Memory) kayıtları gör, gereksizleri sil.
4. **Limit:** 10'dan fazla kayıt varsa en benzer 10'u enjekte edilir. Daha fazlası için Ayarlar → Intelligence → Memory Limit'i 20-30'a çıkar (max 30).

## İpuçları
- **Kısa, bağımsız cümleler** kullan ("Python ve Rust tercih ederim", "Akşehir'de yaşıyorum") — benzerlik araması böyle çalışır.
- Çok genel cümleler ("ben bir insanım") kaydetme; retrieval'da gürültü olur.
- Aynı şeyi farklı kelimelerle kaydetme (dedup eşiği 0.68 cosine → yakın kayıtlar güncellenir).
- `importance` depolanır ama retrieval **benzerliğe** göre sıralanır; importance bilgilendirme amaçlıdır.
- Kayıtlar kullanıcıya özeldir (`user_id` ile izole); çok kullanıcılı kurulumda başkası göremez.

## Gizlilik
Hafıza kayıtları yerel `assistant.db`'de tutulur — git/journal'a girmez, hiçbir yere gönderilmez (Open-Meteo/Nominatim hariç hiçbir entegrasyon hafızaya erişmez). Silmek için UI'dan veya `DELETE FROM memories WHERE ...` ile.
