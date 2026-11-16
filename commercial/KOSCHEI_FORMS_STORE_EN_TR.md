# Koschei Forms: Polar store listing

Product name: **Koschei Forms**
Price: **19 USD, one-time** (pay what you want: off)
Benefit: file download `koschei-forms-1.0.0.zip` (build with `python tools/forms_bundle_v1.py`)

## English

**Your website's forms, on your own server. Provably nowhere else.**

Koschei Forms is a self-hosted backend for contact forms, job applications
and waiting lists. Point your site's `<form>` at it; submissions are kept as
small files in one directory on your server. Read them in a password-protected
panel or export them as CSV.

Why it is different: it is written in Koschei, a language where a program can
only reach what it is explicitly granted. Run `ks caps main.ks` and you get the
complete list: one port, one data directory, one password variable, the clock
and the random source. No outgoing network, no analytics, no third party. Show
that list to your client or your data protection officer.

It is enforced at run time too: Forms ships as one static binary in which the
code runs in a process the kernel confines (seccomp, no new privileges, empty
environment); only a small broker holds the port, the directory and the
password.

- Unlimited forms and submissions
- Spam honeypot, no CAPTCHA
- CSV export, safe to open in Excel
- Hardened admin panel: escaped output, strict CSP, secure sessions
- Docker image holding only the binary, or build it yourself with `ks build`
- One purchase: run as many copies as you like, for you and your clients
- 12 months of updates; Koschei Lang runtime included for running it

Not for high-traffic sites: requests are answered one at a time. Run it behind
a reverse proxy with HTTPS.

## Türkçe

**Web sitenizin formları, kendi sunucunuzda. Başka hiçbir yere gitmediği kanıtlı.**

Koschei Forms; iletişim formları, iş başvuruları ve bekleme listeleri için kendi
sunucunuzda çalışan bir arka uçtur. Sitenizdeki `<form>`'u ona yönlendirin;
gönderimler sunucunuzda tek bir dizinde küçük dosyalar olarak saklanır. Şifreli
panelden okuyun ya da CSV olarak indirin.

Farkı: Koschei ile yazıldı; Koschei'de bir program yalnızca açıkça izin verilen
şeylere erişebilir. `ks caps main.ks` çalıştırınca listenin tamamını görürsünüz:
tek port, tek veri dizini, tek şifre değişkeni, saat ve rastgele sayı kaynağı.
Dışarıya ağ bağlantısı yok, analitik yok, üçüncü taraf yok. Bu listeyi
müşterinize ya da KVKK sorumlunuza gösterebilirsiniz.

Bu, çalışma anında da geçerlidir: Forms tek bir statik binary olarak gelir; kod,
çekirdeğin kısıtladığı bir süreçte çalışır (seccomp, yeni yetki yok, boş ortam).
Port, dizin ve şifre yalnızca küçük bir aracı süreçtedir.

- Sınırsız form ve gönderim
- CAPTCHA'sız spam tuzağı
- Excel'de güvenle açılan CSV dışa aktarma
- Sağlamlaştırılmış yönetim paneli: kaçışlı çıktı, sıkı CSP, güvenli oturum
- Yalnızca binary'yi içeren Docker imajı ya da `ks build` ile kendiniz derleyin
- Tek satın alma: kendiniz ve müşterileriniz için istediğiniz kadar kopya
- 12 ay güncelleme; çalıştırmak için Koschei Lang lisansı dahil

Yüksek trafikli siteler için değildir: istekler tek tek yanıtlanır. HTTPS'li bir
reverse proxy arkasında çalıştırın.
