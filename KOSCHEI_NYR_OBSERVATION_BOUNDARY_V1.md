# KOSCHEI NYR OBSERVATION BOUNDARY V1

Status: IMPLEMENTED PROTOTYPE / NOT YET NATIVE-ENFORCED

## Purpose

Nyr v2 is an observer-facing, non-faithful projection of sealed native Koschei MIR. A valid projection is not automatically a live projection. Observation must therefore cross a boundary that proves both integrity and liveness before any Nyr surface is rendered.

Canonical semantics and observer-visible representation remain different worlds. The observation boundary does not grant authority and does not turn visible Nyr aliases into canonical identities.

## Semantic invariant

For a Nyr v2 surface S produced in visibility epoch E:

1. S must exactly match the hidden sealed MIR, Veyra, Nur visibility envelope and veil key context from which it was projected.
2. S is live only while trusted runtime epoch == E.
3. S expires before E + 1.
4. A previously valid S presented at or after its expiry is replay and must be rejected.
5. A future S presented before its birth epoch must be rejected.
6. Epoch-source failure or malformed epoch state fails closed.
7. A contained Nur envelope cannot open the observation boundary.

## Prototype boundary

`koschei.nur_nyr_observation_gate_v1.NyrObservationGateV1`

The gate owns the hidden verification context and receives a trusted `epoch_source`. Its only sanctioned observer-output operation is `render(surface)`. `render` reads the live epoch, invokes `require_live_nyr_surface_v2`, and returns the non-faithful Nyr rendering only after verification succeeds.

`require_nyr_surface_v2` remains an integrity primitive. It is not sufficient at an observation or execution boundary.

## PROTECTS AGAINST

- Replay of a correctly generated but expired Nyr v2 surface through the sanctioned gate.
- Presentation of a future/not-yet-live Nyr surface through the sanctioned gate.
- Visible-surface tampering becoming accepted merely because the epoch is current.
- Observation continuing after the trusted epoch source fails.
- Opening an observer surface from a contained Nur visibility state.

## DOES NOT PROTECT AGAINST

- Compromise of the canonical MIR, Veyra inputs or veil key before they reach the gate.
- A malicious or compromised trusted epoch provider that lies consistently about current epoch state.
- Canonical semantic leakage through unrelated logs, memory disclosure, debugger access, crash dumps or other side channels.
- Direct calls to lower-level Python bootstrap helpers by code already executing with arbitrary access to the compiler implementation.
- Native/backend paths that fail to preserve this boundary.

## ASSUMPTIONS

- The runtime supplies current epoch state from a trusted monotonic visibility authority rather than from observer-controlled input.
- Hidden MIR and Veyra objects retain valid seals.
- The Nur envelope is authentic and authority-free.
- Veil-key custody is outside observer control.
- Production/native API surfaces will not export a bypass that is treated as authoritative observation.

## FAILURE MODE

Replay resistance collapses if runtime code consumes `NyrSurfaceV2.render()` directly, treats `require_nyr_surface_v2` as sufficient, or accepts attacker-controlled epoch state as trusted time. If veil-key or canonical-state custody fails, rotating aliases alone do not restore secrecy.

## Native enforcement requirement

This Python implementation is a bootstrap prototype, not proof that bypass is physically impossible. The native Koschei runtime must expose observer rendering through a gate-equivalent ABI and keep raw canonical/Nyr rendering primitives non-authoritative or unavailable outside the trusted runtime compartment.

The next design step is to bind observation/execution to a time-scoped capability/token whose identity includes Veyra, projection digest, permitted operation and validity epoch. The token must narrow authority rather than create ambient permission.
