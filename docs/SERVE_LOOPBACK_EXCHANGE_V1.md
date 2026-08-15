# Serve Loopback Exchange v1

This slice is Koschei's first runtime primitive that actually opens an inbound
socket. It is deliberately **not** a server framework and not a claim of general
HTTP support.

The primitive exists to prove the lowest-level ingress security envelope before
routing, callbacks, persistence or public exposure are added.

## Language surface

Given an already narrowed `ServeCaps` token:

```text
let body = server.exchange("accepted") or return
```

`exchange`:

1. opens the exact loopback bind sealed into `ServeCaps`;
2. accepts one connection;
3. reads one strict HTTP/1.x request under one absolute I/O deadline;
4. returns the request body as UTF-8 `String`;
5. writes one fixed `200 OK` text response bounded by the response-byte budget;
6. closes the connection and listener.

There is no callback or user handler in this version. Therefore the authority's
I/O deadline is not misrepresented as a CPU/handler execution deadline.

## Network authority

`exchange` cannot construct its own socket scope. It consumes the loopback-only
`ServeCaps` created by Serve Authority v1. Public/wildcard binds remain
unrepresentable through this bootstrap path.

## Absolute I/O deadline

One monotonic deadline is computed before socket I/O begins. The remaining time is
re-applied before accept, request reads and response write. Progress does not reset
the deadline, so a slow peer cannot keep the one-shot exchange alive indefinitely
by sending occasional bytes.

## Request budget

`max_request_bytes` bounds the complete request materialized by the primitive,
including headers and body. Headers also have an independent hard 64 KiB ceiling.

The body length is determined only by a single valid `Content-Length` header. A
message whose declared body would exceed the request budget is rejected before the
body is fully materialized.

## Reduced HTTP grammar

The first parser intentionally accepts less than a general-purpose HTTP server.
For HTTP/1.1 it requires exactly one `Host` header. It also requires:

- one uppercase alphabetic method token;
- printable ASCII origin-form request target beginning with `/`;
- HTTP/1.0 or HTTP/1.1 only;
- strict token-shaped header names;
- no control bytes in header values;
- at most one `Content-Length`;
- no `Transfer-Encoding`;
- no bytes beyond the declared request body;
- UTF-8 request body.

Chunked transfer, duplicate/conflicting length headers and pipelined bytes are
rejected rather than normalized. This deliberately reduces framing and request-
smuggling ambiguity in the bootstrap primitive.

## Response budget

`max_response_bytes` bounds the **entire wire response**, not only its body. The
response contains:

- `HTTP/1.1 200 OK`
- `Content-Type: text/plain; charset=utf-8`
- exact `Content-Length`
- `Connection: close`
- the caller-supplied UTF-8 String body

If the complete response would exceed the budget, `exchange` fails before opening
the listener.

## Errors

- `KS3410` — protocol/framing/byte-budget contract violation
- `KS3411` — socket failure or I/O deadline expiry

Both have Turkish and English explanation catalog entries.

## Standard-library truth

The `serve` family becomes `partial`, but `exchange` remains `reserved` in the
stdlib truth catalog. The catalog's `supported` state means interpreter/native-Go
parity. Native Go still fails closed for Serve authority, so this experimental
interpreter primitive is intentionally **not** advertised as supported.

`listen` remains planned.

## Acceptance tests

The test suite opens a real loopback TCP client against a Koschei interpreter
thread and sends a POST body. It also checks:

- exact response wire body;
- capability-manifest operation attribution;
- response-budget rejection before bind;
- bounded accept timeout;
- Transfer-Encoding rejection;
- duplicate Content-Length rejection;
- strict Host/header/method/target rules;
- stdlib status does not claim backend parity.

## Non-claims

This version does not provide:

- public network ingress;
- TLS;
- routing;
- request metadata objects;
- user callbacks/handlers;
- handler CPU deadlines;
- keep-alive;
- pipelining;
- chunked bodies;
- streaming bodies;
- native-Go parity;
- direct-MIR execution of the Serve capability;
- production server readiness.

Those are separate security contracts, not implicit extensions of this primitive.

## Originality provenance

This surface is driven by Koschei invariants — explicit authority, bounded resource
use and fail-closed ambiguity — rather than by copying a framework API. The current
`ServeCaps.exchange` spelling still lives on the legacy/bootstrap syntax surface
and is not a declaration of final Koschei-native grammar vocabulary.
