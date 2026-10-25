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
| **G1.3** | `Bytes` tipi | Yok | Dosya ve ağdan ikili veri okunur, `secure.hash` baytlar üzerinde çalışır, hex kodlaması var; dört çalıştırıcı ve native aynı; değer bütçesine uyar | Geliştirme |
| **G2** | Derlenmiş ikili dış dünyayla konuşur | Yok (bilerek kapalı, `KS4004`) | Disk ve ağ yetkileri native ikilide ayrı bir yetki aracısı ve işletim sistemi kısıtlamasıyla çalışır; `ks caps` manifesti ikilinin gerçekte yapabildikleriyle eşleşir; saldırı testleri | Geliştirme |
| **G3** | Saat ve rastgele sayı | Yok (katalogda planlı) | `clock` ve `random` aileleri yetki olarak gelir; rastgele sayı işletim sisteminin denetlenmiş kaynağından alınır; Koschei kriptografik ilkel yazmaz | Geliştirme |
| **G4** | Sürekli çalışan sunucu | Kısmi (tek istekli yerel `serve.exchange`) | Çok istekli sunucu; Knowhere (istekler arası kalıntı yok) ve Sakaar (örtük girdi işleme yok) yasaları testle; POST; istek başına bütçeler | Geliştirme |
| **G5** | 1.0 kararlılık sözü | Yok | Söz dizimi ve standart kütüphane yüzeyi kararlı / deneysel / iç olarak işaretli; uyumluluk ve kullanımdan kaldırma politikası; sürüm numaralama kuralı | Geliştirme + Sahip onayı |
| **G6** | Kurulum ve dağıtım | Kısmi (`pip install .`, imzalı ve yeniden üretilebilir sürüm araçları var) | Tek komutla kurulum; iki bağımsız temiz derlemede bayt bayt aynı sürüm; korumalı `main` dalı; imzalı sürüm | Geliştirme + Sahip (dal koruması, imza anahtarı) |
| **G7** | Belgeler | Kısmi (rehber, Core Library ve tasarım belgeleri var) | Türkçe ve İngilizce dil rehberi, standart kütüphane başvurusu, hata kodları kataloğu, en az üç uçtan uca örnek proje | Geliştirme |
| **G8** | Güvenlik kanıtı | Kısmi (saldırı laboratuvarı, fark fuzz'ı, güvenlik regresyonları) | Tehdit modeli dosyası; ölçülebilir karşılaştırma ölçütleri (Rust dahil); bağımsız güvenlik denetimi raporu | Geliştirme + Dış taraf |
| **G9** | Ticari hazırlık | Kısmi (`LICENSE` proprietary) | Lisans ve kullanım sözleşmesi, fiyat, destek ve güvenlik açığı bildirme süreci, hukuki inceleme | Sahip + Dış taraf |

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
