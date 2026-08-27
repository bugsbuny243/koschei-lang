# KOSCHEI PROVIDER NATIVE VERIFIER V1

Status: IMPLEMENTED BOOTSTRAP PROTOTYPE / PROVIDER NETWORK ADAPTER REMAINS EXTERNAL

## PURPOSE

`effect-completed` is a local Koschei fact. A provider-finality verdict must not be
minted from caller-selected `state`, transaction digest, or proof digest.

The sanctioned bridge is:

`local effect result bytes`
`-> raw provider response bytes`
`-> trusted provider-native verifier`
`-> ProviderNativeVerificationReceiptV1`
`-> ExternalProviderFinalityVerdictV1`
`-> ExternalFinalityAttestationV1`
`-> ExternalFinalityProofEnvelopeV1`

The provider-native verifier remains provider-specific. Generic Koschei Lang core does
not invent provider JSON schemas, consensus semantics, settlement rules, or network
protocols.

## V1 REFERENCE CONTRACT

For V1, the complete successful effect callback result bytes are the canonical expected
external reference.

For the Pi payment profile this means:

`effect_result_bytes = canonical txid bytes`

The trusted Pi verifier must extract/verify the Pi-native transaction reference from
raw provider response/proof material and return exactly the same canonical txid bytes.
A mismatch is rejected before a sanctioned finality verdict can be derived.

If a future provider needs a richer effect-result structure, it MUST define a separate
canonical extraction contract. V1 must not silently parse `repr`, arbitrary JSON field
order, or caller-selected metadata.

## NATIVE VERIFICATION RECEIPT

`ProviderNativeVerificationReceiptV1` binds:

- provider id,
- exact effect-execution envelope digest,
- exact effect receipt digest,
- exact local effect measurement digest,
- raw provider response digest,
- expected reference digest derived from local effect-result bytes,
- verified reference digest returned by the trusted provider verifier,
- canonical provider proof digest,
- observed epoch,
- provider-native state: pending/finalized/rejected,
- authority=false.

The receipt is HMAC-SHA256 authenticated with a dedicated
`provider_native_verifier_key`.

## TRUST-ROLE SEPARATION

The finality chain now has distinct roles:

- `decision_key`: canonical authorization bridge
- `runtime_key`: permit/consumption
- `effect_key`: local effect measurement
- `provider_native_verifier_key`: raw provider response verification receipt
- `provider_verifier_key`: provider finality verdict
- `finality_key`: Koschei finality attestation

Key separation does not make compromise harmless. It prevents one trust primitive from
implicitly impersonating every later role.

## SANCTIONED FINALITY BRIDGE

`issue_provider_finality_verdict_from_native_receipt_v1(...)` derives provider id,
external reference, provider proof, observed epoch, and state from the authenticated
native verification receipt.

Application/provider code must not select those fields again after native verification.
The older Python low-level verdict issuer remains an implementation primitive for
bootstrap compatibility and unit isolation; production/native API MUST not expose that
primitive as the authoritative path.

## PI PROFILE

`pi_finality_profile_v1.py` fixes `provider_id = pi` and provides:

- `verify_pi_native_payment_response_v1(...)`
- `issue_pi_finality_verdict_v1(...)`

The profile deliberately does not hard-code an unverified Pi backend JSON schema.
Current official Pi materials document payment identifiers and transaction ids (`txid`)
and transaction/payment verification APIs, but raw response parsing/network verification
belongs in the trusted Pi adapter until an exact provider schema is pinned and tested.

## PROTECTS AGAINST

- caller-selected finality state after native verification,
- caller-selected transaction/reference digest after native verification,
- caller-selected provider proof digest after native verification,
- provider response verifying a different transaction than the locally measured effect result,
- raw provider response rebinding after verification,
- native verification receipt field tampering without its key,
- finality verdict rebinding away from the native verification receipt in the full envelope,
- dropping raw provider response provenance from the final end-to-end proof.

## DOES NOT PROTECT AGAINST

- a malicious or buggy provider-native verifier,
- compromised provider-native verifier key,
- provider API/consensus returning false information that the trusted verifier accepts,
- host/runtime compromise,
- network MITM if provider-native verifier fails to authenticate its transport/proof,
- provider reorg/reversal after its own declared finality,
- durable replay-state rollback elsewhere in the execution chain.

## ASSUMPTIONS

- provider-specific verifier performs real native validation before returning its result,
- provider-native verifier canonicalizes the external reference deterministically,
- successful effect-result bytes represent exactly one external reference in V1,
- raw response bytes are the exact bytes observed by the verifier boundary,
- all trust-role keys are separately protected,
- full finality consumers validate `ExternalFinalityProofEnvelopeV1`, not a raw verdict alone.

## FAILURE MODE

If the trusted provider-native verifier lies or is compromised, Koschei can prove which
raw response digest and authenticated verifier receipt were used, but cannot manufacture
truth about the external provider.

If production exposes the low-level caller-parameter verdict issuer as an authoritative
API, the native-verification invariant can be bypassed. Native enforcement must expose
only the receipt-bound bridge.

If a provider response contains a different external reference than the effect-result
bytes, verification must fail before verdict issuance.

## NEXT

Move the provider-native verifier interface behind a runtime-owned adapter ABI with:

1. authenticated transport/provider proof verification,
2. deterministic canonical parsing,
3. provider schema/version identity,
4. verifier implementation measurement/provenance,
5. durable audit storage for raw-response digest + native verification receipt.

For Pi, the next implementation should pin the exact supported Pi payment/backend API
schema/version before any production parser is admitted.
