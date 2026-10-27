# Koschei Lang Satışa Hazırlık Yol Haritası v1

Durum: **ÇALIŞMA PLANI — SATIŞA HAZIR OLDUĞU İDDİASI DEĞİLDİR**

Amaç: Koschei Lang'i genel amaçlı, ücretli bir programlama dili ürünü olarak
satılabilir hâle getirmek. Bu belge ürün kapılarını sıralar. Satın alma ve
devir kapıları (`KOSCHEI_ACQUISITION_READINESS_V1.md`) ayrıca geçerlidir; bu
belge onların yerini almaz.

Bir kapı ancak depo veya bağımsız olarak yeniden üretilebilen bir kanıt onu
gösterdiğinde **kapandı** sayılır. Niyet, yol haritası veya test sayısı tek
başına kanıt değildir.

## Durum etiketleri

- **Kapandı:** kod, test ve belge birlikte var; tam doğrulama geçti.
- **Kısmi:** anlamlı bir parça var, kapanış şartı karşılanmadı.
- **Yok:** henüz başlanmadı.
- **Dış kanıt:** yalnızca kaynak koddan kanıtlanamaz; sahibin veya bağımsız
  bir tarafın işi.

## Kimin işi

- **Geliştirme:** depoda kod, test ve belge olarak yapılabilir.
- **Sahip:** Koschei'nin sahibinin kararı veya hesabı gerekir (lisans, fiyat,
  GitHub ayarları, imza anahtarları).
- **Dış taraf:** bağımsız denetim, hukuki inceleme, gerçek müşteri.

## Ürün kapıları

| Kapı | Konu | Durum | Kapanış şartı | Kimin işi |
|---|---|---|---|---|
| **G1.1** | `disk.read` UTF-8 olmayan dosyada hata değeri | **Kapandı** | Dosya geçerli UTF-8 değilse program `or` ile yakalanabilen bir hata değeri alır; host istisnası yok (`tests/test_disk_read_text_v1.py`) | Geliştirme |
| **G1.2** | Program girdisi: komut satırı argümanları ve standart girdi | **Kapandı** | `caps.input.allow(bayt)` → `InputCaps.args()` / `read_text()`; bütçe `ks caps`'te görünür; UTF-8 olmayan girdi, bütçe aşımı ve okuma hatası `or` ile yakalanan hata değerleri; üç çalıştırıcı ve native ikili aynı baytları verir; diğer yetkiler native'de hâlâ KS4004 (`docs/PROGRAM_INPUT_V1.md`, `tests/test_program_input_v1.py`) | Geliştirme |
| **G1.3** | `Bytes` tipi | **Kapandı** (standart girdi, dosya ve rastgele kaynaktan ikili veri; `secure.hash_bytes`; hex; dört çalıştırıcı ve native aynı; ağ gövdesi G4/G2 ile: `docs/BYTES_V1.md`, `tests/test_bytes_v1.py`) | Dosya ve ağdan ikili veri okunur, `secure.hash` baytlar üzerinde çalışır, hex kodlaması var; dört çalıştırıcı ve native aynı; değer bütçesine uyar | Geliştirme |
| **G2** | Derlenmiş ikili dış dünyayla konuşur | **Kapandı, linux/amd64** (işçi seccomp izin listesiyle kilitli: listede olmayan her çağrı `EPERM`, `clone` yalnızca iş parçacığı, sinyal ve `prlimit` yalnızca kendine; disk okuma/yazma/silme ve ortam: ayrı aracı süreç + seccomp ile kilitli işçi, linux/amd64, `ks run` ile aynı yanıtlar ve aynı dosya ağacı, atomik yazma, kip korunur: `docs/NATIVE_BROKER_V1.md`, `tests/test_native_broker_v1.py`; ağ `GET`: kanonik URL, yönlendirme, vekil, TLS ve hata kuralları iki çalıştırıcıda aynı: `docs/NET_V1.md`, `tests/test_native_net_v1.py`; çok istekli sunucu aracı üzerinden: `tests/test_native_serve_v1.py`; süreçler ve tek seferlik `exchange` hâlâ `KS4004`) | Disk ve ağ yetkileri native ikilide ayrı bir yetki aracısı ve işletim sistemi kısıtlamasıyla çalışır; `ks caps` manifesti ikilinin gerçekte yapabildikleriyle eşleşir; saldırı testleri | Geliştirme |
| **G3** | Saat ve rastgele sayı | **Kapandı** | `caps.clock.allow(çözünürlük)` → `now_ms()` / `monotonic_ms()`; `caps.random.allow(bayt)` → `hex()` / `below()`, işletim sisteminin güvenli kaynağından, yetki başına bütçeyle; `ks run` ve native aynı kuralları ve hata değerlerini verir; zaman aşımı (`deadline`) planlı (`docs/CLOCK_RANDOM_V1.md`, `tests/test_clock_random_v1.py`) | Geliştirme |
| **G4** | Sürekli çalışan sunucu | **Kapandı** (`ks run` altında: `server.accept()` / `server.reply()`; Knowhere ve Sakaar yasaları, POST, istek başına bayt ve süre bütçeleri gerçek istemcilerle test edildi; native ikilide de aracı üzerinden, istemcilerin aldığı baytlar `ks run` ile aynı: `docs/SERVE_KNOWHERE_V1.md`, `tests/test_serve_knowhere_v1.py`, `tests/test_native_serve_v1.py`) | Çok istekli sunucu; Knowhere (istekler arası kalıntı yok) ve Sakaar (örtük girdi işleme yok) yasaları testle; POST; istek başına bütçeler | Geliştirme |
| **G5** | 1.0 kararlılık sözü | **Kısmi** (politika yazıldı: `docs/STABILITY_V1.md`; sahibin onayı ve 1.0.0 sürüm numarası bekleniyor) | Söz dizimi ve standart kütüphane yüzeyi kararlı / deneysel / iç olarak işaretli; uyumluluk ve kullanımdan kaldırma politikası; sürüm numaralama kuralı | Geliştirme + Sahip onayı |
| **G6** | Kurulum ve dağıtım | **Kısmi** (tek komut `./install.sh`; native ikili artık bayt bayt yeniden üretilebilir, farklı dizinlerden bile: `tests/test_native_reproducible_build_v1.py`; korumalı `main` ve imza anahtarı sahipte) | Tek komutla kurulum; iki bağımsız temiz derlemede bayt bayt aynı sürüm; korumalı `main` dalı; imzalı sürüm | Geliştirme + Sahip (dal koruması, imza anahtarı) |
| **G7** | Belgeler | **Kapandı** | Türkçe ve İngilizce dil rehberi, her programı test edilen (`docs/guide/`, `tests/test_language_guide_v1.py`); kaynaktan üretilen hata kodları kataloğu ve Core Library başvurusu (`docs/reference/`, `--check` testi); `ks run` ve native'de aynı çıkan beş uçtan uca uygulama (gizli bilgi tarayıcı ve dosya bütünlüğü denetleyici dahil) (`examples/apps/`, `tests/test_example_apps_v1.py`) | Geliştirme |
| **G8** | Güvenlik kanıtı | **Kısmi** (tehdit modeli `docs/THREAT_MODEL_V1.md`, her tehdide test kanıtı; Python/Go/Rust ile ölçülen karşılaştırma `docs/benchmarks/`; bağımsız denetim dış tarafta) | Tehdit modeli dosyası; ölçülebilir karşılaştırma ölçütleri (Rust dahil); bağımsız güvenlik denetimi raporu | Geliştirme + Dış taraf |
| **G9** | Ticari hazırlık | **Kısmi** (satış modeli ticari lisans: kişisel kullanım ücretsiz, kalıcı ticari lisans + 12 ay güncelleme, 49 / 249 / 999 USD: `LICENSE`, `LICENSE.tr.md`, `LICENSING.md`; Polar indirme paketi `tools/polar_bundle_v1.py`; kalan: Polar mağazası, sahiplik beyanı ve destek / güvenlik açığı bildirme süreci; hukuki inceleme sahip kararıyla yapılmıyor: `KOSCHEI_SAHIP_EYLEM_LISTESI_V1.md`) | Lisans ve kullanım sözleşmesi, fiyat, destek ve güvenlik açığı bildirme süreci, hukuki inceleme | Sahip + Dış taraf |

## Sıra

1. **G1** (girdi ve veri temeli): ürünü gerçek işte kullanılabilir kılan en
   küçük adımlar.
2. **G3** (saat, rastgele): küçük, G4 için gerekli.
3. **G2** (native yetkiler): en büyük teknik iş; G4'ün native hâli buna bağlı.
4. **G4** (sunucu).
5. **G5** ve **G7** (kararlılık ve belgeler), G4 biterken.
6. **G6** (dağıtım) ve satın alma kapısının P0 maddeleri.
7. **G8** (bağımsız denetim) ve **G9** (ticari), aday sürüm hazır olunca.

## Bu belgenin kuralı

Her kapı kapandığında bu tabloda durumu güncellenir ve kanıtı yazılır.
Bir kapı yalnızca tam doğrulama (bütün testler, `verify.sh`, sınır, saldırı
laboratuvarı, SBOM, ceremony) geçtikten sonra "Kapandı" olur.
