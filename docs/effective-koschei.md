# Effective Koschei

> Bu belge dilin kurallarını değil, **üslubunu** anlatır.
> Kurallar `docs/language-core.md` içindedir; burada "derlenen kod" ile
> "Koschei gibi yazılmış kod" arasındaki farkı bulacaksınız.

Koschei kodunu bir bakışta tanımalısınız. Aşağıdaki yedi ilke o görünümü tanımlar.

Girinti, aralık ve satır düzeni tartışma konusu değildir: `ks fmt
--write dosya.ks` ne yaparsa doğru biçim odur. Bu belge biçimi değil, **karar
verme tarzını** anlatır — biçimlendiricinin dayatamayacağı kısmı.

---

## 1. Yetki tepeden daraltılır, aşağıya dar paslanır

Jetonlar yalnızca `main` içinde doğar. Fonksiyonlar kök yetki (`SystemCaps`,
`DiskRoot`, `NetRoot`) almaz — ihtiyaç duydukları en dar jetonu alır.

Bu örnek `/etc/app/config.json` dosyasının varlığını varsaydığı için release gate
onu çalıştırmaz; sözdizimi ve capability sözleşmesi compiler testlerinde ayrıca
kapsanır.

<!-- verify: skip — host üzerinde /etc/app/config.json gerektirir -->
```ks
// ✅ Koschei tarzı
fn load_config(disk: DiskReadCaps, path: String) -> String or Error {
    let content = disk.read(path) or return Error("Config okunamadı: {path}")
    return content
}

fn main(caps: SystemCaps) {
    let cfg_read = caps.disk.allow_read_only("/etc/app/")
    let config = load_config(cfg_read, "/etc/app/config.json") or return
}
```

<!-- verify: skip — kasıtlı olarak eksik bırakılmış karşı-örnek -->
```ks
// ❌ Koschei tarzı DEĞİL: tüm yetki aşağı taşınıyor
fn load_config(caps: SystemCaps, path: String) -> String or Error { ... }
```

İlk örnek derlenir. İkinci satır ise gövdesi özellikle `...` bırakılmış bir
üslup karşı-örneğidir; tek başına derlenebilir program değildir.

İkisi de tamamlanmış gövdelerle yazıldığında derlenebilir. Ama ikincisi, dilin var oluş sebebini çöpe atar: yetki ne
kadar aşağı inerse, o kadar çok kod her şeye dokunabilir hale gelir.
**Kural: bir fonksiyon ne kadar az yetki alıyorsa o kadar iyidir.**

## 2. İmza, iznin belgesidir

Bir fonksiyonun neye dokunduğunu anlamak için gövdesini okumayın —
parametrelerine bakın. Bu yüzden yetki parametreleri **her zaman başta** durur
ve gerçek adıyla anılır. Aşağıdaki satır bir API imzası örneğidir; gövde
bilerek gösterilmez.

<!-- verify: skip — yalnızca fonksiyon imzası örneği -->
```ks
fn sync_prices(net: NetCaps, cache: DiskCaps, symbol: String) -> Int or Error
```

Bu satır tek başına şunu söyler: bu fonksiyon ağa çıkar, diske yazar, başka
hiçbir şeye erişemez. Yorum satırına gerek yoktur — imza zaten dokümandır.

## 3. Hatalar tek kelimeyle karşılanır

`or` üç biçimde kullanılır ve seçim niyet bildirir:

```ks
let content = disk.read(path) or return Error("okunamadı")   // sorumluluğu üste devret
let port    = raw.to_int() or 8080                            // makul varsayılan
let cfg     = load() or { println("config yok, devam") }      // yerinde ele al
```

Hangisini seçtiğiniz, hatanın ne kadar önemli olduğunu okuyucuya söyler.
Piramit yok, `try` yok, sessizce yutulan hata yok — KS1401 zaten buna izin vermez.

## 4. Değişim işaretlenir

`mut` görmüyorsanız o değer sabittir. `mut` bir kolaylık değil, bir **uyarı
işaretidir**: "burada durum değişiyor, dikkat et."

```ks
let limit = 3               // sabit
let mut attempts = 0        // değişecek — bilinçli
```

Bir fonksiyonda çok sayıda `mut` varsa, bu genellikle o fonksiyonun çok fazla iş
yaptığının işaretidir.

## 5. Tören yok

Noktalı virgül yok. Konfigürasyon dosyası yok. Tip tekrarı yok. Yazdığınız her
satır iş yapmalıdır.

```ks
let user = fetch_user(api, 101) or return Error("kullanıcı çekilemedi")
```

Tip yazmak isteğe bağlıdır; **API sınırlarında** (fonksiyon parametreleri, dönüş
tipleri) tip zorunludur çünkü orası sözleşmedir. Gövde içinde çıkarıma güvenin.

## 6. İsimler kuralı taşır

Büyük harfle başlayan her isim tiptir; değişken ve fonksiyon adları küçük
harfle başlar. Yetki değişkenlerini kapsamlarıyla adlandırın — `disk` değil
`cfg_read`, `net` değil `api_net`:

```ks
let cfg_read = caps.disk.allow_read_only("/etc/app/")
let api_net  = caps.net.allow("https://api.example.com")
```

Böylece çağrı satırına bakan kişi, hangi kapının açıldığını okur.

## 7. En dar kapı, en kısa süre

Yetki daraltmasını gerçekten gereken en küçük kapsamla yapın: tüm diski değil o
dizini, yazma değil okuma, tüm ağı değil o origin'i açın. Salt-okunur yeterliyse
`allow_read_only` kullanın — daha sonra yazma gerekirse kök yetkiden yeni bir
jeton türetirsiniz (daraltılmış jeton genişletilemez: KS2403).

```ks
// ✅ iki ayrı, dar jeton
let cfg_read = caps.disk.allow_read_only("/etc/app/")
let cache    = caps.disk.allow("/var/cache/app/")

// ❌ tek geniş jeton
let disk = caps.disk.allow("/")
```

---

## Program iskeleti

Tipik bir Koschei programı şu sırayla okunur. Örnek gerçek bir dış API çağrısı
varsaydığı için release gate tarafından çalıştırılmaz.

<!-- verify: skip — api.example.com dış servisini gerektirir -->
```ks
// 1. Veri tipleri
struct UserProfile { id: Int, username: String }

// 2. Yetki alan iş fonksiyonları — en dar jetonlarla
fn fetch_user(net: NetCaps, user_id: Int) -> UserProfile or Error {
    let response = net.get("https://api.example.com/users/{user_id}")
        or return Error("API isteği başarısız")
    return parse_json(response.text()) or return Error("JSON ayrıştırılamadı")
}

// 3. main: yetkilerin doğduğu ve daraltıldığı TEK yer
fn main(caps: SystemCaps) {
    let api_net = caps.net.allow("https://api.example.com")
    let user = fetch_user(api_net, 101) or {
        println("Kullanıcı çekilemedi")
        return
    }
    println("Kullanıcı: {user.username}")
}
```

`main`'e bakan biri, programın **tüm saldırı yüzeyini** birkaç satırda görür.
Koschei tarzının özeti budur: güç tek yerde açılır, geri kalan her şey o gücün
küçük parçalarıyla çalışır.

---

## Kod incelemesinde sorulacak sorular

1. Bu fonksiyon aldığı yetkinin tamamını kullanıyor mu? Kullanmıyorsa daraltın.
2. `main` dışında `allow` çağrısı var mı? Varsa neden?
3. Salt-okunur yeterliyken yazma yetkisi mi verilmiş?
4. Her `or` biçimi doğru niyeti mi anlatıyor? (Sessizce varsayılana düşülen bir
   hata, aslında yukarı fırlatılması gereken bir hata olabilir.)
5. `mut` sayısı gereğinden fazla mı?

---

## Kısaca

| Yapın | Yapmayın |
|---|---|
| Yetkiyi `main`'de daralt | Kök yetkiyi fonksiyonlara pasla |
| En dar jetonu ver | "Nasılsa lazım olur" diye geniş ver |
| `or` ile niyeti belirt | Hatayı görmezden gel (zaten derlenmez) |
| Sabit varsayılan, `mut` istisna | Her şeyi `mut` yap |
| İmzayı belge gibi yaz | Ne yaptığını yorumla anlat |
