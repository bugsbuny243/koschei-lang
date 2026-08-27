# KOSCHEI PI ADAPTER CONTRACT V1

Status: IMPLEMENTED PROFILE / EXTERNAL PI SDK IMPLEMENTATION NOT PART OF LANG

## PURPOSE

Pi is the first provider profile for Koschei Lang's generic external-adapter boundary.
Pi Network SDK, wallet custody, settlement and chain behavior remain outside Koschei
Lang. The adapter may introduce verified external facts; it may not introduce ambient
Koschei authority.

## ALLOWED PI ACTIONS

The v1 profile recognizes only:

- `identity.verify`
- `payment.request`
- `payment.observe`

Every action remains app/consumer, subject and epoch scoped through the generic
`ExternalAdapterGrantV1` physics.

## AUTHORITY HANDOFF

A Pi payment or identity fact is never an execution capability.

The sanctioned path is:

`Pi native fact`
`-> Pi adapter validation`
`-> ExternalAdapterEvidenceV1(provider=pi)`
`-> Koschei Native MIR + Canonical Effect Request + Request-Bound Proof`
`-> CanonicalAuthorityBasisV1`
`-> AuthorizationDecisionV1`
`-> ExecutionPermitV1`
`-> single exact effect`

The external grant's `subject_scope_digest` must match the deterministic canonical
scope derived from the sealed Koschei request's subject and identity digest before an
authorization decision can be issued.

## KOSCHEI LAB EXAMPLE

A settled Pi payment may be admitted as `payment.observe` evidence. A separate
Koschei native request may ask for `subscription.enable`. Only when the existing
native Koschei proof/enforcement chain returns ALLOW for that exact request can the
bridge derive an authorization decision and single-use execution permit.

There is no rule of the form:

`Pi payment -> arbitrary Koschei authority`

and neither the Pi adapter, decision issuer nor permit minter receives a free-form
argument that can widen `subscription.enable` into `treasury.withdraw` after native
authority evaluation.

## PROTECTS AGAINST

- Pi facts becoming ambient disk/network/process/treasury authority,
- ungranted Pi adapter actions,
- expired external grants,
- cross-grant evidence rebinding,
- external subject scope being bridged to another canonical request identity,
- operation widening after native Koschei authorization,
- hard-coupling Pi SDK shapes into canonical language semantics.

## DOES NOT PROTECT AGAINST

- compromised or dishonest Pi provider/SDK behavior,
- a Pi-specific adapter accepting false native evidence before admission,
- compromised Koschei native enforcement/runtime/key custody,
- Pi settlement/finality/economic guarantees,
- host compromise or side channels.

## ASSUMPTIONS

- Pi-specific native verification is implemented correctly outside Lang core,
- external credentials are not embedded into Koschei source,
- Koschei native authority/proof evaluation is fail-closed,
- runtime lifecycle/epoch and key custody are trusted at the authoritative boundary.

## FAILURE MODE

The separation collapses if Pi/provider code can bypass generic evidence admission or
invoke privileged effects without the native authority -> decision -> permit chain.
It also collapses if the trusted Koschei enforcement/runtime boundary itself is
compromised.

## PRODUCT BOUNDARY

Koschei Lab may expose Attack Demo / Build Secure Pi App / verified provenance UX, but
that product surface must consume these Lang contracts rather than moving Pi Network
business logic into Koschei Lang.
