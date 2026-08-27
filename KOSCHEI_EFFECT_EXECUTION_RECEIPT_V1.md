# KOSCHEI EFFECT EXECUTION RECEIPT V1

Status: IMPLEMENTED BOOTSTRAP PROTOTYPE / LOCAL RUNTIME EFFECT ATTESTATION / REMOTE FINALITY NOT PROVEN

## PURPOSE

A consumed execution permit is not proof that the requested effect completed.
Koschei therefore separates permit consumption from effect execution and measures the
runtime-observed callback outcome itself.

Sanctioned path:

`ExecutionPermitV1`
`-> ExecutionConsumptionReceiptV1`
`-> runtime invokes exact effect callback`
`-> EffectExecutionReceiptV1`
`-> EffectExecutionProofEnvelopeV1`

No caller argument may declare `effect-completed` or provide a precomputed result digest.

## SEMANTIC INVARIANTS

1. The exact permit must be authenticated and consumed first.
2. The canonical request digest, operation and epoch must match the permit.
3. The sanctioned executor invokes the callback itself.
4. A successful callback must return `bytes`; arbitrary Python object serialization is not accepted as canonical measurement.
5. Successful returned bytes are measured with SHA-256 under a domain-separated result context.
6. A caught normal `Exception` becomes `effect-failed` and is measured from its qualified exception type plus message under a separate domain.
7. The effect observation is HMAC-SHA256 authenticated with a dedicated `effect_key`.
8. `effect_key` is distinct in role from `decision_key` and permit/consumption `runtime_key`.
9. The effect receipt carries `authority = false`.
10. The higher effect envelope layers over the existing `permit-consumed` envelope rather than changing the older envelope's meaning.

## TERMINAL STATES

`effect-completed`

The runtime callback returned canonical bytes and the exact returned bytes were measured.
This means local callback completion only.

`effect-failed`

The callback raised a normal Python `Exception`, or violated the required bytes-result
contract. The permit remains consumed; the runtime does not silently make it reusable.

## PROTECTS AGAINST

- caller-selected success/failure labels,
- caller injection of a precomputed result measurement,
- operation/request/epoch widening after permit consumption,
- moving an effect receipt to a different canonical request/permit/consumption chain,
- changing result measurement or terminal state after receipt issuance,
- forging a locally valid effect receipt without the effect key under stated HMAC assumptions,
- replaying the same permit through one authoritative ledger before callback invocation.

## DOES NOT PROTECT AGAINST

- a malicious or compromised effect executor holding `effect_key`,
- host/runtime compromise,
- process kill, power loss, or fatal runtime termination between external side effect and receipt creation,
- external provider lying or returning a misleading response,
- asynchronous settlement/finality occurring after callback return,
- replay-ledger rollback, fork, or non-shared state,
- side channels or memory disclosure,
- proof that remote Pi/blockchain/bank/cloud state actually finalized.

## ASSUMPTIONS

- `effect_key` is at least 32 bytes and isolated from provider/observer input,
- `decision_key`, `runtime_key`, and `effect_key` remain separate trust roles,
- the canonical request and permit chain has already been verified fail-closed,
- authoritative execution uses durable monotonic consumption state in production,
- effect callbacks expose canonical result bytes rather than unstable object representations.

## FAILURE MODE

If the callback performs an irreversible external effect and the process dies before the
receipt is authenticated, Koschei may have an external effect without an effect receipt.
This V1 does not solve distributed transaction atomicity.

If a callback returns `bytes` claiming success before the external provider reaches finality,
`effect-completed` proves only that the local callback completed with those bytes. It does
not prove remote settlement.

If replay state forks, the same permit may execute in more than one fork. HMAC receipts do
not repair a broken monotonic consumption authority.

## PI EXAMPLE

`Pi payment.observe evidence`
`-> native Koschei ALLOW`
`-> execution permit`
`-> consume once`
`-> runtime calls subscription-enable adapter`
`-> adapter callback returns canonical response bytes`
`-> effect-completed receipt`

A later Pi-specific settlement/finality attestation may bind the provider's final transaction
state to this receipt. That is a separate layer and must not be inferred from local callback
completion.

## NEXT

Define provider-finality attestation as a separate non-authoritative evidence layer and bind
it to `EffectExecutionReceiptV1`. For Pi this should prove the exact provider transaction or
state transition reached the required settlement/finality condition without moving Pi SDK
semantics into Koschei Lang core.
