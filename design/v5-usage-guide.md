# Koschei v5 — Kullanım Rehberi (TASARIM)

> ## ⚠️ Bu bir doküman değil, bir tasarım hedefidir
>
> **Bu rehberin tamamı bugün gerçek değildir.** Bazı sözdizimi parçaları V5 geçişi sırasında inmeye başladı; fakat blokların anlattığı uçtan uca güvenlik, runtime ve backend sözleşmeleri tamamlanmış değildir. Bugünkü sürüm v0.9'dur.
>
> Bu dosya `docs/` altında değil `design/` altında durur, çünkü `docs/` "çalışan şeyler" demektir.
>
> Derleyicinin doğrudan ayırt edebildiği gelecek kod bloklarının üstünde `<!-- verify: future -->` işareti vardır. `verify.sh` bu blokların henüz derlenmediğini doğrular. Region tabanlı bellek gibi aynı sözdizimiyle çalışan ama arka uç garantisi henüz gelmemiş hedefler, nedenini yazan `verify: skip` işaretiyle ayrı takip edilir. Bir `future` bloğu derlenmeye başladığı gün script şunu basar:
>
> ```
> NEW!  design/v5-usage-guide.md:120 — this v5 feature now compiles. Update the guide.
> ```
>
> Yani bu rehber bir vaat değil, **makine tarafından izlenen bir ilerleme panosudur.** Bir özellik indiğinde rehber `docs/` tarafına taşınır.
>
> Bugün çalışan şeyler için: `docs/koschei-ile-kod-yazma-rehberi.md`.

---

## 0. v5 neyi vaat ediyor

Tek cümle:

> **Rust'tan daha ileri güvenlik garantisi veren, ama günlük yazımda Python kadar kolay bir dil.**

Bu iki yarının nasıl aynı anda tutulacağı tek bir mühendislik kuralına dayanıyor:

> **Derleyicinin çıkarabildiği hiçbir şey kullanıcıya yazdırılmaz.**

v5'te güvenlik bilgisi *görünürdür* ama *yazılmaz*. `ks caps` her şeyi gösterir; kaynak kodu sessiz kalır. Aşağıdaki her tasarım kararı bu kuraldan türüyor.

---

## 1. v0.9'dan v5'e ne değişiyor

| Bugün (v0.9) | v5 |
|---|---|
| `let x = 5` (tip yazılamaz) | `let x = 5` veya `let x: Int = 5` — ikisi de |
| `break` / `continue` yok | Var, etiketli `break 'dis` dahil |
| `match` kolları sadece ifade | Kollar blok olabilir, yan etki serbest |
| Lambda yok | Birinci sınıf fonksiyonlar ve closure |
| `impl` / metot yok | `impl` blokları ve trait'ler |
| Struct alanı değiştirilemez | `let mut` bağlamada değiştirilebilir |
| Generic fonksiyonlar, structlar ve enumlar | Trait sınırları, closure generic'leri ve MIR monomorphization |
| `Int / Int` bozuk | `Int / Int -> Int`, `%` kalan, `Float` ayrı |
| Eşzamanlılık yok | Yapılandırılmış eşzamanlılık |
| Küçük stdlib | 12 modül |
| Go arka ucu, Go GC'si | Kendi arka ucu, region tabanlı bellek |
| `[capabilities]` denetlenmiyor | Registry tarafından zorlanıyor |

---

## 2. Temeller

<!-- verify: future -->
```ks
fn main() {
    let ad = "Onur"
    let mut sayac: Int = 0

    sayac = sayac + 1

    let toplam = 10 / 3          // 3 — tam bölme
    let kalan = 10 % 3           // 1
    let oran = 10.0 / 3.0        // 3.333... (Float)

    println("{ad}: {sayac}, {toplam}, {kalan}, {oran}")
}
```

Tip anotasyonu **isteğe bağlıdır.** Yazmazsan çıkarılır; yazarsan zorlanır. Sayısal tipler arasında örtük dönüşüm yoktur — `Int` ve `Float` karışmaz.

### Döngü kontrolü

<!-- verify: future -->
```ks
fn ilk_ciftin_indeksi(sayilar: List<Int>) -> Option<Int> {
    let mut i = 0
    while i < sayilar.length() {
        let x = sayilar.get(i) or return None()
        if x % 2 != 0 {
            i = i + 1
            continue
        }
        return Some(i)
    }
    return None()
}

fn main() {
    'dis: for satir in tablo() {
        for hucre in satir {
            if hucre == "dur" {
                break 'dis
            }
        }
    }
}
```

---

## 3. Generic'ler

Generic fonksiyonlar ile kullanıcı tanımlı generic struct/enumların ilk güvenli
dilimi bugün çalışıyor. Çıkarılabilen tip argümanları çağrı veya constructor
yerinde tekrar yazılmaz:

```ks
struct Onbellek<K, V> {
    girdiler: Map<K, V>,
    kapasite: Int,
}

enum Durum<T> {
    Hazir(T),
    Eksik,
}

fn ilk<T>(items: List<T>) -> Option<T> {
    return items.get(0)
}

fn main() {
    let cache = Onbellek { girdiler: {"port": 8080}, kapasite: 16 }
    let durum = Hazir("tamam")
    let mesaj = match durum {
        Hazir(value) => value,
        Eksik => "yok",
    }
    println(cache.girdiler.get("port") or 0)
    println(mesaj)
}
```

Bu dilimde raw `Onbellek` API tipi ve çelişen çıkarım `KS1307` ile reddedilir;
capability değerleri `T` arkasına saklanamaz. Çalışan ayrıntılar
`docs/generic-aggregates-v5.md` içindedir.

Birinci sınıf fonksiyon tipi, lambda ve closure generic'leri henüz gelmedi:

<!-- verify: future -->
```ks
fn esle<T, U>(items: List<T>, f: fn(T) -> U) -> List<U> {
    let mut cikti = []
    for item in items {
        cikti = cikti.push(f(item))
    }
    return cikti
}

fn main() {
    let uzunluklar = esle(["ada", "lin"], fn(s: String) -> Int { return s.length() })
    println("{uzunluklar}")
}
```

V5 hedefinde generic'ler MIR üzerinde monomorphize edilir. İlk mühürlü MIR kapısı
bugün çalışıyor; generic fonksiyon çağrıları geçiş katmanında uzmanlaştırılıyor.
Normalize çekirdek MIR talimatları ve basic block’lar şema 2 ile indi. Backend’lerin
bu düğümleri doğrudan çalıştırması, `ast_fallback` kalemlerinin kaldırılması ve
generic monomorphization hâlâ açık kapılardır.

---

## 4. Trait'ler

<!-- verify: future -->
```ks
trait Yazdirilabilir {
    fn to_string(self) -> String
}

struct Urun {
    ad: String,
    fiyat: Int,
}

impl Yazdirilabilir for Urun {
    fn to_string(self) -> String {
        return "{self.ad} ({self.fiyat} TL)"
    }
}

impl Urun {
    fn zamli(self, oran: Int) -> Urun {
        return Urun { ad: self.ad, fiyat: self.fiyat + self.fiyat * oran / 100 }
    }
}

fn yazdir<T: Yazdirilabilir>(item: T) {
    println(item.to_string())
}

fn main() {
    let kahve = Urun { ad: "Kahve", fiyat: 120 }
    yazdir(kahve.zamli(10))
}
```

Kalıtım **yoktur.** Yalnızca trait bileşimi. Ve bir güvenlik kuralı: **trait implementasyonu capability üretemez.** Parametreyle alabilir, ama yoktan var edemez. Bu kural olmasaydı capability modeli trait sistemi üzerinden delinirdi.

---

## 5. Closure'lar

<!-- verify: future -->
```ks
fn main() {
    let iki_kat = fn(x: Int) -> Int { return x * 2 }
    let toplam = [1, 2, 3].map(iki_kat).reduce(0, fn(a: Int, b: Int) -> Int { return a + b })
    println("{toplam}")
}
```

### Closure ve yetki

Bir closure yakaladığı yetkiyi taşır, ama **sen bunu yazmazsın — derleyici çıkarır:**

<!-- verify: future -->
```ks
fn okuyucu(disk: DiskReadCaps) -> fn() -> String {
    return fn() -> String {
        return disk.read("/etc/app/config") or "varsayilan"
    }
}
```

Üç katmanlı kural:

1. **Fonksiyon içinde serbest.** Yakalama kısıtsız, hiçbir şey yazmazsın.
2. **Modül sınırında görünür.** Yakalanan yetki, dışa açık fonksiyonun imzasına derleyici tarafından eklenir ve `ks caps` manifestosunda listelenir.
3. **Sandbox sınırında yasak.** Yetki yakalayan closure, Phantom Sandbox'a geçirilemez — `KS2410`.

---

## 6. Desen eşleme

<!-- verify: future -->
```ks
enum Teslimat {
    Bekliyor,
    Gonderildi(String),
    Basarisiz(Error),
}

fn isle(t: Teslimat) -> Int {
    match t {
        Bekliyor => {
            println("henuz cikmadi")
            return 0
        }
        Gonderildi(takip) => {
            println("takip no: {takip}")
            kaydet(takip)
            return 1
        }
        Basarisiz(hata) => {
            uyar(hata)
            return -1
        }
    }
}
```

v5'te `match` hem ifade hem deyimdir. Kollarda blok açabilir, birden fazla iş yapabilirsin. Tamlık denetimi korunur: bir varyantı unutursan derleme durur.

---

## 7. Hata yönetimi

<!-- verify: future -->
```ks
fn config_yukle(disk: DiskReadCaps, yol: String) -> Result<Config, Error> {
    let ham = disk.read(yol) or return Err(Error("okunamadi: {yol}"))
    let ayrisik = json.parse(ham) or return Err(Error("gecersiz JSON"))
    return Ok(Config { port: ayrisik.get_int("port") or 8080 })
}

fn main(caps: SystemCaps) {
    let cfg_disk = caps.disk.allow_read_only("/etc/app/")

    match config_yukle(cfg_disk, "/etc/app/config.json") {
        Ok(cfg) => println("port {cfg.port}"),
        Err(e) => {
            println("varsayilan yapilandirmaya dusuldu")
            calistir(Config { port: 8080 })
        }
    }
}
```

`or` üç biçimini korur: `or return`, `or <değer>`, `or { blok }`. İşlenmemiş hata hâlâ derleme hatasıdır.

---

## 8. Standart kütüphane

v5'te 12 modül. Yetki gerektirenler işaretli:

<!-- verify: future -->
```ks
import string
import collections
import math
import encoding
import time                      // ClockCaps (ortam)
import random                    // EntropyCaps (ortam)
import io                        // ConsoleCaps (ortam)
import fs                        // DiskCaps (jeton)
import net                       // NetCaps (jeton)

fn main(caps: SystemCaps) {
    let ad = "  Onur Sel  ".trim().upper()
    let bas = ad.substring(0, 4)
    println("{bas} / {ad.starts_with("ONUR")}")

    let sayilar = [5, 3, 9, 1]
    let en_buyuk = sayilar.reduce(0, fn(a: Int, b: Int) -> Int { return math.max(a, b) })
    let tekil = collections.Set.from(sayilar)

    let veri = encoding.json.stringify(sayilar) or "[]"
    println("{en_buyuk} / {tekil.length()} / {veri}")

    let simdi = time.now()
    let satir = io.read_line() or ""
    println("{simdi} — girdi: {satir}")
}
```

---

## 9. Yetkiler: iki katman

v5'in en önemli ergonomi kararı. Yetkiler ikiye ayrılır:

| Katman | Yetkiler | Uygulamada |
|---|---|---|
| **Ortam** | `ConsoleCaps`, `ClockCaps`, `EntropyCaps` | `main`'e otomatik gelir, hiçbir şey yazmazsın |
| **Jeton** | `DiskCaps`, `NetCaps`, `EnvCaps`, `ProcessCaps`, `ListenCaps`, `FfiCaps` | Açıkça verilir ve daraltılır |

Kural: bir yetki **veriyi dışarı sızdırabiliyor veya sistemi değiştirebiliyorsa** jeton ister. Yalnızca gözlem yapıyorsa ortam yetkisidir.

**Kritik nokta:** Ortam yetkileri yalnızca uygulama kodu için otomatiktir. **Kütüphaneler hiçbir yetkiyi implicit almaz** — bir paket senin terminalinden okuyamaz, saati okuyup parmak izi çıkaramaz, entropi tüketemez.

<!-- verify: future -->
```ks
fn main(caps: SystemCaps) {
    println("bu satir icin jeton gerekmez")          // ConsoleCaps ortam

    let cfg = caps.disk.allow_read_only("/etc/app/")  // jeton, daraltılmış
    let api = caps.net.allow("https://api.example.com")

    servisi_calistir(cfg, api)
}
```

### Süreç çalıştırma

v0.9'da kapalı olan `process`, v5'te **güvenli sözleşmeyle** açılır:

<!-- verify: future -->
```ks
fn main(caps: SystemCaps) {
    let git = caps.process.allow("/usr/bin/git")
    let sonuc = git.run(["status", "--porcelain"], env: {}) or return
    println(sonuc.stdout)
}
```

- Kabuk **yoktur.** argv doğrudan `execve`'ye gider; shell injection kategorik olarak imkânsız.
- Binary yolu allowlist'te sabittir.
- Varsayılan environment **boştur**; devredilen her değişken yazılır.
- Alt süreç yetki **miras almaz.**

---

## 10. Eşzamanlılık

<!-- verify: future -->
```ks
fn main(caps: SystemCaps) {
    let gorevler = caps.tasks.allow(max_concurrent: 4)
    let api = caps.net.allow("https://api.example.com")

    let sonuclar = gorevler.scope(fn(s: Scope) -> List<Result<String, Error>> {
        let a = s.spawn(fn() -> Result<String, Error> { return cek(api, "/v1/a") })
        let b = s.spawn(fn() -> Result<String, Error> { return cek(api, "/v1/b") })
        return [a.join(), b.join()]
    })

    for sonuc in sonuclar {
        match sonuc {
            Ok(veri) => println("geldi: {veri.length()} bayt"),
            Err(e) => println("basarisiz"),
        }
    }
}
```

Üç ilke:

1. **Paylaşılan mutable durum yoktur.** Değerler immutable olduğu için veri yarışı tip sistemiyle imkânsızdır, kilit disipliniyle değil.
2. **Yapılandırılmış eşzamanlılık.** `scope` dönmeden hiçbir görev hayatta kalamaz. Sızdırılmış görev kategorisi yoktur.
3. **Eşzamanlılık bir yetkidir.** Bir kütüphane sana sormadan iş parçacığı açamaz; `max_concurrent` tavanı senindir.

`async` anahtar kelimesi **yoktur.** Renkli fonksiyon problemi tasarımla dışarıda bırakıldı: tüm IO scope içinde bloklanabilir, çalışma zamanı M:N zamanlar.

---

## 11. Bellek

Çöp toplayıcı yoktur. Lifetime anotasyonu da yoktur.

Aşağıdaki kaynak sözdizimi bugün de derlenebilir; V5 hedefi, aynı kodu Go GC yerine region tabanlı bellek modeliyle çalıştırmaktır. Bu nedenle compile-only kapı bu bloğun inişini ölçemez; ayrı backend/bellek raporu testi gelene kadar manuel olarak işaretlenmiştir.

<!-- verify: skip — region backend garantisi compile-only kapıyla ölçülemez -->
```ks
fn ozet(satirlar: List<String>) -> String {
    let mut cikti = ""
    for satir in satirlar {
        cikti = cikti + satir.trim() + "\n"
    }
    return cikti
}

fn main() {
    println(ozet(["  bir  ", "  iki  "]))
}
```

Bu kodda bellek yönetimi görünmüyor — **görünmemesi tasarım hedefidir.** Derleyici her ayırmanın hangi region'a ait olduğunu ve kapsamdan kaçıp kaçmadığını çıkarır. Kaçmayan değer kapsam bitince tek seferde serbest bırakılır; kaçan değer çağıranın region'ına terfi eder.

Çıkarım yetmediğinde **anotasyon yazmazsın, kaçış kapısı kullanırsın:**

<!-- verify: future -->
```ks
fn graf_kur(dugumler: List<String>) -> Arena<Dugum> {
    let mut arena = Arena.new()
    for ad in dugumler {
        arena.ekle(Dugum { ad: ad, komsular: [] })
    }
    return arena
}
```

`Arena<T>` ve `Rc<T>` stdlib'in parçasıdır. Region inference bir kaçış kapısı olmadan sevilmez — ve Rust'ın `<'a>` ceremonisi bu dilde açıkça **yasaklı** bir tasarım seçeneğidir.

Reddedilen program olursa tanı nettir:

```text
KS5001: bu değerin ömrü çıkarılamadı — kapsamdan kaçıyor ama nereye
        gittiği belirsiz. Arena<T> veya Rc<T> kullanın.
```

---

## 12. Paketler

`koschei.toml` v5'te **bağlayıcıdır**:

```toml
[package]
name = "http-client"
version = "2.1.0"
entry = "src/main.ks"

[capabilities]
net = ["https://api.example.com"]
disk = []
env = []
process = false

[dependencies]
json = "1.4"
```

Registry üç kuralı zorlar:

1. **Beyan edilmeyen yetki kullanılamaz.** Yayın anında `ks caps` çıktısı manifestle karşılaştırılır; uyuşmazsa paket yayınlanmaz.
2. **Yetki artışı büyük sürüm gerektirir.** `net` istemeyen bir paket 2.1.0'dan 2.1.1'e geçerken `net` istemeye başlayamaz. Gerçek dünyadaki tedarik zinciri saldırılarının en yaygın biçimi bu kuralla ölür.
3. **Geçişli yetki görünürdür.**

```bash
ks audit
```

```text
47 paket, 3'ü ağa çıkabiliyor, hiçbiri diske yazamıyor.

  http-client 2.1.0   net: https://api.example.com
  telemetry   0.9.2   net: https://t.vendor.io      ⚠ 0.9.1'de net yoktu
  json        1.4.0   —
```

---

## 13. Araçlar

```bash
ks new proje              # proje oluştur
ks add json@1.4           # bağımlılık ekle
ks check .                # tip, yetki, region denetimi
ks mir .                  # mühürlü backend sözleşmesini göster
ks run .                  # çalıştır
ks test                   # birim + tablo + property testleri
ks bench                  # istatistiksel ölçüm
ks build . -o app         # tek native binary
ks build --print-hash     # yeniden üretilebilirlik doğrulaması
ks build --report-memory  # statik tepe bellek tahmini
ks caps . --deny net      # CI yetki kapısı
ks audit                  # bağımlılık grafiği yetki raporu
ks doc                    # dokümantasyon üret, örnekleri test olarak koştur
ks fmt --write src/
ks explain KS5001
```

Editörde: autocomplete, go-to-definition, hover, canlı tanı ve **capability sızıntısı uyarısı**. Region görselleştirmesi hata ayıklayıcıda.

---

## 14. v0.9 kodunu v5'e taşıma

| v0.9 kodu | v5'te |
|---|---|
| `fn f(l: List) -> Int` | `fn f(l: List<Int>) -> Int` — ham `List` uyumluluk için kalır ama önerilmez |
| `-> String or Error` | Çalışmaya devam eder; yeni kod `Result<T, E>` kullanır |
| `Bekliyor()` | `Bekliyor` — parantez artık gerekmez |
| Bayrak değişkenli döngü | `break` / `continue` |
| Yeni struct üreterek mutasyon | `let mut` ile doğrudan alan atama |
| `disk.read("/tam/yol")` | Aynı; ayrıca kapsama göreli yol desteklenir |

`ks fix` komutu mekanik dönüşümleri otomatik uygular. Sözdizimi v1.0'da donduğu için v1→v5 arası **kırıcı değişiklik yoktur**; v0.9 bu garantiden önce olduğu için tek istisnadır.

---

## 15. v5'te bilerek olmayanlar

- **Kalıtım ve sınıf hiyerarşisi** — trait bileşimi yeterli
- **`async` anahtar kelimesi** — renkli fonksiyon problemi tasarımla dışarıda
- **Runtime yansıma (reflection)** — capability modelini deler, statik analizi imkânsızlaştırır
- **Genel `unsafe` bloğu** — FFI ayrı ve `FfiCaps` gerektiren bir kapıdır; dilin içinde serbest kaçış kapısı yok
- **Lifetime anotasyonu** — çıkarım yetmezse çözüm `Arena`/`Rc`, anotasyon değil
- **Çöp toplayıcı** — region yetersiz kalırsa karar yeniden açılır ve **duyurulur**
- **Makro sistemi** — v5 kapsamı dışı

---

## 16. Bu rehber ne zaman gerçek olur

Her kod bloğu `verify.sh` tarafından izleniyor. İlerleme şöyle ölçülür:

```bash
./verify.sh | grep "NEW!"
```

Boş çıktı: hiçbir v5 özelliği inmedi.
Her `NEW!` satırı: bir özellik indi, o bölüm `docs/` tarafına taşınabilir.

Rehber tamamen `docs/`'a taşındığında v5 gelmiş demektir. O gün gelene kadar bu dosya bir **hedef**, bir doküman değil — ve `verify.sh` bu ayrımın korunmasını senin yerine denetliyor.
