# KOSCHEI EXECUTION PERMIT V1

Status: IMPLEMENTED BOOTSTRAP PROTOTYPE / CANONICAL AUTHORITY BASIS WIRED / AUTHENTICATED CONSUMPTION RECEIPT WIRED / DURABLE NATIVE CONSUMPTION PENDING

## PURPOSE

External evidence is not execution authority, and the permit issuer must not choose
new authority on its own.

The sanctioned chain is now:

`External Evidence`
`-> Native MIR / Canonical Request / Request-Bound Proof`
`-> CanonicalAuthorityBasisV1`
`-> AuthorizationDecisionV1`
`-> ExecutionPermitV1`
`-> Single Consume`
`-> ExecutionConsumptionReceiptV1`
`-> ExecutionProofEnvelopeV1`

A permit is a narrowed transport of an already-authenticated native `allow` decision.
It is not identity, ambient permission, or a replacement for Koschei's native
enforcement chain.

## SEMANTIC INVARIANTS

For permit P, decision D, evidence E and grant G:

1. D is derived from a verified `CanonicalAuthorityBasisV1`.
2. D must authenticate under the dedicated decision key.
3. D.outcome must equal `allow`.
4. P is bound to D.decision_digest.
5. P is bound to E.evidence_digest.
6. P inherits provider, consumer, subject, operation, canonical request digest and epoch from D/G/E.
7. Permit minting accepts no independently chosen operation/request.
8. P is separately HMAC-authenticated with a runtime permit key of at least 32 bytes.
9. P is live only in its bound epoch and exact request/operation.
10. P is single-use through the sanctioned replay ledger.
11. Successful consumption emits an authenticated `ExecutionConsumptionReceiptV1`.
12. External evidence never becomes ambient authority merely by existing.
13. A consumption receipt proves accepted permit consumption, not external side-effect completion.

## KEY SEPARATION

- `decision_key`: authenticates canonical-authority -> authorization-decision transition.
- `runtime_key`: authenticates authorization-decision -> execution-permit and consumption-receipt transitions.

The keys have different trust roles and must remain separate.

## AUTHORITY PROVENANCE

`authority_basis_digest` is no longer caller-supplied. It is derived from the existing
native enforcement chain and binds:

- native MIR fingerprint,
- Universe-plan identity,
- canonical effect request,
- request-bound proof,
- native proof bundle,
- native enforcement decision,
- canonical subject identity,
- operation,
- epoch,
- ALLOW/DENY/CONTAIN outcome.

For v1, the authorization decision's `policy_digest` is derived from the sealed native
MIR fingerprint. The permit then authenticates the full authorization decision digest.

The provenance chain is therefore:

`native authority basis + external evidence`
`-> authorization decision digest`
`-> permit digest`
`-> authenticated consumption receipt`
`-> execution proof envelope`

## BOOTSTRAP IMPLEMENTATION

- `koschei/canonical_authority_basis_v1.py`
- `koschei/authorization_decision_v1.py`
- `koschei/execution_permit_v1.py`
- `koschei/execution_proof_envelope_v1.py`
- `CanonicalAuthorityBasisV1`
- `AuthorizationDecisionV1`
- `ExecutionPermitV1`
- `ExecutionConsumptionReceiptV1`
- `ExecutionPermitLedgerV1`
- `ExecutionProofEnvelopeV1`

Decision, permit and consumption-receipt authentication use HMAC-SHA256 with
constant-time MAC comparison. The aggregate proof envelope uses deterministic SHA-256
and re-verifies the authenticated lower layers; its hash is not a new authority key.

## PROTECTS AGAINST

- external/provider code injecting an arbitrary authority-basis digest,
- permit minting from native DENY or CONTAIN decisions,
- decision or permit issuer selecting a wider operation than the canonical request,
- changing request/evidence/subject/provider/consumer/epoch after issuance,
- cross-request and cross-decision reuse,
- epoch replay,
- same-permit replay through one trusted ledger,
- silent relabeling of a verified consumption chain inside the proof envelope,
- forgery without the relevant HMAC keys under stated assumptions.

## DOES NOT PROTECT AGAINST

- compromise or bugs inside the native MIR/Library/proof/enforcement chain,
- compromise of decision or permit/runtime keys,
- malicious code inside a trusted issuer/runtime compartment,
- rollback/fork/loss of permit-consumption state,
- workers that do not share authoritative replay state,
- host/runtime compromise,
- false external evidence admitted earlier in the chain,
- side-channel or memory disclosure,
- failure of the real side effect after permit consumption.

## ASSUMPTIONS

- native authority/proof evaluation is fail-closed,
- decision and permit/runtime keys remain separated and outside provider/observer control,
- canonical request epoch comes from trusted Koschei lifecycle state in production,
- authoritative consumers share durable monotonic replay state,
- external evidence admission already succeeded,
- callers do not interpret `permit-consumed` as `effect-completed`.

## FAILURE MODE

Authority integrity fails if the native enforcement path can be bypassed or a trusted
issuer/key is compromised.

Authentication fails if either HMAC trust role is exposed.

Replay protection fails if consumption state is reset, forked or not shared.

The current Python ledger is therefore a semantic/bootstrap implementation, not a
claim of durable cross-process replay protection.

A valid consumption receipt can exist even if the downstream side effect fails after
consumption. That is why V1 terminates at `permit-consumed`.

## PI EXAMPLE

`Pi payment.observe evidence`
`-> sealed Koschei request: subscription.enable`
`-> native request-bound proof + ALLOW`
`-> canonical authority basis`
`-> AuthorizationDecision(subscription.enable)`
`-> permit inherits exact decision/request`
`-> consume once`
`-> authenticated consumption receipt`
`-> proof envelope terminal=permit-consumed`

Neither the Pi adapter nor the permit minter gets an argument that can rewrite that
operation into `treasury.withdraw`.

## NEXT NATIVE STEP

Add a sanctioned **effect execution receipt** that consumes the permit, executes one
bounded effect callback and measures the actual canonical outcome. Only that runtime-
produced receipt may extend the proof-envelope terminal state from `permit-consumed`
toward `effect-attempted` or `effect-completed`.

Then move replay state and key custody into a runtime-owned monotonic/transactional
boundary.
