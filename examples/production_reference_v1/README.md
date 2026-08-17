# Koschei Production Reference v1

This is an acceptance workload for the language and toolchain, not a marketing demo and not a claim that Koschei is already production-ready.

The committed workspace now exercises a realistic financial order-processing path across thirteen independently owned realms:

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
- `http_ingress` — bounded loopback HTTP ingress boundary that depends on the JSON gateway and order worker while keeping Serve authority out of the core worker graph.

The current workspace-v1 loader still requires `koschei.toml`; that filename and its manifest vocabulary are compatibility debt under the Koschei Originality Contract. The reference deliberately avoids the conventional `src/main.ks` scaffold and uses `matter.ks` inside realm roots. When Native Reality becomes the default project loader this reference must migrate without changing its semantic acceptance contract.

The legacy `[capabilities]` table in each `koschei.toml` is not treated as the semantic source of Serve authority. Serve authority is explicit in Koschei source and in the capability-analysis evidence. This mismatch is compatibility debt to remove when the project/authority manifest is redesigned rather than papered over by inventing an ignored `serve = ...` field.

## Acceptance contract

The test suite requires all of the following:

1. The committed thirteen-realm workspace checks as one dependency graph.
2. Core matching/risk/ledger/worker/JSON/dispatch graphs request no disk/network/env/process/serve capability.
3. The external `market_feed` boundary reports exactly outbound network authority.
4. The `http_ingress` boundary reports exactly Serve authority while the imported `order_worker` graph remains authority-free.
5. A deterministic order-processing scenario runs only after a verified workspace lock.
6. Source drift after lock creation fails before program output.
7. Interpreter output and native binary output are byte-for-byte identical for the deterministic worker when Go is available.
8. JSON parse/canonical encode and structured `parallel_map` are exercised on the root worker execution path.
9. A generated 32-realm / 64-function transitive workspace checks and runs successfully.
10. The same 32-realm graph executes through the AST-free direct-MIR executor.
11. The same 32-realm graph builds and executes as a native binary when Go is available.
12. The complete 11-module `order_worker` dependency graph executes through direct MIR and preserves the deterministic worker output.
13. A locked `http_ingress` workspace accepts a real loopback TCP POST, canonicalizes the JSON body, invokes the production order worker, and returns a bounded HTTP response.
14. On Linux with Go available, the locked native `http_ingress` binary must satisfy the same real TCP/JSON/order-processing contract.

## Manual deterministic-worker commands

Run these from the repository root:

```text
ks workspace check examples/production_reference_v1
ks workspace caps examples/production_reference_v1
ks workspace lock create examples/production_reference_v1
ks workspace run order_worker examples/production_reference_v1
ks workspace build order_worker examples/production_reference_v1 -o /tmp/koschei-order-worker
```

The `http_ingress` realm is intentionally not listed as a casual manual-run command because it binds a real loopback port (`127.0.0.1:18080`) and waits for one bounded request. Its network acceptance path is exercised by dedicated tests that allocate a temporary free loopback port before creating the workspace lock.

The lock command writes a control artifact into the workspace. Do not commit a locally generated lock unless the release process explicitly requires it.

## Authority topology

`order_worker` is intentionally capability-free. It imports matching, settlement, report, JSON and dispatch realms without receiving Serve or outbound network authority.

`http_ingress` owns the inbound Serve token and imports `json_gateway` plus `order_worker`. This creates a one-way boundary: inbound authority can call pure/core processing, but the core does not inherit the listener capability merely because an ingress package depends on it.

`market_feed` remains a separate outbound-network boundary and is not a dependency of either `order_worker` or `http_ingress` in v1.

## What this proves — and what it does not

Passing these gates would prove that the current compiler/runtime can carry a non-trivial multi-package program, preserve explicit authority boundaries, lock source identity, execute deterministic core work, preserve tested interpreter/native parity, and drive that core through a bounded loopback ingress boundary at the tested scale.

It does **not** prove that Koschei can already replace a mature general-purpose language for every large system, and it does not make `ServeCaps.exchange` a production HTTP framework. Public ingress, TLS, routing, long-running handlers, persistence/database adapters, observability, package distribution, profiling and larger graph/compile stress remain separate gates.

The point of this reference is to turn those long-term requirements into executable work: future revisions must grow this same system and fix compiler/runtime/stdlib gaps exposed by the workload instead of shrinking the workload to preserve a claim.
