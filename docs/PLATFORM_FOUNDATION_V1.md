# Koschei Lang — four-platform foundation v1

Status: `experimental`, capability-free library admission layer, not a production platform.

## Proven source baseline

The main branch already contains a 14-realm production-reference *example* with an interpreter/native Go-backed locked worker, loopback HTTP ingress, JSON canonicalization and exact-object persistence. Existing K0 UEFI x86_64 work is C/Clang under separate experimental staging; it does not make Koschei Lang a self-hosted OS language. The new work extends the separately owned Koschei Core Library with **four first-party, pure `.ks` modules**.

| Module | Implemented today | Explicitly absent |
| --- | --- | --- |
| `platform_web` | UTF-8 byte length <=256, restricted ASCII route syntax, exact GET/POST path admissions, <=1MiB body limit predicate | TLS, public HTTP, auth, sessions, rate limiting, router captures, database |
| `platform_web3` | canonical lower-case 0x quantities and EVM 20-byte addresses, read-only JSON-RPC method/chain admission | RPC connection, JSON verification, signatures, wallet, chain state, receipts, finality |
| `platform_ai` | caller-supplied model allowlist, 1MiB max input and 8192 max declared output-token budget, bounded batch admission | model inference, tokenizer enforcement, GPU scheduler, tool execution, training |
| `platform_kernel` | low-1GiB 4KiB frame range checks, exact nonduplicated claimed ledger checks, disjointness | physical RAM writes, page-table installation, UEFI, GDT/IDT, scheduler, hardware isolation |

These library modules contain **no `SystemCaps` parameter** and grant no network, disk, environment, serve, process, persist, model-tool or kernel privileges. Any future adapter must separately take a narrowed capability and validate the exact object it accesses. An admission decision is not an identity or cryptographic attestation.

## Tested real HTTP vertical slice

`examples/platform_foundation_v1/loopback_gateway.ks` exercises the
actual `ServeCaps.accept/reply` runtime. Its only capability is a
statically narrowed `127.0.0.1:PORT` listener, bounded to 5 connections,
4096-byte requests, 256-byte responses and a 3-second deadline. The
first connection is the test readiness probe. Four real HTTP requests
then exercise two accepted GET routes, an accepted POST route, and a
method/path denial. Both `ks run` and Linux/amd64 native-Go compilation
are exercised by `tests/test_platform_foundation_v1.py`, and responses
must match exactly. This is a LOCAL-only HTTP gateway; no public bind,
TLS, authentication, concurrent processing, persistent state or Web3/AI
execution is implied.

## Run the real interpreter/native slice

```sh
ks check examples/platform_foundation_v1/main.ks
ks caps examples/platform_foundation_v1/main.ks
ks run examples/platform_foundation_v1/main.ks
ks build examples/platform_foundation_v1/main.ks -o /tmp/koschei-platform-foundation
/tmp/koschei-platform-foundation
python -m pytest -q tests/test_platform_foundation_v1.py
```

Expected bytes from both executors:

```text
web=health denied=DENY
web3=block-number signed=DENY
ai=local-model denied=DENY
kernel-claimed=true forged=false
```

## Read-only network-backed Web3 proof (experimental)

The first real Web3 adapter, `web3_rpc.block_number`, uses
a narrowed `NetCaps` token to make exactly two JSON-RPC POST requests
to a single local origin, checking chain ID, JSON-RPC version, response
request IDs, status, **byte-exact canonical JSON envelopes** and a
lower-case minimal hex quantity. Other valid JSON whitespace/key orders
are deliberately refused until the imported-module JSON decoder has
interpreter/native parity; no partial accept or host-language fallback. The integration fixture supplies a mocked JSON-RPC peer,
runs interpreter and Linux native broker implementations, and attempts
wrong-chain, duplicate-key, extra-field, wrong-ID, bad status, redirect,
oversize response, noncanonical hex and cross-origin failures. Only
`eth_chainId` and `eth_blockNumber` are transmitted, and no real
chain can be queried by this test. It is a **peer observation**, not
cryptographic chain trust, finality, a wallet or production Web3 Hub.

## Next implementation gates (not yet accepted)

1. **Web:** grow the existing 14-realm HTTP/persistence reference into an authenticated, bounded route dispatcher with concurrent request, timeout, audit receipt, TLS frontend and rollback tests. Existing native HTTP broker is Linux/amd64 and loopback-only.
2. **Web3:** add a read-only, explicit-origin RPC adapter whose chain-ID and response proofs are bound to immutable request identities; test origin redirects, malformed RPC, bounded responses, chain-ID mismatch, reorg ambiguity and shadow execution. No signing or transaction submission.
3. **AI:** create a strictly bounded inference-adapter ABI, real tokenizer accounting, model provenance, cancellation and tool-denial receipts with deterministic simulated provider tests. No GPU or trained model is supplied by the new library.
4. **OS:** extend the separate QEMU-only K0 experiment to a real native `.ks` ABI only after toolchain lowering, interrupt/exception handlers, ownership and physical hardware acceptance. Never describe the C kernel as compiled from `.ks`.

## Acceptance and promotion

* The four modules must be explicitly registered, resolved from a clean checkout and recognized by the compiler without special host operations.
* Adversarial parse/check/run tests must deny unsafe routes, uncanonical RPC quantities, non-allowlisted models, over-budget requests and duplicate/unowned physical frames.
* `ks caps` must report zero external authority for the executable example.
* Native build when Go is present must return **exactly the same output and exit status** as `ks run`.
* Main-branch promotion requires exact-head canonical CI success, independent review and a scoped PR. GitHub Actions or a green test does not prove full-system production security.

**Non-claims:** This milestone does not build a large web platform, blockchain node, general AI platform or standalone Koschei-language OS. It creates the first reusable language-level admission primitives and executable parity evidence for those future programs.
