# Koschei Server v1 (Knowhere and Sakaar)

Status: **multi-request server under `ks run` and in native binaries
(linux/amd64, through the capability broker); readiness gate G4.** The
one-shot `exchange` is still refused by `ks build` (`KS4004`).

The program stays in control: there is no callback, no framework and no
routing table.

```ks
fn handle(server: ServeCaps) -> Int {
    let mut served = 0
    while served < 100 {
        served = served + 1
        let request = server.accept() or {
            continue
        }
        let name = request.header("X-Name") or "stranger"
        let sent = server.reply(200, "{request.method()} {request.path()} hello {name}") or {
            continue
        }
    }
    return served
}

fn main(caps: SystemCaps) {
    let server = caps.serve.allow("127.0.0.1:8080", 100, 65536, 65536, 5000)
    println(handle(server))
}
```

## Surface

| Expression | Type | Meaning |
|---|---|---|
| `caps.serve.allow(bind, max_connections, max_request_bytes, max_response_bytes, deadline_ms)` | `ServeCaps` | a loopback bind, or `0.0.0.0:PORT` / `[::]:PORT` for every interface; static literals (`KS2410`/`KS2411`) |
| `server.accept()` | `HttpRequest or Error` | opens the listener on first use, accepts and reads one request |
| `server.reply(status, body)` | `Void or Error` | answers the pending request as `text/plain; charset=utf-8` (`String` or `Bytes` body) and closes it |
| `server.reply_as(status, content_type, body)` | `Void or Error` | the same with the given content type, such as `application/json` or `text/html; charset=utf-8` |
| `request.method()`, `request.path()` | `String` | raw request line parts |
| `request.header(name)` | `String or Error` | case-insensitive name; `KS3473` when absent |
| `request.body()` | `String or Error` | `KS3430` when the body is not UTF-8 |
| `request.body_bytes()` | `Bytes` | the body as received |

Statuses: 200, 201, 204, 400, 403, 404, 405, 409, 413, 422, 429, 500, 503
(`KS3472` otherwise; a 204 cannot carry a body). A content type is 1–256
printable ASCII characters with no space at either end, the rule of
`NetCaps.post` (`docs/NET_V1.md`): a line break can never add a header.
Otherwise the client gets `500` and `reply_as()` returns `KS3472`. Koschei
does not build JSON or HTML for the program; the body is the text or bytes
it gives.

## The Knowhere law: nothing carries over

- Each connection carries exactly one request and is closed after its reply
  (`Connection: close`). There is no keep-alive state to leak between
  clients.
- A request is answered once. Calling `accept()` while one is unanswered
  closes it with `500` and returns `KS3470`; `reply()` with nothing pending
  returns `KS3470`. A client is never left hanging and never receives a reply
  meant for someone else.
- An `HttpRequest` is plain data; it holds no socket and no authority.

## The Sakaar law: no implicit input processing

The program sees the raw path (query string included, nothing decoded),
header values by name and the body. The server does no routing, URL decoding,
cookie, form or JSON parsing: every interpretation of input is code the
program calls and can be reviewed. The `http` Core Library module
(`route`, `query`, `params`, `decode`, `escape_html`) and `parse_json` are
that code, written in Koschei and pure.

## Budgets

| Budget | Enforced |
|---|---|
| `max_connections` | total requests one token may accept; then `KS3471` |
| `max_request_bytes` | headers (hard ceiling 64 KiB) plus body; over it the client gets `413` and `accept()` returns the Error value |
| `max_response_bytes` | the complete response; over it the client gets `500` and `reply()` returns the Error value |
| `deadline_ms` | per request: waiting in `accept()` (then `KS3411`) and reading the whole request |

The strict HTTP/1.x grammar of the one-shot `exchange` applies: one `Host`
for HTTP/1.1, a single `Content-Length`, no `Transfer-Encoding`, no
pipelining. A protocol error answers `400` and the server keeps listening.

## Evidence

`tests/test_serve_knowhere_v1.py` runs servers under `ks run` with real HTTP
clients: GET and POST with raw paths, headers, UTF-8 and binary bodies;
protocol and budget failures answered and survived; the unanswered-request
rule; reply status, size and 204 rules; the request budget; the accept
deadline; checker rules; and the native `KS4004` refusal of `exchange`.

## Native binaries

The worker has no sockets. The broker binds the listener on the first
`accept()` (backlog `min(max_connections, 128)`), keeps the one pending
connection, and ports every rule above: the loopback bind, the effective
request grammar (`serve_loopback_exchange_v1` with its strict and parity
layers), the budgets, the Knowhere rule and each Error text. Failures name
socket codes (`KS3411: listener failed: EADDRINUSE`), never host messages,
in both executors. Header names are tokens, so `request.header()` folds ASCII
letters only.

A server lives as long as the program holds it, in both executors: a MIR
slot holding the `ServeCaps` keeps its listener open. When the program drops
it, `ks run` closes the listener and an unanswered connection at once; in a
binary the worker's garbage collector finalizes the token and the broker
closes both. If a later server's bind is taken by an earlier server of the
same program, the worker collects first and asks again once, so a server
opened anew each round of a loop listens under both. While a server is still
held, another one on its bind gets `KS3411: listener failed: EADDRINUSE`
under both.

`tests/test_native_serve_v1.py` sends 28 requests to the same server under
`ks run` and as a binary: well-formed, binary and Latin-1 requests, every
protocol refusal, both size budgets, a client that stalls past the deadline,
a client that stops half way through its body, unsupported and empty-body
statuses, an oversized reply, the unanswered-request rule, the accept
deadline, JSON and HTML replies and two refused content types. The replies the clients read and the program's output are the same
bytes. More cases cover the connection budget (`KS3471`), a port already in
use, and forty servers opened in turn on two binds: dropped servers close
their unanswered connections and free their bind, a held one does not. The worker runs under seccomp and holds no socket but its
broker channel while serving.

## Public servers

`caps.serve.allow("0.0.0.0:8080", ...)` listens on every interface, so other
machines can connect. Everything above still applies: one request per
connection, the strict grammar, every budget and every Error text.

- **Serve with a binary.** `ks run` stops a program after its step budget
  (`--max-steps`, one million by default), so a long-running server is built
  with `ks build` and run as a native binary.
- **More requests than one token allows.** `max_connections` (at most 4096)
  bounds one token. A program that serves for longer opens a fresh server when
  one is spent; the bind is freed when the old token is dropped:

  ```text
  fn main(caps: SystemCaps) {
      while true {
          let server = caps.serve.allow("0.0.0.0:8080", 4096, 65536, 65536, 10000)
          serve(server, 4096)
      }
  }
  ```

  Connections that arrive in the moment between two servers are refused, so
  put a reverse proxy or a platform router that retries in front of it.
- **One request at a time.** A server answers requests in turn; a slow client
  holds it for at most `deadline_ms`. Keep the deadline short on a public
  server.
- **Containers.** A platform that sets `PORT` cannot pass it to the program,
  since the bind is a literal: set the platform's port to the one the program
  names.
