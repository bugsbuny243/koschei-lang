# Koschei ile kod yazma rehberi — v0.10

Bu rehber yalnızca bugün çalışan dil yüzeyini anlatır.

## Değerler ve tipler

Tipi çoğu zaman yazmanız gerekmez:

```ks
let name = "Ada"
let count = 5
```

Bir sınırı özellikle belgelemek veya zorlamak istediğinizde yerel anotasyon kullanabilirsiniz:

```ks
let count: Int = 5
let mut ports: List<Int> = [8080, 8081]
```

Anotasyon ile değer uyuşmazsa program çalıştırılmadan `KS1301` üretilir.

## Döngüler

```ks
for value in [1, 2, 3, 4] {
    if value == 2 { continue }
    if value == 4 { break }
    println("{value}")
}
```

Artık döngüyü durdurmak için bayrak değişkeni yazmayın. `break` en yakın döngüden çıkar; `continue` en yakın döngünün sonraki adımına geçer. Etiketli dış döngü kontrolü henüz yoktur.

## Yüzde ve kalan hesabı

```ks
let remainder = 10 % 3
let percent = amount * 20 / 100
```

`Int / Int` tamsayı sonucu, `Int % Int` tamsayı kalanı üretir. `%` Float üzerinde kullanılamaz.

## Option ile güvenli liste erişimi

```ks
fn first<T>(items: List<T>) -> Option<T> {
    return items.get(0)
}

fn main() {
    match first([7]) {
        Some(value) => println("{value}"),
        None => println("empty"),
    }
}
```

Geçerli indeks `Some(value)`, geçersiz indeks `None()` üretir. Değer gerekiyorsa kısa biçim de kullanılabilir:

```ks
let first = items.get(0) or 0
```

## Match blokları

Bir kolda birden fazla işlem yapabilirsiniz:

```ks
let score = match Some(4) {
    Some(value) => {
        println("found")
        value + 1
    }
    None => {
        0
    }
}
```

Son ifade kolun değeridir. Bütün varyantların yazılması zorunludur.

## Struct güncelleme

```ks
struct Counter { value: Int }

fn main() {
    let mut counter = Counter { value: 0 }
    counter.value = counter.value + 1
}
```

Alanı değişecek struct bağlaması `let mut` olmalıdır. `let` ile tanımlanan değerler değişmez kalır. İç içe alan ataması bu sürümde yoktur.

## Hata değerleri

Hata dönebilen işlem açıkça ele alınmalıdır:

```ks
let text = disk.read(path) or return Error("read failed")
let port = raw.to_int() or 8080
let value = operation() or {
    println("using fallback")
    fallback
}
```

Satır sonunda çıplak `or return` kullanıp sonraki satır bir ifade ile başlıyorsa sınırı `;` ile açık yazın:

```ks
let value = operation() or return;
println(value)
```

## Yetki ilkesi

Paketler disk, ağ, ortam veya süreç yetkisini otomatik almaz. Yetki `main` içinde daraltılır ve ihtiyaç duyan fonksiyona değer olarak geçirilir:

```ks
fn load(disk: DiskReadCaps, path: String) -> String or Error {
    return disk.read(path)
}

fn main(caps: SystemCaps) {
    let config_disk = caps.disk.allow_read_only("/etc/app")
    let text = load(config_disk, "/etc/app/config") or ""
    println(text)
}
```

Bu kural ergonomi özellikleriyle gevşetilmemiştir.
