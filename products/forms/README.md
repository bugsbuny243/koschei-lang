# Koschei Forms

A self-hosted backend for the forms on your website: contact forms, job
applications, waiting lists. Your static site posts to it, submissions are
kept as small files in one directory on your server, and you read them in a
password-protected panel or download them as CSV.

Written in [Koschei](https://koschei.dev). Before it runs, `ks caps main.ks`
prints everything it can reach, and the compiler refuses a program that
reaches for anything else:

```text
HTTP SERVER:  0.0.0.0:8080
DISK:         /data/koschei-forms   (read, write, list, delete)
ENVIRONMENT:  KOSCHEI_FORMS_PASSWORD
CLOCK, RANDOM
NETWORK:      none    PROCESSES: none
```

No call to a third-party service, no analytics, no outgoing connection: the
submissions of your visitors stay on your server. You can show that list to a
customer or an auditor.

### Enforced at run time too

`ks build` turns it into one static binary that runs as two processes:

- a **broker** that holds the listening socket, the data directory and the
  password variable, and nothing else the program can ask for;
- a **worker** that runs the Forms code with an empty environment, under
  `no_new_privs` and a seccomp allow list: opening a file, creating a
  socket, starting a process or changing the file system is refused by the
  kernel (`EPERM`). Every disk and network action is a request to the broker,
  which applies the same scope as the manifest above.

So the manifest is not only a compile-time promise: a bug in the program or
in the generated runtime still cannot reach outside it. linux/amd64 only.

## Run it

With Docker (linux/amd64):

```sh
docker build -t koschei-forms .
docker run -d -p 8080:8080 -v koschei-forms-data:/data \
  -e KOSCHEI_FORMS_PASSWORD='a long passphrase of 12+ characters' \
  koschei-forms
```

The image holds only the binary (distroless, non-root).

Without Docker (Python 3.12+ and Go 1.24+ to build, nothing to run):

```sh
pip install koschei-lang==0.14.0
CGO_ENABLED=0 ks build main.ks -o koschei-forms
sudo mkdir -p /data/koschei-forms && sudo chown "$USER" /data/koschei-forms
KOSCHEI_FORMS_PASSWORD='a long passphrase' ./koschei-forms
```

Put it behind a reverse proxy with HTTPS (Caddy, nginx, Railway, Fly.io). The
admin session cookie is `Secure`, so browsers send it over HTTPS only (and to
`localhost`). The proxy also matters for availability: see *Limits*.

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
| Sign-in | Sessions of 12 hours in an `HttpOnly; Secure; SameSite=Strict` cookie; random 256-bit tokens; only their SHA3-256 digest is written to disk. After 10 wrong passwords in 15 minutes, sign-in pauses for everyone. |
| Limits | 64 KiB per submission, 10 s per request. |

## Storage

Everything is in `/data/koschei-forms`, one file per record:

| File | Content |
|---|---|
| `form_<name>` | the form's redirect address, empty for the thank-you page |
| `sub_<name>_<time>_<random>` | one submission's fields, form-encoded |
| `session_<digest>` | a session's expiry |
| `fail_<time>_<random>` | one failed sign-in |

Back it up by copying the directory. Files are written atomically (a new file
beside the old one, `fsync`, then `rename`), so a crash never leaves half a
submission.

## Limits

- **One connection is served at a time, for up to 10 s.** A client that opens
  a connection and sends nothing holds the server for those 10 s; three such
  connections delayed a normal request by 30 s in our test. Run it behind a
  reverse proxy that buffers whole requests before passing them on (nginx and
  Caddy do by default), so slow or idle clients wait at the proxy, not here.
- Every admin page lists the whole directory, so it slows down as
  submissions accumulate; export and remove old submissions now and then.
- One administrator password; no user accounts.
- The panel shows the latest 200 submissions per form; CSV has all of them.
- File uploads are not accepted (only `application/x-www-form-urlencoded`).

## License

Koschei Forms is sold under the Koschei Lang License 1.0 commercial terms. See
`LICENSE` in the Koschei Lang repository.
