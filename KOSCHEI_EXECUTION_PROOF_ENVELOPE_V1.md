# KOSCHEI EXECUTION PROOF ENVELOPE V1

Status: IMPLEMENTED BOOTSTRAP PROTOTYPE / NOT YET NATIVE-ENFORCED

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

V1 terminates at:

`terminal_state = permit-consumed`

This means the trusted bootstrap execution boundary authenticated and accepted one
exact single-use permit consumption.

V1 MUST NOT claim `effect-completed`, `payload-applied`, `payment-settled`, or any
other external side-effect completion state. A consumed permit and a completed side
effect are different facts.

## CONSUMPTION RECEIPT

`ExecutionPermitLedgerV1.consume(...)` now returns
`ExecutionConsumptionReceiptV1` after:

1. permit authentication,
2. authorization-decision authentication,
3. exact request/operation/epoch liveness checks,
4. replay rejection,
5. insertion into the bootstrap consumed-permit set.

The receipt is HMAC-SHA256 authenticated with the runtime permit key and binds:

- exact permit digest,
- exact authorization-decision digest,
- exact external-evidence digest,
- exact operation,
- exact canonical request digest,
- exact consumed epoch,
- consumed=true.

The receipt is not a new permission. It is evidence of accepted consumption.

## ENVELOPE SEAL

The envelope binds:

- grant digest,
- evidence digest,
- native MIR fingerprint,
- Universe plan digest,
- canonical request digest,
- native proof digest,
- request-bound proof digest,
- canonical authority-basis digest,
- authorization-decision digest,
- permit digest,
- consumption-receipt digest,
- subject-scope digest,
- operation,
- epoch,
- terminal state.

Its own `envelope_digest` is deterministic SHA-256 over these links.

The envelope digest is NOT an independent signature. Verification re-checks the
underlying sealed/authenticated objects, including the decision HMAC, permit HMAC and
consumption-receipt HMAC. The aggregate hash prevents silent relabeling of the
verified chain after construction.

## AUTHORITY RULE

`ExecutionProofEnvelopeV1.authority` is always `False`.

A proof envelope cannot:

- mint a permit,
- authorize a new operation,
- widen capability scope,
- change epoch,
- substitute for canonical native enforcement,
- be replayed as authority.

It is provenance, not permission.

## PROTECTS AGAINST

- replacing one grant/evidence pair with another after envelope creation,
- replacing the canonical request or native proof world,
- replacing the request-bound proof,
- substituting a different authority basis,
- substituting a different authorization decision,
- substituting a different permit,
- inventing or modifying a consumption receipt without the runtime key,
- changing operation, request identity, subject scope or epoch inside the envelope,
- relabeling `permit-consumed` as `effect-completed`,
- presenting a deterministic envelope hash whose underlying authenticated chain does
  not verify.

## DOES NOT PROTECT AGAINST

- compromise of the canonical native enforcement chain,
- compromise of decision or runtime keys,
- a malicious trusted issuer/runtime holding those keys,
- rollback, fork or loss of the bootstrap consumption ledger,
- multiple workers with non-shared replay state,
- host compromise, debugger access, memory scraping or side channels,
- false external evidence that was already admitted as valid,
- failure of the real side effect after permit consumption,
- proving that an external system actually applied the requested state transition.

## ASSUMPTIONS

- native MIR, request, proof and request-bound proof validators remain fail-closed,
- canonical authority basis is derived from the native enforcement path,
- authorization decision and execution permit keys remain separated,
- runtime key remains secret from observer/provider code,
- current epoch supplied during consumption is trusted,
- production replay state will be durable, shared and monotonic,
- consumers do not treat the envelope itself as authority.

## FAILURE MODE

If application code can bypass the sanctioned permit ledger and execute the effect
directly, the envelope only proves the sanctioned path for executions that used it;
it cannot prove bypasses did not happen.

If replay state rolls back or forks, more than one valid-looking consumption receipt
may be emitted for the same permit by compromised/divergent runtimes.

If the runtime key is compromised, an attacker can forge permit and consumption HMAC
material within that trust role.

If the side effect fails after consumption, V1 intentionally stops at
`permit-consumed`; it must not be upgraded to a completion claim by convention.

## NEXT

Add an effect-execution receipt produced by the sanctioned runtime itself, not by a
caller-supplied result digest. The runtime must:

1. consume the exact permit,
2. execute one bounded effect callback,
3. measure a canonical effect-result representation,
4. emit an authenticated success/failure receipt bound to the consumption receipt,
5. extend the envelope terminal state only when that receipt verifies.

That next layer is where Koschei can safely distinguish:

`permit-consumed`
from
`effect-attempted`
from
`effect-completed`.
