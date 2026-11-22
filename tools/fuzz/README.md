# Fuzzers

Each script takes a seed and a count, is deterministic for a given seed, and
exits non-zero when it finds something.

| Script | What it attacks | Allowed outcomes |
|---|---|---|
| `source_fuzz.py SEED N [check\|run]` | lexer, parser, checker, lowering and the interpreter, with mutated copies of the repository's `.ks` programs | success, or a `KSxxxx` diagnostic; never an internal error, a Python traceback or a 20 s hang |
| `native_diff_fuzz.py SEED N` | `ks run` against the native `ks build` binary on mutated programs that pass `ks check` | identical stdout and exit status, or a `KS40xx` refusal by `ks build` |
| `package_bytes_fuzz.py SEED N` | package archives, `koschei.packages.lock.json`, `koschei.toml` and registry index JSON, mutated byte by byte | `PackageError` / `ModuleError` only |
| `package_format_fuzz.py SEED N` | the lock and index formats with fields replaced by values of the wrong type | `PackageError` only |

`tests/test_fuzz_smoke_v1.py` runs a small batch of each on every pull
request; `.github/workflows/fuzz.yml` runs larger batches every night and on
demand.
