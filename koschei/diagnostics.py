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

    def render(self, locale: str = "tr") -> str:
        locale = normalize_locale(locale)
        if locale == "en":
            sections = ("WHAT HAPPENED", "WHY", "HOW TO FIX", "EXAMPLE")
        else:
            sections = ("NE OLDU", "NEDEN", "NASIL DÜZELTİLİR", "ÖRNEK")
        happened, why, fix, example = sections
        return (
            f"{self.code} — {self.title}\n"
            f"\n{happened}\n{self.summary}\n"
            f"\n{why}\n{self.why}\n"
            f"\n{fix}\n{self.fix}\n"
            f"\n{example}\n{self.example}\n"
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
    "KS1701": Diagnostic(
        code="KS1701",
        title="Enum veya varyant sözleşmesi hatası",
        summary="Enum tanımı ya da varyant constructor çağrısı bildirilen sözleşmeyle uyuşmuyor.",
        why=(
            "Varyant adları program genelinde benzersizdir ve payload taşıyan bir "
            "varyant tam olarak bir değer alır. Bu sözleşme gevşerse match kolları "
            "hangi veriyle çalıştığını güvenli biçimde bilemez."
        ),
        fix="Enum varyant adlarını benzersiz tutun ve constructor'a bildirilen payload tipini verin.",
        example=(
            "enum State { Idle, Ready(String) }\n"
            "let state = Ready(\"hazır\")"
        ),
    ),
    "KS1702": Diagnostic(
        code="KS1702",
        title="match sözleşmesi tamamlanmadı",
        summary="match ifadesi bir varyantı atladı, aynı kolu tekrarladı veya uyumsuz sonuç tipleri üretti.",
        why=(
            "Koschei match ifadeleri exhaustive olmak zorundadır. Enum'a yeni bir "
            "varyant eklendiğinde işlenmeyen durum sessizce runtime'a taşınmaz; "
            "derleme anında görünür olur."
        ),
        fix="Enumun tüm varyantlarını tam birer kez ele alın ve kolları uyumlu tipte değer döndürecek şekilde düzenleyin.",
        example=(
            "match state {\n"
            "    Idle => \"bekliyor\",\n"
            "    Ready(message) => message,\n"
            "}"
        ),
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
        title="Native hedef capability sözleşmesini güvenle uygulayamıyor",
        summary=(
            "Programın istediği capability, seçilen native hedefte aynı güvenlik "
            "anlamıyla uygulanamıyor. Derleyici daha zayıf bir uygulamaya sessizce "
            "düşmek yerine üretimi durdurur."
        ),
        why=(
            "Bir jetonun kapsamı interpreter ve native binary arasında değişirse "
            "capability modeli yalnızca kâğıt üzerinde kalır. Örneğin disk sınırı "
            "yarışsız dosya-tanıtıcısı geçişi gerektirir; bunu sağlayamayan hedefte "
            "yol metni kontrolüne geri dönmek TOCTOU açığını yeniden doğururdu."
        ),
        fix=(
            "Programı capability'nin güvenli ABI'sini destekleyen hedefte derleyin "
            "(disk ABI alpha için Linux) veya 'ks run' ile interpreter runtime'ını "
            "kullanın. Desteklenmeyen capability daha sonra ayrı bir ABI diliminde "
            "eklenecektir."
        ),
        example="ks build examples/runtime_demo.ks -o runtime-demo",
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

ENGLISH_TEXT: dict[str, tuple[str, str, str, str]] = {
    "KS1101": (
        "Undefined name",
        "The variable, parameter, or function is not defined in this scope.",
        "Every name must be declared before use so spelling and scope mistakes fail during compilation.",
        "Check the spelling, declare the value with 'let', pass it as a parameter, or move the use into the declaring scope.",
    ),
    "KS1102": (
        "Duplicate definition",
        "The name is already defined in the same scope.",
        "Two definitions with the same name make ownership of the value ambiguous.",
        "Rename the second definition, or declare the original value with 'let mut' and assign to it.",
    ),
    "KS1201": (
        "Assignment to an immutable value",
        "A value declared with 'let' was assigned a new value.",
        "Koschei values are immutable by default so state changes stay explicit and reviewable.",
        "Declare the value with 'let mut' only when mutation is required.",
    ),
    "KS1301": (
        "Type mismatch",
        "The operation cannot be applied to the supplied types.",
        "Compile-time type checks prevent invalid operations and non-Bool conditions from reaching runtime.",
        "Convert values explicitly, use interpolation for text, and handle fallible conversions with 'or'.",
    ),
    "KS1302": (
        "Int literal outside the signed 64-bit range",
        "The integer literal exceeds the bounds of Koschei Int.",
        "Int is signed 64-bit on both the interpreter and native backend to preserve target parity.",
        "Use a value between -9223372036854775808 and 9223372036854775807.",
    ),
    "KS1401": (
        "Unhandled error value",
        "A fallible result was neither bound nor handled with 'or'.",
        "Errors are values in Koschei; silently discarding one would let the program continue in an invalid state.",
        "Bind the result, use 'or return', provide a fallback with 'or value', or handle it in an 'or { ... }' block.",
    ),
    "KS1501": (
        "Invalid structural literal",
        "A struct field is missing, unknown, or repeated, or a Map contains a duplicate constant key.",
        "Structural values must be complete and unambiguous at construction time.",
        "Provide every declared struct field exactly once and keep Map keys unique.",
    ),
    "KS1502": (
        "Unknown field or method",
        "The field does not exist on the struct or the method is unsupported for the receiver value.",
        "Field and method names are checked before execution so spelling mistakes do not become runtime failures.",
        "Check the struct declaration or use a method supported by the receiver type.",
    ),
    "KS1601": (
        "Module file not found",
        "The .ks file requested by an import could not be found.",
        "Module resolution is deterministic and relative to the importing source file.",
        "Make the file name match the module name and place it in the expected directory.",
    ),
    "KS1602": (
        "Import cycle",
        "Modules import each other directly or indirectly.",
        "A cycle has no deterministic initialization order.",
        "Move shared declarations into a third module imported by both sides.",
    ),
    "KS1603": (
        "Duplicate import",
        "The same module is imported more than once in one source file.",
        "A repeated import is usually a source error and is not silently ignored.",
        "Remove the duplicate import statement.",
    ),
    "KS1604": (
        "Conflicting struct name",
        "Two reachable modules define the same unqualified struct name.",
        "Unqualified imported type names must resolve to exactly one declaration.",
        "Rename one of the structs so every imported type name is unique.",
    ),
    "KS1605": (
        "Missing module member",
        "The imported module does not export the requested function, struct, or enum.",
        "Module boundaries are validated during compilation.",
        "Check the member name and the declarations exposed by the imported module.",
    ),
    "KS1701": (
        "Invalid enum or variant contract",
        "The enum declaration or variant constructor call does not match its declared payload contract.",
        "Variant names, payload arity, and payload types are part of the enum's type contract.",
        "Use a declared variant and pass exactly the payload type it declares.",
    ),
    "KS1702": (
        "Incomplete match contract",
        "A match omits a variant, repeats a branch, or produces incompatible result types.",
        "Exhaustive matching guarantees that adding or receiving a variant cannot fall through silently.",
        "Handle every variant exactly once and make all branches produce compatible values.",
    ),
    "KS2401": (
        "Required capability is unavailable in this scope",
        "A disk, network, environment, or process operation was attempted without the corresponding capability token.",
        "Authority must be passed explicitly so imports and callees cannot acquire ambient access.",
        "Accept the required narrowed capability as a parameter and pass it from an authorized caller.",
    ),
    "KS2402": (
        "Root capability cannot perform I/O directly",
        "A root authority such as caps.disk or caps.net was used for an operation without narrowing it first.",
        "Root capabilities exist only to derive auditable, least-authority tokens.",
        "Call allow or allow_read_only with a concrete path, origin, or variable before performing the operation.",
    ),
    "KS2403": (
        "A narrowed capability cannot be widened",
        "allow was called on an already narrowed capability token.",
        "Allowing re-widening would let a callee escape the scope granted by its caller.",
        "Derive the required scope from the root capability instead of widening a child token.",
    ),
    "KS2404": (
        "Capability type does not permit this operation",
        "The token lacks the requested authority, such as writing through a read-only disk token.",
        "Capability types encode the operations the holder is permitted to perform.",
        "Use a token with the required authority or remove the operation.",
    ),
    "KS2405": (
        "Network origin scheme rejected",
        "NetRoot.allow received a non-HTTP(S) or invalid absolute origin.",
        "Network authority must not become a bridge to local files or unsupported protocols.",
        "Use an absolute http:// or https:// origin with a valid host.",
    ),
    "KS3101": (
        "Runtime undefined name or invalid call",
        "The interpreter encountered an unknown name, invalid constructor, duplicate Map key, or incompatible call.",
        "The runtime keeps a defensive validation layer even when semantic checks have already run.",
        "Correct the referenced name or call contract and run 'ks check' again.",
    ),
    "KS3105": (
        "Call-depth limit exceeded",
        "Function calls exceeded the 512-frame safety limit.",
        "The limit prevents uncontrolled recursion from exhausting the host stack.",
        "Add a terminating condition or rewrite the recursion as iteration.",
    ),
    "KS3201": (
        "Runtime assignment to an immutable value",
        "The runtime detected an assignment to a value that was not declared mutable.",
        "Runtime immutability is a defense-in-depth mirror of the compiler rule.",
        "Declare the value with 'let mut' or remove the assignment.",
    ),
    "KS3401": (
        "Runtime capability type-integrity violation",
        "A capability or capability-carrying value was disguised, stored, or returned as an ordinary value.",
        "Capability laundering would bypass explicit authority flow and containment rules.",
        "Keep capability values in capability-typed variables and never place them in structs, enums, Lists, or Maps.",
    ),
    "KS3402": (
        "Out-of-scope access",
        "A file path, network origin, or redirect crossed the boundary granted by the capability token.",
        "The runtime enforces the exact authority scope rather than trusting path or URL text alone.",
        "Request a separate token from the root for the required path or origin.",
    ),
    "KS3403": (
        "Runtime capability widening attempt",
        "A narrowed token was widened at runtime.",
        "This defense-in-depth check prevents scope escalation even if compile-time validation is bypassed.",
        "Derive the wider scope directly from the root capability.",
    ),
    "KS3404": (
        "Runtime operation not permitted",
        "The token type does not carry the requested operation.",
        "Runtime checks preserve read-only and operation-specific authority boundaries.",
        "Use a token that explicitly grants the operation or remove the operation.",
    ),
    "KS3405": (
        "Symbolic links are not followed inside a disk scope",
        "A path component inside the granted disk scope is a symbolic link.",
        "Each component is opened with O_NOFOLLOW to prevent TOCTOU and symlink-swap escapes.",
        "Use the real path or derive a separate capability for the target directory.",
    ),
    "KS3406": (
        "Disk capability unsupported on this platform",
        "Secure disk operations require openat/dir_fd and O_NOFOLLOW primitives.",
        "Koschei refuses to fall back to weaker path-text validation on unsupported platforms.",
        "Run on a supported platform or use interpreter features that do not require disk authority.",
    ),
    "KS3501": (
        "Int overflow",
        "An integer operation exceeded the signed 64-bit Int range.",
        "Overflow behavior is checked so interpreter and native targets cannot diverge.",
        "Keep the calculation within Int bounds or redesign it around smaller values.",
    ),
    "KS4001": (
        "Native target cannot safely implement the capability contract",
        "The requested capability cannot be preserved with equivalent security on the selected native target.",
        "A weaker native implementation would make the same token mean different authority on different targets.",
        "Build on a supported target or run the program with the interpreter runtime.",
    ),
    "KS4002": (
        "Unsupported native construct",
        "The Go backend does not yet support this language construct.",
        "Failing closed is safer than emitting a binary with silently different behavior.",
        "Run with 'ks run' or rewrite the construct using the currently supported native subset.",
    ),
    "KS4003": (
        "Call argument count mismatch",
        "The function was called with a different number of arguments than its declaration accepts.",
        "Arity is part of the function contract and is checked before execution.",
        "Pass exactly one argument for each declared parameter.",
    ),
}


def normalize_locale(locale: str | None) -> str:
    value = (locale or "en").strip().lower().replace("_", "-")
    if value.startswith("tr"):
        return "tr"
    if value.startswith("en"):
        return "en"
    raise ValueError(f"Unsupported diagnostic language: {locale!r}. Use 'en' or 'tr'.")


ENGLISH_CATALOG: dict[str, Diagnostic] = {
    code: Diagnostic(
        code=code,
        title=fields[0],
        summary=fields[1],
        why=fields[2],
        fix=fields[3],
        example=CATALOG[code].example,
    )
    for code, fields in ENGLISH_TEXT.items()
}

if set(ENGLISH_CATALOG) != set(CATALOG):
    missing = sorted(set(CATALOG) - set(ENGLISH_CATALOG))
    extra = sorted(set(ENGLISH_CATALOG) - set(CATALOG))
    raise RuntimeError(f"Diagnostic catalog mismatch: missing={missing}, extra={extra}")

CATALOGS: dict[str, dict[str, Diagnostic]] = {
    "tr": CATALOG,
    "en": ENGLISH_CATALOG,
}

CODE_PATTERN = re.compile(r"KS\d{4}")
LOCATION_PATTERN = re.compile(
    r"KS\d{4}(?: \[(?:satır|line) (\d+), (?:sütun|column) (\d+)\])?",
    re.IGNORECASE,
)


def catalog(locale: str = "en") -> dict[str, Diagnostic]:
    return CATALOGS[normalize_locale(locale)]


def lookup(code: str, locale: str = "tr") -> Diagnostic | None:
    """Resolve a bare code or an error string in the selected language catalog."""
    match = CODE_PATTERN.search(code.upper())
    if match is None:
        return None
    return catalog(locale).get(match.group(0))


def diagnostic_payload(
    message: str,
    *,
    locale: str = "en",
    source: str | None = None,
    error: BaseException | None = None,
) -> dict[str, object]:
    selected = normalize_locale(locale)
    diagnostic = lookup(message, selected)
    code_match = CODE_PATTERN.search(message.upper())
    code = code_match.group(0) if code_match else None
    line: int | None = None
    column: int | None = None
    location = getattr(error, "location", None)
    if location is not None:
        line = getattr(location, "line", None)
        column = getattr(location, "column", None)
    else:
        match = LOCATION_PATTERN.search(message)
        if match is not None:
            line = int(match.group(1)) if match.group(1) else None
            column = int(match.group(2)) if match.group(2) else None

    if diagnostic is None:
        title = "Compiler error" if selected == "en" else "Derleyici hatası"
        summary = message
    else:
        title = diagnostic.title
        summary = diagnostic.summary

    return {
        "ok": False,
        "code": code,
        "title": title,
        "message": summary,
        "source": source,
        "line": line,
        "column": column,
    }


def render_error(
    message: str,
    *,
    locale: str = "en",
    error: BaseException | None = None,
) -> str:
    payload = diagnostic_payload(message, locale=locale, error=error)
    code = payload["code"]
    title = payload["title"]
    summary = payload["message"]
    line = payload["line"]
    column = payload["column"]
    location = ""
    if line is not None and column is not None:
        if normalize_locale(locale) == "en":
            location = f" [line {line}, column {column}]"
        else:
            location = f" [satır {line}, sütun {column}]"
    prefix = f"{code}{location}: " if code else ""
    return f"{prefix}{title} — {summary}"


def known_codes(locale: str | None = None) -> list[str]:
    if locale is not None:
        normalize_locale(locale)
    return sorted(CATALOG)
