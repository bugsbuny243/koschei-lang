# KOSCHEI EXTERNAL FINALITY ATTESTATION V1

Status: IMPLEMENTED BOOTSTRAP PROTOTYPE / PROVIDER-NATIVE VERIFICATION NOT IMPLEMENTED IN LANG CORE

## PURPOSE

`effect-completed` is a local runtime fact. It is not remote settlement, blockchain
finality, bank settlement, cloud commit durability, or payment finality.

Koschei therefore separates local effect provenance from external-provider finality:

`EffectExecutionProofEnvelopeV1(effect-completed)`
`-> ExternalProviderFinalityVerdictV1`
`-> ExternalFinalityAttestationV1`
`-> ExternalFinalityProofEnvelopeV1`

The provider-specific verifier and Koschei finality attestor use separate keys and
separate records.

## SEMANTIC STATES

Provider verifier states:

- `pending`
- `finalized`
- `rejected`

Finality proof-envelope states:

- `provider-pending`
- `provider-finalized`
- `provider-rejected`

A caller cannot turn `pending` into `provider-finalized` by changing a label because
both the provider verdict and Koschei attestation are authenticated.

## TRUST-ROLE SEPARATION

- `provider_verifier_key`: belongs to the trusted provider-native verification role.
- `finality_key`: belongs to the Koschei finality-attestation role.

These keys MUST remain distinct in production.

The provider verifier answers:

> What did the external provider prove about this exact external reference?

The Koschei finality attestor answers:

> Which authenticated provider verdict belongs to this exact measured Koschei effect
> chain?

Neither role creates Koschei execution authority.

## PROVIDER VERDICT BINDING

`ExternalProviderFinalityVerdictV1` binds:

- provider identity,
- exact `EffectExecutionProofEnvelopeV1` digest,
- exact effect measurement digest,
- external transaction/reference digest,
- provider-native proof/response digest,
- observed epoch,
- provider state,
- `authority=false`.

The verdict issuer is a trusted bootstrap boundary. The generic Lang core does not
know how to verify every provider's native protocol.

Provider-specific code MUST verify native provider evidence first, then invoke the
verdict issuer while holding the provider-verifier key.

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

`ExternalFinalityProofEnvelopeV1` re-verifies the complete prior execution chain:

`External evidence`
`-> native MIR / canonical request / native proof`
`-> canonical authority basis`
`-> authorization decision`
`-> execution permit`
`-> permit consumption`
`-> local effect receipt`
`-> local effect proof envelope`
`-> provider verdict`
`-> finality attestation`
`-> finality proof envelope`

Only this full envelope may expose `provider-finalized` as an end-to-end provenance
claim for V1.

## PI PROFILE

`koschei/pi_finality_profile_v1.py` fixes only:

- provider id = `pi`,
- Pi finality state vocabulary,
- Pi transaction/reference and provider-proof digest fields.

It does NOT implement:

- Pi SDK networking,
- wallet custody,
- payment settlement,
- chain consensus,
- Pi transaction lookup,
- confirmation polling,
- Pi-specific cryptographic verification.

Those remain external provider-integration responsibilities.

## PROTECTS AGAINST

- relabeling local `effect-completed` as provider finality,
- changing provider verdict state after issuance,
- changing provider/external-reference/provider-proof digest after verdict issuance,
- moving a verdict to an effect envelope with a different measurement,
- using one key to silently impersonate both provider verification and finality attestation,
- changing pending/rejected attestations into finalized attestations,
- treating a raw provider verdict as complete end-to-end Koschei provenance,
- replacing effect/finality links inside the full finality proof envelope.

## DOES NOT PROTECT AGAINST

- a compromised or malicious provider-native verifier,
- incorrect Pi/provider-native verification logic,
- compromise of provider-verifier or finality keys,
- provider reorgs or semantic reversals after the provider's own claimed finality model,
- lying/compromised external provider infrastructure,
- host/runtime compromise, memory scraping, debuggers, or side channels,
- replay-state rollback/fork earlier in the execution chain,
- process death between irreversible remote action and local receipt creation.

## ASSUMPTIONS

- `EffectExecutionProofEnvelopeV1` is fully re-verified before full finality proof sealing,
- provider-native verification is fail-closed and runs outside untrusted application code,
- provider-verifier and finality keys are separately protected,
- external-reference digest identifies the exact provider object checked by the verifier,
- provider-proof digest commits to the exact provider response/proof used for the verdict,
- observed epoch is trusted lifecycle metadata for the protected Koschei universe.

## FAILURE MODE

The finality claim is only as strong as the provider-native verifier. If it marks an
unfinalized transaction as finalized, Koschei can prove which verifier verdict was
used but cannot magically repair the provider-verification error.

If either finality trust key is compromised, the corresponding authenticated link can
be forged.

If an external provider later reverses something it previously defined as final,
Koschei's receipt remains historical evidence of what was verified at that time; it
is not a guarantee that an external system can never violate its own finality model.

## NEXT

1. Define a provider-native verifier interface that produces canonical provider-proof
   bytes without exposing provider SDK semantics to Lang core.
2. Implement the Pi provider verifier outside the semantic core.
3. Bind provider proof bytes to the exact callback-returned external reference, not
   merely to an independently supplied reference digest.
4. Move finality keys and replay state into runtime-owned durable compartments.
5. Add a public verification/export format for the eventual `Verified by Koschei`
   product surface.
