# Koschei Lang 0.22.0 — Sürüm Notları

**Ürün:** Koschei Lang (Koschei Sentinel ve Web3 Hub'dan bağımsız)  
**Sürüm:** 0.22.0  
**Ürün hattı:** ticari lisanslı, 1.0 öncesi programlama dili ve araç zinciri

## 0.22.0'da yeni

- **Güvenlik düzeltmesi: disk, ortam değişkeni, ağ veya sunucu kullanan native
  binary üretiyorsanız güncelleyin.** Yetki aracısı (broker), worker'dan gelen
  disk ve ortam değişkeni isteklerine koşulsuz cevap veriyordu. Ele geçirilmiş
  bir worker, yalnızca dosya okuyan ya da yalnızca ağ kullanan bir programda
  bile yazılabilir dizin ve ortam değişkenleri isteyebiliyordu; bunlara gizli
  bilgiler de dahildi. Seccomp yine devredeydi. Artık broker yalnızca
  derleyicinin programda gördüğü yetkilere hizmet ediyor, gerisinde bağlantıyı
  kesiyor. Açığı bir formal model (TLA+) buldu.
- **Formal modeller.** `formal/tla` altında paket güncelleme kuralının ve broker
  kısıtının TLC ile denetlenen modelleri var. Her modelde koddaki her kontrolün
  gerekli olduğu gösteriliyor: kontrol kapatılınca karşı örnek çıkıyor.

## 0.21.0'da yeni

- **Güvenlik düzeltmesi — `ks workspace build` kullanıyorsanız
  güncelleyin.** Workspace'ten derlenen native binary'ler eski backend'i
  kullanıyordu; bu backend disk, ağ, sunucu ve kalıcı kayıt işlemlerini
  programın kendi sürecinde, `ks build`'in zorunlu tuttuğu yetki broker'ı ve
  seccomp koruması olmadan çalıştırıyordu. Workspace derlemeleri artık
  korumalı backend'i kullanır ve koruyamadığı her şeyi reddeder (`KS4004`).
  Tek dosyalı `ks build` etkilenmedi.
- **Native binary'lerde kalıcı kayıt ve tek seferlik sunucu.** `PersistCaps`
  (`caps.persist.allow`, `load`, `commit`) ve `ServeCaps.exchange` artık
  broker üzerinden, yorumlayıcıyla birebir aynı davranış ve hata
  metinleriyle çalışır. Repodaki her program ve her workspace `main`'i native
  derlenir; 1.0'ın 2. kapısı kapandı.
- Depodaki üç paket sahibi tarafından imzalandı.

## 0.20.0'da yeni

- **İmzalı paketler ve herkese açık kayıt.** `ks pkg keygen`, `ks pkg
  publish --key`, `ks pkg sign`. Sürümler paket sahiplerinin Ed25519
  anahtarıyla imzalanır. Kilit dosyanız her paketi kimin imzaladığını
  hatırlar: başka biri tarafından imzalanmış bir sürüm
  `--allow-new-signer <paket>` verilmeden reddedilir. `registry/log.jsonl`
  her yayını, imzayı ve geri çekmeyi zincirleme kaydeder; kilidiniz
  gördüğünüz kısmı sabitler, geçmişi yeniden yazan bir depo reddedilir.
  `[policy] require_signed = true` imzasız paketleri reddeder. Ed25519
  bağımlılıksız yazıldı (RFC 8032, OpenSSL ile karşılaştırıldı); Koschei
  hâlâ başka hiçbir şey kurmaz.
- **Fuzzing.** `tools/fuzz/` derleyiciyi bozulmuş ve üretilmiş programlarla,
  rastgele derinlikte yetki kötüye kullanımıyla, disk kaçış denemeleriyle ve
  bozuk paket dosyalarıyla dener. Bulduğu iki kilit dosyası hatası
  düzeltildi. Her pull request'te küçük bir tur çalışır.
- **Denetim belgesi.** `docs/AUDIT_SCOPE_V1.md`, bağımsız bir denetçinin
  kırmaya çalışması gereken yedi iddiayı listeler; tehdit modeli paketleri,
  depoyu ve imzaları kapsar.
- **1.0 kapıları** `docs/RELEASE_PLAN_AFTER_0_14.md`'de izlenir; kendi
  kendini derleme 1.0'ın kapsamı dışındadır.

## 0.19.0'da yeni

- **Paket deposu** (`ks pkg add ad@sürüm`, `ks pkg publish`, `ks pkg yank`
  ve `{ version = "x.y.z" }` bağımlılıkları). Depo,
  `https://koschei.dev/registry/` adresindeki düz dosyalardır; yayın bir pull
  request'tir. İstemci arşiv ve paket özetlerini doğrular, yalnızca `.ks`
  kaynaklarını çıkarır ve her paketin yetki yüzeyini kendisi yeniden
  hesaplar; indeksle uyuşmayan paketi reddeder. Sürümler değiştirilemez,
  geri çekilen sürümler yalnızca mevcut bir kilitten kurulur, benzer isimler
  incelemeye takılır.
- **İlk paketler**, hepsi saf: `hexfmt` 1.0.0, `base64` 1.0.0, `semver`
  1.0.0. Deneyin: `ks pkg add base64@1.0.0`.
- **`KS1402`:** Sonucu atılan bir List, Map, String veya Bytes metodu
  (tek başına `items.push(x)`) artık derlenmez. Bu değerler değiştirilemez;
  o satır hiçbir şey yapmıyordu.
- `"x".bytes()` artık `KS1306` yerine bilinmeyen metot (`KS1502`,
  `to_bytes` önerisiyle) bildirir.

## 0.18.0'da yeni

- **Yetki yüzeyi kilitlenen paket bağımlılıkları** (`ks pkg sync`,
  `ks pkg list`, `ks pkg verify`). Bağımlılıklar bir klasörden veya bir git
  commit'inden gelir. Derleyici her paketin yüzeyini (disk, ağ, ortam vb.
  hangilerini çağırandan istediğini) hesaplar ve paketin SHA-256 özetiyle
  birlikte kilitler. Yeni yetki ekleyen bir güncelleme `--allow <yetki>`
  verilmeden reddedilir; `[policy] deny` bir yetkiyi tamamen yasaklar;
  kilitlendikten sonra değişen bir paket derlenmez (`KS1606`). Henüz merkezi
  depo yok: bu, `docs/PACKAGES_V1.md` planının 1. aşaması.
- **Tedarik zinciri demosu** (`examples/supply_chain_demo`): aynı zararlı
  bağımlılık Rust'ta ve Koschei'de; `cargo build`'in sorgusuz kabul ettiği,
  `ks pkg sync`'in reddettiği bir güncelleme dahil.
- **Kararlılık politikası onaylandı** (`docs/STABILITY_V1.md`); 1.0.0 ile
  yürürlüğe girer.
- **Sertleştirilmiş native derleme:** `ks build` Go ortamını sabitler
  (`GOFLAGS`, `GOENV`, `GOPROXY`, `GOTOOLCHAIN`, `GOWORK`, `CGO_ENABLED`);
  kötü niyetli bir ortam `-toolexec` kancası ekleyemez veya modül indiremez.

## 0.17.0'da yeni

- `ks build`, `ks run`'ın çalıştırdığı programların neredeyse tamamını
  derliyor. Native binary'lerde yeni: daha fazla List/Map metodu (`sum`,
  `min`, `max`, `unique`, `flatten`, `chunks`, `partition`, `scan`, `merge`,
  `add`, …), Data (`parse_json`, `encode_json`, `json_*`), tam hassasiyetli
  ondalık sayılar, generic ve typestate struct'lar, sınırlı kuyruklar, görev
  kapsamları ve `parallel_map`. Çıktılar ve hata mesajları `ks run` ile aynı.
  Repodaki programlardan yalnızca biri hâlâ `ks run` gerektiriyor
  (`PersistCaps` kullanıyor).
- `sha256_bytes(data)`: `sha3_256_bytes`'ın yanında, host kütüphanesinden
  SHA-256.
- Python bekçilerini bayt bayt yeniden üreten kütüphane modülleri: `vormir`
  (yeniden doğuştan önce kurban), `galaxy_identity` (Veyra ve Aevra) ve
  `matrix_reality` (Matrix, Hara ve kabul). Fark testleri bunları Python
  modülleriyle hem `ks run` hem binary olarak karşılaştırır.
- Düzeltmeler: `json_int` çok büyük ya da üslü sayılarda artık `ks run`'ı iç
  hatayla durdurmuyor; Go ve Python JSON çekirdekleri hataları aynı
  bildiriyor; List/Map öğelerindeki yanlış `KS2401` giderildi.

## 0.16.0'da yeni

- `ks build`, `List.sort()`, `filter`, `find`, `map` ve `any` kullanan
  programları derliyor. Bu programlar `ks run` ile çalışıyor ama binary'ye
  dönmüyordu; artık binary aynı sonuçları ve hataları veriyor. Callback,
  `ks run`'daki gibi tek parametreli bir üst düzey fonksiyon ya da lambda.
- Doğrulama başarısız olduğunda çıktı, yalnızca son satırları göstermek
  yerine düşen testlerin adını yazıyor.

## 0.15.0'da yeni

- Sunucular boşta bekleyen istemcilerin arkasında kilitlenmiyor. İstekler
  programın yanında okunuyor (sunucu başına aynı anda 128'e kadar); bağlanıp
  hiçbir şey göndermeyen bir istemci sunucuyu değil yalnızca bir okuyucuyu
  meşgul ediyor. Önceden üç boşta bağlantı diğer her isteği 30 sn bekletiyordu.
- `ks build` her zaman statik binary üretiyor; Alpine dahil her linux/amd64
  sistemde ve yalnızca binary içeren imajlarda çalışıyor.
- `ks caps` manifestoyu seçtiğiniz dilde basıyor (`--lang en|tr`, varsayılan
  İngilizce); `--json` değişmedi.
- Düzeltmeler: `or` ile bir `List`'ten alınan `Map` artık yanlış KS2401
  vermiyor; içe aktarılan bir modüldeki hata o modülün adıyla raporlanıyor.

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
