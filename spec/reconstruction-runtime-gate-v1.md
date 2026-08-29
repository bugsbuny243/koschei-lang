# Koschei Reconstruction Runtime Gate V1

Status: **implemented bootstrap / exact-request grant + shared Continuity liveness + single-use reconstruction + opaque materialization**

Parent law: **OBSERVABLE WORLD != CANONICAL WORLD**

## 1. Sanctioned path

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
-> same CanonicalEffectRequest + RequestBoundProof
-> shared ContinuityEpochAuthorityV1
-> ALLOW / DENY / CONTAIN
```

The visible Nyr surface is not inverted. Trusted runtime custody already holds canonical
MIR. Reconstruction decides whether that hidden world may be materialized for one exact
request. The broad runtime receives an opaque handle, not `NativeSigilMir`.

## 2. One Continuity truth

Sanctioned observer, reconstruction and materialization gates no longer accept independent
`epoch_source` callbacks. They require the typed `ContinuityEpochAuthorityV1` interface.

The same contract is consumed by:

- `NyrObservationGateV1`;
- `RepresentationReconstructionGateV1`;
- `CanonicalMaterializationEffectGateV1`.

The intended runtime invariant is:

`one authoritative Continuity state -> observation liveness + reconstruction liveness + materialization liveness`

If that shared state advances from E to E+1, an E-bound Nyr surface, reconstruction request
and held materialization handle all become operationally stale through their sanctioned
boundaries.

The bootstrap Continuity identity seal does **not** prove monotonic hardware time, reader
honesty, rollback resistance or physical isolation. A rolled-back underlying source can
make all three gates consistently accept stale reality.

## 3. Exact-request reconstruction grant

Grant issuance requires the exact sealed `CanonicalEffectRequest`.

The grant does not contain raw `CanonicalEffectRequest.digest`. It carries an HMAC
`request_binding` over request digest + Veyra + observer + session + visibility epoch under
the reconstruction key. The grant context additionally binds canonical semantic seal,
Veyra, visibility context, grant id, purpose and expiry.

Request-A grant therefore cannot reconstruct request-B even under the same MIR, Veyra,
epoch and purpose.

## 4. Single-use reconstruction

`ReconstructionConsumptionLedgerV1` atomically consumes the exact grant context in one
process. The authenticated `ReconstructionConsumptionReceiptV1` carries:

- grant context;
- opaque request binding;
- representation digest;
- canonical semantic seal;
- purpose;
- consumed Continuity epoch.

Failed purpose/key/equivalence/liveness/request checks occur before ledger consumption.

## 5. Opaque materialization

Successful reconstruction does not return canonical MIR. The trusted registry retains it
and returns `CanonicalMaterializationHandleV1`.

The handle exposes no MIR fingerprint, Universe digest, sigil/subject/domain names, Veyra,
canonical seal or raw canonical-request digest. It carries a separate materialization-key
request binding, issue/expiry epoch and reconstruction receipt identity.

Possession of the handle is not generic execute authority. It can attempt only the same
sealed canonical request.

## 6. Request-bound effect admission

```text
opaque handle
+ same CanonicalEffectRequest
+ RequestBoundProof
+ NativeSigilProofBundle
+ shared Continuity current epoch
-> request-binding equality
-> handle liveness
-> atomic handle consumption
-> hidden MIR resolution inside registry
-> exact request/proof/MIR validation
-> ALLOW / DENY / CONTAIN
```

The callback receives `CanonicalEffectRequest`, never `NativeSigilMir`. Once the exact
request/world relation is accepted, the handle is consumed before proof/effect evaluation;
DENY/CONTAIN therefore cannot leave reusable canonical access.

## 7. PROTECTS AGAINST

- independent arbitrary epoch callbacks drifting across observer/reconstruction/materialization;
- stale/future epoch use through sanctioned liveness gates;
- widening a reconstruction grant from one canonical request to another;
- raw canonical-request digest exposure in grant/handle;
- repeated/concurrent reconstruction through one process-local authoritative ledger;
- request-binding receipt tamper;
- broad-runtime receipt of canonical MIR from sanctioned reconstruction;
- repeated handle use through one process-local registry;
- purpose/request substitution;
- effect callback after native DENY/CONTAIN.

## 8. DOES NOT PROTECT AGAINST

- compromised or rolled-back underlying Continuity state;
- full compromise/introspection of the trusted Python process;
- restart/fork/rollback of in-memory consumption state;
- direct imports of lower-level/private helpers;
- leaked veil/reconstruction/receipt/materialization keys;
- malicious compiler/proof/request-binding code inside the trusted boundary;
- canonical leakage through logs/debugger/crash dumps/side channels;
- native/backend paths that bypass these gates.

## 9. ASSUMPTIONS

- sealed MIR, Veyra, canonical request and request-bound proof logic remain trustworthy;
- Nur visibility context is authentic, allowed and authority-free;
- one production Continuity source is supplied to all sanctioned liveness boundaries;
- trust-role keys remain separated;
- production keeps raw MIR/request identity inside a non-observer-accessible compartment;
- durable/shared monotonic state is added where restart/fork/rollback matters.

## 10. FAILURE MODE

Shared Continuity removes internal disagreement about "what epoch is now". It does not
make the underlying state monotonic. If an attacker rolls that state back, observation,
reconstruction and materialization may all agree on the same stale epoch.

Python privacy is conventional. This V1 proves semantic/API convergence and one-process
one-shot behavior, not hardware isolation or global replay immunity.

## 11. Security meaning

> **Canonical semantics are not an ordinary runtime value. A live exact-request
> reconstruction capability is consumed once under the same Continuity truth that governs
> observer and materialization liveness, and only an opaque request-bound handle crosses
> into the wider runtime.**

## 12. NEXT

1. Connect existing Khar/Galaxy/Matrix/Hara and relevant power-domain admission to this same exact request-bound execution gate without creating a parallel authority system.
2. Move reconstruction/handle consumption into durable monotonic runtime custody.
3. Add compartment identity/revocation to materialization handles.
4. Route debugger/introspection/runtime surfaces through observer-safe representations.
5. Carry registry custody into native execution so raw MIR never crosses the compartment ABI.
6. Add canonical release validation proving sanctioned runtime APIs do not return raw MIR.
7. Extend opaque materialization from native sigil MIR to general function/closure MIR.
