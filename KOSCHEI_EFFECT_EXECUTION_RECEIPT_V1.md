# KOSCHEI EFFECT EXECUTION RECEIPT V1

Status: IMPLEMENTED BOOTSTRAP PROTOTYPE / LOCAL EFFECT MEASUREMENT WIRED / PROVIDER NATIVE VERIFICATION SEPARATE

## PURPOSE

A consumed execution permit is not proof that the requested effect completed. Koschei
therefore separates permit consumption from effect execution and measures the
runtime-observed callback outcome itself.

Sanctioned local path:

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
4. A successful callback must return canonical `bytes`.
5. Successful returned bytes are measured under a domain-separated result context.
6. A caught normal `Exception` becomes `effect-failed` under a separate failure-measurement domain.
7. The effect observation is HMAC-SHA256 authenticated with a dedicated `effect_key`.
8. `effect_key` is distinct from decision/runtime/finality trust roles.
9. The effect receipt carries `authority = false`.
10. The higher effect envelope layers over the stable `permit-consumed` envelope.

## TERMINAL STATES

`effect-completed` means the local sanctioned callback returned canonical bytes and the
exact returned bytes were measured.

`effect-failed` means the callback raised a normal Exception or violated the bytes-result
contract. The permit remains consumed.

Neither state is remote provider finality.

## EXTERNAL REFERENCE BINDING

For V1 provider-finality flows, the successful callback result may itself be the
canonical external reference.

For the Pi payment profile:

`effect_result_bytes = canonical txid bytes`

`ProviderNativeVerificationReceiptV1` later requires the trusted Pi-native verifier to
extract/verify the same canonical txid from the exact raw provider response bytes.
A different txid fails before sanctioned finality-verdict derivation.

Providers needing richer effect results must define a later canonical extraction
contract rather than silently parsing arbitrary object/JSON representations.

## PROTECTS AGAINST

- caller-selected success/failure labels,
- caller injection of a precomputed result measurement,
- operation/request/epoch widening after permit consumption,
- moving an effect receipt to a different canonical request/permit/consumption chain,
- changing result measurement or terminal state after receipt issuance,
- forging a locally valid effect receipt without the effect key,
- replaying the same permit through one authoritative ledger before callback invocation.

## DOES NOT PROTECT AGAINST

- malicious/compromised effect executor holding `effect_key`,
- host/runtime compromise,
- process death between irreversible external effect and receipt creation,
- external provider lying or returning misleading data,
- asynchronous settlement/finality after callback return,
- replay-ledger rollback/fork/non-shared state,
- side channels or memory disclosure.

## ASSUMPTIONS

- effect key is isolated from provider/observer input,
- trust-role keys remain separated,
- canonical request and permit chain verify fail-closed,
- production consumption state is durable/monotonic,
- effect callbacks expose canonical bytes.

## FAILURE MODE

If the callback performs an irreversible external effect and the process dies before
receipt authentication, Koschei may observe an external effect without an effect receipt.
V1 does not solve distributed transaction atomicity.

If a callback returns bytes before the external provider reaches finality,
`effect-completed` proves only local callback completion.

## PI EXAMPLE

`Pi payment.observe evidence`
`-> native Koschei ALLOW`
`-> execution permit`
`-> consume once`
`-> runtime calls payment/subscription adapter`
`-> callback returns canonical txid bytes`
`-> effect-completed receipt`
`-> raw Pi response verified against same txid`
`-> provider-native verification receipt`
`-> provider finality provenance`

## NEXT

Move provider-native verification behind a runtime-owned adapter ABI with pinned
provider schema/version, authenticated transport/proof verification, implementation
measurement, and durable audit storage.
