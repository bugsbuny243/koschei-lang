# Koschei Reconstruction Runtime Gate V1

Status: **implemented bootstrap / compiler-bound exact request + shared Continuity + one-shot materialization + Galaxy constitutional execution**

Parent law: **OBSERVABLE WORLD != CANONICAL WORLD**

## 1. Sanctioned privileged path

```text
sealed checked compiler MirGraph
-> exact leaf capability call
-> CompilerCapabilityEffectBasisV1
-> compiler-derived CanonicalEffectRequest.operation
-> compiler-bound RequestCapabilityDomainConstraintV1

ObservableRepresentationV1
+ hidden sealed NativeSigilMir
+ exact compiler-bound CanonicalEffectRequest
-> exact-request ReconstructionGrantV1
-> shared ContinuityEpochAuthorityV1
-> live representation + exact request validation
-> atomic ReconstructionConsumptionLedgerV1
-> ReconstructionConsumptionReceiptV1
-> CanonicalMaterializationHandleV1
-> trusted CanonicalMaterializationRegistryV1
-> same request + reconstruction Veyra + shared Continuity
-> compiler-bound deny-only same-domain constraint
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

## 2. Compiler-bound privileged request

The sanctioned bootstrap request path no longer accepts a runtime-selected capability type/method or privileged operation label.

`CompilerCapabilityEffectBasisV1` derives one exact direct canonical capability call from sealed checked compiler MIR. Bootstrap V1 deliberately requires one leaf function with exactly one direct capability call and no local/imported call indirection. Ambiguous shapes fail closed rather than being guessed.

`seal_compiler_bound_effect_request_v1(...)` then sets:

`CanonicalEffectRequest.operation = compiler_basis.canonical_effect`

and binds `RequestCapabilityDomainConstraintV1` to that exact request plus the compiler basis.

The constraint is `compiler_bound=True`, `deny_only=True`, `authority=False`. It can reject a mismatch but can never produce ALLOW.

This compiler basis uses deterministic structural seals. At issuance it can be re-derived from sealed compiler `MirGraph`. The later broad-runtime materialization surface does not carry the full compiler MIR, so this Python bootstrap does not claim cryptographic non-forgeability against code already executing inside the trusted Python process.

## 3. One Continuity truth

Sanctioned observer, reconstruction and materialization gates require `ContinuityEpochAuthorityV1`; they do not accept independent raw `epoch_source` callbacks.

The same contract is consumed by:

- `NyrObservationGateV1`;
- `RepresentationReconstructionGateV1`;
- `CanonicalMaterializationEffectGateV1`.

If shared state advances from E to E+1, an E-bound Nyr surface, reconstruction request and held materialization handle all become operationally stale through sanctioned boundaries.

The bootstrap Continuity identity seal does **not** prove monotonic hardware time, reader honesty, rollback resistance or physical isolation.

## 4. Exact-request reconstruction grant

Grant issuance requires the exact sealed `CanonicalEffectRequest`.

The grant does not contain raw `CanonicalEffectRequest.digest`. It carries an opaque HMAC request binding over request + Veyra + observer + session + visibility epoch. Request-A grant therefore cannot reconstruct request-B even under the same MIR, epoch and purpose.

The request itself has already had its privileged operation identity bound to compiler capability evidence in the sanctioned bootstrap path.

## 5. Single-use reconstruction

`ReconstructionConsumptionLedgerV1` atomically consumes the exact grant context in one process. The authenticated `ReconstructionConsumptionReceiptV1` binds grant context, opaque request binding, representation digest, canonical seal, purpose and consumed epoch.

Failed purpose/key/equivalence/liveness/request checks occur before ledger consumption.

## 6. Opaque request + Veyra materialization

Successful reconstruction does not return canonical MIR. `CanonicalMaterializationRegistryV1` retains hidden MIR together with the reconstruction Veyra binding and returns `CanonicalMaterializationHandleV1`.

The handle exposes no raw request identity, Veyra identity, MIR fingerprint, Universe digest, canonical naming map or semantic seal. Its keyed materialization binding covers exact request + Veyra.

Therefore possession of a handle is not generic execute authority and another Galaxy/Veyra cannot substitute itself at materialization time.

## 7. Compiler-bound domain constraint before materialization

`CanonicalMaterializationEffectGateV1` requires `RequestCapabilityDomainConstraintV1` before touching one-shot materialization state.

The constraint verifies:

- exact request binding;
- compiler basis structural seal;
- capability type/method/effect/domain equality with that basis;
- request operation equality with compiler-derived canonical effect;
- same-domain canonical capability contract semantics.

A malformed, foreign, relabelled or domain-drifted constraint therefore rejects before a valid materialization handle is consumed.

PR #260's `PowerGrant` / `CrossDomainPermit` authority model is intentionally absent. Only its default-deny law was extracted.

## 8. Constitutional effect admission

The sanctioned materialization gate does **not** directly invoke a weaker native request-bound effect helper.

After compiler-bound domain validation plus exact request/Veyra/Continuity checks, it consumes the handle and delegates to the existing `enforce_galaxy_critical_effect()` path. `GalaxyMaterializationContextV1` is only a typed non-authoritative bundle carrying already-existing constitutional inputs.

Execution therefore requires:

- Veyra bound to canonical Khar v1;
- living Aevra outside Morth/Black Hole;
- exact current Matrix/Hara admission;
- Matrix epoch equal to request epoch;
- exact 6/6 Sathra for the critical event;
- sealed failure-root independence proof;
- exact `RequestBoundProof` + `NativeSigilProofBundle`;
- durable atomic claim/finalization through `AtomicExecutionCoordinator`.

This closes the architectural possibility that materialization could be followed by a weaker direct native effect path.

## 9. Burn semantics

Cross-request, cross-Veyra, or foreign compiler-domain-constraint substitution fails before the registry entry is consumed, leaving the valid handle available for its original context.

Once exact request + Veyra + current Continuity resolve the hidden world, the materialization handle is burned before constitutional execution. Later Khar/Galaxy DENY/CONTAIN/failure does not restore reusable canonical access.

Galaxy's durable atomic coordinator independently protects the exact critical event from replay once constitutional execution reaches its claim boundary.

## 10. PROTECTS AGAINST

- runtime/bootstrap selection of capability type/method independently of checked compiler evidence;
- caller-selected privileged operation labels diverging from the compiler-derived canonical effect;
- ambiguous multiple capability call-sites being guessed into one privileged request in basis V1;
- accidental capability-domain drift or request-operation relabeling before materialization;
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

## 11. DOES NOT PROTECT AGAINST

- arbitrary internal Python dataclass/helper construction by malicious code already inside the TCB;
- malicious compiler/runtime logic forging compiler basis and dependent policy together;
- compromised or rolled-back underlying Continuity state;
- full compromise/introspection of trusted Python memory;
- direct imports of lower-level/private helpers;
- restart/fork/rollback of in-memory reconstruction/materialization state;
- leaked trust-role keys;
- false claims of physical failure-root independence when evidence is not really independent;
- canonical leakage through logs/debugger/crash dumps/side channels;
- native/backend paths that bypass sanctioned APIs or ignore compiler-bound provenance;
- legitimate multi-call/transitive privileged functions, which basis V1 currently rejects rather than models incompletely.

## 12. ASSUMPTIONS

- checked compiler `MirGraph` + Typed-HIR evidence are trustworthy compiler products;
- `capability_effect_contract_v1` is the single canonical capability/effect authority;
- compiler-bound request issuance is used instead of low-level manual Python constructors;
- sealed NativeSigilMir, Veyra/Aevra, Matrix/Hara, request/proof/Sathra logic remain trustworthy;
- Nur visibility context is authentic, allowed and authority-free;
- production supplies one Continuity source to all sanctioned liveness boundaries;
- durable Galaxy stores preserve their claimed semantics;
- production keeps raw MIR/request identity inside a trusted compartment;
- replay/materialization custody becomes durable/shared where restart/fork/rollback matters.

## 13. FAILURE MODE

The architecture fails if runtime code regains the ability to relabel compiler-known capability authority, if shared Continuity can be bypassed, if production exposes another privileged execution route that skips `enforce_galaxy_critical_effect()`, or if deterministic bootstrap provenance is treated as physically non-forgeable isolation.

## 14. Security meaning

> **Canonical semantics are not a broad-runtime value. Privileged operation identity is derived from checked compiler capability evidence, exact-request reconstruction/materialization are one-shot under one Continuity truth, and execution crosses the existing Khar/Galaxy constitutional gate rather than a parallel authority path.**

## 15. NEXT

1. Make exact capability call-site identity first-class normalized MIR instead of deriving it by walking sealed AST fallback.
2. Make interpreter/native/backend paths consume that same normalized call-site capability identity.
3. Move compiler/runtime provenance, reconstruction and handle custody into stronger native/durable isolation.
4. Route debugger/introspection/runtime surfaces through observer-safe representations.
5. Run canonical/adversarial validation before PR #263 leaves draft.
