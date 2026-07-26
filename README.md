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

`main` dalı şu anda **v0.8.0 — Derleyici verdiğimiz sözü tutsun**
kararlı sürümündedir.

Tamamlanan v0.8 dilimleri:

- Enum + exhaustive `match`
- Gerçek `Option<T>` ve `Result<T, E>` tipleri
- `or` sonrası union/Option/Result daraltması
- Mutable atamalarda ve fonksiyon sınırlarında tip sözleşmesi
- Enumların modüller arasında taşınması
- Native `SystemCaps` enjeksiyonu
- Native environment kapsamı
- Native HTTP GET: yalnız `http/https`, aynı-origin ve redirect sınırı
- Native disk ABI (Linux): sabitlenen kök fd, `openat`/`O_NOFOLLOW`,
  read/write/list/delete ve salt-okunur jeton savunması
- Native enum constructor, exhaustive `match`, `Option<T>`, `Result<T, E>` ve
  `or`/`or return` davranış eşliği
- Native immutable List/Map literal ve metotları, String `split/join`, `for` döngüsü
  ve insertion-order Map gösterimi
- Native struct literal/alan erişimi, yapısal eşitlik ve capability containment
- Çok dosyalı programların tek binary'ye güvenli flatten edilmesi; nested import
  ad alanları ve modül içi yerel fonksiyonlar izole edilir

v0.8'in destek matrisi bilinçli olarak dar ve fail-closed'dur:

- Güvenli native disk ABI Linux `openat`/`O_NOFOLLOW` hedefindedir; güvenli eşdeğer
  bulunmayan platformda disk kullanan build **KS4001** ile durur.
- Process capability `run/spawn` işlem başlatmaz ve hata değeri döndürür. Güvenli
  process sözleşmesi ayrı bir sürüm kapısıdır; mevcut sürüm yetkiyi sessizce açmaz.

Sıradaki ürün kapısı **v0.9 — Müşteri karşısına çıkabilsin**: İngilizce tanılar,
VS Code entegrasyonu, `ks new` ve minimal proje manifesti.

Static region inference, C backend ve Sentinel/Tarpit/Phantom katmanları henüz
tasarım/spec aşamasındadır; tamamlanmış özellik olarak sunulmaz.

## Proje durumu

Koschei erken compiler geliştirme aşamasındadır. Sözdizimi ve runtime sözleşmeleri v1.0'a kadar değişebilir.

## License

MIT
