# KOSCHEI PI ADAPTER CONTRACT V1

Status: experimental Lang-side interoperability boundary.

## Purpose

Koschei Lang may be demonstrated and commercialized inside the Pi ecosystem, but Pi-specific execution, wallet, settlement, or SDK behavior must not become part of Koschei's canonical language semantics.

Pi is an external ecosystem. Koschei remains the authority/identity/representation/execution system.

The allowed direction is:

Pi external fact -> non-authoritative adapter -> scoped Koschei capability -> sealed evidence -> Koschei policy/execution decision

The forbidden direction is:

Pi SDK/API semantics -> Koschei canonical semantics

or

external Pi identity/payment fact -> ambient Koschei authority

## V1 actions

The first contract deliberately exposes only three abstract adapter actions:

- `identity.verify`
- `payment.request`
- `payment.observe`

These are semantic interface labels, not implementations of Pi APIs.

A later concrete adapter may map official Pi SDK operations onto these labels, but the adapter remains outside canonical Koschei semantics and must be replaceable without changing the language.

## Capability physics

Every Pi adapter grant is:

- app-scoped
- subject-scoped by digest
- action-scoped
- time/epoch-scoped
- sealed
- non-authoritative outside its declared actions

The grant cannot widen itself and cannot create disk/network/process authority.

External Pi evidence is admitted only when:

1. the capability seal is valid,
2. the requested action is explicitly allowed,
3. the current/observed epoch is inside the grant lifetime,
4. the external evidence is represented by a digest,
5. the resulting evidence object is itself sealed.

## Koschei Lab for Pi

The first Pi-facing product should not be a compiler download page. It should be a proof-oriented interactive application called `Koschei Lab`.

### Public demo track

The visitor sees concrete security behavior:

1. No ambient authority demo
   - malicious dependency attempts a forbidden effect
   - Koschei rejects the effect because the required capability is absent

2. Rotating representation demo
   - an observer-visible representation is captured
   - epoch rotates
   - replay becomes non-authoritative / rejected at the enforced boundary

3. Verified artifact chain demo
   - Source Intent
   - Verified IR
   - Build Artifact
   - Payload
   - Execution evidence

The public message is not `our syntax is different`.

The message is:

`The code you can observe is not automatically the authority that may execute.`

### Developer track

A Pi developer enters through `Build Secure Pi App`.

V1 developer flow:

1. declare which Pi bridge actions the application needs,
2. derive a least-authority adapter capability,
3. compile/check the Koschei portion of the application,
4. produce a capability manifest,
5. produce provenance/artifact evidence,
6. verify that external Pi evidence enters only through the adapter boundary.

Future paid services may add hosted build verification, provenance storage, deployment attestation, team policy, and audit receipts. These are product-layer services; they do not alter Koschei language semantics.

## Threat model

### PROTECTS AGAINST

- treating an external Pi identity/payment response as ambient Koschei authority,
- using an adapter action that was never granted,
- reusing a time-scoped adapter capability after expiry,
- rebinding admitted external evidence to a different capability,
- accidental coupling of Pi SDK implementation details to Koschei canonical semantics.

### DOES NOT PROTECT AGAINST

- compromise of the external Pi service or SDK itself,
- a malicious adapter implementation that lies before evidence is hashed,
- theft of secrets held outside Koschei custody,
- compromise of the host process/runtime beneath the current bootstrap implementation,
- economic or settlement guarantees that only the Pi network can provide.

### ASSUMPTIONS

- concrete Pi integration uses official, authenticated external interfaces,
- trusted adapter code correctly maps Pi facts into the narrow abstract actions,
- epoch state used for capability liveness is trusted,
- Koschei's canonical compiler/runtime boundaries remain authoritative.

### FAILURE MODE

If external Pi data is allowed to bypass the adapter contract and directly create runtime authority, this boundary fails. If a concrete adapter is allowed to widen actions or lifetime after issuance, least-authority guarantees fail. If product code starts depending on Pi-specific SDK shapes inside canonical language semantics, Koschei becomes ecosystem-coupled and the architecture must be rejected.

## Separation rule

This work belongs only to Koschei Lang as an interoperability contract.

It must not modify or absorb Koschei Web3 or Koschei Sentinel responsibilities.

## Next technical slice

After this contract is validated, the next Lang-side slice is a generic `ExternalCapabilityAdapter` contract so Pi becomes the first implementation rather than a permanent special case. Pi-specific SDK code should then live at the product/integration edge, not inside the canonical compiler or runtime core.
