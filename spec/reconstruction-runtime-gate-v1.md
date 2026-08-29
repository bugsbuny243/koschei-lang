# Koschei Reconstruction Runtime Gate V1

Status: **implemented bootstrap prototype / trusted-epoch + atomic single-use reconstruction + exact-request opaque materialization handle**

Parent law: **OBSERVABLE WORLD != CANONICAL WORLD**

## 1. Purpose

Representation separation is incomplete if an observer-safe surface can be converted back
into canonical semantics through a reusable helper or if successful reconstruction simply
returns `NativeSigilMir` to the broad runtime.

The sanctioned V1 path is now:

```text
observer-safe ObservableRepresentationV1
+ hidden sealed NativeSigilMir
+ exact ReconstructionGrantV1
+ sealed CanonicalEffectRequest
+ trusted epoch source
+ authoritative reconstruction-consumption ledger
-> validate live representation/grant/request
-> atomically consume grant context
-> ReconstructionConsumptionReceiptV1
-> mint CanonicalMaterializationHandleV1 for exact request digest
-> hidden MIR remains in trusted CanonicalMaterializationRegistryV1
```

The visible Nyr surface is not inverted. The trusted runtime already owns canonical MIR;
this boundary controls when one hidden semantic world may be materialized and returns only
an opaque, one-shot, exact-request capability handle to the wider execution surface.

## 2. Runtime-owned time

The sanctioned reconstruction gate does not accept `current_epoch` from the caller.
`RepresentationReconstructionGateV1` calls a trusted epoch source at use time.

The epoch source fails closed when it raises, is negative, is non-integer or is boolean.
The sealed canonical request epoch must equal both the live representation epoch and the
runtime epoch at reconstruction. Production should bind epoch truth to Koschei
Continuity/lifecycle state rather than application convention.

## 3. Single-use reconstruction identity

The reconstruction replay identity is `ReconstructionGrantV1.context_digest`, which binds:

- hidden canonical semantic seal;
- Veyra identity;
- observer and session;
- visibility epoch and expiry;
- grant id;
- purpose.

`ReconstructionConsumptionLedgerV1` atomically check-and-records the exact context under a
process lock. Concurrent callers therefore cannot both mint canonical materialization
handles from one context through the same authoritative ledger.

Failed purpose/key/equivalence/liveness/request-epoch checks occur before consumption and
do not burn the grant.

## 4. Consumption receipt

`ReconstructionConsumptionReceiptV1` binds grant context, observer-safe representation,
canonical semantic seal, purpose and trusted consumed epoch. It is HMAC-authenticated
under a dedicated receipt key and is provenance, not another reconstruction capability.

## 5. Opaque exact-request materialization

After reconstruction consumption, the sanctioned gate does **not** return canonical MIR.
It asks `CanonicalMaterializationRegistryV1` to custody the hidden MIR and returns
`CanonicalMaterializationHandleV1`.

The handle contains only:

- a CSPRNG-generated opaque handle id;
- purpose;
- sealed `CanonicalEffectRequest.digest`;
- issue epoch;
- expiry epoch;
- reconstruction-receipt digest;
- authenticated handle digest.

The handle MUST NOT contain canonical MIR fingerprint, Universe-plan digest, canonical
sigil/subject/domain names, canonical semantic seal digest or Veyra identity.

The request digest is intentionally opaque but stable for that exact sealed request. It
binds the materialization capability to effect id, `vor` subject, operation, payload
request digest, identity digest, epoch, nonce, MIR fingerprint, Universe identity and
activation-plan identity through the existing `CanonicalEffectRequest` seal.

Possession of the handle is therefore not a generic `execute` authority. It is a narrow
capability to attempt exactly one sealed request against exactly one hidden semantic world.

## 6. Request-bound effect admission

The sanctioned effect path is:

```text
CanonicalMaterializationHandleV1
+ same sealed CanonicalEffectRequest
+ RequestBoundProof
+ NativeSigilProofBundle
+ trusted epoch source
-> verify handle/request digest equality before registry consumption
-> atomically consume handle
-> resolve hidden MIR inside trusted registry only
-> verify CanonicalEffectRequest against hidden MIR
-> verify RequestBoundProof against exact request + proof + MIR
-> native proof-bound enforcement
-> ALLOW / DENY / CONTAIN
-> effect callback only for ALLOW
```

The external callback receives `CanonicalEffectRequest`, not `NativeSigilMir`.

Cross-request substitution fails before the registry entry is consumed, so a valid handle
remains usable for its original request. Once the exact request has been proven to belong
to the hidden world, the handle is removed before proof/effect evaluation; DENY, CONTAIN
or later failure therefore burns the one-shot materialization capability rather than
leaving reusable canonical access.

## 7. PROTECTS AGAINST

- application-selected stale/future epochs through sanctioned reconstruction/effect gates;
- repeated reconstruction with one grant context in one authoritative ledger;
- concurrent double-reconstruction through the same ledger;
- broad-runtime receipt of canonical MIR from the sanctioned reconstruction API;
- stable canonical identifiers appearing directly in the opaque handle;
- repeated use of one materialization handle through one registry;
- purpose substitution on the handle;
- handle-field tampering without the materialization key;
- changing effect id/subject/operation/payload/identity/epoch/nonce after handle minting;
- moving a valid native proof to another canonical request through this gate;
- treating successful reconstruction as permission to execute arbitrary effects;
- effect execution when native proof evaluation returns DENY or CONTAIN.

## 8. DOES NOT PROTECT AGAINST

- direct Python imports of low-level reconstruction or registry-private helpers;
- a process that can introspect the trusted registry's Python memory;
- process restart/fork/rollback of in-memory reconstruction or materialization state;
- a malicious trusted epoch source;
- leaked veil/reconstruction/receipt/materialization keys;
- malicious or buggy compiler/native proof/request-binding logic inside the trusted boundary;
- canonical leakage through logs, debugger, crash dump, tracing or other unclassified paths;
- a trusted effect callback leaking data available through its request/effect context;
- native/backend paths that bypass these gates.

## 9. ASSUMPTIONS

- sealed `NativeSigilMir`, Veyra, `CanonicalEffectRequest`, `RequestBoundProof` and native proof validation are trustworthy;
- the visibility envelope is allowed and authority-free;
- trust-role keys remain separated;
- runtime epoch truth comes from authoritative Continuity state in production;
- production keeps the materialization registry and raw MIR inside a non-observer-accessible compartment;
- one deployment has authoritative replay/materialization custody or equivalent distributed monotonic coordination.

## 10. FAILURE MODE

The Python registries are process-local. Restart, fork or snapshot rollback can forget a
prior grant/handle consumption. Python also cannot make `_consume_hidden_mir` physically
private. Therefore this V1 proves semantic/API separation and one-process one-shot
behavior, not hardware/process isolation or global replay immunity.

If production code exports raw MIR, registry internals, faithful debugger views or direct
reconstruction helpers elsewhere, the repository-wide `observable != canonical` claim is
false even if this module is correct.

## 11. Security meaning

The model is now stronger than "the visible mapping rotates":

> **Canonical semantics are not an ordinary runtime value. Crossing into the canonical
> world requires a live scoped reconstruction capability, creates only an opaque one-shot
> handle for one exact sealed request, and that handle can be consumed only inside a
> trusted request-bound effect admission boundary.**

This is an execution-semantic distinction, not syntax decoration.

## 12. NEXT

1. Replace callable epoch sources with sealed Continuity epoch authority.
2. Move reconstruction and handle-consumption state into durable monotonic runtime custody.
3. Add compartment identity and revocation to materialization handles.
4. Route debugger/introspection/runtime surfaces through observer-safe representations.
5. Carry registry custody into native execution so raw MIR never crosses the compartment ABI.
6. Add canonical release validation proving no sanctioned runtime API returns raw MIR.
7. Extend the same opaque materialization model from native sigil MIR to general function/closure MIR.
