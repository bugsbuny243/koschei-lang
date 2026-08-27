# KOSCHEI EXECUTION PERMIT V1

Status: IMPLEMENTED BOOTSTRAP PROTOTYPE / NOT YET NATIVE-ENFORCED

## PURPOSE

External facts are not execution authority.

The external-adapter boundary can admit a Pi payment observation, an identity fact,
or a future cloud/bank/chain fact as sealed evidence. That evidence must not directly
unlock a Koschei operation.

The v1 execution-permit boundary inserts a narrower transition:

`External Evidence -> Canonical Policy/Capability Check -> Authenticated Permit -> Single Execution Request`

A permit is not a user identity and is not ambient permission. It is an authenticated,
request-bound statement that a trusted Koschei runtime may accept for one exact
operation during one exact epoch and consume once.

## SEMANTIC INVARIANTS

For permit P derived from sealed external evidence E and grant G:

1. P is bound to E.evidence_digest.
2. P is bound to G.provider_id, G.consumer_id, and G.subject_scope_digest.
3. P names exactly one operation.
4. P is bound to one request/challenge digest.
5. P is valid only in E.observed_epoch.
6. P is authenticated with a runtime-held HMAC key of at least 32 bytes.
7. P is single-use through the sanctioned consumption ledger.
8. Changing operation, request, evidence, subject, provider, consumer, or epoch invalidates authentication or liveness.
9. External evidence never becomes ambient disk/network/process/treasury authority merely by existing.

## AUTHORITY RULE

HMAC authentication proves that the trusted permit issuer produced P. It does NOT,
by itself, prove that the requested operation was authorized by Koschei policy.

Therefore the sanctioned mint path MUST occur only after the canonical Koschei
capability/policy layer has established that the requested operation is already
permitted for the bound subject and consumer. The permit narrows and transports
that decision; it must never manufacture a new authority category.

A future native integration should bind the permit cryptographically to the digest
of the already-validated canonical capability/policy decision.

## BOOTSTRAP IMPLEMENTATION

`koschei/execution_permit_v1.py`

- `ExecutionPermitV1`
- `mint_execution_permit_v1(...)`
- `ExecutionPermitLedgerV1`

Authentication uses HMAC-SHA256 with a runtime-held key. Permit comparison uses
constant-time `hmac.compare_digest`.

The request digest acts as a challenge/request binding. Capturing a permit for one
request does not make it valid for a different request in the same epoch.

The ledger rejects a second consumption of the same permit digest.

## PROTECTS AGAINST

- changing the permitted operation after minting,
- changing request/challenge binding after minting,
- rebinding a permit to different external evidence,
- rebinding provider/consumer/subject fields,
- using a permit after its epoch rotates,
- replaying the same permit twice through one trusted ledger,
- forging a valid permit without the runtime HMAC key under the stated cryptographic assumptions,
- treating external Pi/payment evidence itself as direct execution authority.

## DOES NOT PROTECT AGAINST

- compromise or exfiltration of the runtime HMAC key,
- a malicious trusted permit issuer,
- a caller that mints before canonical capability/policy authorization,
- rollback/loss of the consumption ledger,
- replay across processes or machines that do not share trusted consumption state,
- host/runtime compromise,
- side channels, debugger inspection, crash dumps, or memory disclosure,
- false external evidence admitted by a compromised provider-specific adapter.

## ASSUMPTIONS

- the HMAC key is generated and held outside observer control,
- canonical Koschei policy/capability authorization runs before permit minting,
- runtime epoch state is trusted and monotonic for the relevant execution universe,
- consumption state cannot be silently rolled back,
- provider-specific evidence admission has already succeeded.

## FAILURE MODE

Replay protection collapses if runtime consumption state is reset, forked, or not
shared across authoritative execution workers.

Authority discipline collapses if arbitrary code can call the mint function with
the runtime key without first passing canonical policy/capability validation.

Authentication collapses if the runtime key is exposed.

Therefore this Python implementation is a semantic/bootstrap prototype, not proof
that bypass is physically impossible. The native runtime must make the sanctioned
mint/consume path authoritative and keep key custody plus consumption state inside
a trusted compartment.

## PI EXAMPLE

A Pi settlement observation should follow this shape:

`Pi payment.observe evidence`
`-> Koschei subscription policy check`
`-> permit(operation=subscription.enable, request=<digest>, epoch=E)`
`-> consume once`
`-> exact subscription state transition`

It must NOT become:

`Pi payment observed -> user now has arbitrary Koschei authority`

## NEXT NATIVE STEP

Bind `ExecutionPermitV1` to the digest of a verified canonical Koschei capability or
policy decision and move single-use consumption from the Python in-memory ledger to
a runtime-owned monotonic/transactional state boundary.
