# Koschei Language Core v0.8 alpha 1

> Çökmeyen, Hacklenemeyen, Ölümsüz Dil.

Bu belge, çalışan Koschei compiler çekirdeğinin kapsamını sabitler.

## Dört ilke

1. **Yetki olmadan yan etki yok.** Disk, ağ, ortam, süreç — hepsi jeton ister ve jeton derleme zamanında denetlenir.
2. **Null yok.** Bulunmayabilecek değerler `Option<T>` ile `Some(value)` / `None()` olarak temsil edilir.
3. **Hatalar değerdir.** `or return`, `or varsayilan`, `or { ... }` ile ele alınır; sessizce yutulamaz.
4. **Varsayılan değişmezlik.** `let` immutable, `let mut` açık niyet ister.

## Canonical sözdizimi

```ks
fn load_config(disk: DiskReadCaps, path: String) -> String or Error {
    let content = disk.read(path) or return Error("Config okunamadı: {path}")
    return content
}

fn main(caps: SystemCaps) {
    let cfg_read = caps.disk.allow_read_only("/etc/app/")
    let config = load_config(cfg_read, "/etc/app/config.json") or {
        println("Başlatma hatası")
    }

    let mut attempts = 0
    while attempts < 3 {
        attempts = attempts + 1
    }

    if attempts == 3 {
        println("Tamam: {config}")
    }
}
```

## Yetki modeli (derleme zamanında zorlanır)

Kök ve daraltılmış yetkiler **farklı tiplerdir**; bu yüzden daraltma tek yönlüdür:

| İfade | Tip | Yapabildikleri |
|---|---|---|
| `caps.net` | `NetRoot` | yalnızca `allow(origin)` |
| `caps.disk` | `DiskRoot` | yalnızca `allow(path)`, `allow_read_only(path)` |
| `caps.env` | `EnvRoot` | yalnızca `allow(name)` |
| `caps.process` | `ProcessRoot` | yalnızca `allow(cmd)` |
| `NetRoot.allow(...)` | `NetCaps` | `get post put delete request` — `allow` **yok** |
| `DiskRoot.allow(...)` | `DiskCaps` | `read write list delete` — `allow` **yok** |
| `DiskRoot.allow_read_only(...)` | `DiskReadCaps` | `read list` — yazma ve `allow` **yok** |
| `EnvRoot.allow(...)` | `EnvCaps` | `get` |
| `ProcessRoot.allow(...)` | `ProcessCaps` | `run spawn` |

Sonuçlar:
- Kök yetkiyle doğrudan G/Ç yapılamaz → **KS2402**
- Daraltılmış yetki yeniden `allow` çağıramaz → **KS2403**
- Salt-okunur yetki yazamaz → **KS2404**
- Yetkisiz scope'ta yetkili işlem → **KS2401**

## Sözdizimi kuralları

- Büyük harfle başlayan her isim **tip** sayılır; değişken ve fonksiyon adları küçük harfle başlamalıdır.
- `true` / `false` Bool değerleridir; `if` ve `while` koşulları Bool olmalıdır.
- Mantıksal işleçler `&&`, `||`, `!` — `or` anahtar kelimesi yalnızca hata/varsayılan akışı içindir.
- Operatör önceliği: `or` → `||` → `&&` → `== !=` → `< <= > >=` → `+ -` → `* /` → `! -` (unary) → çağrı.
- String interpolasyonu normal Koschei ifadelerini kabul eder: `"{items.length()}"`, `"{1 + 2}"`, `"{config.get("name") or "?"}"`. Düz süslü parantez için `\{` ve `\}` kullanılır.

## 'or' biçimleri

```ks
let a = f() or return Error("üst kata fırlat")
let b = f() or 8080                  // varsayılan değer
let c = f() or { println("logla") }  // blokla ele al
```

## Enum, exhaustive `match`, Option ve Result

Enum varyantları constructor gibi çağrılır. Payload taşımayan varyantlarda da
parantez kullanılır; bu, değer ile tip adını açık biçimde ayırır:

```ks
enum Delivery {
    Pending,
    Sent(String),
    Failed(Error),
}

let state = Sent("kargoya verildi")
```

`match` bir ifade üretir ve **exhaustive** olmak zorundadır. Aynı varyant iki kez
yazılamaz; payload taşıyan kol bir bağlama adı ister:

```ks
let message = match state {
    Pending => "bekliyor",
    Sent(text) => text,
    Failed(error) => "hata",
}
```

Bir enum'a yeni varyant eklendiğinde eski `match` ifadeleri sessizce eksik
çalışmaz; KS1702 ile derleme durur. Bu, durum uzayının tamamını derleyicinin
korumasına verir.

Yerleşik cebirsel tipler aynı runtime modelini kullanır:

```ks
fn find(active: Bool) -> Option<String> {
    if active { return Some("Onur") }
    return None()
}

fn load(active: Bool) -> Result<String, Error> {
    let name = find(active) or return Err(Error("bulunamadı"))
    return Ok(name)
}
```

- `Option<T>` varyantları: `Some(T)`, `None()`
- `Result<T, E>` varyantları: `Ok(T)`, `Err(E)`
- `or` başarı varyantını açar; `None` / `Err` / legacy `Error` akışını ele alır.
- `or return` hata varyantını üst fonksiyona taşır.
- Generic arity sabittir: `Option` bir, `Result` iki tip argümanı alır.
- Capability değerleri enum, Option veya Result payload'ına saklanamaz.

Bu alpha diliminde generic sözdizimi yalnızca `Option<T>` ve `Result<T, E>` için
açıktır. Kullanıcı tanımlı generic struct/fonksiyonlar v1.x kapsamındadır.

## Map / sözlük

Map anahtarları `String` olmak zorundadır. Map değerleri List gibi immutable'dır:
`set` mevcut değeri değiştirmez, yeni bir Map döndürür.

```ks
let customer = {"name": "Ali", "age": 42}
let updated = customer.set("city", "Istanbul")
let name = updated.get("name") or "bilinmiyor"
let keys = updated.keys()
let has_city = updated.contains("city")
```

Metotlar:

| Metot | Sonuç |
|---|---|
| `get(key)` | Değer veya hata; `or` ile ele alınır |
| `set(key, value)` | Anahtarı eklenmiş/değiştirilmiş yeni `Map` |
| `keys()` | Ekleme sırasındaki anahtarları taşıyan `List` |
| `contains(key)` | Anahtar varsa `true` |

Capability değerleri Map içine konamaz. `Map.get()` öğe tipini henüz statik
olarak korumadığı için compiler ve runtime bu yolu capability type-laundering'e
karşı kapatır.

## Günlük String ve List metotları

String değerleri immutable'dır:

```ks
let clean = "  ali,ayşe  ".trim()
let names = clean.split(",")
let label = " | ".join(names)
```

| String metodu | Sonuç |
|---|---|
| `trim()` | Baştaki/sondaki boşlukları kaldıran `String` |
| `split(separator)` | Parçalardan oluşan `List`; boş ayıraç hata değeridir |
| `join(parts)` | String öğeli List'i alıcı String ile birleştirir |
| `length()` | Unicode karakter sayısı |
| `contains(value)` | Alt metin varsa `true` |

List metotları mevcut listeyi değiştirmez:

```ks
fn positive(value: Int) -> Bool {
    return value > 0
}

let values = [3, -1, 2]
let ordered = values.sort() or []
let selected = values.filter(positive) or []
```

`filter`, lambda sözdizimi gelene kadar tek argüman alan ve `Bool` döndüren yerel,
adlandırılmış bir fonksiyon kullanır. `sort()` yalnızca homojen String veya sayısal
List'leri sıralar; desteklenmeyen öğeler hata değeridir. Capability değerleri List
içine konamaz veya `push` ile eklenemez.

## Hata kodları

| Kod | Anlamı |
|---|---|
| KS1101 | Tanımsız isim |
| KS1102 | Aynı scope içinde tekrar tanım |
| KS1201 | Immutable değere atama |
| KS1301 | Tip uyuşmazlığı (`"abc" + 5`, Bool olmayan `if` koşulu vb.) |
| KS1401 | Ele alınmayan hata değeri (sonuç `let` ile bağlanmalı ya da `or` ile ele alınmalı) |
| KS1501 | Struct alanı veya Map sabit anahtarı hatası (eksik, bilinmeyen veya yinelenen) |
| KS1502 | Struct'ta böyle bir alan yok / desteklenmeyen metot |
| KS1601 | Modül dosyası bulunamadı |
| KS1602 | Döngüsel import |
| KS1603 | Aynı modül birden fazla kez içe aktarılmış |
| KS1604 | İki modül aynı struct adını tanımlıyor |
| KS1605 | Modülde böyle bir fonksiyon, struct veya enum yok |
| KS1701 | Enum/varyant constructor sözleşmesi hatası |
| KS1702 | `match` exhaustive değil veya kol sözleşmesi hatalı |
| KS2401 | Gerekli yetki bu scope içinde mevcut değil |
| KS2402 | Kök yetki doğrudan kullanılamaz; önce daraltılmalı |
| KS2403 | Daraltılmış yetki yeniden genişletilemez |
| KS2404 | Bu yetki türü ilgili işleme izin vermez |
| KS4001 | Native hedef capability sözleşmesini aynı güvenlikle uygulayamıyor |
| KS4002 | Native derlemede desteklenmeyen dil yapısı |
| KS4003 | Çağrıda argüman sayısı uyuşmuyor |

Runtime (çalışma anı) hata kodları:

| Kod | Anlamı |
|---|---|
| KS3101 | Tanımsız isim / geçersiz çağrı (savunma katmanı) |
| KS3105 | Çağrı derinliği sınırı aşıldı (512) — sonsuz özyineleme koruması |
| KS3201 | Immutable değere runtime ataması (savunma katmanı) |
| KS3402 | Kapsam dışı erişim: disk yolu, ağ origin'i **veya kapsam dışına çıkan ağ yönlendirmesi** |
| KS3403 | Runtime'da daraltılmış yetkiyi genişletme girişimi |
| KS3404 | Yetki türünün izin vermediği işlem (ör. salt-okunur yetkiyle yazma) |

## Biçimlendirme (`ks fmt`)

Koschei kodunun tek bir doğru görünümü vardır ve bunu araç belirler:

```bash
ks fmt program.ks           # kanonik biçimi yazdırır
ks fmt --write program.ks   # dosyayı yerinde düzeltir
ks fmt --check program.ks   # biçim bozuksa çıkış kodu 1 (CI kapısı)
```

Kurallar: 4 boşluk girinti, işleçlerin iki yanında tek boşluk, `name: Type`,
`,` sonrası tek boşluk, dosya sonunda tek satır sonu, art arda en fazla bir boş
satır. Süslü parantezler ve deyim anahtar kelimeleri (`let`, `return`, `if`,
`while`, `fn`) her zaman satır kırar; böylece tek satıra sıkıştırılmış kod açılır.
`or return` ve `else if` bölünmez. Yorumlar korunur.

İki garanti testlerle sabitlenmiştir: biçimlendirme **değişmezdir**
(`fmt(fmt(x)) == fmt(x)`) ve **anlamı korur** (yorum dışı token akışı
değişmez). Depodaki örneklerin kanonik biçimde kalması CI'da doğrulanır.

**Bilinen sınır:** anahtar kelimeyle başlamayan deyimler (ör. arka arkaya iki
`println(...)`) aynı satıra yazılmışsa ayrılmaz. Biçimlendirici yazarın ayırdığı
satırları asla birleştirmez; tokenlardan deyim sınırı tahmin etmek yanlış
birleştirmelere yol açacağı için denenmez.

## Yetki manifestosu

Bir programın neye erişebildiği, programı çalıştırmadan listelenebilir:

```bash
ks caps program.ks           # okunabilir manifesto
ks caps program.ks --json    # araçlar için JSON
ks caps program.ks --deny net --deny process   # politika kapısı
```

Örnek çıktı:

```text
KOSCHEI YETKİ MANİFESTOSU: examples/showcase.ks

DİSK:
  - /etc/app/  [salt-okunur]  (satır 9)
  kullanılan işlemler: read
AĞ:
  - https://api.example.com  (satır 10)
ORTAM DEĞİŞKENİ: yok
SÜREÇ: yok

YETKİ TAŞIYAN FONKSİYONLAR:
  - load_config(disk: DiskReadCaps)

Bu program yukarıda listelenen kapsamların DIŞINDA hiçbir şeye erişemez.
```

`--deny` ile belirtilen bir alan talep edilirse çıkış kodu **2** döner; böylece
CI'da "bu servis ağa çıkmamalı" gibi politikalar zorlanabilir.

Manifesto bilinçli olarak muhafazakârdır: kapsam sabit bir metin değilse
(örneğin bir değişkenden geliyorsa) `<DİNAMİK>` olarak işaretlenir ve manifesto
**kesin sayılmaz**. Bilmediğini bildiğini iddia eden bir güvenlik raporu, rapor
olmaktan çıkar.

## Native derleme (v0.8 alpha 2)

Koschei programları Go ara koduna çevrilip tek bir native binary olarak
derlenebilir:

```bash
ks emit-go program.ks        # üretilen Go ara kaynağı (Go gerekmez)
ks build program.ks -o prog  # tek dosya binary (Go kurulu olmalı)
./prog                                       # hiçbir bağımlılık gerektirmez
```

Üretilen Go kodu bir **ara temsildir**, kullanıcıya gösterilmek için değildir:
okunabilirlik değil davranış eşliği hedeflenir. `build` çıktısı ile `run`
çıktısının aynı olması CI'da her koşuda doğrulanır.

v0.8 alpha 2, capability runtime ABI v1 çekirdeğini üretilen binary'ye taşır:

- `main(caps: SystemCaps)` için kök yetki çalışma anında enjekte edilir.
- `EnvCaps`, yalnız izin verilen environment değişkenini okuyabilir.
- `NetCaps.get`, yalnız `http/https` kullanır; scheme + host + etkin port aynı
  origin olmak zorundadır. Redirect zinciri de aynı origin içinde kalır.
- `DiskCaps` ve `DiskReadCaps`, Linux hedefinde kapsam kökünü bir dosya
  tanıtıcısıyla sabitler; yol bileşenleri `openat` ve `O_NOFOLLOW` ile geçilir.
  `read/write/list/delete` kapsam dışına ve sembolik bağlara karşı fail-closed'dur.
- `ProcessCaps.run/spawn` henüz işlem başlatmaz; hata değeri döndürerek kapalı kalır.

Native disk ABI daha zayıf bir yol kontrolüne GERİ DÜŞMEZ. Güvenli primitive'ler
bulunmayan hedefte derleme **KS4001** ile durur. Enum/match/Option/Result,
List/Map/struct/import gibi henüz taşınmamış dil yapıları da **KS4002** ile açıkça
reddedilir; sessiz yanlış çeviri yapılmaz.

Native tarafta ayrıca korunan davranışlar: hatalar değerdir (`or`'un üç biçimi),
çağrı derinliği sınırı (KS3105), sıfıra bölme bir hata değeridir ve değer gösterimi
host dilden bağımsızdır (`true`/`false`, `4.0`).

**Bilinen sınırlar:** Int aritmetiği native tarafta 64 bit ile sınırlıdır
(yorumlayıcıda Python'un sınırsız tam sayıları kullanılır); çok büyük sayılarla
çalışan programlarda iki hedef farklılaşabilir.

## v0.8 alpha compiler hattı

```text
.ks source
    -> lexer.py     (interpolasyon, enum/match, generic tip işaretleri)
    -> parser.py    (öncelik zinciri, üç 'or' biçimi, exhaustive match AST)
    -> ast_nodes.py
    -> semantic.py  (scope, tip, kök/daraltılmış yetki denetimi)
    -> interpreter.py  (tree-walking runtime, yetki denetimi çalışma anında)
    -> codegen_go.py   (Go ara kodu -> native binary + capability ABI v1 alpha)
```

## CLI

```bash
ks tokens examples/capability.ks
ks ast examples/capability.ks
ks check examples/capability.ks
ks run examples/capability.ks
ks explain KS2403      # hata kodunu açıklar, düzeltme örneği verir
```

`explain`, ham kodu (`KS2403`) veya kodu içeren tam hata metnini kabul eder.
Bir derleme/çalışma hatası oluştuğunda CLI zaten ilgili `explain` komutunu önerir.
Tanı katalogu sabittir: yalnızca açıklama üretir, hiçbir denetimi gevşetmez.

`check` komutu lexer, parser ve semantic güvenlik kontrollerini birlikte çalıştırır.

## Bilinen sınırlar (v0.8 alpha 2)

- Generic sözdizimi yalnızca `Option<T>` ve `Result<T, E>` için açıktır; List/Map ve kullanıcı tanımlı generics henüz yoktur.
- Map anahtarları yalnızca String'dir; List ve Map öğe tipi akış boyunca statik olarak korunmaz.
- Go backend enum/match/Option/Result ile List/Map/struct/import yapılarını henüz üretmez; bunlar **KS4002** ile fail-closed reddedilir.
- Native ağ ABI bu aşamada yalnız GET'i gerçekleştirir; POST/PUT/DELETE/request hata değeri olarak kapalıdır.
- Native disk ABI alpha yalnız Linux `openat`/`O_NOFOLLOW` hedefindedir. Güvenli eşdeğeri olmayan platformlarda **KS4001** üretilir.
- Native process capability işlem başlatmaz; `run/spawn` hata değeri döndürür.
- Tanı mesajları şimdilik Türkçedir; İngilizce yerelleştirme v0.9 kapsamındadır.
