# Koschei V5 standard-library security contract

Koschei targets secure backend services without cloning the syntax, library
surface, or trust model of another language. Its standard library therefore
starts from machine-enforced security properties rather than familiar package
names.

The executable source of truth is `koschei/stdlib_catalog.py` with schema
`koschei.stdlib/v2`:

```bash
ks-stdlib
ks-stdlib --json
```

## What the catalog means

Each operation has one of three states:

- **supported** — present in both bootstrap execution paths and allowed by the
  current security gate;
- **reserved** — a name or partial implementation exists, but programs must not
  rely on it as a secure standard-library feature;
- **planned** — roadmap only, with no implementation claim.

Resource limits are deliberately split into two fields:

- `required_budgets` describes every resource dimension needed before the
  operation can be considered secure;
- `enforced_budgets` lists only limits implemented in both bootstrap backends.

A security-sensitive operation cannot be `supported` unless every required
budget is enforced. Partial defenses remain visible without being promoted to a
false support claim. For example, outbound HTTP GET currently enforces a deadline
and redirect limit, but not a response-body byte limit, so it remains `reserved`.

## Current truth

The compiler package still has zero third-party runtime dependencies. The target
catalog contains 32 families:

| Phase | Families |
|---|---|
| Existing bootstrap/partial surface | `core`, `result`, `text`, `list`, `map`, `data`, `request`, `disk`, `env`, `process` |
| V1 secure backend core | `serve`, `clock`, `log`, `secure`, `random`, `identity`, `encode`, `config`, `database`, `test` |
| V2 production services | `task`, `channel`, `stream`, `tls`, `cache`, `queue`, `metrics`, `trace`, `health`, `compress`, `dns` |
| V3 persistent sessions | `websocket` |

The following operations are explicitly reserved until their security contracts
are complete:

- `core.print` and `core.println`: capability values are not yet rejected or
  identically redacted across both backends;
- `text.to_int`: the Python bootstrap does not yet match native signed 64-bit
  overflow behavior;
- `data.parse_json`: bounded interpreter/native execution does not exist yet;
- `request.get`: response bytes are not capped;
- HTTP `post`, `put`, `delete`, and generic `request`: execution is unavailable;
- disk read/write/list operations: content, entry, or deadline budgets are not
  enforced identically in both backends;
- `env.get`: no cross-backend value-size limit;
- `process.run` and `process.spawn`: intentionally fail closed.

This is not a regression in honesty. The runtime may contain partial bootstrap
implementations, but the secure standard-library contract does not promote them
until all required guarantees are enforced.

## Non-negotiable rules

1. **No ambient authority.** Effects require explicit narrow capabilities.
2. **No backend split.** `supported` requires interpreter and native parity.
3. **Fail closed.** Unsupported targets never silently weaken behavior.
4. **Bounded attacker-controlled work.** Network, disk, parsing, database,
   concurrency, compression, telemetry, and similar workloads require enforceable
   limits.
5. **No capability laundering.** Containers, serialization, output, errors, logs,
   and messages cannot hide or duplicate authority.
6. **Deterministic output.** Encoding, diagnostics, maps, and artifacts are
   canonical where reproducibility matters.
7. **Secret-safe by construction.** Future secret values are non-printable and
   rejected by ordinary serialization.
8. **No shell by default.** Process execution uses an exact executable and
   argument vector.
9. **Protocol policy is explicit.** TLS, redirects, DNS, private ranges, trust
   roots, and server limits are values rather than hidden globals.
10. **Tests precede status.** Adversarial, parity, malformed-input, and resource
    exhaustion tests must pass before a status changes to `supported`.

## Delivery order

### Gate 1 — truthful catalog

- Separate required limits from enforced limits.
- Reject one-backend-only support.
- Reject security-sensitive support with missing enforced budgets.
- Keep partial protections visible without overstating completion.

### Gate 2 — bounded `data`

- Deterministic JSON decode and encode.
- Maximum input/output bytes, nodes, and depth.
- Duplicate object keys rejected.
- Integer overflow and non-finite numbers rejected.
- Capability and secret values cannot be encoded.
- Interpreter/native structural parity.

### Gate 3 — bounded output and scalar parity

- `print` and `println` reject capabilities and secrets before formatting.
- Output byte budgets are enforced identically.
- `to_int` accepts only signed 64-bit results in both backends.

### Gate 4 — bounded disk and outbound HTTP

- Exact file, directory-entry, request, and response limits.
- Mandatory deadlines.
- Origin confinement survives redirects and DNS changes.
- No partial output or partial file commit after budget failure.

### Gate 5 — first secure backend service

- Capability-bound HTTP server.
- Bounded request/response bodies, headers, connections, and deadlines.
- Bounded JSON, capability-scoped database access, and redacted structured logs.

### Gate 6 — production services

- Structured concurrency and bounded channels/streams.
- Database row/byte/deadline limits.
- TLS and DNS policy values.
- Bounded caches, queues, telemetry, and decompression ratios.

### Gate 7 — independent `.ks` standard library

The long-term standard library is implemented primarily in Koschei itself. Only
the smallest audited native syscall and cryptographic boundary remains in the
runtime. Importing a standard module grants no authority; capabilities still
arrive only through explicit parameters.

## Production-ready definition

A family is production-ready only when its contract is versioned, both backends
are structurally equivalent, every effect has a narrow capability, every
attacker-controlled workload is bounded, malformed inputs cannot panic or
partially commit output, and the catalog, implementation, tests, and secure
examples change together.
