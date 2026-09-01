# Koschei HTTP Response Budget v1

Status: experimental Library contract

## Purpose

`request.get` must not turn a scoped `NetCaps` authority into an unbounded host-memory consumption primitive. A response that is valid at the network/protocol layer can still be hostile at the resource layer.

This contract defines the first backend-independent response-body budget for the Koschei Library.

## Canonical v1 limit

- `HTTP_RESPONSE_MAX_BYTES_V1 = 1_048_576` bytes (1 MiB)
- the limit applies to HTTP response body bytes before conversion into a Koschei `String`
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

## Transport representation parity gate

Resource-budget parity is necessary but not sufficient for `supported` status. The interpreter and native backend must also observe the same HTTP body representation before the byte budget is applied.

A backend MUST NOT silently enable transparent content decompression when the other backend observes the encoded wire body. In particular, Go's default HTTP transport may negotiate and transparently decode gzip while Python `urllib` does not guarantee the same behavior.

Before `request.get` can leave `reserved`, Koschei must define and enforce one canonical policy. The preferred v1 direction is to request `Accept-Encoding: identity` in every backend and fail closed if a non-identity content encoding is nevertheless returned. Until that policy and its machine-readable failure identity are implemented and tested in both backends, transport representation parity is not proven.

## Canonical failure

When the response body exceeds the v1 maximum, the operation returns a deterministic Koschei error whose stable machine identity is `KSNET_RESPONSE_BUDGET`.

Human wording may be localized, but the machine identity and fail-closed behavior must remain stable.

## Security properties

### PROTECTS AGAINST

- one HTTP response consuming unbounded process memory through the standard `request.get` path;
- interpreter/native disagreement where one backend accepts an over-budget response the other rejects;
- silent truncation being mistaken for an authenticated or complete response;
- short-read host behavior bypassing the response-byte sentinel.

### DOES NOT PROTECT AGAINST

- aggregate memory use across many individually bounded concurrent requests;
- decompression bombs when transport/content decoding occurs before this byte budget;
- backend content-encoding divergence until the transport representation parity gate is implemented;
- slow-response attacks beyond the separate deadline contract;
- application-level semantic payload bombs inside a body smaller than 1 MiB.

### ASSUMPTIONS

- both backends apply this budget before materializing an unbounded body;
- redirect and deadline limits remain independently enforced;
- a zero-length blocking read represents EOF for the HTTP body stream;
- future transparent decompression introduces its own decoded-output budget rather than treating compressed bytes as sufficient.

### FAILURE MODE

If a backend cannot enforce the exact bound, or if interpreter/native transport representation parity is not established, `request.get` remains `reserved` and must fail closed rather than advertising `supported` parity.

## Evolution rule

The fixed 1 MiB v1 cap is a safe baseline, not the final authority model. A later version may carry `response_bytes` as a scoped capability-bound budget, but it must never widen authority implicitly or remove hard fail-closed semantics.
