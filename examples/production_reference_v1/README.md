# Koschei Production Reference v1

This is an acceptance workload for the language and toolchain, not a marketing demo and not a claim that Koschei is already production-ready.

The committed workspace exercises a realistic financial order-processing path across twelve independently owned realms:

- `order_core` — order validity and exact integer notional calculation.
- `market_rules` — crossing and execution rules.
- `risk_engine` — notional and quantity limits.
- `fee_engine` — deterministic basis-point fees using integer division.
- `matching_engine` — risk-gated trade formation.
- `ledger_engine` — cash/asset deltas and conservation invariant.
- `settlement_engine` — buyer/seller settlement and fees.
- `report_engine` — deterministic engineering output.
- `market_feed` — explicit network-capability boundary.
- `json_gateway` — parse + canonical JSON boundary with deterministic encoding.
- `dispatch_runtime` — structured parallel work that returns `List<Int>` across a package boundary.
- `order_worker` — runnable/buildable orchestration root with no ambient authority.

The current workspace-v1 loader still requires `koschei.toml`; that filename and its manifest vocabulary are compatibility debt under the Koschei Originality Contract. The reference deliberately avoids the conventional `src/main.ks` scaffold and uses `matter.ks` inside realm roots. When Native Reality becomes the default project loader this reference must migrate without changing its semantic acceptance contract.

## Acceptance contract

The test suite requires all of the following:

1. The committed twelve-realm workspace checks as one dependency graph with at least 40 real Koschei declarations.
2. Core matching/risk/ledger/worker, JSON, and dispatch graphs request no disk/network/env/process capability.
3. The external `market_feed` boundary reports exactly network authority.
4. A deterministic order-processing scenario runs only after a verified workspace lock.
5. JSON is parsed and canonically re-encoded on the root execution path.
6. Structured `parallel_map` work executes in another realm, returns a generic `List<Int>` across the workspace boundary, and is consumed by the root worker.
7. Source drift after lock creation fails before program output.
8. Interpreter output and native binary output are byte-for-byte identical when Go is available.
9. A generated 32-realm / 64-function transitive workspace checks and runs successfully.
10. The same 32-realm graph builds and executes as a native binary when Go is available.

## Manual commands

Run these from the repository root:

```text
ks workspace check examples/production_reference_v1
ks workspace caps examples/production_reference_v1
ks workspace lock create examples/production_reference_v1
ks workspace run order_worker examples/production_reference_v1
ks workspace build order_worker examples/production_reference_v1 -o /tmp/koschei-order-worker
```

The lock command writes a control artifact into the workspace. Do not commit a locally generated lock unless the release process explicitly requires it.

## What this proves — and what it does not

Passing this gate proves that the current compiler/runtime can carry a non-trivial multi-package program, preserve explicit authority boundaries, lock source identity, execute deterministic domain logic, move a typed generic collection across a package boundary, exercise structured parallel work, canonicalize JSON, and preserve interpreter/native parity at the tested scale.

It does **not** prove that Koschei can already replace a mature general-purpose language for every large system. The point of this reference is to turn that long-term requirement into an executable gate. Future production-reference revisions must grow the same workload toward HTTP server ingress, persistence, long-running workers and queues, database adapters, observability, package distribution, profiling, and substantially larger graph/compilation stress without weakening the existing guarantees.
