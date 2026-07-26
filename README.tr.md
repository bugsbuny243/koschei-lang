# Koschei (`.ks`)

**Capability tabanlı güvenli bir programlama dili. İçe aktardığınız bir paket, siz açıkça bir jeton vermedikçe diskinize, ağınıza veya ortam değişkenlerinize dokunamaz.**

Tedarik zinciri saldırılarının çalışma nedeni şu: bir bağımlılık, sürecin sahip olduğu bütün izinleri otomatik olarak devralır. Paketi kurarsınız ve o paket `~/.ssh` dizinini, `.env` dosyanızı okuyabilir veya bir socket açabilir — hiç sormadan. Koschei bu "ortamdan gelen yetki"yi kaldırır: yan etki erişimi, fonksiyona parametre olarak geçirilmesi gereken bir değerdir ve derleyici, kendisine verilmemiş bir yetkiye uzanan programı reddeder.

English: [README.md](README.md)

---

## 60 saniyede dene

Kasıtlı olarak zararlı hazırlanmış bir paket, bir sır dosyasını okuyup çağırana döndürmeye çalışıyor. Hiç çalışmadığını kendi makinenizde doğrulayın.

```bash
git clone https://github.com/bugsbuny243/koschei-lang
cd koschei-lang
pip install .
ks check examples/supply_chain/main.ks
```

Test edilen paket — `examples/supply_chain/analytics.ks`:

```ks
fn track(event: String) -> String or Error {
    let secret = disk.read("/etc/app/secrets.env") or return Error("okunamadi")
    return secret
}
```

Çıktı:

```text
KOSCHEI ERROR: KS2401 [line 6, column 18]: Required capability is unavailable
in this scope — A disk, network, environment, or process operation was
attempted without the corresponding capability token.
Hint: run 'ks --lang en explain KS2401' for details.
```

Çıkış kodu `1`. Program hiç çalışmadı. Dosya hiç açılmadı. Hiçbir yere hiçbir şey gönderilmedi.

Bu, çağrıyı yakalayan bir runtime sandbox değil. `track` fonksiyonunun içinde `disk` diye bir şey hiç yok — saldırı derleme anında ölüyor.

---

## Kurulum

Python 3.12 veya üstü. Başka hiçbir bağımlılık yok — bir güvenlik dilinin kurulumu, güvenmek zorunda olduğunuz paket sayısını artırmamalı.

```bash
pip install git+https://github.com/bugsbuny243/koschei-lang
ks version
```

İlk programınız:

```bash
ks new hello-koschei
cd hello-koschei
ks run .
```

`ks new`, `koschei.toml` ve `src/main.ks` içeren sıfır bağımlılıklı bir proje oluşturur. Komutlar kaynak dosyası, proje dizini veya doğrudan `koschei.toml` yolu kabul eder.

---

## Temel ilkeler

- **Ortamdan gelen yetki yok.** Disk, ağ, ortam değişkeni ve process erişimi açık bir capability değeri gerektirir. Kendisine böyle bir değer geçirilmemiş fonksiyon o etkiyi gerçekleştiremez.
- **Yetkiler daralır, asla genişlemez.** `caps.disk` yalnızca devredebilen bir kök jetondur; `caps.disk.allow(yol)` daraltılmış bir jeton üretir ve bu jeton yeniden genişletilemez (`KS2403`), kök jeton da doğrudan I/O yapamaz (`KS2402`).
- **`null` yok.** Bulunmayabilecek değerler `Option<T>` ile temsil edilir (`Some` / `None`).
- **Hatalar birer değerdir.** `Result<T, E>` ve tek bir `or` anahtar sözcüğünün üç biçimi: `or return`, `or default`, `or { blok }`. Ele alınmamış hata değeri derleme hatasıdır (`KS1401`).
- **Varsayılan immutable.** Değer değiştirmek için `let mut` gerekir.
- **Her tanı açıklanabilir.** 33 hata kodu, Türkçe/İngilizce katalog; `ks explain KS2401` nedeni ve çözümü yazdırır.

## Örnek

```ks
fn fetch_data(net: NetCaps, url: String) -> String or Error {
    let response = net.get(url) or return Error("istek başarısız")
    return response.text()
}

fn main(caps: SystemCaps) {
    let api_net = caps.net.allow("https://api.example.com")
    let response = fetch_data(api_net, "https://api.example.com/v1")
    println(response)
}
```

`fetch_data` tam olarak tek bir origin'e erişebilir. Diske dokunamaz, ortam değişkeni okuyamaz, process başlatamaz — denetlenip "yapmıyor" bulunduğu için değil, buna izin verecek jetonu taşımadığı için.

## Yetki manifestosu

Yetki kaynak kodda açık olduğu için makineyle özetlenebilir. `ks caps`, bir programın erişebildiği her şeyi tüm modül grafiği boyunca raporlar:

```bash
ks caps examples/app.ks
ks caps --json src/main.ks
ks caps --deny net src/main.ks   # program ağa erişebiliyorsa 2 ile çıkar
```

Saf bir program için manifesto boştur ve bu, kod incelemesinde verilen bir söz değil, doğrulanabilir bir olgudur:

```text
KOSCHEI YETKİ MANİFESTOSU: examples/app.ks

Bu program hiçbir yan etki yeteneği taşımıyor.
Disk, ağ, ortam değişkeni ve süreç erişimi YOKTUR — saf hesaplama.
```

`--deny` kapısı CI için tasarlandı: bir bağımlılık güncellemesi sessizce erişim ekliyorsa build düşer.

## Dil özellikleri

Bugün çalışan: tipli parametrelerle fonksiyonlar, `let` / `let mut`, struct, `List`, immutable `Map` (`get`/`set`/`keys`/`contains`), `for`-in, yalnızca `Bool` koşullu `if`/`else`/`while`, exhaustive `match` ile enum'lar, gerçek `Option<T>` / `Result<T, E>`, tam ifade interpolasyonu (`"{items.length()}"`), günlük stdlib (`String` `trim`/`split`/`join`, `List` `sort`/`filter`/`contains`) ve `import risk` yazınca yanındaki `risk.ks` dosyasını bağlayan modül sistemi — manifest yok, build script yok, config yok.

## Araç zinciri

```bash
ks check src/main.ks          # tip, modül ve capability denetimi
ks run src/main.ks            # interpreter
ks build src/main.ks -o app   # üretilen Go üzerinden native binary
ks fmt --write src/           # kanonik biçimlendirme
ks caps src/main.ks           # yetki manifestosu
ks explain KS2401             # tanılar, Türkçe için --lang tr
ks check --json src/main.ks   # editörler için sabit code/message/line/column
ks tokens / ks ast / ks emit-go
```

Hat şöyle: `.ks` → lexer → parser → AST → tip, capability ve immutability denetimleri → Go kod üretimi → native binary. Tanılar varsayılan olarak İngilizcedir; `--lang tr` veya `KOSCHEI_LANG=tr` aynı hata kodlarıyla Türkçe kataloğu seçer.

## Editör desteği

`editors/vscode` içinde resmi uzantı var: `.ks` syntax highlighting, bracket/comment kuralları, `Koschei: Check Current File` komutu ve kaydette tanılar. npm bağımlılığı yoktur.

## Testler

```bash
python -m unittest discover -s tests -v
```

321 test. Atlanan 33 tanesi yerel Go toolchain gerektirir ve CI'da koşar; CI her push ve pull request'te tüm test setini çalıştırır — buna zararlı `examples/supply_chain/` paketinin hâlâ derlenemediğinin doğrulanması da dahil.

## Durum

Koschei **v0.9.0**, alpha aşamasında. Gerçek çok dosyalı programları çalıştırıyor ve capability modeli baştan sona uygulanıyor, ancak sözdizimi ve runtime sözleşmeleri v1.0'a kadar değişebilir. Henüz prodüksiyona koymayın.

Native tarafta şu anda uygulanan güvenlik sınırları:

- Güvenli native disk ABI, Linux `openat` / `O_NOFOLLOW` hedefler. Güvenli eşdeğerin bulunmadığı bir platformda disk kullanan build daha zayıf bir yola düşmek yerine `KS4001` ile durur.
- Process capability'sinin `run` / `spawn`'ı process başlatmaz; hata değeri döndürür.
- Çalışma anında path traversal, symlink kaçışı ve kapsam dışı yollar `KS3402` verir; salt-okunur jetonla yazma `KS3404` verir; izin verilen origin'den çıkan HTTP redirect reddedilir; çağrı derinliği 512 ile sınırlıdır (`KS3105`).

Sıradaki kapı **v1.0**: dondurulmuş sözdizimi ve capability runtime ABI, SemVer uyumluluk taahhüdü, en az `List<T>` ve `Option<T>` için generic sözleşme, kilit dosyalı paket çözümleme ve migration testleri.

**Tasarlandı ama yapılmadı** — ve tamamlanmış özellik olarak sunulmuyor: static region inference, C backend, Sentinel / tarpit katmanları. Koschei yetkileri tip sisteminde zorunlu kılar; formel matematiksel kanıt üretmez ve bugün region tabanlı bellek yönetimi kullanan bir dil değildir — mevcut backend Go üretir ve Go'nun çöp toplayıcısını kullanır.

## Katkı

Şu anda en faydalı katkı gerçek bir program. Koschei'de küçük bir şey yazın ve dil ayağınıza dolandığında issue açın — eksik bir stdlib fonksiyonu, kafa karıştıran bir tanı, derlenmesi gerekirken derlenmeyen bir kalıp. Problemi tekrar üreten bir `.ks` dosyasıyla gelen hata bildirimleri en hızlı düzelen bildirimlerdir.

## Lisans

MIT
