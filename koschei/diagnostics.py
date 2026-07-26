"""Koschei tanı kataloğu — hata kodlarının insan diliyle açıklamaları.

Dilin "akıllı" tarafı burada yaşar: derleyici yalnızca reddetmez, ne olduğunu,
neden böyle olduğunu ve nasıl düzeltileceğini anlatır.

Kurallar sabittir; öğrenen/uyarlanan hiçbir şey YOKTUR. Bu katman yalnızca
açıklama üretir, hiçbir denetimi gevşetmez.
"""

from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Diagnostic:
    code: str
    title: str
    summary: str
    why: str
    fix: str
    example: str

    def render(self) -> str:
        return (
            f"{self.code} — {self.title}\n"
            f"\nNE OLDU\n{self.summary}\n"
            f"\nNEDEN\n{self.why}\n"
            f"\nNASIL DÜZELTİLİR\n{self.fix}\n"
            f"\nÖRNEK\n{self.example}\n"
        )


CATALOG: dict[str, Diagnostic] = {
    "KS1101": Diagnostic(
        code="KS1101",
        title="Tanımsız isim",
        summary="Kullanılan değişken, parametre veya fonksiyon bu scope içinde tanımlı değil.",
        why=(
            "Koschei'de her isim kullanılmadan önce tanımlanmalıdır. Bu kural, yazım "
            "hatalarının çalışma anında değil derleme anında yakalanmasını sağlar."
        ),
        fix=(
            "İsmi yazım hatasına karşı kontrol edin; değişkeni kullanmadan önce 'let' "
            "ile tanımlayın veya fonksiyona parametre olarak geçirin. Blok içinde "
            "tanımlanan değişkenler blok dışında görünmez."
        ),
        example="let user_name = \"onur\"\nprintln(\"Merhaba {user_name}\")",
    ),
    "KS1102": Diagnostic(
        code="KS1102",
        title="Aynı scope içinde tekrar tanım",
        summary="Bu isim aynı scope içinde zaten tanımlanmış.",
        why=(
            "Aynı isimde ikinci bir tanım, hangi değerin geçerli olduğunu belirsizleştirir. "
            "Koschei belirsizliği derleme anında reddeder."
        ),
        fix=(
            "İkinci değere farklı bir isim verin; değeri değiştirmek istiyorsanız 'let mut' "
            "ile tanımlayıp atama yapın."
        ),
        example="let mut retry_count = 0\nretry_count = retry_count + 1",
    ),
    "KS1201": Diagnostic(
        code="KS1201",
        title="Immutable değere atama",
        summary="'let' ile tanımlanan bir değer değiştirilmeye çalışıldı.",
        why=(
            "Koschei'de değerler varsayılan olarak değişmezdir. Bu, bir değerin "
            "beklenmedik bir yerde değiştirilmesinden doğan hataları imkânsız kılar; "
            "değişecek her değer kodda açıkça işaretlenir."
        ),
        fix="Değişmesi gereken değeri 'let mut' ile tanımlayın.",
        example="let mut attempts = 0\nattempts = attempts + 1",
    ),
    "KS1301": Diagnostic(
        code="KS1301",
        title="Tip uyuşmazlığı",
        summary="İşleç, verilen tiplere uygulanamaz (örn. String + Int, Bool olmayan bir 'if' koşulu).",
        why=(
            "Tipler derleme anında denetlenir; böylece 'undefined' benzeri çalışma anı "
            "sürprizleri oluşmaz."
        ),
        fix=(
            "Değerleri aynı tipe getirin: sayıyı metne katmak için string interpolasyonu "
            "kullanın, metni sayıya çevirmek için '.to_int()' kullanın ve dönüşüm hatasını "
            "'or' ile ele alın. 'if' ve 'while' koşulları Bool olmalıdır."
        ),
        example="let count = 5\nprintln(\"Toplam: {count}\")\nlet parsed = \"42\".to_int() or 0",
    ),
    "KS1302": Diagnostic(
        code="KS1302",
        title="Int literal 64-bit aralığın dışında",
        summary="Kaynak koddaki tamsayı, Koschei Int tipinin sınırlarını aşıyor.",
        why=(
            "Koschei Int, yorumlayıcı ve native backend arasında aynı sonucu vermek "
            "için işaretli 64-bit olarak tanımlıdır. Daha büyük bir literal Python'da "
            "çalışıp Go'da taşamayacağı için derleme anında reddedilir."
        ),
        fix=(
            "Değeri -9223372036854775808 ile 9223372036854775807 aralığında tutun "
            "veya ileride eklenecek keyfi hassasiyetli sayı tipini kullanın."
        ),
        example="let en_buyuk = 9223372036854775807",
    ),
    "KS1401": Diagnostic(
        code="KS1401",
        title="Ele alınmayan hata değeri",
        summary="Hata dönebilen bir çağrının sonucu ne bir değişkene bağlandı ne de 'or' ile ele alındı.",
        why=(
            "Koschei'de hatalar istisna değil DEĞERDİR. Sessizce yutulan hata, en tehlikeli "
            "hata türüdür: program yanlış durumda çalışmaya devam eder. Bu yüzden hata "
            "dönebilen her çağrının sonucu açıkça karşılanmalıdır."
        ),
        fix=(
            "Üç seçenekten birini kullanın: sonucu 'let' ile bağlayın, 'or return' ile "
            "yukarı fırlatın, 'or varsayılan' ile bir yedek değer verin veya 'or { ... }' "
            "ile blokla ele alın."
        ),
        example=(
            "let content = disk.read(path) or return Error(\"okunamadı\")\n"
            "let port = raw.to_int() or 8080\n"
            "disk.read(path) or { println(\"config yok, varsayılanla devam\") }"
        ),
    ),
    "KS1501": Diagnostic(
        code="KS1501",
        title="Yapısal literal alan/anahtar hatası",
        summary=(
            "Struct oluşturulurken bir alan eksik bırakıldı, tanımsız bir alan verildi "
            "ya da aynı alan birden fazla kez yazıldı. Map literalinde aynı sabit "
            "anahtarın tekrarlanması da bu hatayı üretir."
        ),
        why=(
            "Bir struct'ın tüm alanları oluşturulduğu anda bilinir. Eksik alan, sonradan "
            "'boş' bir değerle karşılaşma riski demektir; Koschei'de null olmadığı için "
            "bu boşluk baştan kapatılır. Map'te yinelenen anahtarın hangisinin geçerli "
            "olacağı belirsiz bırakılmaz."
        ),
        fix=(
            "Struct tanımındaki alanların tamamını, tam olarak birer kez verin. Alan "
            "adlarını tanımla karşılaştırın. Map literalindeki sabit anahtarları "
            "benzersiz tutun."
        ),
        example=(
            "struct UserProfile { id: Int, username: String }\n"
            'let user = UserProfile { id: 1, username: "onur" }\n'
            'let labels = {"role": "admin", "active": true}'
        ),
    ),
    "KS1502": Diagnostic(
        code="KS1502",
        title="Böyle bir alan veya metot yok",
        summary=(
            "Struct'ta bulunmayan bir alana erişildi ya da bir değer üzerinde "
            "desteklenmeyen bir metot çağrıldı."
        ),
        why=(
            "Alan ve metot adları derleme zamanında denetlenir; yazım hatası çalışma "
            "anına taşınmaz."
        ),
        fix=(
            "Alan adını struct tanımıyla karşılaştırın. String için: length, "
            "to_int, to_float, contains, trim, split, join. List için: length, "
            "get, push, contains, sort, filter. Map için: get, set, keys, contains."
        ),
        example=(
            "let items = [1, 2, 3]\n"
            "let count = items.length()\n"
            "let first = items.get(0) or 0\n"
            'let config = {"port": 8080}\n'
            'let port = config.get("port") or 3000'
        ),
    ),
    "KS1601": Diagnostic(
        code="KS1601",
        title="Modül dosyası bulunamadı",
        summary="'import' ile istenen modülün .ks dosyası bulunamadı.",
        why=(
            "Koschei'de modül çözümlemesi dosya sistemine dayanır: konfigürasyon "
            "dosyası, paket bildirimi veya derleme betiği yoktur. 'import risk', "
            "içe aktaran dosyanın yanındaki 'risk.ks' anlamına gelir."
        ),
        fix=(
            "Dosya adının modül adıyla birebir aynı olduğundan ve içe aktaran "
            "dosyayla aynı dizinde bulunduğundan emin olun."
        ),
        example="import risk    // aynı dizindeki risk.ks dosyasını bağlar",
    ),
    "KS1602": Diagnostic(
        code="KS1602",
        title="Döngüsel import",
        summary="Modüller birbirini doğrudan veya dolaylı olarak içe aktarıyor.",
        why=(
            "Halka oluşturan modüllerin hangi sırayla yükleneceği tanımsızdır. "
            "Koschei bu belirsizliği kabul etmek yerine reddeder."
        ),
        fix=(
            "Ortak kodu üçüncü bir modüle taşıyın ve iki modül de onu içe aktarsın."
        ),
        example="// a.ks -> ortak.ks  ve  b.ks -> ortak.ks",
    ),
    "KS1603": Diagnostic(
        code="KS1603",
        title="Aynı modül birden fazla kez içe aktarılmış",
        summary="Bir dosyada aynı 'import' satırı birden çok kez yazılmış.",
        why="Yinelenen import bir yazım hatasının işaretidir; sessizce yok sayılmaz.",
        fix="Fazladan 'import' satırını silin.",
        example="import risk",
    ),
    "KS1604": Diagnostic(
        code="KS1604",
        title="İki modül aynı struct adını tanımlıyor",
        summary=(
            "İçe aktarılan bir modüldeki struct adı, bu dosyadaki ya da başka bir "
            "modüldeki bir struct adıyla çakışıyor."
        ),
        why=(
            "İçe aktarılan struct'lar niteliksiz adlarıyla kullanılır. Aynı adın iki "
            "kaynaktan gelmesi hangi tipin kastedildiğini belirsizleştirir."
        ),
        fix="Struct adlarından birini değiştirin.",
        example="struct HolderRow { address: String }   // çakışmayan bir ad",
    ),
    "KS1605": Diagnostic(
        code="KS1605",
        title="Modülde böyle bir fonksiyon veya struct yok",
        summary="İçe aktarılan modülde bulunmayan bir isme erişilmeye çalışıldı.",
        why=(
            "Modül sınırları derleme zamanında denetlenir; yazım hatası çalışma anına "
            "taşınmaz."
        ),
        fix=(
            "Modüldeki üst düzey fonksiyon ve struct adlarını kontrol edin. v1'de bir "
            "modülün tüm üst düzey tanımları içe aktarılabilir."
        ),
        example="import risk\nlet etiket = risk.label(62)",
    ),
    "KS2401": Diagnostic(
        code="KS2401",
        title="Gerekli yetki bu scope içinde mevcut değil",
        summary="Disk/ağ/ortam işlemi denendi ama bu fonksiyonda ilgili yetki jetonu yok.",
        why=(
            "Koschei'de ortam yetkisi (ambient authority) yoktur: hiçbir kod, kendisine "
            "açıkça verilmemiş bir yeteneği kullanamaz. Kütüphanelerin gizlice dosya "
            "okuyup ağa göndermesi bu sayede derlenemez hale gelir."
        ),
        fix=(
            "İhtiyaç duyulan yetkiyi fonksiyona parametre olarak ekleyin ve çağıran taraftan "
            "daraltılmış bir jeton paslayın."
        ),
        example=(
            "fn load(disk: DiskReadCaps, path: String) -> String or Error {\n"
            "    let content = disk.read(path) or return Error(\"okunamadı\")\n"
            "    return content\n"
            "}"
        ),
    ),
    "KS2402": Diagnostic(
        code="KS2402",
        title="Kök yetki doğrudan kullanılamaz",
        summary="'caps.disk' / 'caps.net' gibi bir kök yetki üzerinde doğrudan G/Ç denendi.",
        why=(
            "Kök yetkiler sınırsızdır ve bilinçli olarak G/Ç yapamaz. Amaç, tam yetkinin "
            "hiçbir zaman dolaşmaması; her kullanımın önce daraltılmasıdır."
        ),
        fix=(
            "Önce 'allow(...)' veya 'allow_read_only(...)' ile kapsamı daraltın, sonra "
            "dönen jetonla işlem yapın."
        ),
        example=(
            "let cfg = caps.disk.allow_read_only(\"/etc/app/\")\n"
            "let content = cfg.read(\"/etc/app/config.json\") or return"
        ),
    ),
    "KS2403": Diagnostic(
        code="KS2403",
        title="Daraltılmış yetki yeniden genişletilemez",
        summary="Daraltılmış bir jeton üzerinde tekrar 'allow' çağrıldı.",
        why=(
            "Daraltma tek yönlüdür. Aksi hâlde kendisine dar bir jeton verilen kod, onu "
            "büyütüp verilmeyen yerlere erişebilirdi — yetki modelinin tamamı çökerdi."
        ),
        fix=(
            "Daha geniş bir kapsam gerçekten gerekiyorsa, jetonu kök yetkiden (main içinde) "
            "yeniden türetip ilgili fonksiyona paslayın."
        ),
        example=(
            "// main içinde iki ayrı kapsam türetilir\n"
            "let cfg = caps.disk.allow_read_only(\"/etc/app/\")\n"
            "let cache = caps.disk.allow(\"/var/cache/app/\")"
        ),
    ),
    "KS2404": Diagnostic(
        code="KS2404",
        title="Yetki türü bu işleme izin vermez",
        summary="Örneğin salt-okunur bir disk jetonuyla yazma denendi.",
        why=(
            "Her yetki türü yalnızca kendi işlem kümesini taşır. Salt-okunur bir jeton, "
            "yazma yeteneğini hiçbir koşulda kazanamaz."
        ),
        fix=(
            "Yazma gerçekten gerekiyorsa kök yetkiden 'allow(...)' ile yazılabilir bir jeton "
            "türetin; gerekmiyorsa salt-okunur kalması güvenlik açısından tercih edilir."
        ),
        example="let cache = caps.disk.allow(\"/var/cache/app/\")\nlet written = cache.write(\"/var/cache/app/x\", \"veri\") or return",
    ),
    "KS2405": Diagnostic(
        code="KS2405",
        title="Ağ origin şeması reddedildi",
        summary=(
            "NetRoot.allow için HTTP/HTTPS dışında bir origin verildi veya "
            "mutlak bir ağ origin'i oluşturulamadı."
        ),
        why=(
            "urllib gibi genel amaçlı istemciler file:, ftp: veya data: şemalarını "
            "açabilir. Ağ yetkisi bu şemaları kabul ederse disk ve veri erişimine "
            "dönüşerek capability sınırını aşar."
        ),
        fix=(
            "Origin'i mutlak bir http:// veya https:// adresi yapın. Yerel dosya "
            "erişimi gerekiyorsa ayrı DiskCaps/DiskReadCaps jetonu kullanın."
        ),
        example=(
            'let net = caps.net.allow("https://api.example.com")\n'
            'let response = net.get("https://api.example.com/data") or return'
        ),
    ),
    "KS3101": Diagnostic(
        code="KS3101",
        title="Çalışma anı: tanımsız isim veya geçersiz çağrı",
        summary="Yorumlayıcı, bilinmeyen bir isim ya da uyumsuz bir çağrı ile karşılaştı.",
        why=(
            "Bu bir savunma katmanıdır: normalde derleme denetimleri bu durumu daha önce "
            "yakalar. Çalışma anında görülmesi, derleyicide kapatılması gereken bir boşluğa "
            "işaret eder."
        ),
        fix="Çağrının argüman sayısını ve isimleri kontrol edin; sorun sürerse hata olarak bildirin.",
        example="println(\"tek argüman\")",
    ),
    "KS3105": Diagnostic(
        code="KS3105",
        title="Çağrı derinliği sınırı aşıldı",
        summary="Fonksiyon çağrıları 512 seviyeyi aştı; büyük olasılıkla sonsuz özyineleme var.",
        why=(
            "Sınırsız özyineleme programı çökertir. Koschei bunun yerine temiz bir hata "
            "üretir: dilin çökmemesi bir tasarım hedefidir."
        ),
        fix=(
            "Özyinelemenin bir durma koşulu olduğundan emin olun ya da döngü ('while') "
            "kullanın."
        ),
        example=(
            "fn countdown(n: Int) -> Int {\n"
            "    if n <= 0 { return 0 }\n"
            "    return countdown(n - 1)\n"
            "}"
        ),
    ),
    "KS3201": Diagnostic(
        code="KS3201",
        title="Çalışma anı: immutable değere atama",
        summary="Değişmez bir değer çalışma anında değiştirilmeye çalışıldı.",
        why="KS1201'in çalışma anı savunma katmanıdır; derleme denetimi atlansa bile atama reddedilir.",
        fix="Değeri 'let mut' ile tanımlayın.",
        example="let mut total = 0\ntotal = total + 1",
    ),
    "KS3401": Diagnostic(
        code="KS3401",
        title="Çalışma anı: capability tip bütünlüğü ihlali",
        summary=(
            "Runtime, bir capability veya capability taşıyan değerin başka bir tip "
            "gibi geçirildiğini ya da döndürüldüğünü tespit etti."
        ),
        why=(
            "Semantic denetim normalde bu kodu derlemeden reddeder. Runtime aynı "
            "sözleşmeyi savunma derinliği için yeniden kontrol eder; bu hata, tip "
            "denetiminin atlatıldığı veya bozuk bir AST çalıştırıldığı anlamına gelir."
        ),
        fix=(
            "SystemCaps'i yalnızca main parametresi olarak kullanın. Kök yetkiyi main "
            "içinde allow/allow_read_only ile daraltın ve fonksiyonlara gerçek NetCaps, "
            "DiskCaps gibi jetonları, bildirilen tiple birebir uyumlu olarak geçirin."
        ),
        example=(
            "fn fetch(net: NetCaps) {\n"
            "    let response = net.get(\"https://api.example.com\") or return\n"
            "}"
        ),
    ),
    "KS3501": Diagnostic(
        code="KS3501",
        title="Int taşması",
        summary="Bir tamsayı işlemi işaretli 64-bit Int aralığının dışına çıktı.",
        why=(
            "Sessiz sarma aynı programın yorumlayıcıda ve native binary'de farklı "
            "sonuç vermesine yol açardı. Koschei taşmayı hata DEĞERİNE çevirerek "
            "iki backend'i eşit ve fail-closed tutar."
        ),
        fix=(
            "İşlemden önce sınırı kontrol edin, daha küçük değerler kullanın veya "
            "sonucu 'or' ile açıkça ele alın."
        ),
        example=(
            "let sonuc = 9223372036854775807 + 1 or "
            "Error(\"Int sınırı aşıldı\")"
        ),
    ),
    "KS3402": Diagnostic(
        code="KS3402",
        title="Kapsam dışı erişim",
        summary=(
            "Jetonun izin verdiği sınırın dışına çıkıldı: izinsiz bir dosya yolu, izinsiz bir "
            "ağ origin'i veya kapsam dışına çıkan bir ağ yönlendirmesi."
        ),
        why=(
            "Jeton yalnızca kendisine verilen kapsamı taşır. Yol denetimi gerçek yol "
            "çözümlemesiyle yapılır: '../' ve symlink hileleri sınırı aşamaz. Ağ tarafında "
            "yönlendirmeler de denetlenir; izinli sunucu başka bir host'a yönlendirse bile "
            "istek takip edilmez."
        ),
        fix=(
            "Erişilecek yolu/origin'i jetonun kapsamına alın (main içinde uygun bir "
            "daraltma yapın) ya da erişimi gerçekten gerekmiyorsa kaldırın. Dönen hata bir "
            "DEĞERDİR; 'or' ile ele alınabilir."
        ),
        example=(
            "let api = caps.net.allow(\"https://api.example.com\")\n"
            "let response = api.get(\"https://api.example.com/v1\") or return Error(\"istek başarısız\")"
        ),
    ),
    "KS3403": Diagnostic(
        code="KS3403",
        title="Çalışma anı: yetki genişletme girişimi",
        summary="Daraltılmış bir jeton çalışma anında genişletilmeye çalışıldı.",
        why="KS2403'ün çalışma anı savunma katmanıdır; derleme denetimi atlansa bile reddedilir.",
        fix="Gerekli kapsamı kök yetkiden yeniden türetin.",
        example="let wide = caps.disk.allow(\"/var/data/\")",
    ),
    "KS3405": Diagnostic(
        code="KS3405",
        title="Kapsam içinde sembolik bağ takip edilmez",
        summary="Disk yetkisi, kapsam içindeki bir yol bileşeni sembolik bağ olduğunda erişimi reddeder.",
        why=(
            "Kapsam sınırı yol METNİYLE değil dosya tanıtıcısıyla korunur. Bir yol "
            "doğrulanıp ardından ayrı bir çağrıda açılsaydı, sandbox'a yazabilen bir "
            "saldırgan aradaki pencerede dosyayı sembolik bağa çevirip açmayı kapsam "
            "dışına yönlendirebilirdi (TOCTOU). Bu yüzden her bileşen O_NOFOLLOW ile "
            "açılır ve hiçbir bağ takip edilmez — bağ kapsam içini gösterse bile."
        ),
        fix=(
            "Gerçek dosya yolunu kullanın. Başka bir dizine erişmeniz gerekiyorsa bu "
            "ayrı bir kapsamdır: kök yetkiden o dizin için ayrı bir jeton türetin, "
            "böylece manifestoda da görünür."
        ),
        example="let veri = caps.disk.allow_read_only(\"/var/data/\")\nlet gunluk = caps.disk.allow(\"/var/log/app/\")",
    ),
    "KS3406": Diagnostic(
        code="KS3406",
        title="Disk yetkisi bu platformda desteklenmiyor",
        summary="Disk işlemleri openat (dir_fd) ve O_NOFOLLOW gerektirir.",
        why=(
            "Kapsam sınırı yalnızca dosya tanıtıcısına bağlı geçişle yarışsız biçimde "
            "korunabilir. Bu çağrıların bulunmadığı bir platformda eski, yarışa açık "
            "uygulamaya geri düşmek jetonun anlamını platforma göre zayıflatırdı; "
            "bunun yerine işlem açıkça reddedilir."
        ),
        fix=(
            "Programı openat destekleyen bir platformda çalıştırın (Linux, macOS, "
            "BSD). Disk yetkisi gerektirmeyen bölümler etkilenmez."
        ),
        example="// Linux/macOS üzerinde:\nlet veri = caps.disk.allow_read_only(\"/var/data/\")",
    ),
    "KS4001": Diagnostic(
        code="KS4001",
        title="Yetki içeren program bu aşamada native derlenemez",
        summary=(
            "Program bir yetki (capability) parametresi alıyor ya da bir yetki işlemi "
            "çağırıyor; native derleme aşama 1 yalnızca yetki içermeyen programları "
            "destekler."
        ),
        why=(
            "Yetki denetimi üretilen binary'ye taşınmadan yetkili program derlemek, dili "
            "kâğıt üstünde güvenli ama gerçekte açık bırakırdı. Bu yüzden native yetki "
            "runtime'ı tamamlanana kadar (aşama 2) bu programlar bilinçli olarak "
            "reddedilir."
        ),
        fix=(
            "Programı şimdilik 'koschei.py run' ile çalıştırın; yetki denetimleri orada "
            "tam olarak uygulanır. Üretilen Go ara kaynağını görmek için "
            "'koschei.py emit-go' kullanabilirsiniz."
        ),
        example="python koschei.py run examples/showcase.ks",
    ),
    "KS4002": Diagnostic(
        code="KS4002",
        title="Native derlemede desteklenmeyen yapı",
        summary="Kullanılan dil yapısı henüz Go üreticisi tarafından desteklenmiyor.",
        why=(
            "Native derleyici dilin tamamını aşamalı olarak kapsar. Desteklenmeyen bir "
            "yapıyı yanlış çevirmektense açıkça reddetmek tercih edilir: sessiz yanlış "
            "çeviri, hata ayıklanamayan bir binary üretirdi."
        ),
        fix=(
            "Programı 'koschei.py run' ile çalıştırın ya da yapıyı desteklenen bir "
            "biçimde yeniden yazın."
        ),
        example="python koschei.py run program.ks",
    ),
    "KS4003": Diagnostic(
        code="KS4003",
        title="Çağrıda argüman sayısı uyuşmuyor",
        summary="Fonksiyon, tanımındakinden farklı sayıda argümanla çağrıldı.",
        why=(
            "Argüman sayısı bir sözleşmedir; uyuşmazlık derleme anında yakalanır, çalışma "
            "anına bırakılmaz."
        ),
        fix="Çağrıyı fonksiyon imzasındaki parametre sayısına göre düzeltin.",
        example=(
            "fn add(a: Int, b: Int) -> Int { return a + b }\n"
            "let total = add(2, 3)"
        ),
    ),
    "KS3404": Diagnostic(
        code="KS3404",
        title="Çalışma anı: izin verilmeyen işlem",
        summary="Jeton türünün taşımadığı bir işlem denendi (ör. salt-okunur jetonla yazma).",
        why="Yetki türleri çalışma anında da korunur; salt-okunur jeton hiçbir koşulda yazamaz.",
        fix="Yazılabilir bir jeton türetin ya da işlemi kaldırın.",
        example="let cache = caps.disk.allow(\"/var/cache/app/\")",
    ),
}

CODE_PATTERN = re.compile(r"KS\d{4}")


def lookup(code: str) -> Diagnostic | None:
    """Verilen kodu (veya kod içeren bir hata metnini) kataloğa göre çözer."""
    match = CODE_PATTERN.search(code.upper())
    if match is None:
        return None
    return CATALOG.get(match.group(0))


def known_codes() -> list[str]:
    return sorted(CATALOG)
