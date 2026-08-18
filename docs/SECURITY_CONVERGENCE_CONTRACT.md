# Koschei Security Convergence Contract v1

Status: architectural hard contract

The internal nickname for this goal may be "Thanos", but production architecture does not depend on fictional terminology.

## Goal

Koschei must not become a pile of independently impressive security features. Its strongest primitives must converge on one execution admission decision while preserving separation of authority.

The six security domains are:

1. **Identity / provenance** — what exact source, artifact, dependency, revision, epoch and policy are being considered?
2. **Authority** — what effects and exact targets may this computation exercise?
3. **Integrity** — is source -> authenticated Object Space -> Native IR -> artifact -> payload still the same admitted object?
4. **Behavior** — has the artifact expanded effects, targets, resource use or execution shape beyond its established contract?
5. **Evidence / prediction** — what deterministic facts exist, and what restrictions does Sentinel recommend from those facts?
6. **Recovery / time** — are leases fresh, epochs monotonic, compromised authority revoked, and re-entry bound to a new proof/revision?

## Convergence law

No single domain can manufacture execution authority.

Execution may continue only when all mandatory deterministic domains agree on the same canonical subject and no hard invariant is violated.

```text
identity/provenance
        +
authority manifest
        +
source/IR/artifact integrity
        +
behavior/invariant state
        +
fresh lease/epoch/recovery state
        |
        v
  deterministic admission
        ^
        |
Sentinel evidence interpretation
(restrict/request quarantine only; never grant)
```

## Non-negotiable invariants

- Evidence is not authority.
- Model confidence is not authority.
- A dependency begins with zero ambient authority.
- Authority widening requires explicit deterministic admission; learning cannot widen it.
- Artifact identity, policy identity and epoch must be bound into admission evidence.
- A source/IR/artifact mismatch fails closed.
- A hard pre-exploit invariant violation fails closed before an external effect.
- Compound risk may suspend continuation but cannot create replacement authority.
- Recovery requires fresh proof and monotonic state; compromised authority is never silently resurrected.
- Sentinel may observe, classify, explain, recommend restriction and request quarantine. It may never grant/widen capability, mutate evidence or override a deterministic rejection.

## Sentinel training synchronization

Every new Koschei-native security primitive that changes one of these six domains must update the versioned model-training contract before it can be advertised as Sentinel-visible semantics.

Training data must pin an exact Koschei Lang commit and compiler/runtime oracle. Sentinel must learn the converged system rather than an obsolete compatibility-only language surface.

## Acceptance target

A future Secure Alpha convergence gate should demonstrate, with executable tests, that a compromised library or component cannot turn one defect into unrelated filesystem, network, process, secret, signing or persistence authority; that integrity drift is detected before admission; and that Sentinel can request restriction without becoming an authority oracle itself.

The objective is not a claim of perfect security. The objective is to make useful attacker authority require crossing multiple independently verified, fail-closed boundaries tied to the same canonical reality.