# Koschei Forms: Polar store listing

Product name: **Koschei Forms**
Price: **19 USD, one-time** (pay what you want: off)
Benefit: file download `koschei-forms-1.0.0.zip` (build with `python tools/forms_bundle_v1.py`)
Live demo: https://koschei-forms-demo-production.up.railway.app

## English

**Your website's forms, on your own server. Provably nowhere else.**

Koschei Forms is a self-hosted backend for contact forms, job applications
and waiting lists. Point your site's `<form>` at it; submissions land in one
SQLite file on your server. Read them in a password-protected panel or export
them as CSV.

Why it is different: it is written in Koschei, a language where a program can
only reach what it is explicitly granted. Run `ks caps main.ks` and you get the
complete list: one port, one database file, one password variable, the clock.
No outgoing network, no analytics, no third party. Show that list to your
client or your data protection officer.

- Unlimited forms and submissions
- Spam honeypot, no CAPTCHA
- CSV export, safe to open in Excel
- Hardened admin panel: escaped output, strict CSP, secure sessions
- Docker image or a single `pip install`
- One purchase: run as many copies as you like, for you and your clients
- 12 months of updates; Koschei Lang runtime included for running it

Not for high-traffic sites: one request at a time (about 20 ms each).

## Türkçe

**Web sitenizin formları, kendi sunucunuzda. Başka hiçbir yere gitmediği kanıtlı.**

Koschei Forms; iletişim formları, iş başvuruları ve bekleme listeleri için kendi
sunucunuzda çalışan bir arka uçtur. Sitenizdeki `<form>`'u ona yönlendirin;
gönderimler sunucunuzdaki tek bir SQLite dosyasına kaydedilir. Şifreli panelden
okuyun ya da CSV olarak indirin.

Farkı: Koschei ile yazıldı; Koschei'de bir program yalnızca açıkça izin verilen
şeylere erişebilir. `ks caps main.ks` çalıştırınca listenin tamamını görürsünüz:
tek port, tek veritabanı dosyası, tek şifre değişkeni, saat. Dışarıya ağ
bağlantısı yok, analitik yok, üçüncü taraf yok. Bu listeyi müşterinize ya da
KVKK sorumlunuza gösterebilirsiniz.

- Sınırsız form ve gönderim
- CAPTCHA'sız spam tuzağı
- Excel'de güvenle açılan CSV dışa aktarma
- Sağlamlaştırılmış yönetim paneli: kaçışlı çıktı, sıkı CSP, güvenli oturum
- Docker imajı ya da tek bir `pip install`
- Tek satın alma: kendiniz ve müşterileriniz için istediğiniz kadar kopya
- 12 ay güncelleme; çalıştırmak için Koschei Lang lisansı dahil

Yüksek trafikli siteler için değildir: istekler sırayla işlenir (her biri ~20 ms).
