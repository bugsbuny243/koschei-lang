# Koschei Network v1

Status: **`NetCaps.get` under `ks run` and in native binaries (linux/amd64,
through the capability broker); third step of readiness gate G2.**

`caps.net.allow(origin)` narrows the network to one origin (scheme, host,
port). `net.get(url)` returns a `Response` (`status()`, `text()`) or an Error
value. The same request gives the same bytes in every executor because none
of the rules below is left to a host HTTP library. They live in
`koschei/net_v1.py`; the native port is `koschei/native_net_v1.py`.

## URL grammar

```
scheme://host[:port][/path][?query][#fragment]
```

- `scheme` is `http` or `https`, in any case.
- `host` is ASCII letters, digits, `.`, `-` and `_` (lowercased), or a
  bracketed IPv6 literal. User information (`user@`) is refused.
- `port` is 1–65535 written with at most five digits; an empty port is
  refused; the default port is not repeated in the `Host` header.
- Every character is printable ASCII; path and query use only RFC 3986
  characters with well-formed `%` escapes. The path is sent as written:
  no dot-segment removal, no re-escaping.
- The fragment is never sent.

A URL outside this grammar, or outside the token's origin, is
`KS3402: Ağ origin kapsamı dışında erişim reddedildi: <url>` and makes no
request.

## The request

`GET` with exactly `User-Agent: koschei/1`, `Accept-Encoding: identity`,
`Connection: close` and `Host`. The host's language and version are never
sent.

## Redirects

Koschei follows 301, 302, 303, 307 and 308 that carry a `Location` itself,
at most five times. A relative location is resolved against the current URL
without dot-segment removal. A target outside the origin, or not a valid
URL, is `KS3402: Ağ yönlendirmesi kapsam dışına çıktı: <target>`; a sixth
redirect is `API isteği başarısız: çok fazla yönlendirme: <url>`. A redirect
status without `Location` is an ordinary response.

## Responses

Every final status is a `Response`; `status()` tells 200 from 404. The body:

- must use the identity encoding (`KSNET_CONTENT_ENCODING`);
- holds at most 1 MiB (`KSNET_RESPONSE_BUDGET`);
- must be complete: a body shorter than its `Content-Length` is
  `ECONNRESET`;
- must be UTF-8, whatever charset the server declares
  (`API yanıtı geçerli UTF-8 metin değil: <url>`).

A `Response` prints as `<Response>` and cannot be compared (`KS2407`).

## Failures

`API isteği başarısız: <CODE>: <url>`, with one code:

| Code | Meaning |
|---|---|
| `ECONNREFUSED` | nothing listens on the port |
| `ECONNRESET` | the peer closed the connection before a full response |
| `ETIMEDOUT` | a connect, read or write made no progress for 10 s |
| `EHOSTUNREACH`, `ENETUNREACH` | no route |
| `EDNS` | the name does not resolve |
| `ETLS` | handshake or certificate verification failed |
| `EPROTO` | the peer did not answer in HTTP/1.x |
| `EIO` | anything else, including a proxy that refuses the tunnel |

## Proxies

Read from the environment of the process that holds the authority (`ks run`,
or the broker; the worker has no environment):

1. Loopback hosts (`localhost`, `*.localhost`, `127.0.0.0/8`, `::1`) are
   never proxied.
2. `no_proxy` (else `NO_PROXY`): `*`, a host (also matches subdomains), a
   `.suffix`, `*.suffix`, an IP address, a CIDR range, each optionally with
   `:port`.
3. Otherwise `http_proxy` / `https_proxy` (lowercase first). A value without
   a scheme means `http://`. Only plain HTTP proxies are supported; any other
   proxy makes every request `EIO` instead of being used differently by each
   host library. HTTPS goes through `CONNECT`.

## TLS

Certificates are verified against the host's trust store; `SSL_CERT_FILE`
and `SSL_CERT_DIR` are honoured by both executors. HTTP/2 is not used.

## Native binaries

The worker cannot open sockets (seccomp, `docs/NATIVE_BROKER_V1.md`).
`caps.net.allow` registers the origin with the broker, which also picks the
proxy then. Each `get` is one request on the channel, and the broker answers
with the status and the body or the Error text. Only programs that use the
network link `net/http`.

## Not yet

`post`, `put`, `delete` and `request` return `… henüz desteklenmiyor`
under `ks run`, and `ks build` refuses them (`KS4004`). There are no request or response
headers in the language and no `Bytes` body.

## Evidence

`tests/test_native_net_v1.py`:

- the grammar, redirect resolution and proxy choice, unit by unit;
- 28 requests against a local server give the same bytes under `ks run` and
  from the binary: statuses, every redirect case, five and six redirects,
  encodings, the exact and the exceeded budget, Latin-1, the headers the
  server saw, early close, a short body, a non-HTTP peer, raw paths, refused
  URLs and a closed port;
- a forwarding proxy sees the same absolute request, a refused `CONNECT` is
  `EIO`, an unsupported proxy is `EIO`, and loopback bypasses the proxy;
- TLS against a self-signed certificate is `ETLS`, and passes in both once
  `SSL_CERT_FILE` trusts it.

A silent peer gave `ETIMEDOUT` after 10 s in both executors (manual check).
So did requests through this environment's proxy to a real HTTPS host and a
name that does not resolve.
