# Koschei Production Reference v1

This is an acceptance workload for the language and toolchain, not a marketing demo and not a claim that Koschei is already production-ready.

The committed workspace exercises a realistic financial order-processing path across fourteen independently owned realms:

- `order_core` — order validity and exact integer notional calculation.
- `market_rules` — crossing and execution rules.
- `risk_engine` — notional and quantity limits.
- `fee_engine` — deterministic basis-point fees using integer division.
- `matching_engine` — risk-gated trade formation.
- `ledger_engine` — cash/asset deltas and conservation invariant.
- `settlement_engine` — buyer/seller settlement and fees.
- `report_engine` — deterministic engineering output.
- `market_feed` — explicit outbound network-capability boundary.
- `json_gateway` — bounded JSON parse/canonical-encode boundary.
- `dispatch_runtime` — structured deterministic parallel dispatch returning `List<Int>`.
- `order_worker` — deterministic orchestration root with no ambient authority.
- `state_store` — exact-object persistence boundary that accepts only a caller-supplied `PersistCaps` token.
- `http_ingress` — bounded loopback HTTP composition boundary that owns Serve + Persist authority while calling the authority-free order worker.

The current workspace-v1 loader still requires `koschei.toml`; that filename and its manifest vocabulary are compatibility debt under the Koschei Originality Contract. The reference deliberately avoids the conventional `src/main.ks` scaffold and uses `matter.ks` inside realm roots. When Native Reality becomes the default project loader this reference must migrate without changing its semantic acceptance contract.

The legacy `[capabilities]` table in each `koschei.toml` is not the semantic source of Serve or Persist authority. Those authorities are explicit in Koschei source and in capability-analysis evidence. The table mismatch is compatibility debt to remove when the project/authority manifest is redesigned; the reference does not invent ignored `serve = ...` or `persist = ...` fields to make the manifest look newer than the loader really is.

## Acceptance contract

The test suite requires all of the following:

1. The committed fourteen-realm workspace checks as one dependency graph.
2. Core matching/risk/ledger/worker/JSON/dispatch graphs request no disk/network/env/process/serve/persist capability.
3. The external `market_feed` boundary reports exactly outbound network authority.
4. `state_store` reports exactly Persist authority when analyzed as a package requirement, while it has no ambient filesystem path authority of its own.
5. `http_ingress` reports exactly Serve + Persist authority while its imported `order_worker` graph remains authority-free.
6. A deterministic order-processing scenario runs only after a verified workspace lock.
7. Source drift after lock creation fails before program output or persistent-state mutation.
8. Interpreter output and native binary output remain byte-for-byte identical for the deterministic authority-free worker when Go is available.
9. JSON parse/canonical encode and structured `parallel_map` are exercised on the root worker execution path.
10. A generated 32-realm / 64-function transitive workspace checks and runs successfully.
11. The same 32-realm graph executes through the AST-free direct-MIR executor.
12. The same 32-realm graph builds and executes as a native binary when Go is available.
13. The complete 11-module `order_worker` dependency graph executes through direct MIR and preserves deterministic worker output.
14. A locked `http_ingress` workspace accepts a real loopback TCP POST, canonicalizes the JSON body, invokes the production order worker, atomically persists the resulting state through an exact-object token, reloads it, and returns a bounded HTTP response.
15. The persisted state file must contain the exact expected canonical state and be created with mode `0600` on the tested POSIX path.
16. On Linux with Go available, the locked native `http_ingress` artifact must perform the same real TCP -> JSON -> order core -> exact-object commit -> reload path and match the interpreter's stdout, response wire, persisted bytes, file mode and workspace digest.
17. Non-Linux native persistence remains fail-closed with `KS4001` until a backend with equivalent descriptor and durability semantics exists.

## Manual deterministic-worker commands

Run these from the repository root:

```text
ks workspace check examples/production_reference_v1
ks workspace caps examples/production_reference_v1
ks workspace lock create examples/production_reference_v1
ks workspace run order_worker examples/production_reference_v1
ks workspace build order_worker examples/production_reference_v1 -o /tmp/koschei-order-worker
```

The `http_ingress` realm is intentionally not listed as a casual manual-run command. Its committed bootstrap configuration binds `127.0.0.1:18080` and points at an example exact persistence object. Dedicated tests copy the workspace, allocate a temporary free loopback port and a temporary exact state path, rewrite both literals **before lock creation**, and then execute the locked graph.

The lock command writes a control artifact into the workspace. Do not commit a locally generated lock unless the release process explicitly requires it.

## Authority topology

`order_worker` is intentionally capability-free. It imports matching, settlement, report, JSON and dispatch realms without receiving Serve, Persist or outbound network authority.

`state_store` does not choose a path. Its public functions accept a `PersistCaps` parameter that is already sealed to one exact state object. The caller cannot use `state_store` to turn that token into general `DiskCaps` authority or choose a sibling path at operation time.

`http_ingress` is the composition boundary. It narrows `SystemCaps.serve` to one loopback endpoint and `SystemCaps.persist` to one exact file, then passes only the narrow persistence token into `state_store`. This creates one-way authority flow: the ingress boundary can call pure/core processing and a narrowly authorized state writer, but the core does not inherit either capability merely because the boundary depends on it.

`market_feed` remains a separate outbound-network boundary and is not a dependency of `order_worker` or `http_ingress` in v1.

## Persistence truth

Persistence v1 is not a database and not a transaction manager. Interpreter and Linux native-Go implementations use the same high-level commit protocol: same-directory temporary object, full-write loop, file `fsync`, descriptor-relative atomic replacement and parent-directory `fsync`. A pre-replace failure leaves the prior canonical object unchanged. A failure after replacement but before durability confirmation is reported separately as `KS3423` because pretending that state rolled back would make blind retry unsafe.

Both implementations anchor the exact parent directory and do not let `load` or `commit` choose another path. Linux native target-shape probing uses a metadata-only `O_PATH | O_NOFOLLOW` descriptor, and the actual load open is non-blocking until `fstat` confirms a regular file. This prevents type probing or a file-to-FIFO race from silently becoming an ambient blocking channel.

The byte budget is hard-enforced in both implementations. The current deadline is still only a cooperative monotonic sequence deadline checked around filesystem syscalls; neither backend claims safe preemption of an indefinitely blocked kernel filesystem call. Hosted parity tests also have not executed while GitHub runner allocation remains billing-blocked. Therefore the stdlib `persist` operations remain **reserved**, not supported, despite interpreter + Linux native implementation source existing.

Concurrent authorized writers do not receive compare-and-swap, transaction isolation or lost-update prevention in v1. Atomic replacement prevents a torn canonical file; it does not decide which of two valid competing commits should win.

## What this proves — and what it does not

If the acceptance gates execute and pass, they prove that the current compiler/runtime can carry a non-trivial multi-package program, preserve explicit authority boundaries, lock source identity, execute deterministic core work, and drive that core through a bounded loopback ingress into a narrowly scoped atomic persistence boundary on the tested interpreter and Linux native paths.

The existence of source/tests alone does **not** establish that proof while CI has not run. It also does not make `ServeCaps.exchange` a production HTTP framework or `PersistCaps` a transactional database. Public ingress, TLS, routing, long-running handlers, true syscall-preemptive I/O deadlines, non-Linux persistence parity, concurrent-write coordination/CAS, database adapters, observability, package distribution, profiling and larger graph/compile stress remain separate gates.

The point of this reference is to turn those long-term requirements into executable work: future revisions must grow this same system and fix compiler/runtime/stdlib gaps exposed by the workload instead of shrinking the workload to preserve a claim.
