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
| Diğer Marvel gezegenleri | Aşağıdaki taramada tek tek ele alındı | — | 6 aday, 11 örtüşen, 6 tanımlanmamış |

### Gezegen taraması

Marvel Sinematik Evreni'nde görünen gezegen ve diyarların hepsi tek tek
incelendi. Çizgi romanlarda yüzlerce gezegen vardır; bu tarama filmlerde
görünenlerle sınırlıdır. Her biri için tek soru soruldu: *mevcut bekçilerde
olmayan hangi güvenlik değişmezini getirir?*

Durum etiketleri:

- **Aday:** yeni bir değişmez öneriyor. Henüz kodu ve testi yok, bu yüzden
  kanonik değil.
- **Örtüşüyor:** anlamı mevcut bir bekçide zaten var. Ayrı bir alt sistem
  açılmaz; isim istenirse o bekçiye takma ad olur.
- **Tanımlanmadı:** henüz ayrı bir güvenlik görevi bulunamadı.

| Gezegen | Filmdeki rolü | Önerilen değişmez | İlişkisi | Durum |
|---|---|---|---|---|
| **Titan** | Thanos'un, kontrolsüz büyümeyle çöken dünyası | Her programın açık bir **bellek bütçesi** vardır. Tükenme her çalıştırıcıda aynı Koschei hatasıyla, tanımlı bir noktada durur. Host çökmesi veya yarım kalmış durum oluşmaz. | Gezegen yasasının 6. özelliği (kaynak bütçesi) bellek için hiç uygulanmadı. Adım ve çağrı derinliği bütçeleri var, bellek bütçesi yok. | **Aday** (PHP2Shell CVE-2026-109618) |
| **Nidavellir** | Cücelerin yıldız ocağı: Stormbreaker ancak ocak tam ısındığında dövülür | **Ya tam ya hiç:** bir değer, kayıt veya kalıcı yazma ya tamamen oluşur ya hiç oluşmaz. Yarıda kesilen yapım iz bırakmaz; temizlik kodu yarım veriyi asla okumaz. | Struct kurucusu (`MirStructFinish`) ve kurtarma günlüğü parçalarını sağlıyor. Kesinti altında tek bir değişmez olarak kanıtlanmadı. | **Aday** (CVE-2026-109618) |
| **Knowhere** | Herkesin uğradığı ortak liman | **İstekler arası kalıntı yok:** uzun yaşayan bir hizmette her istek yeni bir gerçeklikte çalışır. Bir isteğin durumu sonrakine ulaşamaz; işçi yeniden kullanılmadan önce istek kapsamının boş olduğunu kanıtlar. | Matrix ufuk çitinin (eski Hara mezara konur) istek ölçeğinde uygulaması | **Aday** (CVE-2026-109619) |
| **Sakaar** | Solucan deliklerinden düşen her şeyin vardığı, Grandmaster'ın yargıladığı gezegen | **Örtük giriş işlemi yok:** dışarıdan gelen veri, program istemeden işlenmez. Çekirdek düzeyinde örtük ayrıştırma, yükleme ilerlemesi veya oturum yazımı yoktur. Ayrıştırma kendi bütçesiyle yapılır; başarısızlık yarım değer değil `Error` değeridir. | Bugünkü serve dilimi bunu sağlıyor (gövde `String` olarak döner) ama yazılı bir değişmez değil | **Aday** (CVE-2026-109619'un `session.upload_progress` yolu) |
| **Xandar** | Nova Corps: kayıtlar ve yasa | **Bilinen açık kabul edilmez:** açık bildirimindeki bir yapıt (bağımlılık, runtime, araç zinciri) kabul edilmez. Karar yapıtın **içerik özetine** bağlıdır, kendi bildirdiği sürüm etiketine değil. | Module Lock zaten özet kullanıyor; açık bildirimi girdisi hiçbir yerde yok. Bildirimden önceki saldırıları yakalayamaz. | **Aday** (haber: yüz binlerce hizmet eski sürümde) |
| **Morag** | Terk edilmiş gezegen, harabe tapınak | **Desteği biten yapıtın süresi dolar:** destek penceresi geçince, adı belli bir bakımcının tarihli yama beyanı olmadan kabul edilmez. | Xandar'dan farklı: bilinen açık olmasa da süre dolar | **Aday** (PHP 8.1 ve öncesi resmî yama almıyor; 23 milyon hizmet bu dallarda) |
| Ego | Başka dünyalara tohum eken yaşayan gezegen | Sonradan uyanan gömülü davranış | `library_behavior_baseline_v1` (yeni etki = yetki farkı) ve yetki modeli | Örtüşüyor |
| Hala | Kree başkenti, Supreme Intelligence | Merkezî yapay zekâ kararının sınırı | Skynet | Örtüşüyor |
| Asgard | "Asgard bir yer değil, bir halktır" | Kimlik konumdan bağımsızdır | Aevra; kanonik kimlik ile fiziksel konum ayrımı | Örtüşüyor |
| Jotunheim | Kadim Kışlar Sandığı (dondurma) | Kabul edilmiş yapıt dondurulur | Wanda ve Module Lock | Örtüşüyor |
| Svartalfheim | Karanlık Elfler, diyarların Yakınsaması | Hizalanan gerçeklikler birleşmez | Gezegen yasası: aynı Matrix dokusu yetki devretmez | Örtüşüyor |
| Muspelheim | Surtur, Ragnarok ateşi | Ele geçirilmiş gerçekliği son çare olarak yok etmek | Morth Kara Delik, `library_compromise_recovery_v0` | Örtüşüyor |
| Hel / Niflheim | Hela'nın diyarı | Ölü yetki geri gelmez | Hela | Örtüşüyor |
| Kyln | Galaksi hapishanesi | Karantina | Gezegenin 8. özelliği, `library_quarantine_contract_v1` | Örtüşüyor |
| Sovereign | Uzaktan kumandalı insansız gemilerle savaşan halk | Uzak denetçi yalnızca sınırlı kanaldan iş görür | `universe_remote_observer_v1` | Örtüşüyor |
| Midgard (Dünya) | İnsanların gezegeni | Host gerçekliği, verilmeyen yetkiyi kullanamaz | Dilin temel ilkesi: ortamdan gelen yetki yok | Örtüşüyor |
| Kuantum Diyarı | Ant-Man | — | 3. bölüm (Kuantum Fiziği) | Örtüşüyor |
| Vanaheim, Alfheim, Contraxia, Berhert, Torfa, Zen-Whoberi | — | — | — | Tanımlanmadı |

Altı adayın hepsi Ekim 2026'daki PHP2Shell olayından çıkan derslere
dayanır (aşağıda). Hiçbiri kod ve test gelmeden kanonik sayılmaz.

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

## PHP2Shell'den dersler (Ekim 2026)

### Ne oldu

- **İki açık:** CVE-2026-109618 ve CVE-2026-109619. İkisi de CVSS v4.0'da
  9.2 puan aldı ve kimlik doğrulamasız uzaktan kod çalıştırmaya izin
  veriyor. Web isteği sunan her PHP kurulumunu etkiliyor (mod_php, PHP-FPM,
  php-cgi, FrankenPHP, LiteSpeed). Son on yılda çıkan, 5.4'e kadar her
  sürüm en az birinden etkileniyor.
- **CVE-2026-109618 (bellek tükenmesi):** bir yapı, girdisi için bellek
  ayrılmadan önce "girdi var" diye işaretleniyor. Ayırma `memory_limit`
  sınırını aşınca girdi eski heap verisini tutuyor. Başarısız isteğin kendi
  temizlik kodu da bu yarım veriyi okuyor ve ona göre dallanıyor.
- **CVE-2026-109619 (bayat global durum):** isteğe bağlı iç durum, işaret
  ettiği bellekten uzun yaşıyor. Aynı işçideki sonraki istek, durum
  sıfırlanmadan onu kullanabiliyor. Bu, use-after-free, bellek sızıntısı
  (parolalar, oturum jetonları, API anahtarları) ve işçi yetkisiyle kod
  çalıştırma demek.
- **Yama:** 8.2.35, 8.3.36, 8.4.27 ve 8.5.12. PHP 8.1 ve öncesi resmî
  güncelleme almıyor. Güvenlik ekibi yalnızca 7.4, 8.0 ve 8.1 için asgari
  kaynak yamaları verdi. PHP'ye göre hiçbir ayar açıkları tamamen kapatmıyor.
- **Dünya (Censys canlı paneli, DonanımHaber'in aktardığı an):**
  - 21 Ekim'den bu yana etkilenen sürümde görülen hizmet: 41.433.822. Son
    taramada hâlâ etkilenen: 33.500.304.
  - Düzeltilmiş sürüme geçen: 7.943.892. Bunların 7.241.171'i son 24 saatte
    görüldü; yama başlayınca hızlı yayılıyor.
  - Son dokuz günde taranan ve sürümünü açıklayan 41,9 milyon hizmetin
    yaklaşık %79,8'i etkilenen kategoride. Yaklaşık 10 milyonu yaması
    çıkmış ama güncellenmemiş bir sürümde, **23 milyonu ise PHP 8.1 veya
    daha eski**, yani desteği bitmiş bir dalda çalışıyor.
- **Türkiye:** sürümünü açıklayan Türkiye kaynaklı PHP hizmetlerinin
  %92,9'u, yani 364.237 hizmet, etkilenen sürümlerde. Türkiye 233 ülke ve
  bölge arasında 19. sırada.
- **Ölçümün sınırı:** Censys sunucu değil hizmet sayar; bir sunucu birçok
  site barındırabilir. Sınıflandırma, hizmetin bildirdiği sürüme dayanır.
  Dağıtımlar yamayı sürüm numarasını değiştirmeden uyguladığı için yamalı
  bir sistem etkilenmiş görünebilir. Sürümünü hiç açıklamayan hizmetler de
  sayılmadığı için gerçek etki alanı daha büyük olabilir. Sürüm etiketi iki
  yönde de yanıltır.
- **Saldırılar duyurudan önce başladı:** açıklar 21 Ekim 2026'da yamalarla
  birlikte duyuruldu. AWS ise 17 Ekim'de, yani dört gün önce, bir
  honeypot'ta istismar girişimi gördüğünü bildirdi. Cloudflare de duyuru
  öncesinde başlayıp sonrasında hızla artan girişimler gözledi.
- **Keşif:** açıklar OpenAI'ın Patch the Planet girişimi kapsamında Calif
  ve Wiz araştırmacılarının yapay zekâ destekli araçlarıyla bulundu. CNN'e
  göre benzer bir sorun 2024'te görülmüş ama düzeltilmemişti.

### Koschei'de bugün ne oluyor (ölçüldü)

| Ders | Koschei bugün | Sonuç |
|---|---|---|
| Bellek tükenmesi tanımsız duruma yol açmamalı | `ks run` sınırsız büyüyen bir String'de Python `MemoryError` izini basıp 1 ile çıkıyor. `ks build` ikilisi Go `fatal error: out of memory` ile 2 ile çıkıyor. İkisinde de süreç ölüyor, yarım veriyi okuyan temizlik kodu yok. Ama bellek bütçesi yok, Koschei tanısı yok ve iki çalıştırıcının çıkış kodu farklı. | **Titan** ve **Nidavellir** gerekli |
| İstekler arasında durum kalmamalı | Her `ServeCaps.exchange` çağrısı yeni bir dinleyici açıyor, tek bağlantı ve tek istek işleyip kapatıyor. İstekler arasında çalışma ortamı düzeyinde durum yok; programın tuttuğu durum açık Koschei değerleri. Bu açık sınıfı bugün oluşamaz. | Kalıcı işçili serve, **Knowhere** olmadan çıkmamalı |
| İstek içeriği program istemeden işlenmemeli | İstek gövdesi bayt bütçesi altında okunup `String` olarak programa veriliyor. Örtük yükleme veya oturum işlemi yok. | **Sakaar** bunu yazılı değişmez yapar |
| Sürüm afişi saldırgana harita verir | Serve yanıtında `Server` veya `X-Powered-By` başlığı yok. | Korunmalı |
| Kabul, sürüm etiketine değil içeriğe bağlı olmalı | Module Lock içerik özeti kullanıyor, ama açık bildirimi veya destek süresi girdisi yok. | **Xandar** ve **Morag** gerekli. En büyük grup (23 milyon) desteği bitmiş dallarda: Morag'ın payı Xandar'ınkinden büyük. |
| Savunma açık bildirimini bekleyemez | İstismar, bildirimden dört gün önce başladı; açık listesine dayanan bir kapı (Xandar) o günlerde hiçbir şey yakalayamazdı. Koschei'nin asıl savunması yetki sınırlamasıdır ve hiçbir bildirime ihtiyaç duymaz. | Xandar tek başına yetmez. Yetki modeli ve Captain Marvel'in yayılma bütçesi önde kalır. |
| Kod çalıştıran saldırgan işçinin bütün yetkisini alır | Koschei'de ele geçirilen kod yalnızca kendisine açıkça verilen yetkiyi kullanabilir; ortamdan gelen yetki yoktur. | Patlama yarıçapı küçülür. Ama bootstrap host (CPython ve Go runtime) kendi bellek hatalarından dilin güvencesiyle korunmaz. |

### Kaynaklar

- [DonanımHaber: PHP açıkları Türkiye'yi de vurdu](https://www.donanimhaber.com/php-aciklari-turkiye-yi-de-vurdu-yuzbinlerce-hizmet-eski-surumde--212007) (Metin Akpınar)
- [Censys PHP2Shell canlı paneli](https://php2shell.censys.com/)
- [12punto: Censys'e göre Türkiye'de %92,9](https://12punto.com.tr/bilim-teknoloji/php2shell-aciklarinda-turkiye-alarmi-censyse-gore-surumunu-aciklayan-php-hizmetlerinin-yuzde-929u-riskli-156728)
- [Censys: CVE-2026-109618 / CVE-2026-109619 bülteni](https://censys.com/advisory/cve-2026-109618-cve-2026-109619/)
- [watchTowr: PHP2Shell SSS](https://watchtowr.com/intelligence/php-cve-2026-109618-faq/)
- [Qualys: PHP2Shell](https://blog.qualys.com/vulnerabilities-threat-research/2026/10/20/php-announces-critical-security-release-for-two-vulnerabilities)
- [Wiz: PHP2Shell](https://www.wiz.io/blog/php2shell-php-rce)
- [NCSC-NL: php2shell operasyon bilgisi](https://github.com/NCSC-NL/php2shell)
- [CNN: PHP2Shell'in geçmişi](https://www.cnn.com/2026/10/23/tech/ai-cybersecurity-php2shell-explained)

## Koschei'ye taşıma sırası

1. ~~**Çekirdek:** denetlenmiş bir sağlayıcıdan gelen özet fonksiyonu (kripto
   çevikliği kuralına uygun, değiştirilebilir).~~ **Tamamlandı:** `sha3_256`
   ve `secure` modülü. Bayt tipi hâlâ açık.
2. ~~**Saf mantıklı bekçiler:** Captain Marvel, Hela, Doctor Strange,
   Wanda.~~ **Tamamlandı:** dört bekçi Koschei'de.
3. **Matrix:** portal geçişi ve ufuk çiti.
4. **Gezegenler:** sekiz özelliği taşıyan bir gezegen yapısı. PHP2Shell
   ölçümüne göre önerilen sıra:
   1. **Titan** ve **Nidavellir:** bellek bütçesi ve "ya tam ya hiç". Ölçüm
      bugünkü açığı gösterdi.
   2. **Morag** ve **Xandar:** destek süresi ve açık bildirimiyle içerik
      özetine bağlı kabul. Habere göre en büyük grup desteği bitmiş
      dallarda olduğu için Morag önce gelir.
   3. **Knowhere** ve **Sakaar:** kalıcı işçili serve'den önce.
   4. **Vormir'in** Koschei'ye taşınması.
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
