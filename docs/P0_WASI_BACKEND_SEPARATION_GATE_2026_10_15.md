# P0.1 WASI backend separation gate — 2026-10-15

Status: **DESIGN / NOT IMPLEMENTED**. Native Go is the existing implementation. The current experimental Go-to-WASI compilation of `examples/hello.ks` is blocked by Linux-specific generated runtime code; CI's import-inventory integration test explicitly **skips** on the recognized compiler blockers. A green workflow does not constitute a WASM artifact or isolation receipt.

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
