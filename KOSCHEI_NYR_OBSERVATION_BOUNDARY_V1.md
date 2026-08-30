# KOSCHEI NYR OBSERVATION BOUNDARY V1

Status: **IMPLEMENTED BOOTSTRAP / SHARED CONTINUITY AUTHORITY / NOT NATIVE-ENFORCED**

## Purpose

Nyr v2 is an observer-facing, non-faithful projection of sealed native Koschei MIR. Projection integrity is not current liveness. A historically authentic surface from an old epoch must not remain usable as the current observer world.

This boundary is now part of the same `nur` lifecycle as exact-request reconstruction and opaque materialization. It does **not** maintain an independent epoch callback.

## One-time truth law

Sanctioned liveness boundaries accept `ContinuityEpochAuthorityV1`:

- `NyrObservationGateV1`
- `RepresentationReconstructionGateV1`
- `CanonicalMaterializationEffectGateV1`

None exposes a raw `epoch_source` constructor field.

The intended invariant is:

`one trusted Continuity state -> observer liveness + reconstruction liveness + materialization liveness`

Changing the shared underlying Continuity epoch changes all three decisions together.

`ContinuityEpochAuthorityV1` is a typed bootstrap interface, not proof of monotonic hardware time. Its identity seal prevents accidental role relabeling; it does not authenticate the Python reader or prevent host rollback.

## Nyr liveness invariant

For Nyr surface S born in epoch E:

1. S must exactly match hidden MIR, Veyra, Nur envelope and veil-key context.
2. S is operationally live only when shared Continuity reports E.
3. S expires before E + 1.
4. An authentic old S at or after expiry is replay and is rejected.
5. A future/not-yet-live S is rejected.
6. malformed, boolean, negative or failed Continuity reads fail closed.
7. a contained Nur envelope cannot open the observation gate.

`require_nyr_surface_v2` remains integrity-only. `require_live_nyr_surface_v2` adds operational liveness.

## Sanctioned observer path

`NyrObservationGateV1.render(surface)`:

`shared Continuity current epoch`
`-> exact Nyr projection integrity`
`-> live visibility epoch`
`-> observer-safe render`

`project_and_render()` additionally requires the supplied Nur envelope itself to be current before projecting.

The visible Nyr surface grants no authority and contains no canonical identity right.

## PROTECTS AGAINST

- replay of an expired but correctly generated Nyr surface through the sanctioned gate;
- future-surface presentation;
- surface tampering accepted merely because an epoch looks current;
- separate arbitrary epoch callbacks drifting between observation, reconstruction and materialization;
- malformed/failed Continuity reads failing open;
- contained Nur state opening an observer surface.

## DOES NOT PROTECT AGAINST

- a compromised or rolled-back underlying Continuity reader/state;
- host/process compromise that can replace the Continuity object or inspect trusted memory;
- raw `NyrSurfaceV2.render()` calls by arbitrary Python code outside the sanctioned API convention;
- canonical leakage through logs, debugger, crash dumps, memory scraping or side channels;
- compromised MIR/Veyra/veil-key custody;
- native/backend paths that bypass the gate.

## ASSUMPTIONS

- production supplies one authoritative Continuity state to all sanctioned liveness gates;
- hidden MIR and Veyra seals remain trustworthy;
- Nur envelope is authentic, allowed and authority-free;
- veil-key custody remains trusted;
- native runtime preserves this observer boundary.

## FAILURE MODE

If the underlying Continuity state is maliciously rolled back, all three gates can agree on the same stale epoch. Shared truth removes internal epoch disagreement; it does not manufacture rollback resistance.

Python privacy is conventional. A caller with arbitrary trusted-process access can bypass these objects. Therefore this prototype proves API/semantic convergence, not physical isolation.

## NEXT

The next core integration step is to connect the existing Khar/Galaxy/Matrix/Hara and relevant power-domain admission to the same exact request-bound execution path without creating a second authority model.
