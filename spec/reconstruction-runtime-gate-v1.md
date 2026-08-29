# Koschei Reconstruction Runtime Gate V1

Status: **implemented bootstrap prototype / exact-request grant + trusted-epoch + atomic single-use reconstruction + opaque materialization handle**

Parent law: **OBSERVABLE WORLD != CANONICAL WORLD**

## 1. Purpose

Representation separation is incomplete if an observer-safe surface can be converted back
into canonical semantics through a reusable/general-purpose helper, if a reconstruction
grant means only "execute something", or if successful reconstruction returns
`NativeSigilMir` to the broad runtime.

The sanctioned V1 path is now:

```text
observer-safe ObservableRepresentationV1
+ hidden sealed NativeSigilMir
+ sealed CanonicalEffectRequest
-> mint exact-request ReconstructionGrantV1
   (raw request digest is not stored in the grant)
+ trusted epoch source
+ authoritative reconstruction-consumption ledger
-> validate live representation + exact request-bound grant
-> atomically consume grant context
-> ReconstructionConsumptionReceiptV1 carrying opaque request binding
-> mint CanonicalMaterializationHandleV1 with a separate keyed request binding
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

## 3. Exact-request reconstruction grant

`ReconstructionGrantV1` is no longer merely purpose-scoped. Grant issuance requires the
exact sealed `CanonicalEffectRequest`.

The grant does **not** contain the raw `CanonicalEffectRequest.digest`. Instead it contains
`request_binding`, an HMAC under the reconstruction key over:

- the canonical request digest;
- Veyra identity;
- observer identity;
- observer session;
- visibility epoch.

Therefore the same canonical request does not create one stable public correlation label
across customer Veyras or observer sessions.

The grant `context_digest` additionally binds:

- hidden canonical semantic seal;
- Veyra identity;
- observer/session;
- visibility epoch and expiry;
- grant id;
- purpose;
- the opaque exact-request binding.

A grant minted for request A cannot reconstruct request B even when MIR, Veyra, epoch and
purpose are otherwise identical.

## 4. Single-use reconstruction identity

The reconstruction replay identity is `ReconstructionGrantV1.context_digest`.

`ReconstructionConsumptionLedgerV1` atomically check-and-records that exact context under a
process lock. Concurrent callers therefore cannot both mint canonical materialization
handles from one grant through the same authoritative ledger.

Failed purpose/key/equivalence/liveness/request checks occur before ledger consumption and
do not burn the valid grant.

## 5. Consumption receipt

`ReconstructionConsumptionReceiptV1` binds:

- grant context digest;
- the grant's opaque exact-request binding;
- observer-safe representation digest;
- canonical semantic seal;
- purpose;
- trusted consumed epoch.

It is HMAC-authenticated under a dedicated receipt key and is provenance, not another
reconstruction capability. Tampering with the request binding invalidates the receipt.

## 6. Opaque exact-request materialization

After reconstruction consumption, the sanctioned gate does **not** return canonical MIR.
It asks `CanonicalMaterializationRegistryV1` to custody the hidden MIR and returns
`CanonicalMaterializationHandleV1`.

The handle contains only:

- a CSPRNG-generated opaque handle id;
- purpose;
- a materialization-key HMAC over the sealed canonical-request digest;
- issue epoch;
- expiry epoch;
- reconstruction-receipt digest;
- authenticated handle digest.

The handle MUST NOT contain canonical MIR fingerprint, Universe-plan digest, canonical
sigil/subject/domain names, canonical semantic seal digest, Veyra identity or the raw
`CanonicalEffectRequest.digest`.

The materialization binding uses a different trust role from the reconstruction-grant
binding. The trusted registry retains the raw request identity privately and recomputes
the keyed binding when the handle is presented.

Possession of the handle is therefore not generic `execute` authority. It is a narrow
capability to attempt exactly one sealed request against exactly one hidden semantic world.

## 7. Request-bound effect admission

The sanctioned effect path is:

```text
CanonicalMaterializationHandleV1
+ same sealed CanonicalEffectRequest
+ RequestBoundProof
+ NativeSigilProofBundle
+ trusted epoch source
-> recompute materialization request binding and compare before registry consumption
-> verify request epoch is current
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

## 8. PROTECTS AGAINST

- application-selected stale/future epochs through sanctioned reconstruction/effect gates;
- reconstruction-grant widening from one canonical request to another request;
- a stable raw canonical-request digest appearing in the reconstruction grant;
- reuse of one request-binding label across different Veyra/session contexts under the sanctioned grant issuer;
- repeated reconstruction with one grant context in one authoritative ledger;
- concurrent double-reconstruction through the same ledger;
- tampering with request-binding provenance in the reconstruction consumption receipt;
- broad-runtime receipt of canonical MIR from the sanctioned reconstruction API;
- raw canonical-request digest appearing directly in the opaque materialization handle;
- repeated use of one materialization handle through one registry;
- purpose substitution on the grant/handle;
- handle-field tampering without the materialization key;
- changing effect id/subject/operation/payload/identity/epoch/nonce after grant/handle minting;
- moving a valid native proof to another canonical request through this gate;
- treating successful reconstruction as permission to execute arbitrary effects;
- effect execution when native proof evaluation returns DENY or CONTAIN.

## 9. DOES NOT PROTECT AGAINST

- direct Python imports of low-level reconstruction or registry-private helpers;
- a process that can introspect the trusted registry's Python memory;
- process restart/fork/rollback of in-memory reconstruction or materialization state;
- a malicious trusted epoch source;
- leaked veil/reconstruction/receipt/materialization keys;
- malicious or buggy compiler/native proof/request-binding logic inside the trusted boundary;
- correlation through other side channels even when raw canonical request digests are absent;
- canonical leakage through logs, debugger, crash dump, tracing or other unclassified paths;
- a trusted effect callback leaking data available through its request/effect context;
- native/backend paths that bypass these gates.

## 10. ASSUMPTIONS

- sealed `NativeSigilMir`, Veyra, `CanonicalEffectRequest`, `RequestBoundProof` and native proof validation are trustworthy;
- the visibility envelope is allowed and authority-free;
- reconstruction and materialization key roles remain separated;
- runtime epoch truth comes from authoritative Continuity state in production;
- production keeps the materialization registry and raw MIR inside a non-observer-accessible compartment;
- one deployment has authoritative replay/materialization custody or equivalent distributed monotonic coordination.

## 11. FAILURE MODE

The Python registries are process-local. Restart, fork or snapshot rollback can forget a
prior grant/handle consumption. Python also cannot make private reconstruction/registry
helpers physically inaccessible. Therefore this V1 proves semantic/API separation and
one-process one-shot behavior, not hardware/process isolation or global replay immunity.

If production code exports raw MIR, registry internals, faithful debugger views or direct
reconstruction helpers elsewhere, the repository-wide `observable != canonical` claim is
false even if this module is correct.

## 12. Security meaning

The model is now stronger than "the visible mapping rotates":

> **Canonical semantics are not an ordinary runtime value. Crossing into the canonical
> world requires a live capability minted for one exact canonical request, that capability
> is consumed once, and the broad runtime receives only another opaque one-shot handle for
> the same request.**

The exact-request invariant now begins at reconstruction grant issuance rather than only at
materialization-handle issuance. This is an execution-semantic distinction, not syntax
decoration.

## 13. NEXT

1. Replace callable epoch sources with one sealed Continuity epoch authority shared with Nyr observation liveness.
2. Absorb the PR #264 live-Nyr gate into this same `nur` lifecycle rather than maintaining a parallel epoch truth.
3. Move reconstruction and handle-consumption state into durable monotonic runtime custody.
4. Add compartment identity and revocation to materialization handles.
5. Route debugger/introspection/runtime surfaces through observer-safe representations.
6. Carry registry custody into native execution so raw MIR never crosses the compartment ABI.
7. Add canonical release validation proving no sanctioned runtime API returns raw MIR.
8. Extend the same opaque materialization model from native sigil MIR to general function/closure MIR.
