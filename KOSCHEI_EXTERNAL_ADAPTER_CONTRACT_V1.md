# KOSCHEI EXTERNAL ADAPTER CONTRACT V1

## Purpose

Koschei Lang must interoperate with external systems without importing their trust model into canonical Koschei semantics.

External systems may include payment networks, identity providers, banks, cloud platforms, blockchains, developer platforms, or customer-owned services. Their SDKs, protocols, credentials, settlement rules, and operational semantics remain outside Koschei Lang.

The Lang-side contract admits only bounded evidence through a scoped, time-limited, non-authoritative grant.

## Canonical boundary

External Provider
→ provider-specific adapter
→ ExternalAdapterGrantV1
→ sealed ExternalAdapterEvidenceV1
→ Koschei policy / execution

The external provider is not a capability issuer for Koschei execution authority.

## Grant semantics

`ExternalAdapterGrantV1` is bound to:

- provider identity
- Koschei consumer/application identity
- subject scope digest
- explicit action set
- valid-from epoch
- expires-before epoch
- authority = false

A grant cannot widen itself after issuance without breaking its seal.

## Evidence semantics

External evidence is opaque to this generic layer. The generic contract proves only that:

- the evidence digest was admitted under one exact sealed grant
- the provider matches that grant
- the action was explicitly permitted
- the observation occurred during the grant lifetime
- the evidence object itself has not been modified after admission
- the evidence carries no Koschei ambient authority

Provider-specific adapters remain responsible for validating provider-native proofs before presenting their digest to this boundary.

## Pi implementation

Pi Network is the first provider-specific adapter profile.

The Pi profile currently admits only:

- `identity.verify`
- `payment.request`
- `payment.observe`

Pi SDK semantics, payment settlement, wallet custody, network calls, and Pi-specific trust assumptions do not become Koschei language semantics.

## PROTECTS AGAINST

- copying the same security-sealing implementation independently into every provider adapter
- external facts becoming ambient Koschei disk/network/process authority
- evidence rebinding to a different provider or grant
- use of actions outside the explicit grant
- reuse of expired grants
- mutation of sealed grant/evidence fields after issuance
- permanent coupling of canonical Koschei semantics to one SDK shape

## DOES NOT PROTECT AGAINST

- a compromised or dishonest external provider
- a provider-specific adapter that accepts false native proofs before hashing them
- compromise of the Koschei host/runtime or trusted policy state
- settlement, finality, chargeback, economic, or identity guarantees owned by the provider
- leakage of external credentials outside the Lang boundary

## ASSUMPTIONS

- provider-specific adapters validate their native protocol correctly
- current epoch is supplied from trusted Koschei runtime state
- digest algorithms and sealed object implementations remain intact
- external credentials are not embedded into Koschei source

## FAILURE MODE

If provider-specific code can bypass `ExternalAdapterGrantV1` and inject external facts directly into authoritative execution, the boundary collapses.

If adapter code treats an external fact as a Koschei capability rather than evidence, ambient authority can re-enter the system.

If runtime epoch state is attacker-controlled, expired-grant replay protection is ineffective.

## Design rule

Provider-specific adapters may narrow the generic contract, but they must not widen it.

A provider can define a smaller action vocabulary or stricter lifetime/policy checks. It cannot turn external evidence into unrestricted Koschei authority.
