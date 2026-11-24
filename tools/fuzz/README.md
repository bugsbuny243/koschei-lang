# Fuzzers

Each script takes a seed and a count, is deterministic for a given seed, and
exits non-zero when it finds something.

| Script | What it attacks | Allowed outcomes |
|---|---|---|
| `source_fuzz.py SEED N [check\|run]` | lexer, parser, checker, lowering and the interpreter, with mutated copies of the repository's `.ks` programs | success, or a `KSxxxx` diagnostic; never an internal error, a Python traceback or a 20 s hang |
| `typed_program_fuzz.py SEED N [--native]` | generated well-typed programs (struct, enum with payloads, `match`, functions, loops, lists, Unicode strings, `to_int`, integer overflow) through check, run and optionally a native binary | accepted by `ks check`; `ks run` without internal errors; identical output and exit status from the native binary or a `KS40xx` refusal |
| `capability_fuzz.py SEED N [--native]` | 15 kinds of capability misuse (ambient I/O, roots, widening, read-only writes, tokens in List/Map, comparison, double use, wrong kind, closure capture, `caps` in a helper, `SystemCaps` to a helper), each at a random depth inside random code and helper chains; plus granted disk access passed through helpers with `..`, absolute-path and symlink escape attempts | every attack refused by `ks check` with its expected code; every escape refused at run time; identical output from the native binary |
| `affine_fuzz.py SEED N` | the affine ownership checker: programs that move, rebind, wrap and borrow tokens in nested `if`/`else if`/`while`/`for`, loop and branch conditions, `break`/`continue`/`return`, judged against a path-exhaustive ownership oracle (`docs/OWNERSHIP_MODEL_V1.md`) | the checker never accepts a program in which some path uses a moved token; never crashes |
| `native_diff_fuzz.py SEED N` | `ks run` against the native `ks build` binary on mutated programs that pass `ks check` | identical stdout and exit status, or a `KS40xx` refusal by `ks build` |
| `package_bytes_fuzz.py SEED N` | package archives, `koschei.packages.lock.json`, `koschei.toml` and registry index JSON, mutated byte by byte | `PackageError` / `ModuleError` only |
| `package_format_fuzz.py SEED N` | the lock and index formats with fields replaced by values of the wrong type | `PackageError` only |

`tests/test_fuzz_smoke_v1.py` runs a small batch of each on every pull
request; `.github/workflows/fuzz.yml` runs larger batches every night and on
demand.
