# Koschei Language Core v0.1

> Çökmeyen, Hacklenemeyen, Ölümsüz Dil.

Bu belge, çalışan Koschei compiler çekirdeğinin kapsamını sabitler.

## Dört ilke

1. **Yetki olmadan yan etki yok.** Disk, ağ, ortam, süreç — hepsi jeton ister ve jeton derleme zamanında denetlenir.
2. **Null yok.** İleride `Option<T>` ile `Some(value)` / `None` kullanılacaktır.
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
- String interpolasyonu: `"Selam {user.email}"`. v0.1'de yalnızca değişken ve alan erişimi desteklenir; `{1 + 2}` geçersizdir. Düz süslü parantez için `\{` ve `\}` kullanılır.

## 'or' biçimleri

```ks
let a = f() or return Error("üst kata fırlat")
let b = f() or 8080                  // varsayılan değer
let c = f() or { println("logla") }  // blokla ele al
```

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
| KS1605 | Modülde böyle bir fonksiyon veya struct yok |
| KS2401 | Gerekli yetki bu scope içinde mevcut değil |
| KS2402 | Kök yetki doğrudan kullanılamaz; önce daraltılmalı |
| KS2403 | Daraltılmış yetki yeniden genişletilemez |
| KS2404 | Bu yetki türü ilgili işleme izin vermez |
| KS4001 | Yetki içeren program native derlemede henüz desteklenmiyor (aşama 1) |
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

## Native derleme (aşama 1)

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

**Aşama 1 kapsamı:** yetki (capability) içermeyen, struct/List/Map/`for`/`import`
kullanmayan programlar. Desteklenmeyen yapılar sessizce yanlış çevrilmez, **KS4002** ile
açıkça reddedilir; bunlar `run` ile çalıştırılır. Yetki taşıyan
programlar bilinçli olarak reddedilir (KS4001) ve `run` ile çalıştırılır. Sıra
kasıtlıdır: yetki denetimi üretilen binary'ye taşınmadan yetkili program
derlemek, dili kâğıt üstünde güvenli ama gerçekte açık bırakırdı. Native yetki
runtime'ı aşama 2'nin konusudur.

Native tarafta halihazırda korunan davranışlar: hatalar değerdir (`or`'un üç
biçimi), çağrı derinliği sınırı (KS3105), sıfıra bölme bir hata değeridir, ve
değer gösterimi host dilden bağımsızdır (`true`/`false`, `4.0`).

**Bilinen sınırlar:** Int aritmetiği native tarafta 64 bit ile sınırlıdır
(yorumlayıcıda Python'un sınırsız tam sayıları kullanılır); çok büyük sayılarla
çalışan programlarda iki hedef farklılaşabilir.

## v0.1 compiler hattı

```text
.ks source
    -> lexer.py     (interpolasyon, && || !, if/else/while, true/false)
    -> parser.py    (öncelik zinciri, üç 'or' biçimi, kontrol akışı)
    -> ast_nodes.py
    -> semantic.py  (scope, tip, kök/daraltılmış yetki denetimi)
    -> interpreter.py  (tree-walking runtime, yetki denetimi çalışma anında)
    -> codegen_go.py   (Go ara kodu -> native binary, aşama 1)
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

## Bilinen sınırlar (v0.1)

- Birleşik dönüş tipleri (`String or Error`) metin olarak taşınır; tam tip denetimi v0.2'de.
- Enum/match, generics ve genel fonksiyon çağrılarında tam argüman tipi denetimi yok.
- Map anahtarları String'dir; generic `Map<K, V>` ve öğe tipi takibi henüz yoktur.
- String interpolasyonu yalnızca değişken ve alan erişimi alır; `{liste.length()}`
  gibi metot çağrıları desteklenmez (önce bir değişkene bağlayın).
- Yol/origin sınırları (`allow("/etc/app/")` kapsamı) statik olarak tip düzeyinde, dinamik olarak runtime aşamasında zorlanacaktır; runtime henüz yazılmadı.
- Tanı mesajları şimdilik Türkçedir; İngilizce yerelleştirme planlanmaktadır.
