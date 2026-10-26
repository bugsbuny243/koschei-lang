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
   randomness directly. The disk (read, write, delete), the environment and
   the network go through a broker process; the program runs in a
   seccomp-confined worker with an empty environment and no sockets
   (`docs/NATIVE_BROKER_V1.md`, `docs/NET_V1.md`). Processes, `persist` and
   `serve` are refused at build time (`KS4004`).

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

## Residual risks

These are known and not closed by the code:

1. **`ks run` is not an OS sandbox.** Capability checks are language
   enforcement inside the CPython process. A bug in the interpreter or in
   CPython can bypass them. Running untrusted code needs OS confinement
   around the process (containers, seccomp) until the native capability
   broker (readiness gate G2) exists.
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
   maintainers' own evidence.

## Reporting

See `SECURITY.md`: report privately through GitHub Security Advisories.
