# Koschei Lang 0.10.0 — Sürüm Notları

**Ürün:** Koschei Lang (Koschei Sentinel ve Web3 Hub'dan bağımsız)  
**Sürüm:** 0.10.0  
**Ürün hattı:** ticari lisanslı, 1.0 öncesi programlama dili ve araç zinciri

## Bu sürümde

- `ks check`: derleme sırasında sözdizimi, tip ve yetki denetimleri.
- `ks caps` ve `ks caps --deny <alan>`: tüm modül grafiği
  için yetki manifestosu ve CI kuralı.
- `ks run`: doğrulama sonrası yorumlayıcıda çalıştırma.
- `ks build`: mevcut Go adaptörü ile native ikili derleme.
- `ks fmt`, `ks lsp`, `ks explain`: geliştirici araçları.
- `Option`, `Result`, açık hata yönetimi ve sınırlandırılmış
  değerlerle Koschei dilinde yazılmış Core Library.
- Ağ yetkisi olmadan belirli klasörlere salt-okunur erişen
  `secretscan` ve `integrity` örnek uygulamaları.
- Yetkisiz disk erişimi talep eden içe aktarılmış bir modülün
  `KS2401` hatasıyla çalıştırılmadan reddedildiği örnek.
- Türkçe/İngilizce dil rehberi, başvuru belgeleri ve lisans şartları.

## Kurulum

`install.sh`, Unix benzeri kabuk ve Python 3.12+ gerektirir.
Native derleme için ayrıca Go 1.24+ gerekir.

```sh
./install.sh
ks version
ks run examples/hello.ks
ks check examples/supply_chain/main.ks # beklenen KS2401, çıkış 1
```

Bilinmeyen üçüncü taraf kurulum betiklerini veya sahte
iş görüşmesi projelerini güvenlik denemesi olarak çalıştırmayın.
Dil derleyicisi işletim sisteminin tamamını izole etmez.

## Lisans

Ticari olmayan kişisel kullanım ücretsizdir. Ticari lisanslar
tek ödemelidir: Individual 49 USD (1 geliştirici), Team 249 USD
(10 geliştiriciye kadar), Enterprise 999 USD (aynı kuruluşta
sınırsız geliştirici). Satın alınan sürümlerin kullanımı
süresizdir; 12 aylık güncelleme hakkı vardır.
Kesin hükümler paket içindeki `LICENSE` ve `LICENSING.md`
ile Türkçe karşılıklarında bulunur.

## Sınırlar

Bu yazılım 1.0 öncesindedir; tamamen kendisini derleyen
bağımsız bir sistem olduğunu iddia etmez. Koschei dışındaki
rastgele zararlı kodun çalıştırılmasını, çalınan kimlik bilgilerini,
ele geçirilmiş geliştirici bilgisayarlarını veya yetkisiz
kripto para imzalamayı bütünüyle engellediği iddiası yoktur.
Bankacılık ve borsa kritik üretim sistemleri için bağımsız
sertifikasyon sunulmaz.

## Sürüm bütünlüğü

ZIP dosyasının SHA-256 özetini, yayıncı tarafından bağımsız
olarak doğrulanmış bir kanaldan alınan değerle karşılaştırın.
Yalnızca bilinmeyen indirme dosyasının yanında verilen özet
yayıncının kimliğini kanıtlamaz.
