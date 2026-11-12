# Koschei Dil Rehberi

Bu rehber dili bugün çalıştığı hâliyle anlatır. İçindeki her program
`tests/test_language_guide_v1.py` tarafından çalıştırılır: ardından `output`
bloğu gelen bir program `ks run` altında tam olarak o bloğu yazdırmalı ve
`ks check`'ten geçmelidir. Native backend programı kabul ediyorsa derlenmiş
ikili aynı baytları yazdırmalıdır.

İngilizce sürüm: [`LANGUAGE_GUIDE.en.md`](LANGUAGE_GUIDE.en.md).

## 1. Kurulum ve çalıştırma

```sh
pip install .            # Python 3.12+; `ks` komutunu kurar
ks run hello.ks          # denetle ve çalıştır
ks build hello.ks -o hello && ./hello   # native ikili (Go 1.24+ gerekir)
```

```ks
fn main() {
    println("Hello, Koschei")
}
```

```output
Hello, Koschei
```

Program çalışmadan önce bütünüyle denetlenir. Tip hatası, eksik yetki veya
ele alınmamış bir hata asla çalışma aşamasına ulaşmaz.

## 2. Değerler

```ks
fn main() {
    let name = "Ada"
    let mut count: Int = 2
    count = count + 1
    println("{name} has {count} items")
    println(7 / 2)
    println(7 % 2)
    println(7.0 / 2.0)
    println(3 > 2 && !(1 == 2))
}
```

```output
Ada has 3 items
3
1
3.5
true
```

- `let` bağları değişmezdir; `let mut` değiştirme niyetini açıkça söyler.
- Tipler çıkarılır; `let count: Int = 2` tipi belgeler ve zorlar.
- `Int` işaretli 64 bit, `Float` 64 bit, `String` UTF-8, `Bool`
  `true`/`false`'tur. `null` yoktur.
- `"{ifade}"` herhangi bir ifadeyi metne katar.

## 3. Listeler ve döngüler

```ks
fn total(prices: List<Int>) -> Int {
    let mut sum = 0
    for price in prices {
        if price < 0 {
            continue
        }
        sum = sum + price
    }
    return sum
}

fn main() {
    let prices = [120, -5, 30]
    println(total(prices))
    let more = prices.push(50)
    println("{prices.length()} -> {more.length()}")
    let first = prices.get(0) or 0
    println(first)
    let missing = prices.get(10) or -1
    println(missing)
    let mut i = 0
    while i < 10 {
        i = i + 3
        if i > 6 {
            break
        }
    }
    println(i)
}
```

```output
150
3 -> 4
120
-1
9
```

Listeler değerdir: `push` yeni bir liste döndürür, asıl listeye dokunmaz.
`get` bir şey bulamayabilir; bu yüzden sonucu ele alınmalıdır, burada `or` ile.

### Günlük sözdizimi tek programda

```ks
enum Light {
    Red,
    Green,
}

fn size(n: Int) -> String {
    if n > 100 {
        return "large"
    } else if n > 10 {
        return "medium"
    } else {
        return "small"
    }
}

fn positive(value: Int) -> Bool {
    return value > 0
}

fn double(value: Int) -> Int {
    return value * 2
}

fn main() {
    println(size(42))
    let words = "pear, fig ,apple".split(",") or []
    let mut clean: List<String> = []
    for word in words {
        clean = clean.push(word.trim())
    }
    let sorted = clean.sort() or []
    println(" | ".join(sorted))
    let numbers = [5, -2, 8]
    println(numbers.filter(positive) or [])
    println(numbers.map(double) or [])
    let mut counts: Map<String, Int> = {}
    for word in ["a", "b", "a"] {
        let seen = counts.get(word) or 0
        counts = counts.set(word, seen + 1)
    }
    println(counts)
    println("12".to_int() or 0)
    print("no newline, ")
    println("then one")
    match Green() {
        Red => println("stop"),
        Green => println("go"),
    }
}
```

```output
medium
apple | fig | pear
[5, 8]
[10, -4, 16]
{"a": 2, "b": 1}
12
no newline, then one
go
```

- `if`, `else if` ve `else` alır. Koşullar `Bool` olmalıdır.
- Aralık döngüsü yoktur. `while` ile sayın ya da `for` ile bir listeyi gezin.
- Boş liste ya da map tipini ister: `let mut xs: List<Int> = []`,
  `let mut m: Map<String, Int> = {}`.
- String metotları: `length()`, `contains(text)`, `trim()`, `split(separator)`,
  `join(list)`, `to_int()`, `to_float()`. `split`, `to_int` ve `to_float`
  başarısız olabilir; `or` ile ele alın.
- List metotları: `length()`, `get(index)`, `push(item)`, `contains(item)`,
  `sort()`, `filter(function)`, `map(function)`. `filter` ve `map` adlandırılmış
  bir fonksiyon alır; lambda yoktur. `sort`, `filter` ve `map` başarısız
  olabilir; `or` ile ele alın.
- `print` satır sonu eklemeden yazar; `println` ekler.
- `match` ifade olarak da deyim olarak da çalışır. Payload taşımayan varyant
  parantezle kurulur (`Green()`), parantezsiz eşlenir (`Green`).

## 4. Hatalar değerdir

Başarısız olabilen bir fonksiyon bunu tipinde söyler ve çağıran hatayı ele
almak zorundadır. `or` bunun üç yolunu verir: `or return ...` hatayı yukarı
iletir, `or değer` varsayılan koyar, `or { ... }` bir blok çalıştırır.

```ks
fn parse_port(text: String) -> Result<Int, Error> {
    let port = text.to_int() or return Err(Error("not a number: {text}"))
    if port < 1 || port > 65535 {
        return Err(Error("out of range: {port}"))
    }
    return Ok(port)
}

fn main() {
    let ok = parse_port("8080") or 0
    println(ok)
    let fallback = parse_port("http") or 80
    println(fallback)
    let message = match parse_port("70000") {
        Ok(port) => "port {port}",
        Err(error) => "refused: {error}",
    }
    println(message)
}
```

```output
8080
80
refused: out of range: 70000
```

Yalın `or return` hatanın kendisini çağırana verir; bu yüzden fonksiyon onu
döndürebilmelidir: hata bir Error ise `-> T or Error`, `None` ya da `Err`
ise `Option` ya da `Result` dönüş tipi. Dönüş tipi olmayan bir fonksiyon
döndüremez (`KS1304`).
Yalnızca `main`, bildirmediği bir Error'u döndürebilir: program
`KOSCHEI RUNTIME ERROR: <mesaj>` yazar ve 1 koduyla biter.

Çalışma zamanı hataları da değerdir: Int taşması (`KS3501`), sıfıra bölme ve
bellek bütçesini aşan değer (`KS3502`) her çalıştırıcıda aynı noktada hata
değeri üretir ve `or` bunları yakalar.

```ks
fn main() {
    let big = 9223372036854775807
    let overflow = big + 1 or -1
    println(overflow)
    let safe = 10 / 0 or 0
    println(safe)
}
```

```output
-1
0
```

## 5. Enum, `match` ve struct

```ks
enum Shape {
    Circle(Int),
    Square(Int),
    Empty,
}

fn area(shape: Shape) -> Int {
    return match shape {
        Circle(r) => 3 * r * r,
        Square(side) => side * side,
        Empty => 0,
    }
}

struct Point {
    x: Int,
    y: Int,
}

fn main() {
    println(area(Circle(2)))
    println(area(Square(3)))
    println(area(Empty()))
    let p = Point { x: 1, y: 2 }
    let mut q = p
    q.x = 10
    println(p)
    println(q)
    println(p == Point { x: 1, y: 2 })
}
```

```output
12
9
0
Point { x: 1, y: 2 }
Point { x: 10, y: 2 }
true
```

`match` her varyantı kapsamalıdır. Struct'ların değer semantiği vardır: `q`
üzerinden alan atamak yeni bir değer kurar ve `p`'yi asla değiştirmez.

## 6. Generic'ler ve Map

```ks
fn first_or<T>(items: List<T>, fallback: T) -> T {
    let item = items.get(0) or return fallback
    return item
}

fn main() {
    println(first_or([3, 4], 0))
    println(first_or(["a"], "none"))
    let ages = {"ada": 36, "alan": 41}
    let age = ages.get("ada") or 0
    println(age)
    let older = ages.set("grace", 85)
    println(older.keys())
    println(ages.contains("nobody"))
}
```

```output
3
a
36
["ada", "alan", "grace"]
false
```

Map anahtarları String'dir ve ekleme sırasını korur. Olmayan bir anahtarda
`get` bir hata değeridir; `or` ile ele alın veya önce `contains` ile sorun.

### JSON

`parse_json` metni opak bir `Data` değerine çevirir; `json_` fonksiyonları onu
okur. Koschei metinlerinde süslü parantezler kaçışlanır (`\{`, `\}`), çünkü
`{...}` interpolasyondur.

```ks
fn price(item: Data) -> Int or Error {
    let field = json_get(item, "price") or return Error("item has no price")
    let value = json_int(field) or return Error("price is not a whole number")
    return value
}

fn main() {
    let text = "\{\"shop\":\"Ada's\",\"open\":true,\"items\":[\{\"name\":\"pen\",\"price\":3\},\{\"name\":\"ink\",\"price\":12\},\{\"name\":\"gift\"\}]\}"
    let order = parse_json(text) or return Error("not JSON")
    let shop = json_get(order, "shop") or return Error("no shop")
    println(json_text(shop) or "?")
    println(json_kind(order))
    println(json_keys(order) or [])
    println(json_has(order, "discount"))
    let list = json_get(order, "items") or return Error("no items")
    println(json_length(list) or 0)
    let mut total = 0
    for item in json_items(list) or [] {
        let name = json_get(item, "name") or item
        let cost = price(item) or 0
        println("{json_text(name) or "?"}: {cost}")
        total = total + cost
    }
    println(total)
    let first = json_at(list, 0) or return Error("empty")
    println(encode_json(first) or "?")
    println(json_at(list, 9))
    println(json_int(shop))
}
```

```output
Ada's
object
["shop", "open", "items"]
false
3
pen: 3
ink: 12
gift: 0
15
{"name":"pen","price":3}
KS3710: json_at(): index 9 is outside 0..2
KS3709: json_int() expects a JSON number, found string
```

| Fonksiyon | Döndürür | Ne için |
|---|---|---|
| `parse_json(text)` | `Data or Error` | metinden `Data` |
| `encode_json(data)` | `String or Error` | `Data` değerinden kanonik JSON metni |
| `json_kind(data)` | `String` | `"object"`, `"array"`, `"string"`, `"number"`, `"bool"` veya `"null"` |
| `json_has(data, key)` | `Bool` | nesnede üye var mı |
| `json_get(data, key)` | `Data or Error` | nesne üyesi |
| `json_at(data, index)` | `Data or Error` | dizi öğesi |
| `json_text(data)` | `String or Error` | JSON metni |
| `json_int(data)` | `Int or Error` | `Int` aralığındaki tam sayı |
| `json_float(data)` | `Float or Error` | herhangi bir sayı |
| `json_bool(data)` | `Bool or Error` | `true` veya `false` |
| `json_length(data)` | `Int or Error` | dizinin öğe, nesnenin üye sayısı |
| `json_keys(data)` | `List<String> or Error` | üye adları, belgedeki sırayla |
| `json_items(data)` | `List<Data> or Error` | dizi öğeleri, `for` ile gezmek için |

- Sessiz dönüşüm yapılmaz: `json_int`, `2.5` değerini ve metni reddeder; yanlış
  tür `KS3709` hata değeridir. Eksik üye ya da dizin `KS3710` olur. İkisini de
  `or` ile ele alın.
- `Data` değeri yazdırılamaz ve interpolasyona giremez; önce `encode_json`
  çağırın ya da bir alan okuyun.
- Bunların hepsi saftır: yetki gerektirmez ve `pure fn` içinde çalışır.
- JSON `ks run` altında çalışır. `ks build`, native arka uç destekleyene kadar
  `Data` kullanan programları reddeder (`KS4004`).

### Bytes

`String` her zaman UTF-8 metindir; ikili veri `Bytes`'tır ve ikisi asla
sessizce birbirine dönüşmez. Kaynaklar: `input.read_bytes()`,
`disk.read_bytes(yol)`, `random.bytes(n)`; bkz. [`../BYTES_V1.md`](../BYTES_V1.md).

```ks
fn main() {
    let data = "héllo".to_bytes()
    println(data)
    println(data.length())
    let head = data.slice(0, 2) or data
    println(head.to_text())
    let key = bytes_from_hex("00ff") or data
    println(key + head)
}
```

```output
Bytes(68c3a96c6c6f)
6
KS3430: Bytes geçerli UTF-8 metin değil.
Bytes(00ff68c3)
```

## 7. Modüller ve Core Library

`import ad`, yandaki `ad.ks` dosyasını veya bir Core Library modülünü bağlar.
Core Library Koschei ile yazılmıştır ve programınızla birlikte derlenir; tam
liste [`../reference/CORE_LIBRARY.md`](../reference/CORE_LIBRARY.md) içinde.

```ks
import text
import list
import math
import secure
import time

fn main() {
    println(text.starts_with("koschei.ks", "koschei"))
    println(text.replace("a-b-c", "-", "+") or "")
    println(text.lines("one\ntwo"))
    println(list.reverse([1, 2, 3]))
    println(list.first(["x", "y"]))
    println(math.max(3, 8))
    println(math.pow(2, 10) or 0)
    println(math.pow(2, 63))
    println(time.iso_utc(1762933548000) or "?")
    println(secure.hash("koschei") or "?")
}
```

```output
true
a+b+c
Ok(["one", "two"])
[3, 2, 1]
Some("x")
8
1024
math.pow: the result is outside Int
2025-11-12T07:45:48Z
sha3-256:3997da0d8a19346db3fb4c5be74689b753e506c8a03f2bba28be7b3bd3125e8c
```

`secure` özetleri host'un denetlenmiş SHA3-256 uygulamasından gelir; Koschei
kendi kriptografik ilkelini yazmaz.

## 8. Saf fonksiyonlar

`pure fn` hiçbir etki olmayacağını söyler: çıktı yok, yetki yok, bunlardan
birine sahip bir şeyi çağırmak yok. Denetleyici bunu kanıtlar (`KS3940`).

```ks
pure fn double(value: Int) -> Int {
    return value * 2
}

fn main() {
    println(double(21))
}
```

```output
42
```

## 9. Yetkiler

Koschei'de ortam yetkisi yoktur. `main` tek bir `SystemCaps` alabilir ve
yazdırma dışındaki her etki ondan daraltılmış bir jetondan geçer. Jetonu
olmayan bir fonksiyon diske, ağa, ortam değişkenlerine, program girdisine,
saate veya rastgeleliğe ulaşamaz; denetleyici bunu kanıtlar.

```ks
fn greet(input: InputCaps) -> String or Error {
    let args = input.args() or return Error("no arguments")
    let name = args.get(0) or return Error("usage: greet NAME")
    return "Hello, {name}!"
}

fn main(caps: SystemCaps) {
    let message = greet(caps.input.allow(1024)) or "usage: greet NAME"
    println(message)
}
```

```output
usage: greet NAME
```

`ks run greet.ks Ada` komutu `Hello, Ada!` yazdırır. Kurallar:

| Kök | Daraltma | Verdikleri |
|---|---|---|
| `caps.input` | `allow(max_stdin_bytes)` | `args()`, `read_text()` |
| `caps.clock` | `allow(resolution_ms)` | `now_ms()`, `monotonic_ms()` |
| `caps.random` | `allow(max_bytes)` | `hex(count)`, `below(bound)` |
| `caps.disk` | `allow(prefix)`, `allow_read_only(prefix)` | `read`, `write`, `list`, `delete` |
| `caps.env` | `allow(name)` | `get()` |
| `caps.net` | `allow(origin)` | `get(url)`, `post(url, content_type, body)` |

- Kök yetki doğrudan iş yapamaz (`KS2402`); daraltılmış jeton genişleyemez
  (`KS2403`) ve kendisine verilmeyeni yapamaz (`KS2404`).
- Jetonlar taşınır: bir fonksiyona vermek onu devreder (yeniden kullanımda
  `KS3931`).
- Jetonlar listeye veya Map'e konamaz (`KS2401`), karşılaştırılamaz
  (`KS2407`) ve anlamlı biçimde yazdırılamaz (`<InputCaps>` olarak görünür).
- `ks caps app.ks` her izni kapsamıyla yazdırır: program bu listenin dışındaki
  hiçbir şeye ulaşamaz.

```ks
fn main(caps: SystemCaps) {
    let clock = caps.clock.allow(1000)
    let now = clock.now_ms()
    println(now % 1000 == 0)
    let random = caps.random.allow(8)
    let token = random.hex(8) or ""
    println(token.length())
    println(random.hex(8))
    println(random.below(6))
}
```

```output
true
16
KS3450: Rastgele sayı bütçesi tükendi: bu yetki en fazla 8 bayt üretebilir.
KS3450: Rastgele sayı bütçesi tükendi: bu yetki en fazla 8 bayt üretebilir.
```

Jeton toplam 8 bayt üretebilir: ilk `hex(8)` hepsini harcar, bu yüzden ikinci
`hex(8)` ve `below` (8 bayt) `KS3450` hata değerini alır ve hiçbir şey
çekmez. Çalışma zamanı mesajları bugün Türkçedir; kodları kararlıdır.

### Dosya okuma

```ks
fn load(disk: DiskReadCaps, path: String) -> String or Error {
    let content = disk.read(path) or return Error("cannot read {path}")
    return content
}

fn main(caps: SystemCaps) {
    let data = caps.disk.allow_read_only("/data")
    let content = load(data, "/data/input.txt") or "missing"
    println(content)
}
```

`read(path)` dosyanın metnini ya da bir Error değerini döndürür; eksik dosyanın
ne anlama geldiğine çağıran karar verir. Bu program `/data/input.txt`
okunamazsa `missing` yazar. `ks caps` bu program için tek bir yetki bildirir:
disk, `/data`, salt-okunur. `list(path)` bir dizindeki adları döndürür;
`allow(prefix)` ile alınan jeton ayrıca `write(path, text)` ve `delete(path)`
yapabilir.

## 10. Araçlar

| Komut | Yaptığı |
|---|---|
| `ks check app.ks` | tam denetim, çalıştırma yok |
| `ks run app.ks [ARG ...]` | denetler, sonra mühürlü MIR üzerinde adım ve çağrı derinliği bütçesiyle çalıştırır |
| `ks build app.ks -o app` | MIR-Go ile native ikili |
| `ks caps app.ks` | yetki manifestosu |
| `ks fmt app.ks` | kanonik biçimlendirme |
| `ks explain KS2402` | bir tanı kodunun açıklaması (`--lang en` / `--lang tr`) |
| `ks lock` / `ks build --locked` | modül kilidi ve doğrulanmış derleme |

Bütün tanı kodları [`../reference/ERROR_CODES.md`](../reference/ERROR_CODES.md) içinde.

## 11. Native derleme

`ks build`; çekirdek dili, struct, enum, generic, Map, modül, Core Library, program
girdisi, saat ve rastgelelik kullanan programları; linux/amd64'te ayrıca
kilitli bir aracı üzerinden disk (okuma, yazma, silme), ortam değişkenleri, ağ ve yerel sunucuyu derler
([`../NATIVE_BROKER_V1.md`](../NATIVE_BROKER_V1.md), [`../NET_V1.md`](../NET_V1.md)). İkili `ks run` ile aynı
baytları ve aynı hata değerlerini yazdırır. Geri çağrılı üyeler
(`filter`, `map`, `sort`) ve süreçler farklı derlenmek yerine `KS4004`
ile reddedilir; bkz.
[`../MIR_GO_CONFORMANCE_ADAPTER_V2.md`](../MIR_GO_CONFORMANCE_ADAPTER_V2.md).

## 12. Bilinmesi gereken sınırlar

- Bir String en fazla 16 MiB UTF-8, bir List en fazla 1.048.576 öğe tutar
  (`KS3502`).
- `ks run` bir programı varsayılan olarak 1.000.000 adımdan sonra
  (`--max-steps`) ve 512 iç içe çağrıda durdurur.
- Henüz etkileşimli satır okuma yoktur; aracı yalnızca linux/amd64'te vardır
  ([`../SERVE_KNOWHERE_V1.md`](../SERVE_KNOWHERE_V1.md)).
