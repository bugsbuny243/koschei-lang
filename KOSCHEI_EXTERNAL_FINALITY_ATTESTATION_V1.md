# KOSCHEI EXTERNAL FINALITY ATTESTATION V1

Status: IMPLEMENTED BOOTSTRAP PROTOTYPE / PROVIDER-NATIVE RAW-RESPONSE VERIFICATION WIRED / NETWORK ADAPTER EXTERNAL

## PURPOSE

`effect-completed` is a local runtime fact. It is not remote settlement, blockchain
finality, bank settlement, cloud commit durability, or payment finality.

Koschei therefore separates local effect provenance from external-provider finality:

`EffectExecutionProofEnvelopeV1(effect-completed)`
`-> ProviderNativeVerificationReceiptV1(raw response bound)`
`-> ExternalProviderFinalityVerdictV1`
`-> ExternalFinalityAttestationV1`
`-> ExternalFinalityProofEnvelopeV1`

Provider-native verification, provider verdict authentication, and Koschei finality
attestation are distinct trust roles.

## SEMANTIC STATES

Provider-native/verifier states:

- `pending`
- `finalized`
- `rejected`

Finality proof-envelope states:

- `provider-pending`
- `provider-finalized`
- `provider-rejected`

A caller cannot turn `pending` into `provider-finalized` by changing a label because
the native verification receipt, provider verdict, and finality attestation are all
bound/authenticated in the full envelope.

## TRUST-ROLE SEPARATION

- `provider_native_verifier_key`: authenticates raw provider response verification receipt.
- `provider_verifier_key`: authenticates the provider finality verdict derived from that receipt.
- `finality_key`: authenticates the Koschei finality attestation.

These roles remain separate from decision/runtime/effect keys.

## PROVIDER-NATIVE VERIFICATION

`ProviderNativeVerificationReceiptV1` binds:

- provider id,
- exact local effect envelope,
- exact effect receipt/measurement,
- raw provider response digest,
- expected external-reference digest derived from local effect-result bytes,
- verified reference digest returned by the trusted provider verifier,
- canonical provider proof digest,
- observed epoch,
- pending/finalized/rejected state,
- authority=false.

For V1 the complete successful effect-result bytes are the expected external reference.
For Pi payment integration these bytes are the canonical `txid` bytes.

The provider-native verifier must return the same canonical reference bytes. Mismatch
is rejected before sanctioned verdict derivation.

## PROVIDER VERDICT BINDING

`issue_provider_finality_verdict_from_native_receipt_v1(...)` is the sanctioned bridge.
It derives provider id, external reference, provider proof, epoch, and state from the
authenticated native verification receipt. Application code does not choose those
fields again.

The older low-level Python verdict issuer remains a bootstrap implementation primitive;
production/native API must not expose it as the authoritative route.

## FINALITY ATTESTATION BINDING

`ExternalFinalityAttestationV1` verifies the provider verdict, then authenticates:

- provider verdict digest,
- provider identity,
- effect-envelope digest,
- external-reference digest,
- provider-proof digest,
- observed epoch,
- provider terminal state.

The finality attestation is provenance, not permission.

## END-TO-END FINALITY PROOF

A raw provider verdict or finality attestation MUST NOT be treated as full Koschei
finality proof.

`ExternalFinalityProofEnvelopeV1` now re-verifies the complete prior execution chain
AND the raw-response native verification receipt:

`External evidence`
`-> native MIR / canonical request / native proof`
`-> canonical authority basis`
`-> authorization decision`
`-> execution permit`
`-> permit consumption`
`-> local effect receipt`
`-> local effect proof envelope`
`-> raw provider response`
`-> provider-native verification receipt`
`-> provider verdict`
`-> finality attestation`
`-> finality proof envelope`

The final envelope carries both `provider_native_verification_receipt_digest` and
`raw_provider_response_digest` so provider-response provenance cannot disappear after
verdict minting.

## PI PROFILE

`koschei/pi_finality_profile_v1.py` fixes provider id = `pi` and exposes:

- `verify_pi_native_payment_response_v1(...)`
- `issue_pi_finality_verdict_v1(...)`

The profile does not invent or hard-code an unverified Pi JSON schema. Current official
Pi materials expose payment identifiers and transaction ids (`txid`) and APIs for
transaction/payment verification; actual raw-response parsing, authenticated transport,
and Pi-native validation remain in the trusted Pi adapter until an exact supported
schema/version is pinned.

Pi SDK networking, wallet custody, consensus, and payment settlement remain outside
Koschei Lang core.

## PROTECTS AGAINST

- relabeling local `effect-completed` as provider finality,
- caller-selected finality state/reference/proof after native verification,
- raw provider response rebinding after verification,
- provider response proving a different reference than the callback-returned reference,
- changing provider-native receipt fields without its key,
- changing provider verdict state/reference/proof after issuance,
- moving a verdict to an effect envelope with a different measurement,
- using one key to impersonate all finality trust roles,
- changing pending/rejected attestations into finalized attestations,
- treating a raw provider verdict as complete end-to-end Koschei provenance,
- dropping raw response/native verifier provenance from the full finality envelope.

## DOES NOT PROTECT AGAINST

- a compromised or malicious provider-native verifier,
- incorrect Pi/provider-native verification logic,
- compromise of provider-native verifier/provider-verifier/finality keys,
- provider reorgs or semantic reversals after the provider's own claimed finality model,
- lying/compromised external provider infrastructure,
- host/runtime compromise, memory scraping, debuggers, or side channels,
- replay-state rollback/fork earlier in the execution chain,
- process death between irreversible remote action and local receipt creation.

## ASSUMPTIONS

- `EffectExecutionProofEnvelopeV1` is fully re-verified before full finality proof sealing,
- provider-native verification is fail-closed and runs outside untrusted application code,
- provider-native verifier returns deterministic canonical reference/proof bytes,
- raw response bytes are the exact bytes observed by the verifier boundary,
- all finality trust-role keys are separately protected,
- provider proof identifies the exact provider evidence used,
- observed epoch is trusted lifecycle metadata for the protected Koschei universe.

## FAILURE MODE

The finality claim is only as strong as the provider-native verifier. If it accepts a
false provider response or wrong provider semantics, Koschei can prove which raw-response
digest and verifier receipt were used but cannot manufacture external truth.

If production exposes the low-level caller-parameter verdict issuer as authoritative,
the native-verification invariant can be bypassed. Native API must expose only the
receipt-bound bridge.

If an external provider later reverses something it previously defined as final,
Koschei's receipt remains historical evidence of what was verified at that time; it
is not a guarantee that external consensus can never violate its own model.

## NEXT

1. Move provider-native verifier behind a runtime-owned adapter ABI.
2. Pin provider schema/version identity and verifier implementation measurement.
3. Add authenticated transport/proof validation in the Pi adapter implementation.
4. Move finality keys and replay/audit state into runtime-owned durable compartments.
5. Add a public verification/export format for the eventual `Verified by Koschei` surface.
