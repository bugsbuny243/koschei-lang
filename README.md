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
- AST üretimi
- Immutable değer denetimi
- Capability scope denetimi
- Satır ve sütun bilgili compiler hataları

## CLI

```bash
ks tokens examples/capability.ks
ks ast examples/capability.ks
ks check examples/capability.ks
```

Örnek doğrulama çıktısı:

```text
KOSCHEI CHECK: PASS
```

## Testler

```bash
python -m unittest discover -s tests -v
```

GitHub Actions, her push ve pull request üzerinde compiler testlerini otomatik çalıştırır.

## Yol haritası

Mevcut sürüm **v0.7.0 — Günlük kod yazılabilsin**. Sonraki ana kapı v0.8'dir:

- Enum + exhaustive `match`
- Gerçek `Option<T>` ve `Result<T, E>` tipleri
- Union daraltma ve tam fonksiyon sınırı tip denetimi
- Capability kullanan programların Go codegen/runtime ABI desteği

Static region inference, C backend ve Sentinel/Tarpit/Phantom katmanları henüz
tasarım/spec aşamasındadır; tamamlanmış özellik olarak sunulmaz.

## Proje durumu

Koschei erken compiler geliştirme aşamasındadır. Sözdizimi ve runtime sözleşmeleri v1.0'a kadar değişebilir.

## License

MIT
