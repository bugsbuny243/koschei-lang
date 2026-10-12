# P0.1 — Three-fixture compiled-symbol and runtime-denial evidence

Evidence: GitHub Actions [run 38231417562](https://github.com/bugsbuny243/koschei-lang/actions/runs/38231417562), artifact `11739235926`, candidate `22c8ffbfa50d70cdf18b0747bdb1f4d33f87f342`. Toolchain `go version go1.24.13 linux/amd64`.

## Compiled Go symbol observations

Method: compile each fixture and inspect `go tool nm`; count presence among **13 preselected names**. This is neither the full v25 56-symbol inventory nor an OS syscall trace.

| Fixture | Watched present | Added relative to hello | Removed relative to hello |
| --- | ---: | --- | --- |
| `examples/hello.ks` | 6/13 | — | — |
| `examples/runtime_demo.ks` | 9/13 | `io.ReadAll`, `os.Remove`, `syscall.Renameat` | none |
| `examples/capability.ks` | 9/13 | `io.ReadAll`, `os.Remove`, `syscall.Renameat` | none |

All three retain `syscall.Close`, `syscall.Socket`, `syscall.Bind`, `syscall.Listen`, `os.NewFile`, `os.LookupEnv`. The three added names are **present in both** the environment and network fixtures, despite their different language-level authority. This indicates the 13-name binary signature does not distinguish those authority types. It does **not** establish that the added functions can be invoked from either program.

Observed absent from all three watched subsets: `syscall.Openat`, `syscall.Unlinkat`, `net.Dial`, `net/http.NewRequest`. Absence of these symbol names is not proof of absence of equivalent behavior.

## Runtime denial evidence

The CI step ran `python -m pytest -q -s tests/test_native_capability_codegen.py` and reported **8 passed in 3.60s**. Existing tests include native read-only write denial, network origin and redirect denial, file-scheme denial, and process fail-closed behavior. Separately, the binary comparison tests reported **2 passed in 1.57s**. Both step outputs were retained as:
- `koschei-validation-evidence/p0-host-binary-symbols.stdout.log`
- `koschei-validation-evidence/p0-native-capability-denial.stdout.log`

The canonical full validation receipt also reported `passed: true`. These facts are **test evidence**, not an isolation guarantee.

## Security contract

- **PROTECTS AGAINST:** Existing capability checks have passing native denial regression tests; this audit adds no new protection.
- **DOES NOT PROTECT:** Compromised Go runtime, direct host syscall access, other unexamined symbols, host compromise, or malicious native dependencies.
- **ASSUMPTIONS:** GitHub Actions artifact is authentic for the named candidate; Go toolchain and fixture content are as recorded; `go tool nm` reports linked symbols faithfully.
- **FAILURE MODE:** Go linker changes or compiler paths hide or retain symbols independently of reachable effects; a bypass outside the tested paths remains possible.

**P0.1 status: OPEN.** P-level P0.1, preparatory for B (limit blast radius). No compiler or runtime enforcement changes, no new `koschei/*.py` modules, no measured blast-radius reduction. Next: full host-call reachability map, explicit per-capability minimal imports, and isolation prototype/parity test; do not equate symbol reduction with access denial.
