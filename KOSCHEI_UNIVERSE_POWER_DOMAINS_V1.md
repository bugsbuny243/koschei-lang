# Koschei Universe Power Domains v1

Status: **first enforceable architecture slice; not yet wired into every language/runtime effect**.

This document converts the six-stone Universe metaphor into real security domains. The names below are canonical technical names; film terminology is not part of the language surface.

## Six real-world power domains

1. **Identity** — who/what a principal is and which authenticated identity facts exist.
2. **Authority** — which privileged decisions or delegations a principal may make.
3. **Data** — which state, records, balances, objects, secrets or supply facts may be read or mutated.
4. **Compute** — which code/workload/effect may execute and with what bounded resources.
5. **Network** — which endpoints, peers, listeners, routes or remote effects may be reached.
6. **Continuity** — epoch, replay, recovery, rebirth, revocation and persistence across time/state transitions.

## Conservation law

**Authority in one power domain does not synthesize authority in another.**

For six domains there are 30 directed cross-domain transitions. All 30 are absent by default.

A cross-domain transition can exist only as an explicit, exact permit bound to:

- subject;
- source domain;
- target domain;
- source grant identity;
- action;
- scope;
- epoch;
- evidence digest.

There is no wildcard cross-domain permit in v1.

## Why this matters for the 22 Aug 2026 SAND bridge incident

Public reporting says an attacker hijacked LayerZero delegate permissions through an `approveAndCall` path and then minted unbacked SAND on Base/BNB Chain. The security lesson for Koschei is not chain-specific: **possession of delegate/authority power must not itself become asset-state/mint power.**

In the v1 model:

`AUTHORITY(delegate compromised)`

cannot implicitly become:

`DATA(mint / supply mutation)`.

The transition is denied unless an exact cross-domain permit exists for the same subject, source grant, action, scope and epoch. This is the first executable form of the Universe rule: **one stolen stone is not the Universe.**

## What v1 does not claim

This module does **not** claim that current Koschei Lang, as deployed today, would automatically have prevented the Sandbox exploit. Prevention requires the affected privileged path to be expressed through and enforced by this gate (or an equivalent compiler/runtime-integrated invariant), plus trustworthy backing evidence. v1 is the first explicit power-domain separation primitive and regression model.

## Next integration steps

- bind power-domain transitions into MIR/effect admission rather than leaving them as a standalone runtime primitive;
- bind Continuity to the existing epoch/rebirth/tombstone machinery;
- require independently produced backing evidence for asset creation/mint effects;
- add cross-domain laundering, permit substitution, replay and compromised-delegate adversarial suites;
- add the suite to the release adversarial gate only after exact branch execution is green.
