# Koschei Multiverse Architecture v1

Koschei is presented as a universe, but every visual metaphor maps to a real security primitive.

## Topology

- **Matrix Fabric** — connectivity and message/evidence transport between isolated Realities. Connectivity never implies authority.
- **Koschei Core / Gauntlet** — deterministic convergence admission across identity, authority, integrity, behavior, evidence and recovery/time.
- **Vormir Root Reality** — isolated root-admission realm. High-value authority requires the Sacrifice Law; discovering Vormir is not sufficient to enter it.
- **Wanda Reality Integrity** — commitment-chain guardian across every Reality. Detects history rewrite, rollback and competing forks.
- **Sentinel / Neo** — model intelligence. Observes evidence and can recommend restriction/quarantine, but cannot grant authority or rewrite Reality.
- **Planetary Realities** — task-specific worlds with explicit capabilities and independent blast radii.

## Planet law

A planet is a security boundary, not a UI category. Each planet has:

1. canonical reality identity,
2. explicit authority manifest,
3. independent epoch,
4. state commitment chain,
5. ingress/egress conduit policy,
6. resource budget,
7. evidence stream,
8. quarantine state.

No planet inherits another planet's authority merely because both belong to the Matrix Fabric.

## Wanda law

> State may change. Accepted history may not be silently rewritten.

Every admitted state transition commits `reality_id + epoch + state_digest + authority_digest + previous_commitment`. A competing commitment for the same reality/epoch is a fork. A candidate at or behind the accepted epoch is rollback evidence. Cross-reality messages must eventually bind both source and destination commitment identities.

## Vormir law

Vormir is deliberately absent from ordinary task discovery. This is defense in depth, not the security root. Even full topology disclosure must not grant admission. Root admission requires deterministic proof, fresh epoch, hardware-backed attestation commitment, and actual irreversible authority attenuation.

## Visual universe contract

The frontend may render planets, orbits, portals, anomalies and guardians, but it must consume canonical backend security state. A red planet means a real quarantine/fork/invariant condition, not decorative animation. UI state never becomes an authority oracle.

## Next convergence gates

- Bind Wanda commitments to Vormir sacrifice/recovery records.
- Bind Matrix conduits to source+destination Reality commitments.
- Stream runtime evidence into the planetary console without granting the console authority.
- Add cross-reality fork isolation and deterministic recovery tests.
- Export the same semantics into the pinned Sentinel training contract.