# P0.1 — Proposed minimum host-import boundary (design, NOT implementation)

Candidate: PR #310. Sources checked: `koschei/stdlib_catalog.py`, `koschei/runtime_authority_surface_v1.py`, `tests/test_native_capability_codegen.py`, and compiled-symbol evidence in `docs/P0_THREE_FIXTURE_RUNTIME_EVIDENCE_2026_10_12.md`.

## Critical distinction: catalog status vs executable paths

The catalog calls `request.allow`, `disk.allow`, `disk.allow_read_only`, `disk.delete`, `env.allow`, and `process.allow` **supported**. However, `request.get`, `disk.read`, `disk.write`, `disk.list`, `env.get`, and `process.run` are **reserved**. Native regression tests execute several of these reserved methods to establish current behavior or denial; passing a test does not promote the catalog entry to supported. In particular, process execution remains fail-closed.

The historic statement that there are **32 supported stdlib operations** must be independently recalculated against the exact catalog revision before it is used as an acceptance count. Do not infer the import set from that number.

## Candidate host ABI (deny-by-default; no raw syscall import)

| Import (proposed) | Koschei authority | Required host-side checks | Status |
| --- | --- | --- | --- |
| `host.stdout_write` | Explicit output budget | Maximum bytes, capability-value redaction | **NOT READY**: catalog reserves `print`/`println` |
| `host.env_get_named` | `EnvRoot.allow(name) -> EnvCaps.get()` | Exact allowlisted key, maximum returned value bytes | **NOT READY**: `env.get` reserved |
| `host.disk_open_scoped` | `DiskRoot.allow(path)` / read-only | Handle-based root, read/write mode, symlink denial, race-safe path resolution | **NOT READY** for read/write |
| `host.disk_delete_scoped` | `DiskCaps.delete` | Scoped descriptor, no symlink traversal, mutation permission | Candidate for supported `delete` |
| `host.net_http_get_scoped` | `NetRoot.allow(origin) -> NetCaps.get(url)` | Exact origin, redirect confinement, deadlines, response bytes, DNS/IP rebinding policy | **NOT READY**: `get` reserved |
| `host.process_spawn` | `ProcessCaps.run/spawn` | Explicit executable, child/cpu/memory/output budgets | **DO NOT IMPORT**: runtime fail-closed |

Pure computation, collections, text transforms, and result constructors need **zero authority-bearing host imports**. For the first WASM/WASI prototype, prefer a pure `.ks` fixture and zero ambient filesystem/network/process/environment imports; stdout must be explicitly granted if output is required. WASI runtime defaults must not accidentally grant preopened directories, inherited environment, network, or process execution.

### Measurable gates before calling this enforcement

1. Generate a canonical operation list from `CATALOG` at the candidate commit, separating supported/reserved/planned, capability name and enforced budgets.
2. Build one pure `.ks` fixture with the existing Go backend and experimental WASM backend; compare deterministic output and errors.
3. Assert pure WASM import inventory contains no disk/network/process/env imports; fail build on any unexpected import.
4. Attempt denied disk/network/process effects in isolated tests, verifying **no host-side effect**, not merely a returned error.
5. Measure effect-reachable host operations, not only linked symbol counts, for each capability class.
6. Retain Go backend; do not label WASI inherently sandboxed or production ready.

## Threat contract

- **PROTECTS AGAINST:** Nothing yet; proposed ABI only.
- **DOES NOT PROTECT:** Host runtime compromise, broad WASI preopens, OS escape, side channels, compromised toolchain, and bypasses through alternate imports.
- **ASSUMPTIONS:** A trusted host mediates all imports and does not expose raw ambient interfaces; capability handles cannot be forged.
- **FAILURE MODE:** An unguarded import, inherited WASI authority, or forged handle defeats intended confinement.

**P0.1 / B design stage.** Compiler: unchanged. Runtime: unchanged. No syntax change, no new `koschei/*.py` modules, no measured blast-radius improvement. NEXT: executable import manifest and WASM parity prototype.
