# Koschei Görünmez ve Sürekli Değişen Kod v1

Durum: **hedef, envanter ve yol belgesi**. Her satırın uygulama durumu
ayrıca yazılıdır.

## Hedef

Koschei ile yazılmış bir proje için üç hedef:

1. **Gerçek kod hiçbir yerde gösterilmez.** GitHub'da veya başka bir depoda
   tutulan şey okunabilir kaynak değildir.
2. **Kod sürekli değişen biçimde durur ve çalışır.** Bugün görülen biçim
   yarın geçersizdir. Bir dağıtımı inceleyen, diğerini incelemiş olmaz.
3. **Ele geçirilen bir yapı diğerine ulaşamaz.** Bir dağıtımın, gezegenin
   veya müşterinin anahtarı, ikilisi ya da yetkisi başka birini açmaz.

## Önce dürüst sınır

- **Güvenlik kodun gizli kalmasına dayanmaz** (Kerckhoffs ilkesi). Saldırgan
  kodu görse bile yetki modeli, mühürler ve anahtarlar yüzünden bir şey
  kazanmamalıdır. Gizlilik ve değişkenlik **ek katmandır**: saldırganın işini
  pahalılaştırır ve ona hazır harita vermez, ama tek başına sınır değildir.
- Çalışan bir programın, çalıştığı makinede çalıştırılabilir bir biçimi
  olmak zorundadır. O makineyi tamamen ele geçiren biri (işletim sistemi
  çekirdeği, hipervizör) çalışan davranışı gözleyebilir.
- Kodu görme yetkisi olan bir geliştiricinin gördüğünü kopyalaması teknik
  olarak engellenemez.
- Kriptografi Koschei'de yazılmaz (`koschei/crypto_agility_v1.py`).
  Mühürleme denetlenmiş bir sağlayıcıya devredilir.

Bu sınırlar `docs/OPAQUE_SOURCE_OBJECTS_V1.md` ve
`koschei/representation_boundary_v1.py` içinde de yazılıdır.

## Katman 1 — Depoda: kaynak hiç düz metin olarak durmaz

| Parça | Ne yapar | Uygulama | Durum |
|---|---|---|---|
| **Object Space** | Proje `k0` (mühürlü kök kapsül) ve `k1/<256-bit opak konum>` nesnelerinden oluşur. Dosya adı, modül adı, test rolü veya bağımlılık adı yoktur; bağımlılık grafiği mühürlü kökün içindedir. | `koschei/object_space_v1.py`, `docs/OBJECT_SPACE_V1.md` | Kod + test |
| **Dönen takma adlar** | Fiziksel adlar her epoch'ta değişir; kanonik kimlik ve içerik özeti değişmez. Depoda görünen biçimin "sürekli değişmesi" budur. | `koschei/epoch_alias_rotation_v1.py` | Kod + test |
| **Sahte görünümler** | Yetkisiz veya doğrulanmamış okuma gerçek baytlara dokunmaz; epoch'a bağlı sentetik bir sahte görünüm alır. Sahte görünüm derlenemez, imzalanamaz, dağıtılamaz. | `koschei/decoy_view_broker_v1.py`, Loki | Kod + test |
| **Korumalı kaynak zarfı** | Kanonik kaynak, ancak zarf, Trust Plane politikası, derleme yetkisi, kapsamlı izin, mühürlü yapıt ve düz metin özeti birlikte uyuşursa açılır. | `koschei/protected_source_envelope_v1.py` | Kod + test |
| **Araç zinciri bağlantısı** | `run`, `mir`, `caps`, `emit-go` ve `build` komutları tek bir güvenilir Object Space oturumundan geçer. Komut satırında anahtar kabul edilmez. Üretilen Go kaynağı yalnızca bellek tabanlı (`/dev/shm`) bir alanda tutulur; normal diske yazılmaz. | `koschei/object_space_commands_v1.py` | Kod + test |

Bu katmanla GitHub'a yalnızca mühürlü nesneler gider. Okunabilir kod,
yetkili geliştiriciye güvenilir aracının bellekte gösterdiği görünümdür.

**Eksik:** anahtar yönetimi gömülü bir Trust Plane'e bırakılmıştır; hazır bir
`ks` iş akışı yoktur. `koschei-lang` deposunun kendisi bugün düz metindir.

## Katman 2 — Çalışırken: gözlemci gerçek yapıyı görmez

| Parça | Ne yapar | Uygulama | Durum |
|---|---|---|---|
| **Temsil sınırı** | Gözlemcinin gördüğü nesnede kanonik adlar, konu, yetki işaretleri, kaynak konumu veya MIR parmak izi yoktur. Kanonik anlam yalnızca tam, süreli ve isteğe bağlı bir yeniden kurma izniyle açılır. | `koschei/representation_boundary_v1.py` | Kod + test |
| **Tek kullanımlık yeniden kurma** | Bir izin kanonik dünyaya en fazla bir kez geçer; geniş runtime kanonik MIR'ı değil, opak bir tutamaç alır. | `koschei/representation_reconstruction_gate_v1.py` | Kod + test |
| **Nyr izdüşümü** | Gözlemci/oturum/epoch'a bağlı takma adlar; eski epoch'un yüzeyi bugün yeniden oynatılamaz. | `koschei/nur_nyr_projection_v2.py` | Kod + test |
| **Loki uyarlanır topolojisi** | Yetkisiz gözlemciye kanıta göre değişen, gerçek hedef veya sır içermeyen yüzeyler. | `koschei/loki_adaptive_topology_v1.py` | Kod + test |

## Katman 3 — Derlenmiş programda: bugün yapı sızıyor (ölçüldü)

Marvel bekçilerini kullanan bir programın `ks build` ikilisi incelendi:

- 19 Koschei fonksiyonu gerçek adlarıyla sembol tablosunda
  (`main._ks_fn_3_2_evaluate`, `main._ks_fn_4_0_bury`, …).
- Modül, fonksiyon ve **parametre adları** sözleşme mesajlarında
  (`hela.bury: argument 'death_epoch' violates its type contract`).
- Programın kendi hata metinleri ve özet bağlam etiketleri
  (`koschei.marvel.hela.tombstone/v1`).
- Dosya yolu yok.
- Aynı kaynaktan her derleme aynı yapıyı üretir: bir dağıtımı inceleyen,
  aynı programın bütün dağıtımlarını incelemiş olur.

### Önerilen: Strange derlemesi (korumalı derleme)

Vizyon raporundaki Doctor Strange görevi: *aynı kanonik kökten farklı
oturum/derleme/epoch temsilleri üretmek ve hepsinin aynı köke bağlı
olduğunu doğrulamak.* Bu, Core Library'deki `strange` modülünden (etkiden
önce yol simülasyonu) ayrı bir parçadır; ikisi de "çok yol, tek kök"
fikrini taşır ve yeni bir karakter açmaz.

- Her dağıtımın gizli bir **tohumu** olur. Tohum Trust Plane'den gelir;
  depoya, komut satırına veya ikiliye girmez.
- Semboller ve tanı etiketleri tohumla türetilmiş opak takma adlara döner
  (`_k_7Q2A9M4K`). Takma ad → gerçek ad eşlemesi ayrı, mühürlü bir dosyada
  durur ve yalnızca yetkili geliştiricinin tanı aracı onu açar.
- Fonksiyon sırası, blok numaraları ve yuva (slot) düzeni her dağıtımda
  farklıdır.
- **Aynı tohum aynı ikiliyi** verir (denetlenebilir yeniden üretim);
  **farklı tohum farklı ikili** verir.
- Her çeşit için `ks run` ile birebir çıktı testi zorunludur: biçim değişir,
  anlam değişmez.

Sınır: bu, tersine mühendisliği pahalılaştırır ve "bir analiz her
dağıtıma uyar" durumunu bitirir. Programın davranışını ve kendi bastığı
metinleri gizlemez.

## Ele geçirilen yapı diğerine ulaşamaz

| Parça | Ne sağlar | Durum |
|---|---|---|
| **Yetki modeli** | Ele geçirilen kod yalnızca kendisine açıkça verilen yetkiyi kullanır; ortamdan gelen yetki yoktur. | Dilin temeli |
| **Captain Marvel** | Bir olayın yayılma bütçesi yalnızca küçülür. | Koschei'de |
| **Hela** | Ele geçirildiği anlaşılan yetki geri dönmemek üzere ölür. | Koschei'de |
| **Wanda** | Ele geçirilen bir gerçekliğin geçmişi yeniden yazması çatallanma olarak yakalanır. | Koschei'de |
| **Veyra / Aevra** | Her müşterinin kendi galaksi geometrisi var; bir programın baytlarını kopyalamak onun doğuşunu kopyalamak değildir (`copy(bytes) != birth(Aevra)`). | Kod + test |
| **Gezegen yasası** | Hiçbir gezegen, aynı Matrix dokusunda olduğu için diğerinin yetkisini devralmaz. | Yasa |
| **Bölme kanıtı** | Bir dağıtımın anahtarı, Strange tohumu ve ikilisi başka bir dağıtımda **fail-closed** reddedilir; test bunu her çift için gösterir. | **Tanımlanmadı:** Strange derlemesiyle birlikte gelmeli |

Yol haritası ölçütü (`KOSCHEI_WEB4_WEB10_ARCHITECTURE_ROADMAP_V1.md`):
*bir diyarın ele geçirilmesi, kanonik yetki zincirinin tamamını açığa
çıkarmamalı veya yeniden üretmemelidir.*

## Sıra

1. **Strange derlemesi:** ikilideki ad sızıntısını kapatır ve dağıtım
   başına çeşitlilik getirir. Ölçülmüş bir açığı kapattığı için ilk sıradadır.
2. **Bölme kanıtı:** dağıtım başına anahtar ve tohum; birinin malzemesi
   diğerinde reddedilir.
3. **Object Space iş akışı:** bir Koschei projesini Object Space'e çevirip
   GitHub'a yalnızca mühürlü nesnelerin gitmesini sağlayan `ks` komutları.
   Anahtarlar denetlenmiş sağlayıcıda kalır.

Her adım aynı kuralla gelir: kod, test ve bu belgedeki satır birlikte.
