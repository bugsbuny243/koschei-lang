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

`localhost` is canonicalized to literal `127.0.0.1` before the runtime policy is
created; authority identity never depends on host DNS resolution. IPv6 loopback
uses only the bracketed `[::1]:port` form so interpreter and native backends share
one unambiguous endpoint grammar.

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
For HTTP/1.1 it requires exactly one **non-empty** `Host` header. It also requires:

- one uppercase alphabetic method token;
- printable ASCII origin-form request target beginning with `/`;
- HTTP/1.0 or HTTP/1.1 only;
- strict token-shaped header names;
- no control bytes in header values;
- at most one `Content-Length`;
- no `Transfer-Encoding`;
- no already-observed bytes beyond the declared request body;
- UTF-8 request body.

Chunked transfer, duplicate/conflicting length headers and observed pipelined bytes
are rejected rather than normalized. A delayed second request is never processed:
exchange v1 closes the connection after the single response. This deliberately
reduces framing and request-smuggling ambiguity without claiming omniscient
detection of bytes that have not yet arrived.

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

## Connection/backlog budget

The interpreter and Linux native implementation both use the exact
`max_connections` policy value as the listener backlog. The interpreter does not
silently clamp the value to a backend default.

The Linux native backend uses `socket/bind/listen` at the OS boundary so the
backlog argument is explicit rather than hidden behind Go's high-level listener
default. This is a resource-policy contract, not a claim that a backlog value is a
portable guarantee of an exact number of established TCP sessions.

## Linux native-Go implementation

A native-Go implementation now exists for Linux. It mirrors:

- canonical loopback-only authority;
- exact policy backlog argument;
- complete request/response byte limits;
- strict HTTP framing rules;
- UTF-8 request body;
- one absolute I/O deadline;
- KS3410 / KS3411 failure classes.

Non-Linux native Serve generation remains fail-closed with `KS4001` in v1 because
the backlog-bound socket ABI has not been sealed for those targets.

Native parity tests build a real Go binary, connect with a real TCP client, execute
a POST exchange, and exercise framing/budget/deadline rejection paths. **Those
tests have not yet executed in hosted CI because GitHub runner allocation is
currently blocked by the account billing/spending-limit condition.**

## Errors

- `KS3410` — protocol/framing/byte-budget contract violation
- `KS3411` — socket failure or I/O deadline expiry

Both have Turkish and English explanation catalog entries.

## Standard-library truth

The `serve` family is `partial`, while `exchange` remains `reserved` in the stdlib
truth catalog. `supported` requires executed cross-backend evidence, not merely two
implementations in source. Interpreter and Linux native-Go implementations plus
parity gates now exist, but the hosted gates have not run, so `exchange` is
intentionally **not** advertised as supported yet.

`listen` remains planned.

## Acceptance tests

Interpreter tests open a real loopback TCP client against a Koschei interpreter
thread. Linux native tests additionally build a Go binary and exercise the same
network boundary. The suite covers:

- exact response wire body;
- capability-manifest operation attribution;
- canonical DNS-free loopback identity;
- exact backlog policy wiring;
- response-budget rejection before bind;
- bounded accept timeout;
- Transfer-Encoding rejection;
- duplicate Content-Length rejection;
- strict non-empty Host/header/method/target rules;
- non-Linux native fail-closed behavior;
- stdlib status does not claim unexecuted parity.

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
- cross-platform native Serve parity;
- direct-MIR execution of the Serve capability;
- production server readiness.

Those are separate security contracts, not implicit extensions of this primitive.

## Originality provenance

This surface is driven by Koschei invariants — explicit authority, bounded resource
use and fail-closed ambiguity — rather than by copying a framework API. The current
`ServeCaps.exchange` spelling still lives on the legacy/bootstrap syntax surface
and is not a declaration of final Koschei-native grammar vocabulary.
