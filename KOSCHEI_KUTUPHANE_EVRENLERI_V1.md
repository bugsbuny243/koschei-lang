# Koschei Kütüphane Evrenleri v1

Durum: **yapı ve envanter belgesi** — her satırın uygulama durumu ayrıca yazılıdır.

Koschei'nin kendi kütüphanesi dört evrenden oluşur:

1. **Marvel Evreni** — gezegenler ve Marvel bekçileri
2. **Matrix Evreni**
3. **Kuantum Fiziği**
4. **Diğer Evrenler ve Karakterler**

Bu evrenlerin tasarımı bugüne kadar birkaç belgeye dağılmıştı
(`KOSCHEI_LIBRARY_UNIVERSE_CONTRACT_V1.md`, `docs/MULTIVERSE_ARCHITECTURE.md`,
`docs/MULTIVERSE_GUARDIAN_MAP.md`, `KOSCHEI_PHYSICS_KERNEL_V1.md`,
`KOSCHEI_GALAXY_CONSTITUTION_V1.md`, `KOSCHEI_LANG_ANA_VIZYON_RAPORU_2026-08-24.md`).
Bu belge onları tek yapı altında toplar; hiçbirinin yerini almaz ve hiçbir
yasayı değiştirmez.

## Temel kural

- Her gezegen, karakter ve yasa **gerçek, test edilebilir bir güvenlik
  ilkesine** karşılık gelir. İsim tek başına özellik değildir.
- Yeni bir isim yalnızca mevcut bekçilerde olmayan **yeni bir değişmez**
  getiriyorsa kabul edilir; aynı görevi yapan ikinci karakter ikinci bir
  alt sistem yaratmaz.
- Hiçbir evren yetki üretmez veya genişletmez. **Bağlantı yetki değildir;
  bilgi yetki değildir; gözlem yetki değildir.**
- Kütüphane evreni yasası: `DISCOVERY != READ != LINK != EXECUTE != DELEGATE != REVEAL`
  — bir modülü bulmak onu okumak, okumak çalıştırmak, çalıştırmak başkasına
  devretmek anlamına gelmez.

## Kütüphanenin katmanları

```text
Görünür dil        ka · vor · shi · thal · nur          (geliştiricinin yazdığı)
      │
Günlük çekirdek    text · list · secure                 (her programın temel araçları)
      │
Dört evren         Marvel · Matrix · Kuantum · Diğer    (güvenlik makinesi)
      │
Evren koordinasyonu  Galaxy · Khar · Veyra · Aevra       (evrenlerin birbirini bozmadan birleşmesi)
```

- **Günlük çekirdek** (`docs/CORE_LIBRARY_V1.md`) metin, liste ve özet gibi
  her programın ihtiyaç duyduğu araçlardır. **Koschei ile yazılmıştır** ve
  `import text` / `import list` / `import secure` ile kullanılır. Dört evren
  bu çekirdeğin üzerine kurulur.
- **Dört evren** dilin arkasındaki büyük güvenlik makinesidir. Geliştirici
  bir sigil yazar; kütüphane ve evren o sigilin gerektirdiği bütün
  güvenceleri otomatik genişletir: *küçük görünür dil, büyük doğrulanmış iç
  makine.*

Durum sütunlarındaki anlamlar:

| Etiket | Anlamı |
|---|---|
| **Koschei'de** | Koschei ile yazılmış Core Library modülü; `ks run` ve `ks build` ile çalışır, Python bekçisiyle aynı kararı verdiği fark testiyle kanıtlanmıştır |
| **Kod + test** | Python ile yazılmış, test edilmiş host modülü var |
| **Kod, test yok** | Modül var ama testi yok |
| **Yalnızca belge** | Tasarım belgede tanımlı, kodu yok |
| **Tanımlanmadı** | Henüz ne görevi ne kodu belirlenmiş |

## 1. Marvel Evreni — Gezegenler

### Gezegen yasası

Gezegen bir arayüz kategorisi değil, bir **güvenlik sınırıdır**. Her gezegenin:

1. kanonik gerçeklik kimliği,
2. açık yetki manifestosu,
3. bağımsız epoch'u,
4. durum taahhüt zinciri,
5. giriş/çıkış kanal politikası,
6. kaynak bütçesi,
7. kanıt akışı,
8. karantina durumu

vardır. Hiçbir gezegen, ikisi de aynı Matrix dokusunda olduğu için başka bir
gezegenin yetkisini devralmaz.

| Gezegen | Güvenlik görevi | Uygulama | Durum |
|---|---|---|---|
| **Vormir** | Kök gerçekliğe giriş. Yüksek değerli yetki ancak gerçek ve geri alınamaz bir yetki azaltma (kurban), taze epoch ve doğrulanabilir kanıtla verilir. Vormir'i bulmak ona girmek demek değildir. | `koschei/vormir_sacrifice_v1.py` | Kod + test |
| Gezegen gerçeklikleri (genel) | Göreve özel dünyalar; her biri yukarıdaki sekiz özelliği taşır ve kendi etki alanıyla sınırlıdır. | `koschei/planetary_console_v1.py` (yalnızca gözlem paneli; yetki üretemez) | Kısmi: gözlem paneli var, gezegen nesnesi yok |
| Diğer Marvel gezegenleri | — | — | **Tanımlanmadı** — her biri için yeni bir güvenlik değişmezi belirlenmelidir |

### Marvel bekçileri

| Karakter | Güvenlik görevi | Yetki kuralı | Uygulama | Durum |
|---|---|---|---|---|
| **Wanda** | Gerçeklik taahhüt zinciri; çatallanma (fork) ve geri sarma (rollback) tespiti | Kabul edilmiş geçmişi yeniden yazamaz | `import wanda` (`koschei/core_library/wanda.ks`); Python referansı `koschei/wanda_reality_integrity_v1.py` | **Koschei'de** |
| **Loki** | Yetkisiz gözlemciler için savunma amaçlı aldatma ve tuzak kanıtı | Yemlerde gerçek sır veya çalıştırılabilir yetki yoktur; geri saldırmaz | `koschei/loki_deception_reality_v1.py`, `koschei/loki_adaptive_topology_v1.py` | Kod + test |
| **Hela** | Geri alınamaz yetki ölümü; ölmüş yetkinin tekrar, eski epoch veya çatallanma yoluyla dirilmesini engeller | Ölü yetki geri gelmez | `import hela` (`koschei/core_library/hela.ks`); Python referansı `koschei/hela_authority_death_v1.py` | **Koschei'de** |
| **Doctor Strange** | Etkiden önce sınırlı gelecek-yol simülasyonu: önerilen yol yetkiyi genişletir mi? | Simülasyon dış etki yapamaz, yetki üretemez | `import strange` (`koschei/core_library/strange.ks`); Python referansı `koschei/strange_future_paths_v1.py` | **Koschei'de** (testleri de taşımayla yazıldı) |
| **Captain Marvel** | Patlama yarıçapı: bir olayın yayılma bütçesi | Bütçe yalnızca korunur veya küçülür; asla büyümez | `import captain_marvel` (`koschei/core_library/captain_marvel.ks`); Python referansı `koschei/captain_marvel_blast_radius_v1.py` | **Koschei'de** |
| **Sonsuzluk Taşları / Gauntlet** | Kritik yetkinin tek noktada toplanmaması; altı güvenlik alanının (kimlik, yetki, bütünlük, davranış, kanıt, kurtarma/zaman) deterministik olarak birlikte onaylaması | Zorunlu alanların hepsi uyuşmadan giriş yok | Belge: `docs/MULTIVERSE_GUARDIAN_MAP.md` | Yalnızca belge |

Yüksek riskli bir işlemin yolu:

```text
Wanda gerçeklik kanıtı → Strange gelecek-yol kanıtı → Gauntlet girişi → etki
  → Captain Marvel yayılma bütçesi → kanıt → yorum
```

İptal Hela'ya, kök yükseltme Vormir'e gider; şüpheli keşif yalnızca Loki'nin
yetkisiz yüzeylerine yönlendirilebilir. Her bekçi kendi başına
**fail-closed** çalışır.

### Koschei'ye taşınan dört bekçi

```ks
import captain_marvel

fn main() {
    let budget = captain_marvel.issue_budget("earth-616", ["earth-838"], 2, 1) or return
    let verdict = captain_marvel.evaluate(budget, "earth-838", 0, 0) or return
    println("{verdict.allowed} {verdict.reason} {verdict.remaining_hops}")
}
```

- Kararlar, gerekçe metinleri (`"hop-budget-exhausted"`, `"future authority expansion"`, …)
  ve hata nedenleri Python bekçileriyle aynıdır;
  `tests/test_marvel_library_v1.py` bunu tohumlu rastgele vakalarla kanıtlar.
- Özetler `secure.digest` ile alan ayrımlı ve uzunluk önekli üretilir
  (`"sha3-256:"` + 64 hex). Bayt düzeni Python sürümünden **bilerek farklıdır**;
  bu yüzden Koschei özetleri Python özetleriyle karşılaştırılmaz, belgelenmiş
  kodlamanın bağımsız bir modeliyle karşılaştırılır.
- Koschei sürümü bir adım daha sıkıdır: her karar fonksiyonu aldığı kaydın
  özetini alanlarından yeniden hesaplar. Sonradan düzenlenmiş veya elle
  kurulmuş bir kayıt (genişletilmiş bütçe, ertelenmiş ölüm epoch'u, yeniden
  yazılmış taahhüt) **fail-closed** cevabı alır: bütçe reddedilir, yetki ölü
  sayılır, zincir uzamaz, çatallanma ve geri sarma var kabul edilir. Özet bir
  imza değildir; kaydı kimin ürettiğini değil, alanlarının değişmediğini
  kanıtlar.
- Python modülleri referans olarak kalır; `matrix_portal_transit_v1.py`
  Matrix taşınana kadar onları kullanır.

## 2. Matrix Evreni

Matrix, **gözlemlenen dünya ile gerçek semantik dünyanın ayrılığını** temsil
eder.

| Öğe | Güvenlik görevi | Uygulama | Durum |
|---|---|---|---|
| **Matrix dokusu** | Yalıtılmış gerçeklikler arasında mesaj ve kanıt taşıma. Bağlantı yetki değildir. | `koschei/matrix_portal_transit_v1.py` | Kod + test |
| **Matrix / Hara** | Matrix, bir Veyra içindeki yerel yürütme gerçekliğidir; Hara o Matrix içindeki programa (Aevra) özel ufuktur. İki program aynı Matrix'i paylaşıp aynı Hara'yı paylaşmayabilir. | `koschei/matrix_reality_v1.py` | Kod + test |
| **Portal geçişi** | Gerçeklikler arası geçiş; kaynak ve hedef taahhütlerine, içerik kimliğine, istenen etkiye ve epoch'a bağlıdır | `koschei/matrix_portal_transit_v1.py` | Kod + test |
| **Ufuk çiti** | Yeni bir Matrix/Hara'ya geçince eski Hara mezara konur; eski ufuktan erişim reddedilir | `koschei/matrix_horizon_fence_v1.py` | Kod + test |
| **Gözlemci izdüşümü (Nyr)** | Gözlemcinin gördüğü yüzey kanonik kimlikleri göstermez (`nur` kökü) | `koschei/nur_nyr_projection_v1.py` | Kod + test |
| **Neo** | Kanonik semantik kimlik ile gözlemcinin gördüğü temsil arasındaki yetkili çözümleme katmanı | Belge: vizyon raporu | Yalnızca belge |
| **Agent Smith** | Tehdit modeli: gözlemlenebilir ortamda kopyalama, tekrar oynatma, kimlik taklidi, yetkisiz yeniden kurma | Belge: vizyon raporu | Yalnızca belge (tehdit sınıfı) |

## 3. Kuantum Fiziği

Kuantum burada "kuantum kodlama" iddiası değildir; **zaman, gözlem, dönüşüm,
durum ve değişken temsil** üzerine modeller ve gerçek kriptografik
gelecek (kuantum sonrası kriptografi) için kullanılır.

| Öğe | Güvenlik görevi | Uygulama | Durum |
|---|---|---|---|
| **Fizik Çekirdeği** | Evrenler arası 12 değişmez yasa (köken zorunluluğu, yetki korunumu, iddia kanıt değildir, bilgi yetki değildir, belirsizlikte reddet, sessiz geri dönüş yok, tek kanonik doğruluk…) | `koschei/physics_kernel_v1.py`, `KOSCHEI_PHYSICS_KERNEL_V1.md` | Kod + test (kayıt). Yasaların 7'si uygulanmış dilim, 4'ü kısmi, 1'i (tek kanonik doğruluk) çatışma durumunda |
| **Kuantum Gerçeklik Sözleşmesi** | Gelecekteki gerçek kuantum arka uçları için kanonik iş tanımı: hazırlama, evrim, ölçüm açık ve özetle bağlı (H, X, Z, CNOT, MEASURE) | `koschei/quantum_reality_contract_v1.py` | Kod + test. Kuantum donanımında çalıştığını iddia etmez |
| **Olay Ufku / Kara Delik / Morth** | Olay Ufku'nu geçen bir program (Aevra) için silinemez bir ölüm kaydı yazılır; Kara Delik'ten silme veya geri getirme yoktur, yeniden doğuş diriliş değildir. Olay Ufku yalıtımı yetkisiz kaynak erişimini, kanonik kimliği hiç göstermeyen tek yönlü bir yüzeye çeker. | `koschei/morth_black_hole_v1.py`, `koschei/event_horizon_isolation_v1.py` | Kod + test |
| **Kripto çevikliği (kuantum sonrası dahil)** | Kriptografi değiştirilebilir kalır ve standart algoritmaları uygulayan denetlenmiş sağlayıcılara devredilir. Koschei özgünlük için yeni kriptografik ilkel icat etmez: özgünlük dildedir, kriptoda değil. Varsayılan bir kuantum sonrası uygulama gelmez. | `koschei/crypto_agility_v1.py` | Kod + test |

## 4. Diğer Evrenler ve Karakterler

| Öğe | Evren | Güvenlik görevi | Uygulama | Durum |
|---|---|---|---|---|
| **Skynet** | Terminator | Çalışma zamanı politika gözcüsü, izin denetimi, anomali çevreleme, kanıt üretimi. Kendisi de yetki ve politika sınırlarına tabidir; sınırsız yetkili bir yapay zekâ değildir. | Belge: vizyon raporu | Yalnızca belge |
| **Khar** | Koschei Galaksisi | Bir uygulamanın Koschei kalabilmesi için uyması gereken açık anayasa yasaları; gizli dosya veya süper kullanıcı değildir | `koschei/khar_constitution_v1.py` | Kod + test |
| **Veyra** | Koschei Galaksisi | Müşteriye özel yaşayan galaksi geometrisi; iki sistem aynı dili konuşup farklı Veyra'da yaşayabilir | `koschei/galaxy_identity_v1.py` | Kod + test |
| **Aevra** | Koschei Galaksisi | Kimliği görünür baytlarının kopyasından büyük olan program varlığı: `copy(bytes) != birth(Aevra)` | `koschei/galaxy_identity_v1.py` | Kod + test |
| **Altı Khar ekseni ve Sathra** | Koschei Galaksisi | `khor` (yer), `sei` (niyet), `rha` (gerçeklik), `vaal` (etki gücü), `teyr` (zaman), `esh` (süreklilik). Kritik işlem altısı aynı olayda birleşmeden olmaz: `5/6 = 0` | `koschei/khar_sathra_v1.py` | Kod + test |

## Bugünkü gerçek durum

- Koschei ile yazılmış olanlar: günlük çekirdek (`text`, `list`, `secure`)
  ve Marvel evreninin dört bekçisi (`captain_marvel`, `hela`, `strange`,
  `wanda`). Hepsi `ks run` ve `ks build` ile aynı çıktıyı verir.
- Diğer evren modülleri hâlâ **Python ile yazılmış host makinesidir**; bir
  Koschei programı onları `import` edemez.
- Özet artık var: çekirdek `sha3_256` işlemi denetlenmiş host uygulamasına
  (Python `hashlib`, Go `crypto/sha3`) devreder; Koschei yeni bir kriptografik
  ilkel yazmaz. Girdi 1 MiB UTF-8 ile sınırlıdır.
- Struct'lar native derlemede de çalışır ve değer semantiğine sahiptir: bir
  alan ataması yalnızca o `let mut` bağlamasını değiştirir.
- Kalan engeller:
  - **Bayt tipi yok.** Özetler hex metin olarak taşınır.
  - **Bit işlemleri yok** (`&`, `|`, `^`, `<<`): hex/base64 gibi
    kodlamalar ve bayt düzeyindeki işler için gerekir.
  - **Map ve generic struct** native derlemede henüz yok.

## Koschei'ye taşıma sırası

1. ~~**Çekirdek:** denetlenmiş bir sağlayıcıdan gelen özet fonksiyonu (kripto
   çevikliği kuralına uygun, değiştirilebilir).~~ **Tamamlandı:** `sha3_256`
   ve `secure` modülü. Bayt tipi hâlâ açık.
2. ~~**Saf mantıklı bekçiler:** Captain Marvel, Hela, Doctor Strange,
   Wanda.~~ **Tamamlandı:** dört bekçi Koschei'de.
3. **Matrix:** portal geçişi ve ufuk çiti.
4. **Gezegenler:** sekiz özelliği taşıyan bir gezegen yapısı; ilk gezegen
   Vormir.
5. **Fizik Çekirdeği** yasalarının Koschei tarafındaki denetimleri.

Her taşıma aynı kurallarla yapılır: modül adı kayıt listesine eklenir ve
özgünlük sözleşmesinden geçer; Python sürümüyle aynı sonucu verdiği fark
testiyle kanıtlanır; `ks run` ve `ks build` aynı çıktıyı üretir; hiçbir
modül yetki taşımaz.

## Yeni gezegen veya karakter ekleme kuralı

1. Hangi **yeni güvenlik değişmezini** getirdiğini yaz.
2. Mevcut bekçilerden hangisinde olmadığını göster.
3. Bu değişmezi ihlal eden durumu **reddeden** bir yol ve testini yaz.
4. Bu belgeye satırını ekle.

İsim, görev ve test birlikte gelmeden hiçbir gezegen veya karakter kanonik
sayılmaz.
