# Koschei Lang 0.14.0 — Sürüm Notları

**Ürün:** Koschei Lang (Koschei Sentinel ve Web3 Hub'dan bağımsız)  
**Sürüm:** 0.14.0  
**Ürün hattı:** ticari lisanslı, 1.0 öncesi programlama dili ve araç zinciri

## 0.14.0'da yeni

- `ks run` yaklaşık iki kat hızlı: bir milyon turluk döngü 8,5 saniyeden
  3,5 saniyeye indi. Sonuçlar, hata değerleri ve adım sayıları değişmedi.
- Lambda'lar: `xs.filter(fn(x: Int) -> Bool { return x > 0 })`. Lambda
  çevresindeki fonksiyonun değişkenlerini yakalamaz; bir yetki jetonunu
  gizlice tutamaz.
- Generic struct'lar tip anotasyonuyla (`let page: Page<Int> = ...`) ve tip
  parametrelerinin yerini değiştiren generic fonksiyonlarda çalışır; tip
  hataları `Pair<Int, String>` gibi kaynak tipleriyle yazılır.

## 0.13.0'da yeni

- Veritabanı: `caps.db.allow(yol, en_fazla_satır, en_fazla_bayt, süre_ms)`
  tek bir SQLite dosyası açar; `exec(sql, parametreler)` satırları
  değiştirir, `query(sql, parametreler)` onları `Data` olarak döndürür. SQL
  bir metin literali olmalıdır, değerler `?` yer tutucularına bağlanır; SQL
  enjeksiyonu yazılamaz. `ATTACH`, `PRAGMA` ve eklentiler reddedilir;
  satır, dosya boyutu ve deyim süresi sınırlıdır. `ks run` ile çalışır;
  `ks build` şimdilik reddeder. Ayrıntılar kaynak depodaki `docs/DB_V1.md`.

## 0.12.0'da yeni

- Dışa açık sunucu: `caps.serve.allow("0.0.0.0:8080", ...)` (veya
  `[::]:PORT`) bütün arayüzlerden dinler; Koschei web uygulamasına başka
  makinelerden erişilebilir. Bütçeler, sıkı HTTP kuralları ve bağlantı
  başına tek istek kuralı değişmedi; başka loopback dışı adresler reddedilir.
- `http` Core Library modülü: `route` `/users/:id` kalıbını eşleştirir,
  `query` ve `params` sorgu ile form gövdesini, `cookies` `Cookie` başlığını
  okur; `escape_html` metni sayfaya güvenle koymaya hazırlar.
- `server.reply_with(durum, başlıklar, gövde)` `Location` ve `Set-Cookie`
  gibi başlıklar gönderir; yönlendirmeler (301, 302, 303, 307, 308) ve 401
  kullanılabilir. Bir başlık değeri başka bir başlık ekleyemez.

## 0.11.0'da yeni

- JSON okuma: `json_kind`, `json_has`, `json_get`, `json_at`, `json_text`,
  `json_int`, `json_float`, `json_bool`, `json_length`, `json_keys` ve
  `json_items`, `parse_json`'un döndürdüğü `Data` değerini okur. Eksik alan
  veya yanlış türde değer program çökertmez, hata değeri döner.
- JSON yazma: `json` Core Library modülü; tırnak, ters bölü ve kontrol
  karakterlerini doğru kaçıran JSON metni üretir.
- `math`: `min`, `max`, `clamp`, `abs`, `pow`, `gcd` ve Float karşılıkları.
  64 bit Int dışına taşan sonuç hata değeridir, yanlış sayı değil.
- `time`: UTC zaman damgasından tarihe ve geri, ISO 8601 metni; 1–9999
  yılları. Olmayan bir tarih hata değeridir.
- `parse_json` artık modül içe aktaran programlarda da çalışır.

## 0.10.1'de yeni

- `ks-mcp` (veya `uvx koschei-lang`): yapay zekâ ajanlarının Koschei
  programlarını, komut satırında bir kez belirlediğiniz yetki politikası
  altında çalıştırmasını sağlayan MCP sunucusu. Fazlasını isteyen program
  çalışmadan reddedilir. Ayrıntılar kaynak depodaki `docs/MCP_SERVER.md`
  dosyasında.
- Sürüm güveni araçları geri geldi: `ks maturity`, `ks maturity-attest`,
  `ks release-proof`, `ks build-compare` ve `ks build-compare-verify`.
- PyPI'da da var: `pip install koschei-lang`. PyPI dosyaları, kaynak
  deponun yayın iş akışına bağlı Sigstore kaynak kanıtı taşır.

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
tek ödemelidir: geliştirici başına 49 USD. Bir kuruluş, Koschei'yi
ticari olarak kullanan her geliştiricisi için bir lisans alır.
Satın alınan sürümlerin kullanımı
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
