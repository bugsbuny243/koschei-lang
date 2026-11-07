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

## Beş kök: devasa anlam, kendi kütüphanemizle

Koschei'nin kendine özgü beş kökü vardır. Her biri küçük bir kelimedir ama
arkasında bütün bir güvenlik alanı durur. Kökün anlamı derleyicide kısa,
kütüphanede devasadır: geliştirici `ka` yazar, kütüphane o kökün bütün
yasalarını çalıştırır. Kökler sıradan anahtar kelimeler değildir; ayrıntılı
yasaları `KOSCHEI_SIGIL_LEXICON_V1.md` içindedir.

| Kök | Anlamı | Taşı | Bekçileri ve gezegenleri |
|---|---|---|---|
| **ka** | Varlık oluşturma, sisteme kabul ve kimlik. Doğan şey tanınır ama **yetkisiz** doğar. | Ruh | Vormir (kök kabul), Aevra, Xandar ve Morag (kabul kapıları), Knowhere (her ziyaretçinin kimliği ayrı) |
| **vor** | Sınırlandırılmış güç, yetki ve erişim. Yetki açıktır, yalnızca daralır, asla kendiliğinden genişlemez. | Güç, Uzay | Yetki modeli, Captain Marvel (yayılma bütçesi), Titan (kaynak bütçesi), Sakaar (varış yetki değildir) |
| **shi** | Kanıt, doğrulama ve tanıklık. İddia kanıt değildir; yazan kendi işini kesinleştiremez. | Gerçeklik, Zihin | Wanda (taahhüt zinciri), `secure` (özet), Doctor Strange (etki öncesi kanıt), Neo/Sentinel |
| **thal** | Koruma, hasarı sınırlama ve güvenli kurtarma. Kurtarma yetki üretmez; eski yetki dirilmez. | Zaman | Hela, Captain Marvel (hasarı sınırlar), Nidavellir (yarım kalan iz bırakmaz), Morth Kara Delik |
| **nur** | Görünürlük, bilgi kontrolü ve gizlilik. Görmek yetki değildir. | — | Loki, Matrix/Nyr, Object Space, [görünmez kod](KOSCHEI_GORUNMEZ_DEGISEN_KOD_V1.md) |

`nur`'un bilerek taşı yoktur: altı taş kabul kararının girdileridir ve
görünürlük hiçbir zaman kabul veya yetki girdisi olamaz. `nur` yalnızca
neyin görüneceğini daraltır.

### Kökün anlamını bugün kim taşıyor

Derleyici bugün `ka x;` gibi kök bildirimlerini ayrıştırıyor
(`koschei/native_sigil_parser_v1.py`) ve şu kuralları uyguluyor: bir kök
bir planda bir kez yazılır, `ka` varsa ilk sıradadır
(`universe_kernel_v1.py`), ve `vor`/`shi`/`thal`/`nur` ancak önce `ka` ile
kabul edilmiş bir konuya uygulanabilir (`native_sigil_semantics_v1.py`).
Her kök sabit yükümlülüklere açılır ve bazı Python host modüllerini
etkinleştirir (`universe_kernel_v1.py`). Her yükümlülüğün bir kütüphane
sahibi vardır (`library_expansion_engine_v1.py`), ama o sahip bugün
yalnızca bir addır (`library.identity_genesis` gibi). Kanıt makbuzlarını
dışarıdan biri getirir. "Kendi kütüphanemiz" hedefi, her yükümlülüğün
**Koschei ile yazılmış** bir modülle karşılanmasıdır.

Köklerin bugün etkinleştirdiği Python modülleri:

- `ka`: `integrity`, `modules`, `mir`
- `vor`: `capability_effect_contract_v1`, `effect_contracts_v1`, `effects`,
  `runtime_capability_registry_v1`, `runtime_boot_v1`
- `shi`: `library_effect_attestation_quorum_v0`, `library_recovery_journal_v0`
- `thal`: `library_multi_scenario_containment_v0`,
  `library_policy_conflict_resolution_v0`, `library_recovery_transaction_v0`,
  `library_recovery_replica_quorum_v0`, `library_recovery_fencing_v0`,
  `library_recovery_exactly_once_v0`
- `nur`: `library_adversary_learning_resistance_v0`,
  `library_adaptive_visibility_v0`

| Kök | Yükümlülük | Bugünkü sahibi | Koschei kütüphanesindeki karşılığı |
|---|---|---|---|
| ka | `establish-canonical-identity` | ad: `library.identity_genesis` | `secure.digest`: alan ayrımlı kanonik özet (parça) |
| ka | `seal-integrity-lineage` | ad: `library.integrity_lineage` | `wanda.commit` / `wanda.extends` |
| ka | `deny-ambient-authority` | derleyici | Dilin kendisi: yetki modeli, `ks caps` |
| vor | `derive-least-authority` | derleyici | Dilin kendisi: yetki daraltma |
| vor | `seal-effect-contract` | derleyici | Dilin kendisi: etki sözleşmeleri |
| vor | `validate-runtime-before-authority-injection` | Python runtime | — |
| shi | `bind-observation-to-effect-receipt` | ad: `library.evidence_binding` | Yazılacak: `secure.digest` üzerine tanık makbuzu |
| shi | `require-independent-evidence` | ad: `library.attestation_quorum` | Yazılacak: bağımsız tanık çoğunluğu |
| shi | `preserve-evidence-lineage` | ad: `library.evidence_lineage` | `wanda` zincir mantığı |
| thal | `derive-minimum-safe-containment` | ad: `library.containment` | `captain_marvel.evaluate` (parça) |
| thal | `fence-stale-writers` | ad: `library.recovery_fencing` | `hela.remains_dead` (parça: eski epoch reddi) |
| thal | `commit-or-abort-recovery` | ad: `library.recovery_transaction` | Nidavellir'in ilk yasası çalışma ortamında (atomik `disk.write`); Koschei kütüphane modülü yok |
| thal | `prove-exactly-once-effect-lineage` | ad: `library.exactly_once` | Yazılacak |
| nur | `measure-knowledge-acquisition` | ad: `library.knowledge_budget` | Yazılacak |
| nur | `shrink-visibility-envelope` | ad: `library.visibility_envelope` | Yazılacak |
| nur | `rotate-observer-compartments` | ad: `library.compartment_rotation` | Yazılacak |
| nur | `preserve-canonical-state-behind-visibility` | ad: `library.canonical_state` | Yazılacak |

Özet: 17 kök yükümlülüğünün 3'ü dilin kendisidir ve öyle kalmalıdır, çünkü
yetki kütüphaneye değil derleyiciye aittir. Kalan 14'ün 5'inin Koschei
kütüphanesinde bugün bir parçası var; `nur`'un hiçbir parçası henüz Koschei
ile yazılmadı. Köklerin birleşiminden doğan 11 ek yükümlülük de
(`bind-authority-to-genesis-identity`, `abort-on-evidence-conflict`, …) aynı
yolu izler.

Yol:

1. Her yükümlülük için Koschei modülü yaz; Python sürümüyle fark testi ve
   `ks run` / `ks build` eşitliği şart.
2. Genişletme motorunu, yükümlülüğün kanıtını o Koschei modülünü
   çalıştırarak alacak şekilde bağla. Bugün kanıt makbuzları dışarıdan
   veriliyor.
3. Bir yükümlülüğün Koschei sürümü geldiğinde Python sahibi yalnızca
   referans olarak kalır.

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
| **Titan** | Thanos'un, kontrolsüz büyümeyle çöken dünyası | Her programın açık bir **bellek bütçesi** vardır. Tükenme her çalıştırıcıda aynı Koschei hatasıyla, tanımlı bir noktada durur. Host çökmesi veya yarım kalmış durum oluşmaz. | İlk yasa uygulandı: değer bütçesi (`KS3502`, `docs/VALUE_BUDGET_V1.md`). Bir String en fazla 16 MiB UTF-8, bir List en fazla 1.048.576 öğe; dört çalıştırıcı aynı noktada durur. Toplam canlı bellek bütçesi henüz yok. | **Kısmi: kod + test** (PHP2Shell CVE-2026-109618) |
| **Nidavellir** | Cücelerin yıldız ocağı: Stormbreaker ancak ocak tam ısındığında dövülür | **Ya tam ya hiç:** bir değer, kayıt veya kalıcı yazma ya tamamen oluşur ya hiç oluşmaz. Yarıda kesilen yapım iz bırakmaz; temizlik kodu yarım veriyi asla okumaz. | Bellekte kanıtlandı: alanı başarısız olan struct'ın tamamı hata değeridir, yarım struct dört çalıştırıcıda da görünmez. Diskte uygulandı: `disk.write` geçici dosya + `fsync` + tek `rename` ile atomik; kesilen yazma eski dosyayı bırakır (`docs/NIDAVELLIR_ALL_OR_NOTHING_V1.md`). Çok dosyalı işlem henüz yok. | **Kısmi: kod + test** (CVE-2026-109618) |
| **Knowhere** | Herkesin uğradığı ortak liman | **İstekler arası kalıntı yok:** uzun yaşayan bir hizmette her istek yeni bir gerçeklikte çalışır. Bir isteğin durumu sonrakine ulaşamaz; işçi yeniden kullanılmadan önce istek kapsamının boş olduğunu kanıtlar. | Matrix ufuk çitinin (eski Hara mezara konur) istek ölçeğinde uygulaması | **Aday** (CVE-2026-109619) |
| **Sakaar** | Solucan deliklerinden düşen her şeyin vardığı, Grandmaster'ın yargıladığı gezegen | **Örtük giriş işlemi yok:** dışarıdan gelen veri, program istemeden işlenmez. Çekirdek düzeyinde örtük ayrıştırma, yükleme ilerlemesi veya oturum yazımı yoktur. Ayrıştırma kendi bütçesiyle yapılır; başarısızlık yarım değer değil `Error` değeridir. | Bugünkü serve dilimi bunu sağlıyor (gövde `String` olarak döner) ama yazılı bir değişmez değil | **Aday** (CVE-2026-109619'un `session.upload_progress` yolu) |
| **Xandar** | Nova Corps: kayıtlar ve yasa | **Bilinen açık kabul edilmez:** açık bildirimindeki bir yapıt (bağımlılık, runtime, araç zinciri) kabul edilmez. Karar yapıtın **içerik özetine** bağlıdır, kendi bildirdiği sürüm etiketine değil. | Karar mantığı Koschei'de: `import xandar` (`koschei/core_library/xandar.ks`). Biçimi bozuk bir bildirim akışı her şeyi reddeder. Araç zincirine (kilit, derleme) henüz bağlı değil. Bildirimden önceki saldırıları yakalayamaz. | **Kısmi: Koschei'de** (haber: yüz binlerce hizmet eski sürümde) |
| **Morag** | Terk edilmiş gezegen, harabe tapınak | **Desteği biten yapıtın süresi dolar:** destek penceresi geçince, adı belli bir bakımcının tarihli yama beyanı olmadan kabul edilmez. | Karar mantığı Koschei'de: `import morag` (`koschei/core_library/morag.ks`). Destek penceresi bilinmeyen yapıt kabul edilmez. Araç zincirine henüz bağlı değil. | **Kısmi: Koschei'de** (PHP 8.1 ve öncesi resmî yama almıyor; 23 milyon hizmet bu dallarda) |
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

### Sonsuzluk Taşları: her gezegenin gücü

Altı Sonsuzluk Taşı, `docs/SECURITY_CONVERGENCE_CONTRACT.md` içindeki altı
güvenlik alanıdır. O sözleşmenin iç adı zaten "Thanos"tur; taşları bir
araya getiren Eldiven (Gauntlet), bütün zorunlu alanlar aynı konu üzerinde
uyuşmadan çalıştırmaya izin vermeyen kabul kararıdır.

| Taş | Güvenlik alanı | Sorduğu soru | Bekçisi | Filmde bulunduğu yer |
|---|---|---|---|---|
| **Ruh** | Kimlik / köken | Bu tam olarak hangi kaynak, yapıt, bağımlılık, sürüm, epoch ve politika? | Vormir, Aevra (`copy(bytes) != birth`) | Vormir |
| **Güç** | Yetki | Bu hesap hangi etkileri, hangi tam hedeflerde kullanabilir? | Yetki modeli, Captain Marvel | Morag → Xandar (Nova Corps) |
| **Gerçeklik** | Bütünlük | Kaynak → Object Space → IR → yapıt → yük hâlâ kabul edilen aynı nesne mi? | Wanda | Svartalfheim → Knowhere (Koleksiyoncu) |
| **Uzay** | Davranış | Yapıt etkilerini, hedeflerini, kaynak kullanımını veya yürütme biçimini sözleşmesinin ötesine genişletti mi? | `library_behavior_baseline_v1` | Asgard'ın kasası (Tesserakt) |
| **Zihin** | Kanıt / öngörü | Hangi deterministik olgular var, Sentinel hangi kısıtlamayı öneriyor? | Neo / Sentinel | Loki'nin asası → Vision |
| **Zaman** | Kurtarma / zaman | Kiralar taze mi, epoch'lar tek yönlü mü, ele geçirilen yetki iptal edildi mi? | Hela, Doctor Strange | Kamar-Taj (Agamotto'nun Gözü) |

Kurallar:

1. **Hiçbir taş tek başına anahtar değildir.** Tek bir alan çalıştırma yetkisi
   üretemez (yakınsama yasası). Kanıt (Zihin) yetki değildir; yalnızca
   kısıtlayabilir.
2. **Her gezegen hangi taşların zorunlu olduğunu ilan eder.** Bir gezegenin
   kararı, ilan ettiği taşlardan biri eksik veya uyuşmazsa **fail-closed**
   reddedilir. İlan edilenden az taşla geçmek mümkün değildir.
3. **Taşlar söz dizimi değildir.** Fizik Çekirdeği kuralı gereği altıncı bir
   taş/eksen, tam anlamı ve sahibi test edilmeden dilin beş köküne
   (`ka`, `vor`, `shi`, `thal`, `nur`) eklenmez.
4. **Eldiven Nidavellir'de dövülür.** Filmde Eldiven'i Eitri Nidavellir'de
   döver. Koschei'de Nidavellir'in "ya tam ya hiç" yasası Eldiven'in de
   yasasıdır: altı alanın kararı ya tamamen oluşur ya hiç oluşmaz.

Gezegenlerin taşları (zorunlu taşlar, aday gezegenler için öneri):

| Gezegen | Ruh | Güç | Gerçeklik | Uzay | Zihin | Zaman | Neden |
|---|:-:|:-:|:-:|:-:|:-:|:-:|---|
| **Vormir** | ● | ● | | | | ● | Kök girişi: kimlik, gerçek yetki azaltma (kurban), taze epoch |
| **Titan** | | | ● | ● | | ● | Bellek davranışı sözleşmeyi aşamaz; tükenme tanımlı noktada, tanımsız durum olmadan durur |
| **Nidavellir** | | | ● | | | ● | Yarım yapım kabul edilmez; kesinti bir önceki durumu bırakır |
| **Knowhere** | ● | | ● | | | ● | Her ziyaretçinin kimliği ayrı; bayat durum yok; istek kirası istekle ölür |
| **Sakaar** | | ● | | ● | | | Varış yetki değildir; giriş örtük etki doğurmaz |
| **Xandar** | ● | | | | ● | | Karar içerik özetine bağlı; açık bildirimi kanıttır, yalnızca kısıtlar |
| **Morag** | ● | | | | | ● | Destek süresi dolar; yama beyanının sahibi belli olmalı |

Filmlerde taşların durduğu yerler, aday gezegenlerle örtüşür: Güç Taşı
Morag'da bulunup Xandar'da korunur; Gerçeklik Taşı Knowhere'deki
Koleksiyoncu'ya verilir; Ruh Taşı Vormir'dedir; Eldiven Nidavellir'de
dövülür; Thanos Titan'dandır.

Kodu ve yapıyı dış saldırgana göstermeme hedefi ayrı belgededir:
[Koschei Görünmez ve Sürekli Değişen Kod](KOSCHEI_GORUNMEZ_DEGISEN_KOD_V1.md).

### Marvel bekçileri

| Karakter | Güvenlik görevi | Yetki kuralı | Uygulama | Durum |
|---|---|---|---|---|
| **Wanda** | Gerçeklik taahhüt zinciri; çatallanma (fork) ve geri sarma (rollback) tespiti | Kabul edilmiş geçmişi yeniden yazamaz | `import wanda` (`koschei/core_library/wanda.ks`); Python referansı `koschei/wanda_reality_integrity_v1.py` | **Koschei'de** |
| **Loki** | Yetkisiz gözlemciler için savunma amaçlı aldatma ve tuzak kanıtı | Yemlerde gerçek sır veya çalıştırılabilir yetki yoktur; geri saldırmaz | `koschei/loki_deception_reality_v1.py`, `koschei/loki_adaptive_topology_v1.py` | Kod + test |
| **Hela** | Geri alınamaz yetki ölümü; ölmüş yetkinin tekrar, eski epoch veya çatallanma yoluyla dirilmesini engeller | Ölü yetki geri gelmez | `import hela` (`koschei/core_library/hela.ks`); Python referansı `koschei/hela_authority_death_v1.py` | **Koschei'de** |
| **Doctor Strange** | Etkiden önce sınırlı gelecek-yol simülasyonu: önerilen yol yetkiyi genişletir mi? | Simülasyon dış etki yapamaz, yetki üretemez | `import strange` (`koschei/core_library/strange.ks`); Python referansı `koschei/strange_future_paths_v1.py` | **Koschei'de** (testleri de taşımayla yazıldı) |
| **Captain Marvel** | Patlama yarıçapı: bir olayın yayılma bütçesi | Bütçe yalnızca korunur veya küçülür; asla büyümez | `import captain_marvel` (`koschei/core_library/captain_marvel.ks`); Python referansı `koschei/captain_marvel_blast_radius_v1.py` | **Koschei'de** |
| **Sonsuzluk Taşları / Gauntlet** | Kritik yetkinin tek noktada toplanmaması; altı güvenlik alanının (kimlik, yetki, bütünlük, davranış, kanıt, kurtarma/zaman) deterministik olarak birlikte onaylaması | Zorunlu alanların hepsi uyuşmadan giriş yok | Belge: `docs/SECURITY_CONVERGENCE_CONTRACT.md`, `docs/MULTIVERSE_GUARDIAN_MAP.md`; taş ↔ alan eşlemesi yukarıda | Yalnızca belge |

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
| **Matrix ufuk geçişi — saf karar katmanı** | Veyra/Aevra sabit; yeni Matrix/Hara ve tam bir sonraki epoch. Self-consistent özet kaydı üretir, yetki vermez ve kalıcı durum güncellemez. | `import matrix_horizon` (`koschei/core_library/matrix_horizon.ks`); kalıcı durum hâlâ `matrix_horizon_fence_v1.py` | **Kısmi: Koschei'de** (saf doğrulama; SQLite tombstone değil) |
| **Portal geçişi** | Gerçeklikler arası içerik bağı, saf politika ön değerlendirmesi ve paylaşılan tek SQLite defterinde atomik tekrar kabul engeli | `import matrix_portal` (`matrix_portal.preview_policy`) + Python `matrix_portal_transit_v1.py`, `matrix_portal_replay_v1.py` | **Kısmi: Koschei'de** (saf politika + host tek-defter replay çiti; imza, kimlik doğrulama ve gerçek yetkili yürütme yok) |
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
- Matrix'in **saf ufuk-geçişi karar katmanı** artık `import matrix_horizon` ile
  Koschei'de; Matrix portalının **saf içerik/etki önerisi** de
  `import matrix_portal` ile Koschei'de. Kalıcı SQLite tombstone, gerçek
  portal yürütme ve yetki denetimi hâlâ dış güvenlik bileşenlerinde.
  Diğer Matrix, Kuantum ve Galaxy modüllerinin çoğu **Python ile yazılmış host
  makinesidir**; bir Koschei programı onları `import` edemez.
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
| Bellek tükenmesi tanımsız duruma yol açmamalı | **Önce:** `ks run` sınırsız büyüyen bir String'de Python `MemoryError` izini basıp 1 ile çıkıyordu; `ks build` ikilisi Go `fatal error: out of memory` ile 2 ile çıkıyordu. **Şimdi (Titan, değer bütçesi):** 16 MiB'yi aşacak String ve 1.048.576 öğeyi aşacak List, her çalıştırıcıda aynı noktada `KS3502` hata değeri olur; `disk.read` de bu sınıra uyar. Toplam bellek host'u tüketirse `ks run` iz dökümü yerine `KS3502` ile durur. İkili hâlâ Go'nun ölümcül hatasıyla durur. | Toplam canlı bellek bütçesi gerekli. **Nidavellir** geldi: yarım değer görünmez, `disk.write` atomik. |
| İstekler arasında durum kalmamalı | Her `ServeCaps.exchange` çağrısı yeni bir dinleyici açıyor, tek bağlantı ve tek istek işleyip kapatıyor. İstekler arasında çalışma ortamı düzeyinde durum yok; programın tuttuğu durum açık Koschei değerleri. Bu açık sınıfı bugün oluşamaz. | Kalıcı işçili serve, **Knowhere** olmadan çıkmamalı |
| İstek içeriği program istemeden işlenmemeli | İstek gövdesi bayt bütçesi altında okunup `String` olarak programa veriliyor. Örtük yükleme veya oturum işlemi yok. | **Sakaar** bunu yazılı değişmez yapar |
| Sürüm afişi saldırgana harita verir | Serve yanıtında `Server` veya `X-Powered-By` başlığı yok. | Korunmalı |
| Kabul, sürüm etiketine değil içeriğe bağlı olmalı | Module Lock içerik özeti kullanıyor. **Xandar** (açık bildirimi) ve **Morag** (destek süresi) karar mantığı olarak Koschei kütüphanesinde; ikisi de kimlik olarak yalnızca içerik özeti kabul ediyor. | Kilide ve derlemeye bağlanmaları gerekli. |
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
3. **Matrix:** Saf ufuk-geçişi (`matrix_horizon`) ve saf portal içerik bağı
   (`matrix_portal`) Koschei'de. **Kalıcı Hara mezarı, gerçek portal yürütme,
   karşılıklı kimlik doğrulama, **çoklu düğüm/defter genelinde replay çiti**,\n   dış etkiyle atomik işlem ve yetkilendirme** hâlâ sırada. Tek SQLite\n   defterindeki atomik replay kaydı host tarafında vardır; tek başına yetki değildir.
4. **Gezegenler:** sekiz özelliği taşıyan bir gezegen yapısı. PHP2Shell
   ölçümüne göre önerilen sıra:
   1. **Titan** ve **Nidavellir:** bellek bütçesi ve "ya tam ya hiç". Titan'ın
      değer bütçesi (`KS3502`) ve Nidavellir'in ilk yasası (yarım değer yok,
      atomik `disk.write`) geldi; toplam canlı bellek ve çok dosyalı işlem
      sırada.
   2. **Morag** ve **Xandar:** destek süresi ve açık bildirimiyle içerik
      özetine bağlı kabul. Karar mantıkları Koschei kütüphanesinde geldi;
      araç zincirine (kilit, derleme) bağlanmaları sırada.
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
