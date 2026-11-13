# Koschei Forms

A self-hosted backend for the forms on your website: contact forms, job
applications, waiting lists. Your static site posts to it, submissions go
into one SQLite file on your server, and you read them in a password-protected
panel or download them as CSV.

Written in [Koschei](https://koschei.dev). Before it runs, `ks caps main.ks`
prints everything it can reach, and the compiler guarantees it can reach
nothing else:

```text
HTTP SERVER:  0.0.0.0:8080
DATABASE:     /data/koschei-forms.db
ENVIRONMENT:  KOSCHEI_FORMS_PASSWORD
CLOCK, RANDOM
NETWORK:      none    DISK: none    PROCESSES: none
```

No call to a third-party service, no analytics, no outgoing connection: the
submissions of your visitors stay on your server. You can show that list to a
customer or an auditor.

## Run it

With Docker:

```sh
docker build -t koschei-forms .
docker run -d -p 8080:8080 -v koschei-forms-data:/data \
  -e KOSCHEI_FORMS_PASSWORD='a long passphrase of 12+ characters' \
  koschei-forms
```

Without Docker (Python 3.12+):

```sh
pip install koschei-lang==0.14.0
sudo mkdir -p /data && sudo chown "$USER" /data
KOSCHEI_FORMS_PASSWORD='a long passphrase' ks run --max-steps 1000000000000000 main.ks
```

Put it behind HTTPS (Railway, Fly.io, Caddy, nginx): the admin session cookie
is `Secure` and browsers send it over HTTPS only (and to `localhost`).

## Use it

1. Open `https://your-server/admin` and sign in with the password.
2. Create a form, for example `contact`. Optionally give it an address to send
   visitors to after they submit; otherwise they see a built-in thank-you page.
3. Point your site's form at it:

```html
<form action="https://your-server/f/contact" method="POST">
  <input name="email" type="email" required>
  <textarea name="message"></textarea>
  <input name="_gotcha" style="display:none" tabindex="-1" autocomplete="off">
  <button type="submit">Send</button>
</form>
```

Submissions appear in the panel, newest first; **CSV** downloads them all.

## What it does for you

| | |
|---|---|
| Spam | The hidden `_gotcha` field: bots fill it, people do not. Such posts are accepted and dropped. |
| Unknown forms | Posts to a form you have not created are refused (404). |
| Redirects | Only the address you set per form, never one sent by the visitor, so the server is not an open redirect. |
| Stored fields | Every field except those whose names start with `_`. |
| Panel safety | Every value is HTML-escaped; strict Content-Security-Policy, `X-Frame-Options: DENY`, `no-store`. |
| CSV safety | Cells that a spreadsheet would run as a formula (`=`, `+`, `-`, `@`) are prefixed with `'`. |
| Sign-in | Sessions of 12 hours in an `HttpOnly; Secure; SameSite=Strict` cookie; random 256-bit tokens, stored hashed. After 10 wrong passwords in 15 minutes, sign-in pauses for everyone. |
| Limits | 64 KiB per submission, 10 s per request, 1 GiB database. |

## Limits

- One request is handled at a time. A submission takes about 20 ms, so this
  suits sites with up to tens of thousands of submissions a day, not
  high-traffic bursts.
- One administrator password; no user accounts.
- The panel shows the latest 200 submissions per form; CSV has all of them.
- File uploads are not accepted (only `application/x-www-form-urlencoded`).

## License

One purchase (19 USD on [Polar](https://polar.sh)) lets one person or
organisation run any number of copies, for itself and its clients, and
includes the right to use Koschei Lang to run it. See `LICENSE.md`.
