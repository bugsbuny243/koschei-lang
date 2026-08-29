# Koschei Reconstruction Runtime Gate V1

Status: **implemented bootstrap prototype / trusted-epoch + atomic single-use reconstruction + opaque materialization handle**

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
+ trusted epoch source
+ authoritative reconstruction-consumption ledger
-> validate live representation/grant
-> atomically consume grant context
-> ReconstructionConsumptionReceiptV1
-> mint CanonicalMaterializationHandleV1
-> hidden MIR remains in trusted CanonicalMaterializationRegistryV1
```

The visible Nyr surface is not inverted. The trusted runtime already owns canonical MIR;
this boundary controls when an exact hidden semantic world may be materialized and returns
only an opaque capability handle to the wider execution surface.

## 2. Runtime-owned time

The sanctioned reconstruction gate does not accept `current_epoch` from the caller.
`RepresentationReconstructionGateV1` calls a trusted epoch source at use time.

The epoch source fails closed when it raises, is negative, is non-integer or is boolean.
Production should bind this source to Koschei Continuity/lifecycle state rather than
application convention.

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

Failed purpose/key/equivalence/liveness checks occur before consumption and do not burn the
grant.

## 4. Consumption receipt

`ReconstructionConsumptionReceiptV1` binds:

- grant-context digest;
- observer-safe representation digest;
- canonical semantic seal digest;
- reconstruction purpose;
- trusted consumed epoch;
- single-use=true;
- authority=false.

It is HMAC-authenticated under a dedicated receipt key. It is provenance, not another
reconstruction capability.

## 5. Opaque materialization

After reconstruction consumption, the sanctioned gate does **not** return canonical MIR.
It asks `CanonicalMaterializationRegistryV1` to custody the hidden MIR and returns
`CanonicalMaterializationHandleV1`.

The handle contains only:

- a CSPRNG-generated opaque handle id;
- purpose;
- issue epoch;
- expiry epoch;
- reconstruction-receipt digest;
- authenticated handle digest.

The handle MUST NOT contain canonical MIR fingerprint, Universe-plan digest, canonical
sigil/subject/domain names, canonical semantic seal digest or Veyra identity.

Possession of the handle is a narrow capability to ask the trusted registry for the one
materialized semantic world. It is not ambient authority and does not itself authorize an
arbitrary effect.

## 6. Effect admission

The sanctioned effect path is:

```text
CanonicalMaterializationHandleV1
+ trusted epoch source
+ NativeSigilProofBundle
+ PrivilegedEffectIntent
-> atomically consume handle
-> resolve hidden MIR inside trusted registry only
-> native proof-bound enforcement
-> ALLOW / DENY / CONTAIN
-> effect callback only for ALLOW
```

The external effect callback receives `PrivilegedEffectIntent`, not `NativeSigilMir`.
The handle is removed from the registry before proof/effect evaluation begins; a DENY,
CONTAIN or later failure therefore burns the one-shot materialization capability rather
than leaving reusable canonical access.

## 7. PROTECTS AGAINST

- application-selected stale/future epoch values through sanctioned reconstruction/effect gates;
- repeated reconstruction with one grant context in one authoritative ledger;
- concurrent double-reconstruction through the same ledger;
- broad-runtime receipt of canonical MIR from the sanctioned reconstruction API;
- stable canonical identifiers appearing directly in the opaque handle;
- repeated use of one materialization handle through one registry;
- purpose substitution on the handle;
- handle-field tampering without the materialization key;
- treating successful reconstruction as permission to execute arbitrary effects;
- effect execution when native proof evaluation returns DENY or CONTAIN.

## 8. DOES NOT PROTECT AGAINST

- direct Python imports of low-level reconstruction or registry-private helpers;
- a process that can introspect the trusted registry's Python memory;
- process restart/fork/rollback of in-memory reconstruction or materialization state;
- a malicious trusted epoch source;
- leaked veil/reconstruction/receipt/materialization keys;
- canonical leakage through logs, debugger, crash dump, tracing or other unclassified paths;
- a trusted callback intentionally leaking data it can derive from the effect context;
- native/backend paths that bypass these gates.

## 9. ASSUMPTIONS

- sealed `NativeSigilMir`, Veyra identity and native proof validation are trustworthy;
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
> materialization handle, and that handle can be consumed only inside a trusted effect
> admission boundary.**

This is an execution-semantic distinction, not syntax decoration.

## 12. NEXT

1. Replace callable epoch sources with sealed Continuity epoch authority.
2. Move reconstruction and handle-consumption state into durable monotonic runtime custody.
3. Bind handle use to canonical request/effect ids, not purpose alone.
4. Add revocation/compartment identity to materialization handles.
5. Route debugger/introspection/runtime surfaces through observer-safe representations.
6. Carry registry custody into native execution so raw MIR never crosses the compartment ABI.
7. Add canonical release validation proving no sanctioned runtime API returns raw MIR.
