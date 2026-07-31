# Koschei V5 standard-library contract and backend roadmap

Koschei targets secure backend services without cloning the surface or trust model
of an existing language. The standard library therefore starts from security
properties rather than from a list of familiar package names.

The machine-readable source of truth is `koschei/stdlib_catalog.py` with schema
`koschei.stdlib/v1`. Run it with:

```bash
ks-stdlib
ks-stdlib --json
```

The catalog uses three operation states:

- **supported** — implemented by both the Python bootstrap interpreter and the
  generated native Go runtime used by current parity tests;
- **reserved** — a name or method is visible in the bootstrap surface, but its
  implementation is intentionally unavailable and must not be treated as a
  usable backend feature;
- **planned** — roadmap only; no implementation claim.

Family maturity is separate. `bootstrap` means the current operation slice is
usable but not yet a production-complete library. `partial` means important
operations or security budgets remain missing. `planned` means the family has
not been implemented.

## Current truth

The compiler package has zero third-party runtime dependencies. Koschei does not
yet ship a directory of independent `.ks` standard-library modules. Its current
public API is embedded in the bootstrap interpreter and generated runtime.

The target catalog contains **32 families**:

| Phase | Families |
|---|---|
| Existing bootstrap/partial surface | `core`, `result`, `text`, `list`, `map`, `data`, `request`, `disk`, `env`, `process` |
| V1 secure backend core | `serve`, `clock`, `log`, `secure`, `random`, `identity`, `encode`, `config`, `database`, `test` |
| V2 production services | `task`, `channel`, `stream`, `tls`, `cache`, `queue`, `metrics`, `trace`, `health`, `compress`, `dns` |
| V3 persistent sessions | `websocket` |

`data.parse_json`, outbound HTTP `post`/`put`/`delete`/generic `request`, and
`process.run`/`spawn` are explicitly **reserved**, not supported. This distinction
prevents a type checker declaration or placeholder runtime method from being
mistaken for a completed standard-library feature.

## Non-negotiable library rules

Every Koschei standard-library operation must satisfy the rules below before it
can move to `supported`:

1. **No ambient authority.** Disk, network, environment, process, clock, random,
   database, server, queue, telemetry, DNS and similar effects require an explicit
   narrow capability value.
2. **No backend split.** An operation cannot be advertised as supported when only
   the interpreter or only the native runtime implements it.
3. **Fail closed.** Missing OS primitives, unsafe fallbacks or unsupported targets
   produce a located error; they never silently weaken the contract.
4. **Bounded work.** Input bytes, output bytes, collection size, tree depth,
   redirects, rows, tasks, messages, deadlines or other relevant resources have
   explicit budgets.
5. **No capability laundering.** Generic containers, serialization, logging,
   errors and asynchronous messages cannot hide or duplicate authority values.
6. **Deterministic output.** Data encoding, maps, diagnostics and build artifacts
   have canonical behavior where reproducibility matters.
7. **Secret-safe by construction.** Future `Secret<T>` values are non-printable,
   redacted in diagnostics and rejected by ordinary serialization.
8. **No shell by default.** Process execution uses an exact executable and an
   argument vector; a shell is not an implicit parsing layer.
9. **Protocol policy is explicit.** TLS versions, trust roots, redirect behavior,
   DNS/private-range rules and server limits are values, not hidden globals.
10. **Tests precede support status.** Unit tests, interpreter/native parity tests,
    resource-exhaustion tests and malformed-input tests must pass before the
    catalog state changes.

## Delivery gates

### Gate 1 — truthful bootstrap surface

- Machine-readable catalog and deterministic CLI.
- CI rejects duplicate families, duplicate operations and one-backend-only
  `supported` claims.
- Reserved operations remain visible as debt but are never counted as completed.
- Semantic/runtime/native declarations are progressively generated from or checked
  against the catalog so they cannot drift independently.

### Gate 2 — bounded `data`

- Deterministic JSON decode and encode.
- Maximum input/output bytes, nodes and depth.
- Duplicate object keys rejected.
- Integer overflow and non-finite floats rejected.
- Capability and secret values cannot be encoded.
- Interpreter/native structural parity.

### Gate 3 — complete outbound `request`

- GET, POST, PUT, DELETE and generic request share one policy engine.
- Origin confinement survives redirects and DNS changes.
- Request/response size limits and deadlines are mandatory.
- Headers are validated and secrets are not reflected into diagnostics.
- Private-network policy is explicit rather than inferred.

### Gate 4 — first Koschei backend server

- `serve` accepts only an explicit listener capability.
- Connection, request-body, response-body, header and deadline budgets.
- Structured handlers return values rather than mutating global response state.
- A complete example serves an API, decodes bounded JSON, calls a capability-
  scoped database and emits redacted structured logs.

### Gate 5 — database, configuration and secrets

- Typed query parameters; no string-built SQL path in the safe API.
- Result row/byte/deadline limits.
- Transaction authority cannot escape its scope.
- Configuration is assembled only from explicitly granted sources.
- `Secret<T>` cannot be printed, serialized, compared with ordinary equality or
  stored in unrestricted containers.

### Gate 6 — structured concurrency and production operations

- Child tasks cannot outlive their lexical task scope.
- Channels and streams are bounded and provide back pressure.
- Metrics reject untrusted-cardinality label explosions.
- Traces and logs bound attributes and redact secrets.
- Queue retries, cache memory and decompression ratios are bounded.

### Gate 7 — independent `.ks` standard library

The long-term standard library should be implemented primarily in Koschei itself.
Only the smallest audited native syscall/cryptographic boundary remains in the
runtime. Modules are versioned, reproducibly built and governed by the same
capability rules as third-party code. Importing a standard module grants no power;
capabilities still arrive only through explicit parameters.

## Definition of a production-ready family

A family is production-ready only when all of the following are true:

- its public contract is versioned;
- interpreter and native behavior are structurally equivalent;
- every effect has a narrow capability;
- every attacker-controlled workload has an enforceable budget;
- malformed and adversarial inputs do not panic or partially commit output;
- no placeholder or host-language exception leaks through the public ABI;
- documentation includes at least one secure example and one denied attack;
- the catalog, implementation and tests change in the same pull request.

This roadmap deliberately avoids claiming that a familiar API name makes Koschei
backend-ready. Koschei becomes backend-ready when the security properties are
machine-enforced across the whole implementation.
