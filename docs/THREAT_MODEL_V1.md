# Koschei Threat Model v1

Status: **current for the code in this repository** (readiness gate G8, the
part that does not need an external auditor)

This document says what Koschei protects, from whom, how, with what evidence,
and what it does not protect. It covers the language toolchain (`ks`), not
the separate Koschei Sentinel product.

## Assets

1. **The user's resources**: files, network, environment, process table,
   standard input, clock and randomness of the machine that runs a program.
2. **The integrity of decisions** a Koschei program makes (admission
   verdicts, digests): the same input must give the same answer in every
   executor.
3. **Availability** of the host running a program: a program must not hang
   or exhaust it unboundedly.
4. **The integrity of the toolchain and its releases.**

## Actors

| Actor | Trusted for |
|---|---|
| Program author / operator | choosing which capabilities `main` narrows and passes |
| Third-party Koschei code (libraries, imported modules) | nothing: it gets only the tokens it is handed |
| Input data (stdin, arguments, files, HTTP bodies) | nothing |
| Host runtime (CPython, Go runtime, OS kernel) | everything below the language boundary |
| Toolchain maintainers | the compiler, runtimes and releases |

## Trust boundaries

1. **Source → checker.** Every program is checked completely before it runs:
   types, capability flow, purity, typestate and affine use.
2. **Checker → sealed MIR.** Execution consumes sealed MIR; there is no
   second semantic authority and no AST fallback for graphs that do not need
   one.
3. **Language → host.** Capability operations are the only path to host
   effects; each is bound to a canonical effect and power domain.
4. **Native binary → OS.** Binaries carry program input, clock and
   randomness directly. The disk (read, write, delete), the environment, the
   network and the loopback server go through a broker process; the program
   runs in a worker confined by a seccomp allow list, with an empty
   environment and no sockets (`docs/NATIVE_BROKER_V1.md`, `docs/NET_V1.md`,
   `docs/SERVE_KNOWHERE_V1.md`). Processes, `persist` and `serve.exchange`
   are refused at build time (`KS4004`).

5. **Package → project.** A dependency is source code fetched from a path,
   a git commit or the registry. Nothing of it runs while it is fetched or
   compiled; its capability surface is computed by the compiler and locked
   with its digest, and every compile verifies the lock and the vendored
   bytes (`docs/PACKAGES_V1.md`).
6. **Registry → client.** The registry is static files. The client trusts
   neither its surface nor its archive: it checks both digests, extracts
   only package sources, and recomputes the surface.

## Threats and controls

| # | Threat | Control | Evidence |
|---|---|---|---|
| T1 | A library reads files, the network or secrets it was not given | No ambient authority; roots cannot act; narrowing only shrinks; tokens move and cannot hide in collections | `tests/test_semantic_capability_contract_v1.py`, `tests/test_affine_resources_v1.py`, adversarial lab |
| T2 | A disk token escapes its prefix (`..`, symlinks, hard links) | Descriptor-anchored, symlink-refusing access; atomic replace on write | `tests/test_nidavellir_all_or_nothing_v1.py`, `tests/test_interpreter.py`, `tests/test_native_broker_v1.py` |
| T3 | Network redirect leaves the allowed origin | Strict URL grammar; Koschei follows redirects itself and refuses any target outside the origin (`KS3402`) | `tests/test_interpreter.py`, `tests/test_network_scheme_security.py`, `tests/test_native_net_v1.py` |
| T4 | Hostile input crashes the program or the host | Errors are values; non-UTF-8 input and files are Error values; value budget (`KS3502`); step and call-depth budgets | `tests/test_disk_read_text_v1.py`, `tests/test_program_input_v1.py`, `tests/test_value_budget_v1.py` |
| T5 | Executors disagree, so a decision depends on where it runs | One rule per operation; differential tests between interpreter, canonical MIR, direct MIR and binaries | `tests/test_mir_go_native_v2_parity.py`, `tests/test_morag_xandar_v1.py`, `tests/test_language_guide_v1.py` |
| T6 | Host details leak into program output or to servers | Capabilities and responses render as their type; comparing them is refused (`KS2407`); errors name codes, not host messages; requests send `User-Agent: koschei/1`, never the host language or version | `tests/test_program_input_v1.py`, `tests/test_native_net_v1.py` |
| T7 | Weak or predictable randomness | Only the OS secure source (`secrets`, `crypto/rand`); failure stops the program | `tests/test_clock_random_v1.py` |
| T8 | Timing side channels through a precise clock | Clock resolution is part of the capability | `docs/CLOCK_RANDOM_V1.md` |
| T9 | Home-made cryptography | None: digests delegate to audited host SHA3-256 | `koschei/secure_hash_v1.py`, `tests/test_secure_library_v1.py` |
| T10 | A dependency or build input is substituted | Module lock, build manifest, hash-locked tooling, digest-pinned containers, SBOM | `docs/MODULE_LOCK.md`, `docs/REPRODUCIBLE_BUILDS.md` |
| T11 | A package update quietly gains authority (the August 2026 crates.io pattern) | Surface computed from source and locked; a wider surface is refused without `--allow`; `[policy] deny`; no build-time code | `tests/test_packages_v1.py`, `tests/test_supply_chain_demo_v1.py` |
| T12 | The registry or a mirror serves a different package or lies about its surface | Archive SHA-256 and package digest checked against the index; surface recomputed and compared; safe extraction (no links, absolute or `..` paths, size limits); immutable versions | `tests/test_registry_v1.py`, `tests/test_registry_contents_v1.py` |
| T16 | A registry or stolen account swaps who signs a package, or rewrites its history | Ed25519 signatures by package owners; signer pinned in the lock (`--allow-new-signer` to change); hash-chained public log with the head pinned in the lock | `tests/test_registry_v1.py`, `tests/test_ed25519_v1.py` |
| T13 | Typosquatting | New names one edit from an existing one are held for maintainer review | `tests/test_registry_v1.py` |
| T14 | `ks build` is steered by the host's Go environment (`GOFLAGS=-toolexec`, proxies, toolchains) | Pinned Go environment for every build | `tests/test_go_build_env_v1.py` |
| T15 | Malformed input to the toolchain itself (source, locks, manifests, archives) crashes it or is half-accepted | Every outcome is success or a coded diagnostic; checked by mutation, structure-aware and differential fuzzers | `tools/fuzz/`, `tests/test_fuzz_smoke_v1.py` |
| T16b | A compromised worker (seccomp still on) asks the broker for authority the program never had: a writable scope in a read-only program, or an environment variable | The broker serves only the disk-read, disk-write and environment authority the compiler saw the program create; anything else ends the conversation. Disk prefixes, environment names, network origins, server binds and persistence files given as string literals are pinned too. Model-checked for every grant set | `formal/tla/BrokerConfinement.tla`, `tests/test_broker_grants_v1.py` |
| T16c | The registry hides a yank (index rolled back after the owner yanked a bad release) or invents one | The client reads yank state from the public log and refuses an index that disagrees | `formal/tla/RegistryLog.tla`, `tests/test_registry_v1.py` |
| T16d | A program duplicates authority by moving a token where the checker under-counts executions (a loop condition, a branch join) | The ownership rule is specified, and every accepted generated program is checked against a path-exhaustive oracle; a `while`-condition double move found this way is fixed | `docs/OWNERSHIP_MODEL_V1.md`, `tools/fuzz/affine_fuzz.py` |

## Residual risks

These are known and not closed by the code:

1. **`ks run` is not an OS sandbox.** Capability checks are language
   enforcement inside the CPython process. A bug in the interpreter or in
   CPython can bypass them. Running untrusted code under `ks run` needs OS
   confinement around the process (containers, seccomp). A native binary on
   linux/amd64 is confined by the broker's seccomp allow list instead; other
   targets refuse to run a binary that needs the broker (`KS4001`).
2. **No total memory budget.** Each value is bounded, but many values can
   still exhaust memory; `ks run` reports `KS3502` when the host runs out,
   a binary ends with Go's fatal out-of-memory error.
3. **Denial of service by CPU** is bounded by the step budget under `ks run`
   only; native binaries are not metered.
4. **Host trust.** CPython, the Go runtime, the OS and the hardware are
   trusted. There is no TPM/TEE/HSM root of trust.
5. **Release signing and protected branches** are owner actions not yet
   evidenced (`KOSCHEI_ACQUISITION_READINESS_V1.md`).
6. **No independent audit yet.** This model and the tests are the
   maintainers' own evidence. `docs/AUDIT_SCOPE_V1.md` is the brief for an
   external reviewer.
7. **Registry publisher identity.** Signatures bind versions to owner keys,
   but a first install trusts whichever owner the index names, there is no
   independent log witness, and a stolen publisher key can sign until the
   owners change. Ed25519 is a dependency-free implementation of RFC 8032
   (`koschei/ed25519_v1.py`) checked against OpenSSL; its signing path is not
   constant-time.

## Reporting

See `SECURITY.md`: report privately through GitHub Security Advisories.
