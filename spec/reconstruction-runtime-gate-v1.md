# Koschei Reconstruction Runtime Gate V1

Status: **implemented bootstrap / exact-request grant + shared Continuity + one-shot materialization + Galaxy constitutional execution**

Parent law: **OBSERVABLE WORLD != CANONICAL WORLD**

## 1. Sanctioned privileged path

```text
ObservableRepresentationV1
+ hidden sealed NativeSigilMir
+ sealed CanonicalEffectRequest
-> exact-request ReconstructionGrantV1
-> shared ContinuityEpochAuthorityV1
-> live representation + exact request validation
-> atomic ReconstructionConsumptionLedgerV1
-> ReconstructionConsumptionReceiptV1
-> CanonicalMaterializationHandleV1
-> trusted CanonicalMaterializationRegistryV1
-> same request + reconstruction Veyra + shared Continuity
-> consume handle once
-> resolve hidden MIR inside trusted boundary
-> enforce_galaxy_critical_effect(...)
   -> canonical Khar
   -> living Aevra
   -> current Matrix/Hara
   -> exact 6/6 Sathra
   -> failure-root independence
   -> RequestBoundProof + NativeSigilProofBundle
   -> durable atomic claim/finality
-> ALLOW / DENY / CONTAIN
```

The visible Nyr surface is not inverted. Trusted runtime custody already holds canonical MIR. Reconstruction decides whether that hidden world may be materialized for one exact request. The broad runtime receives an opaque handle, not `NativeSigilMir`.

## 2. One Continuity truth

Sanctioned observer, reconstruction and materialization gates require `ContinuityEpochAuthorityV1`; they do not accept independent raw `epoch_source` callbacks.

The same contract is consumed by:

- `NyrObservationGateV1`;
- `RepresentationReconstructionGateV1`;
- `CanonicalMaterializationEffectGateV1`.

If the shared state advances from E to E+1, an E-bound Nyr surface, reconstruction request and held materialization handle all become operationally stale through sanctioned boundaries.

The bootstrap Continuity identity seal does **not** prove monotonic hardware time, reader honesty, rollback resistance or physical isolation.

## 3. Exact-request reconstruction grant

Grant issuance requires the exact sealed `CanonicalEffectRequest`.

The grant does not contain raw `CanonicalEffectRequest.digest`. It carries an opaque HMAC request binding over request + Veyra + observer + session + visibility epoch. Request-A grant therefore cannot reconstruct request-B even under the same MIR, epoch and purpose.

## 4. Single-use reconstruction

`ReconstructionConsumptionLedgerV1` atomically consumes the exact grant context in one process. The authenticated `ReconstructionConsumptionReceiptV1` binds grant context, opaque request binding, representation digest, canonical seal, purpose and consumed epoch.

Failed purpose/key/equivalence/liveness/request checks occur before ledger consumption.

## 5. Opaque request + Veyra materialization

Successful reconstruction does not return canonical MIR. `CanonicalMaterializationRegistryV1` retains hidden MIR together with the reconstruction Veyra binding and returns `CanonicalMaterializationHandleV1`.

The handle exposes no raw request identity, Veyra identity, MIR fingerprint, Universe digest, canonical naming map or semantic seal. Its keyed materialization binding covers exact request + Veyra.

Therefore possession of a handle is not generic execute authority and another Galaxy/Veyra cannot substitute itself at materialization time.

## 6. Constitutional effect admission

The sanctioned materialization gate does **not** directly invoke a weaker native request-bound effect helper.

After exact request/Veyra/Continuity checks, it consumes the handle and delegates to the existing `enforce_galaxy_critical_effect()` path. `GalaxyMaterializationContextV1` is only a typed non-authoritative bundle carrying the already-existing constitutional inputs.

Execution therefore requires:

- Veyra bound to canonical Khar v1;
- living Aevra outside Morth/Black Hole;
- exact current Matrix/Hara admission;
- Matrix epoch equal to request epoch;
- exact 6/6 Sathra for the critical event;
- sealed failure-root independence proof;
- exact `RequestBoundProof` + `NativeSigilProofBundle`;
- durable atomic claim/finalization through `AtomicExecutionCoordinator`.

This closes the former architectural possibility that materialization could be followed by a weaker direct native effect path.

## 7. Burn semantics

Cross-request or cross-Veyra substitution fails before the registry entry is consumed, leaving the valid handle available for its original context.

Once exact request + Veyra + current Continuity resolve the hidden world, the materialization handle is burned before constitutional execution. Later Khar/Galaxy DENY/CONTAIN/failure does not restore reusable canonical access.

Galaxy's durable atomic coordinator independently protects the exact critical event from replay once constitutional execution reaches its claim boundary.

## 8. PROTECTS AGAINST

- independent arbitrary epoch callbacks drifting across observer/reconstruction/materialization;
- stale/future epoch use through sanctioned liveness gates;
- reconstruction-grant widening to another canonical request;
- raw canonical-request digest exposure in grant/handle;
- cross-Veyra/Galaxy materialization substitution;
- repeated/concurrent reconstruction through one process-local ledger;
- repeated handle use through one process-local registry;
- bypassing Khar/Aevra/Matrix/Hara/Sathra checks through the sanctioned materialization path;
- replay of exact critical events covered by Galaxy's durable coordinator;
- effect callback after constitutional/native DENY or CONTAIN.

## 9. DOES NOT PROTECT AGAINST

- compromised or rolled-back underlying Continuity state;
- full compromise/introspection of trusted Python memory;
- direct imports of lower-level/private helpers;
- restart/fork/rollback of in-memory reconstruction/materialization state;
- leaked trust-role keys;
- malicious compiler/proof/Galaxy dependencies inside the TCB;
- false claims of physical failure-root independence when evidence is not really independent;
- canonical leakage through logs/debugger/crash dumps/side channels;
- native/backend paths that bypass sanctioned APIs.

## 10. ASSUMPTIONS

- sealed MIR, Veyra/Aevra, Matrix/Hara, request/proof/Sathra logic remain trustworthy;
- Nur visibility context is authentic, allowed and authority-free;
- production supplies one Continuity source to all sanctioned liveness boundaries;
- durable Galaxy stores preserve their claimed semantics;
- production keeps raw MIR/request identity inside a trusted compartment;
- replay/materialization custody becomes durable/shared where restart/fork/rollback matters.

## 11. FAILURE MODE

Shared Continuity removes internal epoch disagreement but does not make underlying state monotonic. Python privacy remains conventional. The security architecture also fails if production exposes another privileged execution route that accepts materialized canonical state while skipping `enforce_galaxy_critical_effect()`.

## 12. Security meaning

> **Canonical semantics are not a broad-runtime value. Exact-request reconstruction and materialization are one-shot and live under one Continuity truth; privileged execution then crosses the already-existing Khar/Galaxy constitutional gate rather than a weaker parallel authority path.**

## 13. NEXT

1. Inspect PR #260 and extract only the minimal request-bound cross-domain default-deny invariant required by Galaxy execution.
2. Consolidate the compiler/MIR/runtime capability contract so that domain admission does not become a second authority system.
3. Move reconstruction/handle consumption into durable monotonic runtime custody.
4. Route debugger/introspection/runtime surfaces through observer-safe representations.
5. Carry registry custody into native execution so raw MIR never crosses the compartment ABI.
6. Add canonical release validation proving sanctioned privileged paths cannot bypass Galaxy/Khar.
