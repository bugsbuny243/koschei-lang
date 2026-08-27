# KOSCHEI EXECUTION PERMIT V1

Status: IMPLEMENTED BOOTSTRAP PROTOTYPE / NOT YET NATIVE-ENFORCED

## PURPOSE

External evidence is not execution authority, and the permit issuer must not choose
new authority on its own.

The sanctioned chain is now:

`External Evidence -> Canonical Authority/Policy Evaluation -> Authenticated Authorization Decision -> Authenticated Execution Permit -> Single Consume`

A permit is a narrowed transport of an already-authenticated `allow` decision. It is
not identity, ambient permission, or a replacement for canonical capability checks.

## SEMANTIC INVARIANTS

For permit P, decision D, evidence E and grant G:

1. D must authenticate under the dedicated decision key.
2. D.outcome must equal `allow`.
3. P is bound to D.decision_digest.
4. P is bound to E.evidence_digest.
5. P inherits provider, consumer, subject, operation, request and epoch from D/G/E.
6. The permit mint API does not accept an independently chosen operation or request.
7. P is separately authenticated with a runtime permit key of at least 32 bytes.
8. P is valid only in its bound epoch and exact request/operation.
9. P is single-use through the sanctioned replay ledger.
10. External evidence never becomes ambient authority merely by existing.

## KEY SEPARATION

- canonical decision boundary: `decision_key`
- execution permit boundary: `runtime_key`

A permit cannot substitute for a decision and a decision cannot substitute for a
permit. Both authenticated links are required by the bootstrap contract.

## AUTHORITY RULE

`AuthorizationDecisionV1` contains authenticated `authority_basis_digest` and
`policy_digest` fields. `ExecutionPermitV1` then binds the resulting decision digest.

Therefore the provenance chain is:

`authority basis + policy + evidence + subject + operation + request + epoch`
`-> authorization decision digest`
`-> permit digest`
`-> single consumption`

The remaining bootstrap limitation is that the Python decision issuer still accepts
`authority_basis_digest` as an input. Native integration must obtain that digest
directly from the canonical capability/authority engine rather than caller input.

## BOOTSTRAP IMPLEMENTATION

- `koschei/authorization_decision_v1.py`
- `koschei/execution_permit_v1.py`
- `AuthorizationDecisionV1`
- `ExecutionPermitV1`
- `ExecutionPermitLedgerV1`

Both decision and permit authentication use HMAC-SHA256 with separate keys and
constant-time MAC comparison.

## PROTECTS AGAINST

- permit minting from authenticated `deny` or `contain` decisions,
- permit minter selecting a wider operation than the canonical decision,
- changing decision, operation, request, evidence, subject, provider, consumer or epoch,
- changing authority-basis or policy identity after decision issuance,
- cross-request and cross-decision reuse,
- epoch replay,
- same-permit replay through one trusted ledger,
- forgery without the relevant HMAC keys under stated assumptions.

## DOES NOT PROTECT AGAINST

- compromise of decision or runtime permit keys,
- a malicious trusted canonical decision issuer,
- fake authority-basis input accepted by the bootstrap Python issuer,
- incorrect canonical policy/capability evaluation,
- rollback/fork/loss of the consumption ledger,
- workers that do not share authoritative replay state,
- host/runtime compromise,
- false external evidence admitted earlier in the chain.

## ASSUMPTIONS

- decision and permit keys are separately held outside observer/provider control,
- native authority/policy evaluation is fail-closed,
- epoch state is trusted and monotonic,
- authoritative consumers share durable monotonic replay state,
- external evidence admission already succeeded.

## FAILURE MODE

Authority discipline collapses if application/provider code can invoke the native
decision issuer with attacker-chosen authority basis while bypassing canonical
capability evaluation.

Authentication collapses if either HMAC key is exposed.

Replay protection collapses if consumption state is reset, forked or not shared.

This Python implementation therefore demonstrates semantics and adversarial
invariants; it is not proof of native isolation.

## PI EXAMPLE

`Pi payment.observe evidence`
`-> canonical subscription capability + policy evaluation`
`-> allow decision(operation=subscription.enable, request=R, epoch=E)`
`-> permit inherits decision digest/operation/request`
`-> consume once`
`-> exact subscription state transition`

There is no permit API argument that can replace `subscription.enable` with
`treasury.withdraw` after the canonical decision.

## NEXT NATIVE STEP

Wire `authority_basis_digest` directly to the repo's canonical capability
consolidation path and emit a deterministic proof envelope covering evidence,
authorization decision, permit consumption and final effect result.
