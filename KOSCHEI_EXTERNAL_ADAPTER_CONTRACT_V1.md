# KOSCHEI EXTERNAL ADAPTER CONTRACT V1

Status: IMPLEMENTED BOOTSTRAP BOUNDARY

## PURPOSE

External providers may report identity, payment, cloud, bank, chain or other facts,
but those facts are not Koschei authority. Provider SDK/protocol semantics stay
outside canonical Koschei Lang semantics.

The generic boundary is:

`External Provider -> Provider Adapter -> ExternalAdapterGrantV1 -> ExternalAdapterEvidenceV1`

When an external fact is later relevant to a privileged Koschei effect, the only
sanctioned handoff is:

`ExternalAdapterEvidenceV1`
`-> existing native Koschei MIR/request/proof/enforcement chain`
`-> CanonicalAuthorityBasisV1`
`-> AuthorizationDecisionV1`
`-> ExecutionPermitV1`

## GRANT

`ExternalAdapterGrantV1` binds:

- provider id,
- consumer/app id,
- subject-scope digest,
- explicit action set,
- valid-from epoch,
- expires-before epoch,
- `authority=False`.

The grant permits an adapter action; it does not grant the resulting application a
privileged Koschei effect.

## EVIDENCE

`ExternalAdapterEvidenceV1` binds an opaque external-evidence digest to exactly one
grant, provider, action and observation epoch. Evidence is also explicitly
non-authoritative.

## CANONICAL AUTHORITY HANDOFF

The authorization bridge no longer accepts a caller-provided authority-basis digest.
It derives one from Koschei's existing native privileged-effect path. External
subject scope must match the deterministic scope of the sealed canonical Koschei
request before a decision can be issued.

Therefore:

`external fact != authority`
`adapter grant != privileged effect grant`
`evidence != permission`
`native ALLOW + exact evidence binding -> narrow authenticated decision`

## PROTECTS AGAINST

- duplicated grant/evidence security physics across providers,
- ambient authority from external facts,
- ungranted or expired adapter actions,
- cross-provider/cross-grant evidence rebinding,
- external subject evidence being bridged to another canonical request identity,
- permanent coupling of provider SDK shapes to canonical Koschei semantics.

## DOES NOT PROTECT AGAINST

- compromised/dishonest external providers,
- provider-specific adapters accepting false native proofs,
- compromise/bugs in later native Koschei authority enforcement,
- provider-owned settlement/finality/economic guarantees,
- host/runtime/key compromise.

## ASSUMPTIONS

- provider-specific adapters correctly validate their native protocols,
- adapter grant/evidence epoch state is trusted at the authoritative boundary,
- external credentials remain outside Koschei source,
- privileged effects cannot bypass native Koschei authority and permit enforcement.

## FAILURE MODE

The boundary fails if provider code can inject facts directly into privileged
execution, if an adapter can widen its grant, or if the later native authority path
can be bypassed.

## PROVIDER PROFILES

Pi is the first profile. Future bank/cloud/EVM/etc. profiles may narrow this generic
contract but may not widen it or redefine external evidence as ambient authority.
