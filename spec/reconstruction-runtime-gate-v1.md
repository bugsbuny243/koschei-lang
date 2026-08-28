# Koschei Reconstruction Runtime Gate V1

Status: **implemented bootstrap prototype / trusted-epoch + atomic single-use reconstruction / native enforcement pending**

Parent law: **OBSERVABLE WORLD != CANONICAL WORLD**

## 1. Purpose

Representation separation is incomplete if an observer-safe surface can be converted back
into canonical semantics through a reusable or caller-timed helper.

V1 therefore treats canonical re-materialization as a privileged runtime transition:

```text
observer-safe ObservableRepresentationV1
+ hidden sealed NativeSigilMir
+ exact ReconstructionGrantV1
+ trusted epoch source
+ authoritative single-use ledger
-> validate live representation/grant
-> atomically consume grant context
-> ReconstructionConsumptionReceiptV1
-> canonical MIR returned to the trusted caller
```

The visible Nyr surface is still not inverted.  The trusted runtime already owns canonical
MIR; this gate controls whether that hidden world may cross the boundary for this exact
context at this exact time.

## 2. Runtime-owned time

The sanctioned gate does not accept `current_epoch` from the reconstruction caller.
`RepresentationReconstructionGateV1` calls a trusted epoch source at use time.

The epoch source fails closed when it:

- raises;
- returns a negative value;
- returns a non-integer;
- returns a boolean.

The bootstrap uses a callable boundary.  Production should bind this source to Koschei
Continuity/lifecycle state rather than application convention.

## 3. Single-use reconstruction identity

The stable replay identity is `ReconstructionGrantV1.context_digest`.

That digest already binds:

- hidden canonical semantic seal;
- Veyra identity;
- observer;
- session;
- visibility epoch;
- expiry epoch;
- grant id;
- purpose.

`ReconstructionConsumptionLedgerV1` atomically check-and-records that context under a
process lock.  Concurrent callers therefore cannot both successfully return canonical
MIR through one authoritative ledger.

A failed purpose/key/equivalence/liveness check occurs before consumption and does not burn
the grant.

## 4. Consumption receipt

`ReconstructionConsumptionReceiptV1` is trusted-side provenance.  It binds:

- grant-context digest;
- observer-safe representation digest;
- canonical semantic seal digest;
- reconstruction purpose;
- trusted consumed epoch;
- `single_use=true`;
- `authority=false`;
- version 1.

The receipt is HMAC-authenticated under a dedicated reconstruction-receipt key.  It is
evidence that the runtime consumed one exact reconstruction context; the receipt itself is
not ambient authority and cannot authorize another reconstruction.

## 5. PROTECTS AGAINST

- application-selected stale/future epoch values through the sanctioned runtime gate;
- repeated reconstruction with the same grant context in one authoritative ledger;
- concurrent double-reconstruction through the same in-process gate/ledger;
- purpose substitution before consumption;
- consumption-receipt field tampering without the receipt key;
- treating an observer-facing representation as sufficient reconstruction authority.

## 6. DOES NOT PROTECT AGAINST

- direct Python imports of the lower-level `reconstruct_canonical_semantics_v1` helper;
- process restart when an in-memory ledger is lost;
- forked processes or separate ledgers consuming the same grant independently;
- rollback of future durable replay state;
- a malicious/compromised trusted epoch source;
- compromise of reconstruction, veil or receipt keys;
- a trusted process already able to read hidden canonical MIR directly;
- memory disclosure, crash dumps, tracing or side channels;
- native/backend paths that bypass this gate.

## 7. ASSUMPTIONS

- `NativeSigilMir.assert_sealed()` and Veyra sealing remain trustworthy;
- the observer visibility envelope is allowed and authority-free;
- reconstruction and veil keys remain separated;
- the reconstruction receipt key is a separate trust role;
- the runtime epoch source reflects authoritative Continuity state;
- one production deployment designates a single authoritative reconstruction-consumption
  state or provides equivalent distributed monotonic coordination.

## 8. FAILURE MODE

The current ledger is process-local.  After restart, snapshot rollback, or fork, another
ledger can forget a prior consumption and admit the same context again.  Therefore this V1
must not be described as globally replay-proof.

The Python package also cannot make direct lower-level helper imports physically
impossible.  Production native/runtime APIs must expose reconstruction through this gate
and keep raw canonical re-materialization primitives trusted-internal.

## 9. Security meaning

This slice changes the Koschei model from:

> "A visible representation expires."

into:

> "Crossing from the visible world back into the canonical semantic world is a scoped,
> time-checked, single-consumption runtime event."

That is an execution-semantic distinction, not syntax decoration.

## 10. NEXT

1. Replace the callable epoch source with a sealed Continuity epoch authority.
2. Move reconstruction-consumption state into durable monotonic runtime custody.
3. Bind canonical materialization to exact effect/compute admission so reconstruction does
   not imply permission to execute arbitrary effects.
4. Add an opaque materialization handle so canonical MIR need not be returned as an ordinary
   Python object across wider runtime surfaces.
5. Route debugger/introspection/runtime surfaces through observer-safe representations by
   default.
6. Carry this invariant into the native backend and canonical release validation.
