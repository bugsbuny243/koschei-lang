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
            "Runtime, bir değerin fonksiyonun bildirdiği parametre veya dönüş tipine "
            "uymadığını ya da bir capability veya capability taşıyan değerin başka "
            "bir tip gibi geçirildiğini tespit etti."
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
            "fn fetch(net: NetCaps) -> String or Error {\n"
            "    let response = net.get(\"https://api.example.com\") or return\n"
            "    return response.text()\n"
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
    "KS3502": Diagnostic(
        code="KS3502",
        title="Bellek bütçesi aşıldı",
        summary=(
            "Bir işlem bütçeden büyük bir String veya List üretecekti ya da host "
            "belleği programın değerlerine yetmedi."
        ),
        why=(
            "Sınırsız büyüyen değerler hizmeti durdurur ve yarım kalmış durum "
            "bırakabilir. Bir String en fazla 16777216 bayt UTF-8, bir List en "
            "fazla 1048576 öğe olabilir; aşan işlem her çalıştırıcıda aynı "
            "noktada KS3502 hata DEĞERİ üretir."
        ),
        fix=(
            "Değeri parçalara bölün, girdinin boyutunu işlemeden önce sınırlayın "
            "veya sonucu 'or' ile açıkça ele alın."
        ),
        example='let birlesik = parca + parca or Error("metin çok büyük")',
    ),
    "KS2407": Diagnostic(
        code="KS2407",
        title="Yetki değerleri karşılaştırılamaz",
        summary="İki yetki jetonu (veya onları taşıyan struct'lar) == ya da != ile karşılaştırıldı.",
        why=(
            "Bu karşılaştırma host'a iki jetonun aynı nesne olup olmadığını sorardı. "
            "Yetkinin kimliği Koschei'de tanımlı bir değer değildir ve çalıştırıcılar "
            "bu soruya farklı cevap verirdi."
        ),
        fix="Jetonları değil, onlarla okuduğunuz değerleri karşılaştırın.",
        example="let same = first.read_text() or \"\"",
    ),
    "KS2430": Diagnostic(
        code="KS2430",
        title="Program girdisi bütçesi statik değil",
        summary="caps.input.allow() tek bir statik Int literal bayt bütçesi bekler.",
        why=(
            "Programın en fazla ne kadar standart girdi okuyabileceği kaynakta "
            "görünmelidir; 'ks caps' bu sınırı derleme zamanında gösterir."
        ),
        fix="Bütçeyi bir sayı olarak yazın.",
        example="let input = caps.input.allow(65536)",
    ),
    "KS2431": Diagnostic(
        code="KS2431",
        title="Program girdisi bütçesi aralık dışında",
        summary="Standart girdi bütçesi 1 ile 16777216 bayt arasında olmalıdır.",
        why=(
            "Okunan metin bir String olur; String en fazla 16777216 bayt UTF-8 "
            "olabilir. Sıfır veya negatif bütçe hiçbir anlam taşımaz."
        ),
        fix="1 ile 16777216 arasında bir bütçe seçin.",
        example="let input = caps.input.allow(1048576)",
    ),
    "KS2440": Diagnostic(
        code="KS2440",
        title="Saat çözünürlüğü statik değil",
        summary="caps.clock.allow() tek bir statik Int literal milisaniye çözünürlüğü bekler.",
        why="Programın zamanı ne kadar ince görebileceği kaynakta ve 'ks caps' çıktısında görünmelidir.",
        fix="Çözünürlüğü bir sayı olarak yazın.",
        example="let clock = caps.clock.allow(1000)",
    ),
    "KS2441": Diagnostic(
        code="KS2441",
        title="Saat çözünürlüğü aralık dışında",
        summary="Saat çözünürlüğü 1 ile 86400000 ms (bir gün) arasında olmalıdır.",
        why="Kaba bir saat daha zayıf bir yetkidir; sıfır veya negatif çözünürlük anlam taşımaz.",
        fix="1 ile 86400000 arasında bir çözünürlük seçin.",
        example="let clock = caps.clock.allow(1)",
    ),
    "KS2450": Diagnostic(
        code="KS2450",
        title="Rastgele sayı bütçesi statik değil",
        summary="caps.random.allow() tek bir statik Int literal bayt bütçesi bekler.",
        why="Bir yetkinin en fazla ne kadar rastgelelik üretebileceği kaynakta görünmelidir.",
        fix="Bütçeyi bir sayı olarak yazın.",
        example="let random = caps.random.allow(64)",
    ),
    "KS2451": Diagnostic(
        code="KS2451",
        title="Rastgele sayı bütçesi aralık dışında",
        summary="Rastgele sayı bütçesi 1 ile 1048576 bayt arasında olmalıdır.",
        why="Bütçe bir yetkinin toplam üretebileceği rastgeleliği sınırlar.",
        fix="1 ile 1048576 arasında bir bütçe seçin.",
        example="let random = caps.random.allow(1024)",
    ),
    "KS3450": Diagnostic(
        code="KS3450",
        title="Rastgele sayı bütçesi tükendi",
        summary="Yetki, caps.random.allow() ile verilen bayt bütçesini tüketti.",
        why=(
            "Bir kütüphaneye verilen rastgele sayı yetkisi sınırsız değildir. Bütçeyi aşan "
            "çağrı hiçbir şey üretmez ve bütçeden düşmez; bir hata değeri döner."
        ),
        fix="Bütçeyi büyütün veya daha az rastgelelik isteyin.",
        example="let token = random.hex(16) or return",
    ),
    "KS3451": Diagnostic(
        code="KS3451",
        title="Rastgele sayı isteği geçersiz",
        summary="random.hex() 1..1024 bayt, random.below() en az 1 olan bir üst sınır bekler.",
        why="Geçersiz istek bir hata değeridir; rastgelelik üretilmez ve bütçeden düşülmez.",
        fix="Argümanı izin verilen aralıkta verin.",
        example="let die = random.below(6) or return",
    ),
    "KS3460": Diagnostic(
        code="KS3460",
        title="Bytes aralığı geçersiz",
        summary="Bytes.get() veya Bytes.slice() değerin uzunluğu dışında bir konum istedi.",
        why="Aralık dışı erişim sessizce kırpılmaz veya başka bir bayt döndürmez; bir hata değeridir.",
        fix="Konumu 0 ile length() arasında tutun veya hatayı 'or' ile ele alın.",
        example="let first = data.get(0) or -1",
    ),
    "KS3461": Diagnostic(
        code="KS3461",
        title="Hex metni geçersiz",
        summary="bytes_from_hex() çift uzunlukta ve yalnızca 0-9, a-f, A-F içeren bir metin bekler.",
        why="Boşluk, ayraç veya tek kalan hane sessizce atlanmaz; anlamı belirsiz girdi hata değeridir.",
        fix="Hex metnini ayraçsız ve çift uzunlukta verin.",
        example='let key = bytes_from_hex("00ff") or return',
    ),
    "KS3470": Diagnostic(
        code="KS3470",
        title='Yanıtlanmamış istek',
        summary='accept() önceki istek yanıtlanmadan çağrıldı veya reply() bekleyen istek yokken çağrıldı.',
        why='Knowhere yasası: hiçbir şey istekten isteğe taşınmaz. Yanıtlanmamış istek 500 ile kapatılır; yanıt asla başka bir istemciye gitmez.',
        fix='Her accept() için tam bir reply() çağırın.',
        example='server.reply(200, "ok") or return',
    ),
    "KS3471": Diagnostic(
        code="KS3471",
        title='Sunucu istek bütçesi tükendi',
        summary='Yetki, caps.serve.allow() ile verilen max_connections kadar isteği kabul etti.',
        why='Bir sunucu yetkisinin ömrü boyunca kabul edebileceği istek sayısı sınırlıdır.',
        fix='Bütçeyi büyütün veya yeni bir yetkiyle devam edin.',
        example='let server = caps.serve.allow("127.0.0.1:8080", 1000, 65536, 65536, 5000)',
    ),
    "KS3472": Diagnostic(
        code="KS3472",
        title='Yanıt kuralı ihlali',
        summary='reply() desteklenmeyen bir durum koduyla veya gövdeli 204 ile çağrıldı.',
        why='Desteklenen durum kodları sınırlı ve açıktır; geçersiz yanıt yerine istemci 500 alır.',
        fix='200, 201, 204, 400, 403, 404, 405, 409, 413, 422, 429, 500 veya 503 kullanın.',
        example='server.reply(404, "not found") or return',
    ),
    "KS3473": Diagnostic(
        code="KS3473",
        title='İstek başlığı yok',
        summary='request.header(name) istekte bulunmayan bir başlık istedi.',
        why='Eksik başlık sessiz bir boş metin değil, açık bir hata değeridir.',
        fix="Hatayı 'or' ile varsayılan değere çevirin.",
        example='let name = request.header("X-Name") or "stranger"',
    ),
    "KS3430": Diagnostic(
        code="KS3430",
        title="Program girdisi metin değil",
        summary="Bir program argümanı veya standart girdi geçerli UTF-8 metin değil.",
        why=(
            "String metin taşır. UTF-8 olmayan baytları sessizce değiştirmek, "
            "programın gördüğü değeri gönderilenden farklı kılar; Koschei bunun "
            "yerine 'or' ile yakalanabilen bir hata değeri verir."
        ),
        fix="Girdiyi UTF-8 olarak gönderin veya hatayı 'or' ile ele alın.",
        example='let text = input.read_text() or return',
    ),
    "KS3431": Diagnostic(
        code="KS3431",
        title="Standart girdi bütçesi aşıldı",
        summary="Standart girdi, caps.input.allow() ile verilen bayt bütçesinden büyük.",
        why=(
            "Sınırsız girdi belleği tüketir. Bütçeyi aşan girdi bir hata değeri "
            "olur; okunan baytlar geri verilmez."
        ),
        fix="Bütçeyi büyütün veya girdiyi parçalara bölün.",
        example="let input = caps.input.allow(1048576)",
    ),
    "KS3432": Diagnostic(
        code="KS3432",
        title="Standart girdi okunamadı",
        summary="Standart girdi okunurken işletim sistemi hata verdi.",
        why=(
            "Okunamayan girdi sessiz bir boş metin değil, açık bir hata değeridir. "
            "Kapalı bir standart girdi ise boş girdi sayılır."
        ),
        fix="Programa okunabilir bir standart girdi verin veya hatayı 'or' ile ele alın.",
        example='let text = input.read_text() or ""',
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
        "A value did not match a function's declared parameter or return type, or a capability or capability-carrying value was disguised, stored, or returned as an ordinary value.",
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
    "KS3502": (
        "Memory budget exceeded",
        "An operation would have built a String or List over the budget, or the host ran out of memory for the program's values.",
        "Values that grow without bound stop a service and can leave half-built state behind. A String holds at most 16777216 bytes of UTF-8 and a List at most 1048576 items; an operation over the budget produces a KS3502 Error value at the same point in every executor.",
        "Split the value, bound the input size before processing it, or handle the result explicitly with 'or'.",
    ),
    "KS2407": (
        "Capability values cannot be compared",
        "Two authority tokens, or structs carrying them, were compared with == or !=.",
        "The comparison asked the host whether two tokens were the same object. Authority identity is not a Koschei value, and executors answered that question differently.",
        "Compare the values you read through the tokens, not the tokens.",
    ),
    "KS2430": (
        "Program input budget is not static",
        "caps.input.allow() expects a single static Int literal byte budget.",
        "How much standard input a program may read must be visible in the source; 'ks caps' shows the bound at compile time.",
        "Write the budget as a number.",
    ),
    "KS2431": (
        "Program input budget is out of range",
        "The standard input budget must be between 1 and 16777216 bytes.",
        "The text read becomes a String, and a String holds at most 16777216 bytes of UTF-8. A zero or negative budget means nothing.",
        "Choose a budget between 1 and 16777216.",
    ),
    "KS2440": (
        "Clock resolution is not static",
        "caps.clock.allow() expects a single static Int literal resolution in milliseconds.",
        "How finely a program may see time must be visible in the source and in 'ks caps'.",
        "Write the resolution as a number.",
    ),
    "KS2441": (
        "Clock resolution is out of range",
        "The clock resolution must be between 1 and 86400000 ms (one day).",
        "A coarse clock is weaker authority; a zero or negative resolution means nothing.",
        "Choose a resolution between 1 and 86400000.",
    ),
    "KS2450": (
        "Random budget is not static",
        "caps.random.allow() expects a single static Int literal byte budget.",
        "How much randomness a token may ever produce must be visible in the source.",
        "Write the budget as a number.",
    ),
    "KS2451": (
        "Random budget is out of range",
        "The random budget must be between 1 and 1048576 bytes.",
        "The budget bounds the total randomness one token can produce.",
        "Choose a budget between 1 and 1048576.",
    ),
    "KS3450": (
        "Random budget exhausted",
        "The token used up the byte budget given to caps.random.allow().",
        "Randomness handed to a library is not unlimited. A call over the budget produces nothing and is not charged; it returns an Error value.",
        "Raise the budget or ask for less randomness.",
    ),
    "KS3451": (
        "Invalid random request",
        "random.hex() expects 1..1024 bytes and random.below() an upper bound of at least 1.",
        "An invalid request is an Error value; nothing is drawn and nothing is charged.",
        "Pass an argument in the allowed range.",
    ),
    "KS3460": (
        "Bytes range is invalid",
        "Bytes.get() or Bytes.slice() asked for a position outside the value's length.",
        "An out-of-range access is not silently clipped and returns no other byte; it is an Error value.",
        "Keep positions between 0 and length() or handle the error with 'or'.",
    ),
    "KS3461": (
        "Hex text is invalid",
        "bytes_from_hex() expects text of even length containing only 0-9, a-f and A-F.",
        "Spaces, separators or a dangling digit are not silently skipped; ambiguous input is an Error value.",
        "Pass hex without separators and of even length.",
    ),
    "KS3470": (
        'Unanswered request',
        'accept() was called before the previous request was answered, or reply() with no request pending.',
        'The Knowhere law: nothing carries over between requests. An unanswered request is closed with 500; a reply never reaches another client.',
        'Call reply() exactly once for every accept().',
    ),
    "KS3471": (
        'Server request budget exhausted',
        'The token has accepted max_connections requests, the number given to caps.serve.allow().',
        'The number of requests one server token may accept in its lifetime is bounded.',
        'Raise the budget or continue with a new token.',
    ),
    "KS3472": (
        'Response rule violated',
        'reply() was called with an unsupported status code or a 204 with a body.',
        'Supported status codes are a small explicit set; instead of an invalid response the client gets 500.',
        'Use 200, 201, 204, 400, 403, 404, 405, 409, 413, 422, 429, 500 or 503.',
    ),
    "KS3473": (
        'Request header missing',
        'request.header(name) asked for a header the request does not carry.',
        'A missing header is an explicit Error value, not a silent empty text.',
        "Turn the error into a default with 'or'.",
    ),
    "KS3430": (
        "Program input is not text",
        "A program argument or the standard input is not valid UTF-8 text.",
        "A String carries text. Silently replacing bytes that are not UTF-8 would make the value the program sees differ from what was sent; Koschei returns an Error value that 'or' can handle instead.",
        "Send the input as UTF-8 or handle the error with 'or'.",
    ),
    "KS3431": (
        "Standard input budget exceeded",
        "The standard input is larger than the byte budget given to caps.input.allow().",
        "Unbounded input exhausts memory. Input over the budget becomes an Error value; the bytes read are not given back.",
        "Raise the budget or split the input.",
    ),
    "KS3432": (
        "Standard input could not be read",
        "The operating system reported an error while reading the standard input.",
        "Input that cannot be read is an explicit Error value, not a silent empty text. A closed standard input reads as empty.",
        "Give the program a readable standard input or handle the error with 'or'.",
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
