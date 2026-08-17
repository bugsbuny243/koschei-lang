# Canonical Native Entrypoints v1

Parent milestone: #240. Inventory slice: #241.

Koschei now has an explicit canonical native API boundary for `check` and `run`:

`authenticated ObjectSpaceProject -> Native IR -> sealed native authority`

The boundary intentionally accepts only an already authenticated `ObjectSpaceProject`. It does not accept a filename, source path, source bytes, parser result, `Program`, `ModuleGraph`, or compatibility MIR as dispatch authority.

## Check

`check_canonical_native_v1(project)` authenticates the Object Space frontend identity through the existing native dispatcher and lowers the admitted reality to `NativeIrRealityV1`. It does not execute the reality and cannot fall back to compatibility checking.

## Run

`run_canonical_native_v1(project)` executes only through `execute_authenticated_object_space_native_ir_v1()`. Unsupported Object Space schemas fail closed. Source appearance and filenames are non-authoritative.

## Deliberate boundary

This slice does not pretend that the public `ks run/check/build` CLI has migrated. Those commands still appear as `COMPAT_MIGRATION_ONLY` in `contracts/canonical-execution-dispatch-v1.json`.

The next migration problem is authority admission at the public tool boundary. `load_object_space_project()` requires an audited `ObjectSpaceCryptoProvider`, temporal key/handle, expected project identity, and epoch. Koschei intentionally does not ship a fake built-in encryption provider. Therefore the CLI must gain an explicit authority-provider contract before `ks run` or `ks check` can securely open canonical Object Space projects.

No source sniffing, filename heuristics, parser coincidence, plaintext downgrade, or silent legacy fallback may be introduced to make that migration convenient.
