# KOSCHEI EXECUTION PROOF ENVELOPE V1

Status: IMPLEMENTED BOOTSTRAP PROTOTYPE / PERMIT-CONSUMED BASE ENVELOPE STABLE

## PURPOSE

Koschei must be able to answer a stronger question than "was an effect allowed?":

> Which exact external evidence, canonical request, native proof world, authority
> decision and single-use execution permit caused this execution boundary to accept
> one consumption?

`ExecutionProofEnvelopeV1` is the machine-verifiable base provenance envelope for that
question. It does not create authority.

The v1 base chain is:

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

It MUST NOT itself claim effect completion or external provider finality.

Higher layers are separate:

`ExecutionProofEnvelopeV1(permit-consumed)`
`-> EffectExecutionReceiptV1`
`-> EffectExecutionProofEnvelopeV1(effect-completed | effect-failed)`
`-> ProviderNativeVerificationReceiptV1(raw provider response bound)`
`-> ExternalProviderFinalityVerdictV1`
`-> ExternalFinalityAttestationV1`
`-> ExternalFinalityProofEnvelopeV1(provider-*)`

Keeping the layers separate preserves the meaning of each proof state.

## CONSUMPTION RECEIPT

`ExecutionPermitLedgerV1.consume(...)` returns `ExecutionConsumptionReceiptV1` only
after permit/decision authentication, exact request-operation-epoch liveness checks,
replay rejection, and insertion into the bootstrap consumed set.

The receipt is HMAC-authenticated under the runtime key. It is evidence of accepted
consumption, not authority.

## ENVELOPE SEAL

The base envelope binds grant, evidence, native MIR, Universe plan, canonical request,
native proof, request-bound proof, authority basis, authorization decision, permit,
consumption receipt, subject scope, operation, epoch and terminal state.

Its own SHA-256 digest is deterministic provenance aggregation, not an independent
signature. Verification re-checks the underlying sealed/authenticated objects.

## AUTHORITY RULE

`ExecutionProofEnvelopeV1.authority` is always `False`.

A proof envelope cannot mint a permit, authorize a new operation, widen capability
scope, change epoch, substitute for native enforcement, or be replayed as authority.

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
- external provider finality by itself.

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

## COMPANION LAYERS

Local effect completion is represented by `EffectExecutionReceiptV1` and
`EffectExecutionProofEnvelopeV1`.

External finality now additionally requires `ProviderNativeVerificationReceiptV1`,
which binds raw provider response bytes and the exact callback-returned external
reference before verdict/finality provenance is admitted.
