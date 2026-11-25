# Koschei Lang — brief for an independent security review

Status: **ready to hand to a reviewer** (readiness gate 7 for 1.0.0,
`docs/RELEASE_PLAN_AFTER_0_14.md`). Version under review: the latest tagged
release (0.19.0 at the time of writing). The threat model this review tests
is `docs/THREAT_MODEL_V1.md`.

## What Koschei claims

Each claim below is something we want you to try to break. A break of any of
them is a critical finding.

1. **No ambient authority.** Code can touch the disk, network, environment,
   processes, stdin, clock or randomness only through a capability token that
   flowed to it from `main(caps: SystemCaps)`. There is no global I/O.
2. **Tokens cannot be forged, duplicated, hidden or widened.** Narrowing only
   shrinks a token; tokens cannot be stored in collections, compared or
   printed as anything but their type; affine tokens are used at most once.
3. **No code from a package runs while it is fetched or compiled.** No build
   scripts, macros, install hooks or compile-time evaluation.
4. **A package cannot gain authority silently.** Its capability surface is
   computed from source and locked; an update that widens it is refused unless
   the application author passes `--allow`; `[policy] deny` refuses outright;
   a vendored package changed after locking does not compile.
5. **The registry is untrusted.** A client accepts a registry package only if
   the archive and package digests match the index, the surface it computes
   equals the listed one, an owner's signature verifies (the signer is pinned
   after the first install), and the public log holds the entry and extends
   the history the project saw.
6. **Executors agree.** `ks run` and a native `ks build` binary give the same
   output for the same program and input, or `ks build` refuses (`KS40xx`).
7. **Malformed input is never half-accepted.** Every outcome of the toolchain
   on any source, lock, manifest or archive is success or a coded `KSxxxx`
   diagnostic, never an internal error.

## In scope

| Component | Files | Lines (approx.) | Claims |
|---|---|---|---|
| Lexer, parser | `koschei/lexer.py`, `koschei/parser.py` | 760 | 7 |
| Checker (types, capability flow, purity, affine use) | `koschei/semantic.py`, `koschei/_typed_ops.py`, `koschei/capabilities.py`, `koschei/affine_resources_v1.py`, `docs/OWNERSHIP_MODEL_V1.md` | 3,100 | 1, 2, 7 |
| Modules and imports | `koschei/modules.py` | 380 | 1, 4 |
| Sealed MIR and its executor | `koschei/mir.py`, `koschei/mir_canonical_lowering_v1.py`, `koschei/mir_executor_v1.py`, `docs/mir-v5.md` | 1,300 | 1, 6 |
| Interpreter host effects | `koschei/interpreter.py` | 2,200 | 1, 2 |
| Native code generation and runtime | `koschei/mir_go_native.py`, `koschei/mir_go_runtime_v2.py`, `koschei/mir_go_*_v1.py` | 4,500 | 6 |
| Native broker and seccomp worker | `native/`, `koschei/native_broker_v1.py`, `koschei/native_net_v1.py`, `koschei/native_serve_v1.py`, `koschei/native_persist_v1.py`, `docs/NATIVE_BROKER_V1.md`, `docs/NET_V1.md` | — | 1 |
| Formal models | `formal/tla/*.tla`, `formal/README.md`, `tests/test_formal_models_v1.py` | 300 | 1, 3, 5 |
| Packages and registry | `koschei/packages_v1.py`, `koschei/registry_v1.py`, `koschei/pkg_cli.py`, `docs/PACKAGES_V1.md` | 1,600 | 3, 4, 5, 7 |
| Ed25519 (dependency-free RFC 8032) | `koschei/ed25519_v1.py` | 190 | 5 |
| Native build environment | `koschei/go_build_env_v1.py` | 30 | 3 |

## Out of scope

- CPython, the Go toolchain and runtime, the OS kernel and hardware (trusted
  base; see the threat model's residual risks).
- `ks run` as an OS sandbox: it is language enforcement inside a CPython
  process, not process isolation.
- The commercial products in `commercial/` and `products/`, the website, and
  the `KOSCHEI_*` contract documents at the repository root.

## Getting started

```sh
git clone https://github.com/bugsbuny243/koschei-lang && cd koschei-lang
python3 -m pip install -e . pytest     # Python 3.12; Go 1.24 for ks build
python3 -m pytest -q tests             # the maintainers' own evidence
examples/supply_chain_demo/run.sh      # claims 3 and 4 side by side with Rust
```

Fuzzers (deterministic per seed, non-zero exit on a finding):

```sh
python3 tools/fuzz/source_fuzz.py 1 5000 check
python3 tools/fuzz/native_diff_fuzz.py 1 100
python3 tools/fuzz/package_bytes_fuzz.py 1 50000
python3 tools/fuzz/package_format_fuzz.py 1 50000
```

## Where we would attack first

- Capability flow through generics, closures, struct fields, `match` arms and
  module boundaries (claims 1, 2).
- Differences between the checker's view of a program and what the MIR
  executor or the Go runtime does with it (claims 1, 6).
- The broker protocol and the seccomp allow list on linux/amd64 (claim 1).
  The broker serves only the domains and the disk/environment authority the
  compiler saw the program use. Within a domain it pins disk prefixes,
  environment names, network origins, server binds and persistence files to the program's string literals.
  Where a program computes one at run time, that kind is not pinned and a
  compromised worker may open any prefix of it, as the program's `SystemCaps`
  could. Server bind addresses and persistence files are pinned the same way.
- The gap between the formal models and the code: the models are bounded
  and the link tests only check that each modelled check is still present.
- Package resolution: import shadowing, transitive dependencies, lock and
  manifest edits between `sync` and `build`, archive extraction (claims 3–5).
- The Ed25519 implementation: encodings, small-order points, malleability,
  and the signed message's canonical form (claim 5).
- Budgets: step, call depth and value size under `ks run`; native binaries are
  not metered (threat model residual risk 3).

## Evidence that already exists

| Kind | Where | What it shows |
|---|---|---|
| Unit and contract tests | `tests/` (≈ 3,000 tests) | each control in the threat model's table |
| Adversarial lab | `tools/run_adversarial_lab.py` | attack programs that must be refused |
| Differential tests | `tests/test_mir_go_native_v2_parity.py`, `tests/test_differential_fuzz.py` | executor agreement |
| Formal models (TLA+, TLC) | `formal/` | the package update rule, broker confinement and the registry log hold against an attacker that controls the registry or the worker; each check in the code is shown to be needed |
| Fuzzing | `tools/fuzz/`, `tests/test_fuzz_smoke_v1.py` | about 9,000 mutated programs (7,000 checked, 2,000 run) and 80,000 malformed package inputs with no internal errors after the two fixes below |

### Formal models and soundness fuzzing (2026-11-24)

Three findings, all fixed and released, with regression tests:

| Found by | Finding | Fixed in |
|---|---|---|
| `formal/tla/BrokerConfinement.tla` | The broker served disk-write and environment requests to any worker, so a compromised worker of a read-only or network-only program could write files or read secrets | 0.22.0 |
| `formal/tla/RegistryLog.tla` | Yank state came only from the index; a rolled-back index could serve a yanked release although the public log recorded the yank | 0.23.0 |
| `tools/fuzz/affine_fuzz.py` | A move in a `while` condition was checked once, so a token could be handed out on every iteration | 0.24.0 |

`formal/tla/PackageUpdate.tla` found nothing. `affine_fuzz.py` has since
judged 12,000 generated programs against its path-exhaustive oracle with no
unsound acceptance.

### Fuzzing results so far (2026-11-22)

| Fuzzer | Cases | Findings |
|---|---|---|
| `source_fuzz.py` (check) | 7,000 | none |
| `source_fuzz.py` (run) | 2,000 | none |
| `native_diff_fuzz.py` | 240 mutated programs, 44 passing check | none (26 identical, 18 refused by `ks build`) |
| `typed_program_fuzz.py` (check + run) | 1,260 generated well-typed programs | none |
| `typed_program_fuzz.py --native` | 350 generated programs, run against native binaries | none: identical output and exit status in all 350, including negative division and modulo, Unicode string lengths, `to_int` and integer overflow |
| `capability_fuzz.py` attacks | 700 misuse programs across 15 kinds, at random depth in random code | none: all refused with the expected code |
| `capability_fuzz.py` granted access | 160 programs (60 also native) passing a narrowed disk token through helpers | none: every `..`, absolute-path and symlink escape refused; native output identical |
| `package_bytes_fuzz.py` | 21,000 | none |
| `package_format_fuzz.py` | 60,000 | **2, fixed**: a lock whose `dependencies` held a list or object raised `TypeError`; lock fields of the wrong type were accepted, and a lock `entry` could point outside its package. Every lock field is now validated, and the lock's version and entry must match the vendored `koschei.toml`. |

Most mutated programs stop at the parser (`KS1002`), so `source_fuzz.py`
mainly exercises error paths; `typed_program_fuzz.py` covers the accepted
side. `capability_fuzz.py` covers capability misuse and disk confinement. Not
generated yet: generics, closures beyond the capture case, maps, multiple
modules, and capabilities other than the disk at run time (network, process,
serve), which is where a reviewer could add the most depth.

## What we ask for

A report with each finding's claim, severity, reproduction (a `.ks` program,
input files or a command line) and suggested fix. Report privately through
GitHub Security Advisories (`SECURITY.md`). We publish the report and our
fixes after they ship.
