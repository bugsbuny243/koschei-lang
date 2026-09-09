# KOSCHEI_AUTHORIZATION_STATE_TRANSITION_V1

Status: Experimental / additive / provider-independent

## Purpose

Koschei authorization is a time-evolving state, not a credential property frozen at issuance time.
This contract adds an execution-time authorization state machine without replacing or widening the existing native authority, `AuthorizationDecisionV1`, `KoscheiExecutionPermitV1`, capability broker, execution proof, or OS-confinement gates.

Canonical security flow:

```text
Principal -> IdentityEvidence
Intent -> IntentCommitment
Authority -> Capability -> ConstraintSet -> DelegationChain
AuthorizationState[n] -> AuthorizationTransition[n->n+1]
ProposedAction -> RuntimeDecision -> ExecutionPermit
Native Broker -> OS Confinement -> Execution
ConsumptionProof -> OutcomeEvidence -> AuditGraph
```

## Hard invariants

```text
INTENT != CAPABILITY
INTENT != EXECUTION_PERMISSION
AUTHORIZED_AT_START != AUTHORIZED_AT_EXECUTION
VALID_CHILD_DELEGATION requires VALID_PARENT_NOW
VALID_EXECUTION requires CURRENT_AUTHORIZATION_STATE_HEAD
AUDIT_LOG != AUDIT_PROOF
```

An intent commitment answers why/under which mandate an action was proposed. It carries no ambient authority.
A capability/delegation constrains what a principal may do.
An authorization state answers what authority is effective now.
An execution permit binds one exact accepted action to the existing Koschei execution path.
Execution evidence answers what actually happened.

Historical validity is insufficient:

```text
was_valid(parent) != valid(parent, now)
was_active(state) != current_state(state, now)
```

A child delegation is rejected when its parent is currently revoked, expired, unknown, stale, incorrectly signed, or no longer permits redelegation.
An old active authorization state is rejected after the monotonic state head advances to a newer transition.

## Canonical constraint lattice

V1 uses provider-independent attenuation axes:

- `resources`
- `operations`
- `arguments`
- `magnitude_max`
- `valid_from_epoch` / `expires_before_epoch`
- `audience`
- `delegation_depth`
- `redelegation`

A child delegation may only attenuate its parent. A delegation hop consumes depth. A false redelegation bit cannot become true. Time cannot widen. Magnitude cannot increase. Resource, operation, argument, and audience sets cannot broaden.

Provider-specific fields such as JWT claims, OAuth parameters, DID/VC structures, workload identity fields, consent encodings, or protocol-specific revocation objects do not belong in this core. Adapters verify them and project only canonical facts into this contract.

## Authorization transitions

V1 defines explicit transitions:

- `NARROW`: reduce currently effective authority.
- `STEP_UP`: restore or expand effective authority only inside the immutable outer authority ceiling.
- `SUSPEND`: make current authority non-executable.
- `REVOKE`: terminal denial.
- `EXPIRE`: terminal expiry.

Initial issuance creates the first active state and is not modeled as an arbitrary transition from caller-controlled data.

A suspended state cannot silently recover. V1 intentionally has no implicit resume transition. Revoked and expired states are terminal.

## Monotonic current-state head

A hash-linked transition history alone is insufficient. After a revocation an attacker could otherwise replay an older, correctly sealed `active` state.

`AuthorizationStateLedgerV1` therefore maintains the current state digest for each subject and requires every committed transition to extend that exact head. Execution snapshots obtained through the ledger reject historical state rollback.

The current implementation is an in-memory bootstrap ledger. It proves the invariant inside one trusted runtime only. Production acceptance requires durable/shared monotonic state with crash/restart, replica, rollback, and concurrency tests. This limitation remains an explicit security gate and must not be hidden by the existence of the bootstrap class.

## Execution-time snapshot

Before an effect may proceed, Koschei must build `ExecutionAuthorizationSnapshotV1` from:

1. the sealed **current monotonic** authorization state;
2. a freshly verified delegation chain at the execution epoch;
3. the immutable delegation-authority commitment;
4. the effective constraint digest;
5. the original intent commitment digest.

Fresh verification data is separate from the stable delegation-authority commitment. This permits current signature/revocation checks without rewriting the historical authority identity.

The snapshot itself carries no ambient authority. It is a deterministic proof input for the existing decision/permit pipeline.

## Relationship to existing V1 contracts

This change MUST NOT add fields to strict `AuthorizationDecisionV1` or `KoscheiExecutionPermitV1` schemas.

The existing execution permit already binds exact request, operation, epoch, canonical authority basis, decision evidence, replay state and runtime authentication. The new state/transition layer belongs before decision/permit issuance and should be bound through a future additive authority-basis/profile digest rather than mutating strict V1 objects.

```text
IntentCommitment
  -> DelegationChain(current)
  -> AuthorizationStateLedger(current head)
  -> ExecutionAuthorizationSnapshotV1
  -> existing native authority/evidence verification
  -> AuthorizationDecisionV1
  -> KoscheiExecutionPermitV1
  -> existing broker / confinement / execution proof
```

No transition object can bypass native enforcement. No external adapter can mint execution authority merely by producing an authorization snapshot.

## Audit proof direction

A normal log records statements made by a component. A Koschei audit proof must make the relevant relationships independently verifiable:

```text
IdentityEvidence
  -> IntentCommitment
  -> DelegationChain
  -> AuthorizationState / ordered transitions / monotonic head
  -> ExecutionAuthorizationSnapshot
  -> RuntimeDecision
  -> ExecutionPermit
  -> ConsumptionProof
  -> OutcomeEvidence
  -> AuditGraphRoot
```

`AuditGraph` is a later additive contract. This document does not claim that a full cryptographic audit graph, transparency publication, remote attestation, or external standards adapter is already production-complete.

## Standards boundary

External agent-audit, delegation, intent-token, OAuth, workload-identity, attestation, transparency, DID/VC, and related standards/drafts are profiles/adapters around the Koschei canonical model. None is a Lang core dependency or a provider-specific trust root.

## Security status

Implementation of `authorization_transition_v1.py`, `authorization_state_ledger_v1.py`, and their unit tests establishes the provider-independent state-machine and bootstrap rollback-prevention primitives only. It does **not** by itself close `LANG-01`, `LANG-02`, or `SUPPLY-02`; durable monotonic state, real broker/worker OS confinement, canonical execution acceptance, provenance/release-root acceptance, and the shared T01-T14 suite remain separate gates.
