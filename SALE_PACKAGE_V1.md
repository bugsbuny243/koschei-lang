# Koschei Lang — Sale Package v1

For an organisation evaluating a Team or Enterprise license, or anyone given
access to this repository. Every claim below points to something you can run
or read in this repository; nothing here is a valuation, legal advice or a
promise beyond the repository's own evidence. Koschei Lang is sold as
commercial licenses, not as a transfer of the project; see `LICENSING.md`.

## What Koschei is

A capability-secure programming language with its own syntax, checker,
standard library and two execution paths:

- `ks run`: checks a program completely, then runs it on sealed MIR under
  step, call-depth and value budgets;
- `ks build`: compiles the same program to a native binary (through Go) that
  prints the same bytes and the same Error values.

Programs have no ambient authority. Disk, network, environment, program
input, clock and randomness are capability tokens that `main` narrows and
hands out; code that was not handed a token cannot reach the resource, and
`ks caps` lists exactly what a program can reach.

## Verify it in ten minutes

```sh
./install.sh                                    # Python 3.12+; or: pip install .
ks run examples/hello.ks
printf 'the cat saw the dog\n' | ks run examples/apps/wordfreq/main.ks
ks caps examples/apps/release_gate/main.ks      # what this program may touch
ks build examples/apps/keygen/main.ks -o keygen && ./keygen 2   # needs Go 1.24+
python3 -m pytest -q tests                      # the full suite
```

## What is included

| Area | Where | Evidence |
|---|---|---|
| Language guide, English and Turkish, every example executed | `docs/guide/` | `tests/test_language_guide_v1.py` |
| Error-code catalog (all diagnostics, both languages) and Core Library reference, generated | `docs/reference/` | `tests/test_reference_docs_v1.py` |
| Three complete applications | `examples/apps/` | `tests/test_example_apps_v1.py` |
| Core Library written in Koschei (`text`, `list`, `secure`, admission modules) | `koschei/core_library/` | `tests/test_core_library_v1.py`, `tests/test_morag_xandar_v1.py` |
| Interpreter / native parity | `koschei/mir_go_native.py` | `tests/test_mir_go_native_v2_parity.py` and every `*_v1` test that builds binaries |
| Threat model with evidence per threat | `docs/THREAT_MODEL_V1.md` | tests named in the table |
| Stability policy (proposed for 1.0) | `docs/STABILITY_V1.md` | — |
| Measured performance against Python, Go and Rust | `docs/benchmarks/` | `bench/compare/run_v1.py` |
| Product readiness gates and their status | `KOSCHEI_SATISA_HAZIRLIK_V1.md` | — |
| Due-diligence checklist | `KOSCHEI_ACQUISITION_READINESS_V1.md` | — |
| Release tooling: module lock, build manifest, SBOM, deterministic packaging | `tools/`, `docs/MODULE_LOCK.md`, `docs/REPRODUCIBLE_BUILDS.md` | `verify.sh`, `tools/acquisition_sbom_v1.py` |

Size: about 100,000 lines of Python in `koschei/` (457 modules), about
62,000 lines of tests in 484 files, and the Koschei-written Core Library.
The compiler core has no runtime Python dependency; native binaries use only
the Go standard library.

## Honest status

What works today is listed in the guide. What does not:

| Limitation | Plan |
|---|---|
| `ks run` is slow: one to three orders of magnitude behind native code on compute-heavy work (see benchmarks) | performance was not a goal so far; the native binary is the fast path |
| Native binaries reach the disk, the environment, the network (`GET`) and the loopback server through a confined broker on linux/amd64 only; the worker runs under a seccomp allow list; binaries still refuse processes (`KS4004`); `post`/`put` are not implemented anywhere; other platforms refuse broker programs (`KS4001`) | process authority and other platforms are not scheduled |
| `ks run` is language enforcement inside CPython, not an OS sandbox | see residual risks in the threat model |
| Runtime messages are Turkish; codes and English diagnostics exist | messages are marked experimental in the stability policy |
| No independent security audit | needs an external party |

## Licensing

Koschei Lang is under the Koschei Lang License 1.0 (`LICENSE`, Turkish
`LICENSE.tr.md`):

- personal, non-commercial use is free;
- commercial use needs a one-time, perpetual license that covers every
  version released within 12 months of purchase: Individual 49 USD, Team (up
  to 10 developers) 249 USD, Enterprise 999 USD (`LICENSING.md`);
- programs written in Koschei, and binaries built from them, belong to their
  authors and may be shipped without royalties;
- revisions released earlier under the MIT License stay under it
  (`KOSCHEI_LICENSE_LINEAGE_V1.md`).

Licenses and the download (`tools/polar_bundle_v1.py`) are sold on Polar.
What the owner still has to do (the Polar store, release signing, an
ownership statement) is listed in `KOSCHEI_SAHIP_EYLEM_LISTESI_V1.md`.
