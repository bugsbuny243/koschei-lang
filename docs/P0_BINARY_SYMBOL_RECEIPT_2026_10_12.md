# P0.1 — First compiled-binary host-symbol receipt

Evidence: GitHub Actions run **38224572876**, validation artifact **11736590940**, file `koschei-validation-evidence/p0-host-binary-symbols.stdout.log`. Candidate PR #310, commit `33127d4c531c1355f72e1be1997d76b18828bb13`.

- Fixture: `examples/hello.ks` (pure).
- Environment: `go version go1.24.13 linux/amd64`.
- Test result: `1 passed in 0.84s`.
- Method: `go tool nm` on a compiled executable; selected exact symbol/prefix matching. Not an ELF syscall audit, call graph, or proof of invocation.

## Present (6 / 13)

`syscall.Close`, `syscall.Socket`, `syscall.Bind`, `syscall.Listen`, `os.NewFile`, `os.LookupEnv`.

## Absent (7 / 13)

`syscall.Openat`, `syscall.Renameat`, `syscall.Unlinkat`, `os.Remove`, `io.ReadAll`, `net.Dial`, `net/http.NewRequest`.

**Interpretation:** A pure program retains some OS/network/environment-related symbols in its executable. Presence is not proof that Koschei user code can invoke them; absence of a symbol is not proof that equivalent effects are impossible through other symbols or raw syscalls. These 13 watched names are a subset of the broader v25 baseline; no claim is made that all 56 have been classified.

## §12

- **PROTECTS AGAINST:** No new attack class; this is evidence gathering only.
- **DOES NOT PROTECT:** Runtime compromise, bypass through other OS interfaces, broad host authority, build compromise or side channels.
- **ASSUMPTIONS:** The CI artifact is authentic for the identified run/commit, Go symbol naming is consistent for this build, and the fixture reflects a pure program.
- **FAILURE MODE:** Compiler/linker changes alter symbols without changing reachable effects, or unexamined call paths expose ambient authority.

**Gate:** P0.1 / B preparatory only; no syntax change; no new runtime enforcement; no reduction in blast radius measured. **Acceptance remains OPEN** until capability-to-host call paths, denied runtime paths, and a complete compiled-artifact host import baseline are demonstrated. No new `koschei/*.py` module.

**NEXT:** Compare a capability-bearing fixture against this pure fixture using the same Go version and symbol extraction; measure differences and perform negative runtime effect tests.
