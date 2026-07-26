# Koschei Programming Language (`.ks`)

> **Çökmeyen, Hacklenemeyen, Ölümsüz Dil.**  
> **Uncrashable, Unhackable, Immortal.**

Koschei, kolay okunabilen sözdizimini bellek güvenliği ve capability tabanlı sistem güvenliğiyle birleştirmeyi amaçlayan yeni nesil bağımsız bir programlama dilidir.

Bu repository yalnızca Koschei dilinin compiler, runtime, standart kütüphane ve geliştirici araçlarını içerir.

## Temel ilkeler

- `null` ve `nil` yoktur; bulunmayabilecek değerler `Option<T>` ile temsil edilir.
- Hatalar `Result<T, E>` ve `or return` akışıyla ele alınır.
- Değişkenler varsayılan olarak immutable'dır; değişiklik için `let mut` gerekir.
- Ağ, disk, environment ve process erişimi açık capability değerleri gerektirir.
- Compiler, kapsam ve capability ihlallerini program çalışmadan önce reddeder.
- Uzun vadeli bellek modeli GC'siz static region inference üzerine kuruludur.

## Örnek Koschei kodu

```ks
fn fetch_data(net: NetCaps, url: String) -> String or Error {
    let response = net.get(url) or return Error("Veri alınamadı")
    return response.text()
}

fn main(caps: SystemCaps) {
    let api_net = caps.net.allow("https://api.example.com")
    let mut retry_count = 3
    let response = fetch_data(api_net, "https://api.example.com/v1")

    retry_count = 2
    println(response)
}
```

## Mevcut compiler hattı

```text
.ks source
    -> lexer.py
    -> parser.py
    -> ast_nodes.py
    -> semantic.py
```

Mevcut prototip şunları destekler:

- `fn` fonksiyon tanımları
- Tipli parametreler
- `let` ve `let mut`
- Fonksiyon ve metot çağrıları
- `return` ve `or return`
- Struct, List, `for` döngüsü ve immutable Map (`get/set/keys/contains`)
- Tam ifade interpolasyonu (`"{items.length()}"`, `"{1 + 2}"`)
- Günlük stdlib: String `trim/split/join`, List `sort/filter/contains`
- Enum constructor'ları ve exhaustive `match`
- Gerçek `Option<T>` / `Result<T, E>` değerleri (`Some/None`, `Ok/Err`)
- `or` sonrası union/Result/Option başarı tipi daraltması
- AST üretimi
- Immutable değer denetimi
- Capability scope denetimi
- Satır ve sütun bilgili compiler hataları

## CLI ve proje araçları

```bash
ks version
ks new hello-koschei
cd hello-koschei
ks check .
ks run .
ks build . -o ./hello-koschei
```

`ks new`, `koschei.toml` ve `src/main.ks` içeren sıfır bağımlılıklı bir proje
oluşturur. Kaynak dosyası yerine proje dizini veya doğrudan `koschei.toml`
verilebilir.

Tanılar varsayılan olarak İngilizcedir; Türkçe katalog aynı hata kodlarıyla
korunur:

```bash
ks explain KS2403
ks --lang tr explain KS2403
ks check --json src/main.ks
```

`check --json`, editör ve CI entegrasyonları için sabit `code`, `message`, `line`
ve `column` alanlarını üretir.

## VS Code

`editors/vscode` içindeki resmi uzantı `.ks` syntax highlighting, bracket/comment
kuralları, `Koschei: Check Current File` komutu ve kaydette otomatik
`ks check --json` tanıları sağlar. Dış npm bağımlılığı yoktur.

## Testler

```bash
python -m unittest discover -s tests -v
```

GitHub Actions, her push ve pull request üzerinde compiler testlerini otomatik çalıştırır.

## Yol haritası

`main` dalı şu anda **v0.9.0 — Müşteri karşısına çıkabilsin** kararlı ürün
kapısındadır.

Tamamlanan v0.9 dilimleri:

- 33 hata kodunun merkezi Türkçe/İngilizce tanı kataloğu
- İngilizce varsayılan CLI ve `--lang tr` / `KOSCHEI_LANG=tr` desteği
- Editörler için kararlı `ks check --json` tanı sözleşmesi
- Resmi VS Code uzantısı: syntax highlight, komut ve kaydette otomatik check
- `ks new`, `ks version`, minimal `koschei.toml` ve proje dizininden
  `check/run/build`
- Manifest entry yolunun proje kökü dışına kaçmasını reddeden fail-closed çözümleme

v0.8'in native güvenlik sınırları aynen korunur:

- Güvenli native disk ABI Linux `openat`/`O_NOFOLLOW` hedefindedir; güvenli eşdeğer
  bulunmayan platformda disk kullanan build **KS4001** ile durur.
- Process capability `run/spawn` işlem başlatmaz ve hata değeri döndürür.

Sıradaki ana kapı **v1.0 — İlk kararlı sürüm**:

- Sözdizimi ve capability runtime ABI v1 dondurması
- SemVer ve geriye dönük uyumluluk taahhüdü
- En az `List<T>` ve `Option<T>` generic sözleşmesi
- Basit paket/dependency çözümleme ve kilit dosyası
- Migration/compatibility testleri ve 1.0 release belgeleri

Static region inference, C backend ve Sentinel/Tarpit/Phantom katmanları henüz
tasarım/spec aşamasındadır; tamamlanmış özellik olarak sunulmaz.

## Proje durumu

Koschei erken compiler geliştirme aşamasındadır. Sözdizimi ve runtime sözleşmeleri v1.0'a kadar değişebilir.

## License

MIT
