# KOSCHEI PI ADAPTER CONTRACT V1

Status: IMPLEMENTED BOOTSTRAP PROFILE / EXTERNAL PI SDK IMPLEMENTATION NOT PART OF LANG

## PURPOSE

Pi is the first provider profile for Koschei Lang's generic external-adapter boundary.
Pi SDK/network/payment logic remains outside Koschei Lang. The adapter may introduce
verified external facts; it may not introduce ambient Koschei authority.

## ALLOWED PI ACTIONS

The v1 profile recognizes only:

- `identity.verify`
- `payment.request`
- `payment.observe`

Every action remains consumer, subject and epoch scoped through generic adapter grants.

## AUTHORITY HANDOFF

A Pi payment or identity fact is never an execution capability.

Sanctioned authority path:

`Pi native fact`
`-> ExternalAdapterEvidenceV1(provider=pi)`
`-> Koschei Native MIR + Canonical Effect Request + Request-Bound Proof`
`-> CanonicalAuthorityBasisV1`
`-> AuthorizationDecisionV1`
`-> ExecutionPermitV1`
`-> single measured effect`

## PI PROVIDER-FINALITY VERIFIER PATH

Provider-finality verification is separately gated:

`effect result txid bytes`
`-> verifier VerifiedIrBuildInputV1`
`-> authenticated ToolchainProvenanceV1`
`-> builder A + builder B observations`
`-> VerifierReproducibleBuildReceiptV1`
`-> VerifierBuildProvenanceV1`
`-> ProviderAdapterAbiV1`
`-> VerifierReproducibleRuntimeAdmissionV1`
`-> raw Pi response bytes`
`-> Pi-native verifier`
`-> provider verdict`
`-> ExternalFinalityProofEnvelopeV1`

The Pi wrapper cannot choose a raw `toolchain_digest`, bypass the reproducible admission
gate, or promote local `effect-completed` into provider finality by itself.

Pi SDK calls, wallet custody, settlement, consensus and a production backend JSON parser
remain outside Lang core.

## PROTECTS AGAINST

- Pi facts becoming ambient authority,
- ungranted/expired adapter evidence,
- subject or operation widening after native authorization,
- provider verification without the two-builder reproducibility gate,
- caller-selected toolchain digest on sanctioned verifier build paths,
- relabeling verifier build evidence under another signed toolchain identity,
- hard-coupling Pi SDK shapes into canonical language semantics.

## DOES NOT PROTECT AGAINST

- compromised/dishonest Pi provider or SDK behavior,
- a malicious verifier/toolchain that is legitimately signed and admitted,
- compromised signing/build/runtime/finality keys,
- common-mode compiler defects across independent builders,
- Pi settlement/economic guarantees beyond verified provider evidence,
- host compromise, replay-state rollback or measure-A/execute-B TOCTOU.

## ASSUMPTIONS

- Pi-specific native verification is implemented correctly outside Lang core,
- signed toolchain bytes are the bytes actually used by builders,
- builder identities map to independent build authorities,
- external credentials are not embedded into Koschei source,
- native authority/proof evaluation and runtime admission fail closed.

## FAILURE MODE

The separation collapses if provider code bypasses generic evidence admission, if lower
verification primitives bypass reproducible admission, or if trusted runtime/signing
boundaries are compromised. Signed/reproducible provenance authenticates identity and
agreement; it does not prove semantic correctness.
