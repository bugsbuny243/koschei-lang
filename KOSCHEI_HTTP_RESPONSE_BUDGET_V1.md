# Koschei HTTP Response Budget v1

Status: experimental Library contract

## Purpose

`request.get` must not turn a scoped `NetCaps` authority into an unbounded host-memory consumption primitive. A response that is valid at the network/protocol layer can still be hostile at the resource layer.

This contract defines the first backend-independent response-body and transport-representation budget for the Koschei Library.

## Canonical v1 limit

- `HTTP_RESPONSE_MAX_BYTES_V1 = 1_048_576` bytes (1 MiB)
- the limit applies to canonical identity HTTP response body bytes before conversion into a Koschei `String`
- interpreter and native backend must enforce the same numeric limit
- the implementation may accumulate at most `limit + 1` bytes only to distinguish exactly-at-limit from over-limit
- host reads are allowed to return short chunks; enforcement MUST continue reading until EOF or the `limit + 1` sentinel is reached
- an over-limit response MUST fail closed and MUST NOT be silently truncated

## Required request.get budgets

`request.get` is eligible for `supported` status only when all three budgets are enforced with backend parity:

1. `deadline`
2. `redirects`
3. `response_bytes`

The existing deadline and redirect controls do not substitute for `response_bytes`.

## Canonical transport representation v1

Resource-budget parity is necessary but not sufficient. The interpreter and native backend must observe the same body representation before the byte budget is applied.

Koschei HTTP v1 therefore uses identity representation only:

- requests are constrained to `Accept-Encoding: identity`;
- missing, empty, or explicit `Content-Encoding: identity` is accepted;
- `gzip`, `br`, `deflate`, or any other non-identity response encoding fails closed;
- native transparent decompression is disabled and a response marked as already transparently decompressed is rejected.

The stable machine identity for this failure class is `KSNET_CONTENT_ENCODING`.

The interpreter validates the returned `Content-Encoding` before body materialization. Public native `ks build` packages that contain the compatibility HTTP runtime receive a small audited `http_transport_v1.go` companion. That companion clones the default Go transport, sets `DisableCompression = true`, forces `Accept-Encoding: identity`, and rejects non-identity or transparently decompressed responses.

Pure MIR-Go packages that do not contain an HTTP runtime do not receive this companion; the guard is not injected into binaries that cannot perform HTTP work.

### Current support gate

Public `ks build` now carries the identity transport guard for HTTP-capable compatibility packages, but `ks emit-go` still emits the generated `main.go` text without the build companion file. Therefore transport representation parity is not yet proven for every public native-source surface and `request.get` remains `reserved`.

`request.get` must also remain `reserved` until the canonical full-repository validation receipt passes.

## Canonical failures

When the response body exceeds the v1 maximum, the operation returns a deterministic Koschei error whose stable machine identity is `KSNET_RESPONSE_BUDGET`.

When a response uses a non-identity representation or transparent native decompression is observed, the stable machine identity is `KSNET_CONTENT_ENCODING`.

Human wording may be localized, but the machine identity and fail-closed behavior must remain stable.

## Security properties

### PROTECTS AGAINST

- one HTTP response consuming unbounded process memory through the standard `request.get` path;
- interpreter/native disagreement where one backend accepts an over-budget response the other rejects;
- silent truncation being mistaken for an authenticated or complete response;
- short-read host behavior bypassing the response-byte sentinel;
- public native builds silently switching from encoded to transparently decompressed HTTP bodies;
- a server ignoring the requested identity representation and returning gzip/br/deflate without a fail-closed signal.

### DOES NOT PROTECT AGAINST

- aggregate memory use across many individually bounded concurrent requests;
- application-layer decompression performed explicitly after an accepted identity response;
- native-source consumers that compile raw `ks emit-go` output without the required companion guard;
- slow-response attacks beyond the separate deadline contract;
- application-level semantic payload bombs inside a body smaller than 1 MiB;
- malicious or compromised host networking code below the assumed Go/Python HTTP implementation boundary.

### ASSUMPTIONS

- both backends apply the body budget before materializing an unbounded body;
- redirect and deadline limits remain independently enforced;
- a zero-length blocking read represents EOF for the HTTP body stream;
- public `ks build` compiles all files in its temporary Go package, including the identity transport companion when HTTP runtime code is present;
- the standard Go `http.DefaultTransport` begins as `*http.Transport`; if that assumption is false the companion fails closed at process initialization rather than silently dropping transport policy;
- future explicit decompression introduces its own decoded-output budget rather than treating compressed bytes as sufficient.

### FAILURE MODE

If a backend cannot enforce the exact byte bound, cannot enforce identity representation, or does not include the required transport companion, `request.get` remains `reserved` and must fail closed rather than advertising `supported` parity.

## Evolution rule

The fixed 1 MiB v1 cap is a safe baseline, not the final authority model. A later version may carry `response_bytes` as a scoped capability-bound budget, but it must never widen authority implicitly or remove hard fail-closed semantics.
