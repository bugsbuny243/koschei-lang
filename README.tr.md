# Koschei (`.ks`)

Koschei Lang; kendi semantiği, derleyicisi, kütüphaneleri ve çalışma ortamıyla siber güvenlik temelli genel amaçlı yazılım geliştirme dilidir. Dış bağımlılıksız ekosistem ve Rust’ı güvenlikte aşmak geliştirme hedefidir. **Lang ve Sentinel aynı ticari paketlerde birlikte sunulacak; dilin bağımsızlığı korunacaktır.** [Güncel ürün yönü](docs/PRODUCT_DIRECTION_2026-09-10.md).

> **Özel ticari geliştirme deposu. Koschei proprietary yazılımdır. Bu repoya erişim; yeniden dağıtım, alt lisanslama, satış veya kaynak kodu yayımlama hakkı vermez. Ayrıntılar için `LICENSE` dosyasına bakın.**

**Capability tabanlı güvenli bir programlama dili. İçe aktardığınız bir paket, siz açıkça bir jeton vermedikçe diskinize, ağınıza veya ortam değişkenlerinize dokunamaz.**

Tedarik zinciri saldırılarının çalışma nedeni şu: bir bağımlılık, sürecin sahip olduğu bütün izinleri otomatik olarak devralır. Paketi kurarsınız ve o paket `~/.ssh` dizinini, `.env` dosyanızı okuyabilir veya bir socket açabilir — hiç sormadan. Koschei bu ortamdan gelen yetkiyi kaldırır: yan etki erişimi fonksiyona geçirilmesi gereken bir değerdir ve derleyici, kendisine verilmemiş bir yetkiye uzanan programı reddeder.

English: [README.md](README.md)

---

## Yetkili geliştirme hızlı başlangıcı

Bu repo özeldir. Aşağıdaki komutlar yalnızca yetkili işbirlikçileri ve lisanslı geliştirme ortamları içindir.

```bash
git clone <yetkili-private-koschei-reposu>
cd koschei-lang
pip install .
ks check examples/supply_chain/main.ks
```

`examples/supply_chain/analytics.ks` içindeki kasıtlı zararlı paket bir sır dosyasını okumaya çalışır. Beklenen sonuç derleme aşamasında reddedilmesidir.

<!-- verify: expect KS2401 -->
```ks
fn track(event: String) -> String or Error {
    let secret = disk.read("/etc/app/secrets.env") or return Error("okunamadi")
    return secret
}
```

Beklenen çıktı:

```text
KOSCHEI ERROR: KS2401 [line 6, column 18]: Required capability is unavailable
in this scope — A disk, network, environment, or process operation was
attempted without the corresponding capability token.
Hint: run 'ks --lang en explain KS2401' for details.
```

Program çalıştırılmaz; dosya açılmaz. Bu bir runtime sandbox yakalaması değildir: `track` içinde `disk` yetkisi olmadığı için saldırı derleme aşamasında reddedilir.

---

## Dağıtım ve kurulum

Koschei sınırsız herkese açık kaynak paketi olarak dağıtılmaz. Geliştirme sürümleri yetkili private source veya onaylı lisanslı artifact kanalı üzerinden kurulur.

Yetkili source checkout için:

```bash
pip install .
ks version
```

İlk program:

```bash
ks new hello-koschei
cd hello-koschei
ks run .
```

`ks new`, `koschei.toml` ve `src/main.ks` içeren sıfır bağımlılıklı bir proje oluşturur.

---

## Temel ilkeler

- **Ortamdan gelen yetki yok.** Disk, ağ, ortam değişkeni ve process erişimi açık bir capability değeri gerektirir.
- **Yetkiler daralır, asla genişlemez.** Daraltılmış capability yeniden genişletilemez.
- **`null` yok.** Bulunmayabilecek değerler `Option<T>` ile temsil edilir.
- **Hatalar birer değerdir.** `Result<T, E>` kullanılır ve ele alınmamış hata derleme hatasıdır.
- **Değerler sınırlıdır.** Bir String en fazla 16 MiB UTF-8, bir List en fazla 1.048.576 öğe olabilir; aşan işlem `ks run` ve `ks build` içinde aynı noktada `KS3502` hata değeri üretir ([Value Budget v1](docs/VALUE_BUDGET_V1.md)).
- **Program girdisi de bir yetkidir.** `caps.input.allow(65536)`, `args()` ve bayt bütçeli `read_text()` (standart girdi) verir; `ks run app.ks a b` ve derlenmiş `./app a b` aynı metinleri ve aynı hata değerlerini döndürür ([Program Input v1](docs/PROGRAM_INPUT_V1.md)).
- **Zaman ve rastgelelik de yetkidir.** `caps.clock.allow(1000)` çözünürlüğünden ince olmayan bir saat okur; `caps.random.allow(64)` işletim sisteminin güvenli kaynağından en fazla 64 bayt çeker ([Clock and Random v1](docs/CLOCK_RANDOM_V1.md)).
- **Test edilen belgelerle öğrenin.** [Dil rehberi](docs/guide/LANGUAGE_GUIDE.tr.md) her örneğini CI'da çalıştırır; [hata kodları](docs/reference/ERROR_CODES.md) ve [Core Library başvurusu](docs/reference/CORE_LIBRARY.md) araç zincirinden üretilir; [`examples/apps`](examples/apps/README.md) üç tam program içerir.
- **Varsayılan immutable.** Değer değiştirmek için `let mut` gerekir.
- **Tanılar açıklanabilir.** Sabit hata kodları ve Türkçe/İngilizce katalog vardır.
- **Kütüphane Koschei ile yazılır.** `import text` ve `import list`, araç zinciriyle gelen ve Koschei ile yazılmış Core Library modüllerini bağlar (`text.starts_with`, `text.replace`, `text.lines`, `list.first`, `list.reverse`, `list.slice`, …). `import secure`, denetlenmiş host uygulamasından gelen alan ayrımlı SHA3-256 özetlerini ekler. İlk evren modülleri de Koschei ile yazıldı: Marvel bekçileri `captain_marvel`, `hela`, `strange` ve `wanda`. `ks run` çalıştırır, `ks build` aynı kaynaktan derler; fonksiyon listesi için [Core Library v1](docs/CORE_LIBRARY_V1.md). Kütüphanenin dört evreni (Marvel, Matrix, Kuantum Fiziği, Diğer Evrenler) [Koschei Kütüphane Evrenleri](KOSCHEI_KUTUPHANE_EVRENLERI_V1.md) belgesinde.

## Yetki manifestosu

`ks caps`, programın erişebildiği yetkileri tüm modül grafiği boyunca raporlar:

```bash
ks caps examples/app.ks
ks caps --json src/main.ks
ks caps --deny net src/main.ks
```

`--deny` kapısı CI için kullanılır; bağımlılık güncellemesi sessizce yeni erişim eklerse build düşer.

## Araç zinciri

```bash
ks check src/main.ks
ks run src/main.ks
ks build src/main.ks -o app
ks fmt --write src/
ks caps src/main.ks
ks explain KS2401
ks check --json src/main.ks
ks mir src/main.ks
ks lsp
ks tokens / ks ast
```

Koschei'nin uzun vadeli kanonik mimarisi Koschei semantiği ve doğrulanmış execution contract'ları tarafından tanımlanır; geçici bootstrap veya tooling katmanlarının uygulama dili Koschei'nin davranışını tanımlamaz. Dış adapter'lar yalnız interoperability içindir.

## Testler

```bash
python -m unittest discover -s tests -v
```

CI paketi compiler/runtime testlerini, parity kontrollerini, capability güvenlik regresyonlarını ve deception-plane saldırı simülasyonlarını içerir.

## Durum

Koschei pre-1.0 aşamasında ve özel ticari geliştirme altında. Sözdizimi, runtime sözleşmeleri, lisanslama, dağıtım ve güvenlik mimarisi ilk production sürümüne kadar değişebilir. Henüz production kullanımı önerilmez.

Korunan source/deception mimarisi aşamalı saldırı dalgalarıyla sertleştirilmektedir. Canonical source identity fiziksel source locator'lardan ayrıdır; decoy view'lar deploy edilemez olarak işaretlenir ve kısa ömürlü epoch-bound read grant'ler ile yetki ayrımı yapılır.

## Ticari geliştirme

Koschei proprietary ticari yazılım olarak geliştirilmektedir. Mevcut repo, compiler/runtime güvenlik implementasyonu, deception mekanizmaları, model entegrasyonları veya bunlardan türetilmiş ticari ürünlerin public yeniden dağıtımı ayrı bir yazılı lisans olmadan yetkili değildir.

Gelecekte müşteri dağıtımı; lisanslı SDK/tooling, imzalı binary'ler, private package/artifact kanalları, enterprise policy yönetimi, audit evidence ve destek/SLA paketleri içerebilir.

## Katkı

Katkılar yalnızca yetkili private collaboration üzerinden kabul edilir. Dışarıdan kod kabul edilmeden önce IP ve contributor şartları açıkça belirlenmelidir.

## Lisans

**Proprietary — mevcut ve gelecekteki proprietary Koschei sürümleri için tüm hakları saklıdır.** Daha önce MIT altında public yayımlanmış belirli revizyonların geçmiş lisans durumunu ve güncel proprietary şartları `LICENSE` dosyası açıklar.
