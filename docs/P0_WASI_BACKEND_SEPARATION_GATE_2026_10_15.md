# P0.1 WASI backend separation gate — 2026-10-15

Status: **PURE PROGRAMS: MEASURED (see 2026-11-16 update at the end). AUTHORITY DOMAINS: NOT IMPLEMENTED.** The paragraph below describes the 2026-10-15 state and is kept as history.

Status on 2026-10-15: **DESIGN / NOT IMPLEMENTED**. Native Go is the existing implementation. The current experimental Go-to-WASI compilation of `examples/hello.ks` is blocked by Linux-specific generated runtime code; CI's import-inventory integration test explicitly **skips** on the recognized compiler blockers. A green workflow does not constitute a WASM artifact or isolation receipt.

## PROTECTS AGAINST

The proposed backend separation prevents a future WASI target from silently inheriting the native Linux capability implementation. A pure-program WASI target must have an explicit host import allowlist and must fail closed if it requests an unreviewed import.

## DOES NOT PROTECT

This design alone does not enforce runtime capabilities, prevent a malicious host from granting preopened directories, guarantee absence of data exfiltration, establish process isolation, or reduce measured blast radius. The current import parser and allowlist are tests, not a host sandbox.

## ASSUMPTIONS

- Native Go output remains unchanged unless separately reviewed and tested.
- `examples/hello.ks` is the first pure fixture; more fixtures are required before claiming language coverage.
- A WASI runner and its preopens/environment/arguments are part of the security boundary; inspect configuration as well as module imports.
- Existing `ksNewDiskCapability` deliberately fails closed outside Linux; do not replace Linux `openat/O_NOFOLLOW` with a weaker pathname fallback.
- `ksNetGet` uses Go HTTP facilities; network authority must not be implicitly exposed by a WASI host.

## FAILURE MODE

- Unexpected WASI import: reject the artifact, print module/member, fail CI.
- Go/WASI compilation fails: mark target unsupported; **never** report successful import auditing of a nonexistent module.
- Missing host runner or parity mismatch: leave P0.1 open.
- A backend silently emits host access without capability review: block promotion to supported target.

## Implementation gates

1. **Separate code paths:** isolate native-only disk/network/process implementations from pure language runtime; do not remove native security checks. The generated Go runtime currently references platform-specific syscall constants/functions even for pure fixtures.
2. **Compile actual fixture:** compile `examples/hello.ks` into `main.wasm` using `GOOS=wasip1 GOARCH=wasm CGO_ENABLED=0`; remove the skip only when compilation succeeds.
3. **Inspect binary:** parse its actual import section and assert exact module/function policy; separately record Go startup imports (`args_*`, `environ_*`) as residual authority, not as a sandbox guarantee.
4. **Run parity:** execute the exact `.ks` fixture through native Go and an explicitly configured WASI runner; compare exit code, stdout and stderr with normalized nondeterministic data only when justified.
5. **Deny host authority:** test no preopened directories, no inherited secrets in environment/arguments, no network host functions, and a negative fixture requesting disk/network/process capability. Reject unsupported operations explicitly.
6. **Measure:** collect artifact import inventory, runner configuration, reachable host calls, and per-attack-class isolation evidence before making a blast-radius claim.

## Current evidence

- `tests/test_p0_wasi_import_inventory.py`: parser and policy unit tests execute, but cross-compiled fixture remains skipped for recognized portability blockers.
- `koschei/codegen_go.py`: `CAPABILITY_RUNTIME` contains Linux-specific disk implementation; `ksNewDiskCapability` rejects non-Linux at runtime but the Go compiler still type-checks unsupported platform symbols.
- PR #310, CI #38702388307: successful workflow for commit `05b0530`; **not** a WASI compilation success.

Acceptance: P0.1 cannot be closed until an actual WASM artifact, import receipt, parity execution, negative host-denial tests and measured isolation evidence exist.

## Update — 2026-11-16: pure programs through the public MIR-Go projection

The evidence above measured the legacy AST-Go generator (`koschei.codegen_go.generate_go`), which public `ks build` no longer uses for output: it uses the sealed-MIR projection `koschei.mir_go_native` and fails closed with KS4004 otherwise. The WASI evidence now measures that projection.

Changes:

- `koschei.mir_go_native.generate_go_mir_wasi_pure(mir)`: returns the same Go source as `generate_go_mir_native` and refuses (`MirGoUnsupported`) any program that uses an authority domain (input, clock, random, disk, env, net, serve).
- `koschei.codegen_go.generate_go_wasi_pure` removed. It was a second, AST-level emitter covering only `main`, immutable `let`, `println` and `+ - *`; it bypassed sealed MIR.
- `tests/test_p0_wasi_pure_backend.py` and the integration case in `tests/test_p0_wasi_import_inventory.py` now compile the MIR-Go projection. The `P0_WASI_COMPILE_BLOCKED` skip is gone: a failed cross-compile fails the test.

Measured with go1.24.7 linux/amd64, `GOOS=wasip1 GOARCH=wasm CGO_ENABLED=0`, Wasmtime (Python package), no preopens, no guest environment, argv of one entry:

- `P0_WASI_PARITY fixtures=9 passed=9` — `app, control_flow, hello, holders, maps, mir_cfg_project, resource_contracts, runtime_budget, v08_types`; stdout, stderr and exit code equal the host binary built from the same source.
- `P0_WASI_IMPORTS` — exactly 15, all `wasi_snapshot_preview1`: `args_get, args_sizes_get, clock_time_get, environ_get, environ_sizes_get, fd_close, fd_fdstat_get, fd_fdstat_set_flags, fd_prestat_dir_name, fd_prestat_get, fd_write, poll_oneoff, proc_exit, random_get, sched_yield`. No `path_*`, no `sock_*`, no `fd_read`. The test fails on any import outside this set.
- Module size: 2.53–2.64 MB raw, 732–759 KB gzip.
- Full suite on this change: 3136 passed, 0 failed, 0 skipped (six `tests/test_strange_*` files were not collected on the measuring host because its Python lacks `fcntl.F_SEAL_WRITE`; unrelated to this change).

### PROTECTS AGAINST

A pure program's WASI module cannot name a filesystem path or a socket: those host functions are not in its import section, so no instruction in the module can call them. A program that uses an authority domain cannot be emitted for this target at all.

### DOES NOT PROTECT

A compromised or misconfigured host (Wasmtime, or a runner that grants preopens or a populated environment). The Go runtime's own startup imports remain: `environ_get`, `environ_sizes_get`, `fd_prestat_get`, `fd_prestat_dir_name`, `args_get`, `random_get`, `clock_time_get`, `poll_oneoff`. Side channels. The compiler and build chain (P0.3).

### ASSUMPTIONS

The runner supplies no preopened directory and no secrets in environment or argv. The import section parsed by the test is the one the host links. Go 1.24's `wasip1` runtime import set; a toolchain upgrade that adds an import fails the test until reviewed.

### FAILURE MODE

A host that preopens a directory or passes environment variables turns the residual startup imports into real authority. Authority-domain programs still have no WASI target; nothing here narrows their native surface.

### Still open

Implementation gates 5 and 6 for authority domains (a reviewed host import set per domain), a public `ks build` target flag for WASI, and `tests/test_p0_host_binary_symbols.py`, which still measures the legacy generator.
