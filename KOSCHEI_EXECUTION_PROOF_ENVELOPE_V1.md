# KOSCHEI EXECUTION PROOF ENVELOPE V1

Status: IMPLEMENTED BOOTSTRAP PROTOTYPE / PERMIT-CONSUMED BASE ENVELOPE STABLE

## PURPOSE

Koschei must be able to answer a stronger question than "was an effect allowed?":

> Which exact external evidence, canonical request, native proof world, authority
> decision and single-use execution permit caused this execution boundary to accept
> one consumption?

`ExecutionProofEnvelopeV1` is a machine-verifiable provenance envelope for that
question. It does not create authority. It aggregates and re-verifies authority and
integrity already established by existing Koschei components.

The v1 chain is:

`ExternalAdapterGrantV1`
`-> ExternalAdapterEvidenceV1`
`-> NativeSigilMir`
`-> CanonicalEffectRequest`
`-> NativeSigilProofBundle`
`-> RequestBoundProof`
`-> CanonicalAuthorityBasisV1`
`-> AuthorizationDecisionV1`
`-> ExecutionPermitV1`
`-> ExecutionConsumptionReceiptV1`
`-> ExecutionProofEnvelopeV1`

## TERMINAL CLAIM

This base envelope terminates at:

`terminal_state = permit-consumed`

This means the trusted bootstrap execution boundary authenticated and accepted one
exact single-use permit consumption.

`ExecutionProofEnvelopeV1` MUST NOT itself claim `effect-completed`, `payload-applied`,
`payment-settled`, or any remote side-effect completion state. A consumed permit and a
completed side effect are different facts.

Effect execution is represented by the separate higher layer:

`ExecutionProofEnvelopeV1(permit-consumed)`
`-> EffectExecutionReceiptV1`
`-> EffectExecutionProofEnvelopeV1(effect-completed | effect-failed)`

Keeping the layers separate preserves the original meaning of this V1 envelope.

## CONSUMPTION RECEIPT

`ExecutionPermitLedgerV1.consume(...)` returns `ExecutionConsumptionReceiptV1` after:

1. permit authentication,
2. authorization-decision authentication,
3. exact request/operation/epoch liveness checks,
4. replay rejection,
5. insertion into the bootstrap consumed-permit set.

The receipt is HMAC-SHA256 authenticated with the runtime permit key and binds the
exact permit, decision, evidence, operation, canonical request and epoch.

The receipt is not a new permission. It is evidence of accepted consumption.

## ENVELOPE SEAL

The envelope binds grant, evidence, native MIR, Universe plan, canonical request,
native proof, request-bound proof, authority basis, authorization decision, permit,
consumption receipt, subject scope, operation, epoch and terminal state.

Its own `envelope_digest` is deterministic SHA-256 over these links. This digest is NOT
an independent signature. Verification re-checks the underlying authenticated/sealed
objects.

## AUTHORITY RULE

`ExecutionProofEnvelopeV1.authority` is always `False`.

A proof envelope cannot mint a permit, authorize a new operation, widen capability
scope, change epoch, substitute for native enforcement, or be replayed as authority.
It is provenance, not permission.

## PROTECTS AGAINST

- replacing one grant/evidence pair with another after envelope creation,
- replacing the canonical request or native proof world,
- replacing request-bound proof, authority basis, authorization decision or permit,
- inventing/modifying a consumption receipt without the runtime key,
- changing operation, request identity, subject scope or epoch,
- relabeling this base envelope from `permit-consumed` to `effect-completed`,
- presenting an aggregate hash whose authenticated underlying chain does not verify.

## DOES NOT PROTECT AGAINST

- compromise of the native enforcement chain,
- compromise of decision/runtime keys,
- malicious trusted issuer/runtime,
- rollback/fork/loss of consumption state,
- workers with non-shared replay state,
- host compromise or side channels,
- false external evidence admitted earlier,
- downstream effect failure after permit consumption,
- proof that a remote system finalized the requested transition.

## ASSUMPTIONS

- native validators remain fail-closed,
- authority basis is derived from native enforcement,
- decision and runtime keys remain separated,
- current epoch is trusted,
- production replay state is durable/shared/monotonic,
- consumers never treat provenance envelopes as authority.

## FAILURE MODE

If code bypasses the sanctioned ledger and executes an effect directly, this envelope
cannot prove that bypasses did not occur.

If replay state rolls back or forks, divergent runtimes may emit valid-looking
consumption receipts for the same permit. HMAC does not replace monotonic consensus.

If the runtime key is compromised, permit/consumption authenticity in that trust role
is lost.

## EFFECT COMPANION

`EffectExecutionReceiptV1` and `EffectExecutionProofEnvelopeV1` are now implemented as
separate companion layers. They distinguish local `effect-completed` and
`effect-failed` without changing this base envelope's semantics.

Those states still do NOT imply remote Pi/blockchain/bank/cloud settlement or finality.
Provider-finality attestation is the next independent evidence layer.
