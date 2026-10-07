# KOSCHEI AUTHORIZATION DECISION V1

Status: IMPLEMENTED BOOTSTRAP PROTOTYPE / NATIVE AUTHORITY INPUT WIRED / FINAL RUNTIME ISOLATION PENDING

## PURPOSE

External evidence is not permission, and a permit issuer must not invent authority.
The v1 bridge now derives its authority basis from Koschei's existing native
privileged-effect path rather than accepting a caller-supplied capability digest:

`External Evidence`
`-> Native MIR + Canonical Effect Request + Request-Bound Proof`
`-> Native Enforcement Decision`
`-> CanonicalAuthorityBasisV1`
`-> AuthorizationDecisionV1`
`-> ExecutionPermitV1`
`-> Single Consume`

No parallel capability system is introduced by this bridge.

## CANONICAL AUTHORITY BASIS

`koschei/canonical_authority_basis_v1.py` turns the already-existing native chain into
a deterministic, non-ambient receipt.

It re-verifies:

- sealed `NativeSigilMir`,
- sealed `CanonicalEffectRequest`,
- sealed `RequestBoundProof`,
- `NativeSigilProofBundle`,
- the resulting `EnforcementDecision` (`ALLOW`, `DENY`, `CONTAIN`).

The basis binds:

- canonical request digest,
- request-bound proof digest,
- enforcement-decision digest,
- native MIR fingerprint,
- Universe-plan digest,
- proof digest,
- canonical subject-scope digest,
- operation,
- epoch,
- native enforcement outcome.

`authority=False` is explicit: the receipt describes verified authority state; it is
not itself ambient authority.

## SUBJECT SCOPE

External adapter subject scope is compared with a deterministic scope derived from
the sealed canonical request's `subject + identity_digest`.

This prevents an external grant for one subject identity from being used as the
bridge for a different canonical privileged request.

## ISSUER SURFACE

`issue_authorization_decision_v1(...)` no longer accepts:

- `authority_basis_digest`,
- `policy_digest`,
- `outcome`,
- `operation`,
- `request_digest`.

Those fields are derived after the native authority basis is re-verified.

For v1, `policy_digest` is the sealed native MIR fingerprint: the executable Koschei
program identity whose Library/proof path produced the enforcement result.

The decision outcome is mapped directly from native enforcement:

- `ALLOW -> allow`
- `DENY -> deny`
- `CONTAIN -> contain`

Only `allow` may later mint an execution permit.

## KEY SEPARATION

- `decision_key` authenticates the external-evidence -> canonical-decision bridge.
- `runtime_key` authenticates the later execution permit.

The two keys have different trust roles and must remain separate.

## PROTECTS AGAINST

- caller injection of a fake authority-basis digest,
- caller selection of allow/deny/contain at decision issuance,
- caller selection of a wider operation or different request at decision issuance,
- rebinding an external subject scope to another canonical request identity,
- bridging external evidence from a different epoch than the canonical request,
- tampering with MIR/request/proof/bound-proof/enforcement identities after basis derivation,
- changing authenticated decision fields after issuance,
- permit minting from native DENY or CONTAIN outcomes.

## DOES NOT PROTECT AGAINST

- bugs or compromise inside the existing native MIR/Library/proof/enforcement chain,
- compromise of `decision_key`,
- malicious code inside the trusted native decision issuer compartment,
- false external evidence admitted before this boundary,
- host/runtime compromise,
- side channels or memory/key disclosure,
- durable replay-state rollback at the later permit boundary.

## ASSUMPTIONS

- `NativeSigilMir`, request binding, proof verification and enforcement remain fail-closed,
- native MIR fingerprint is a stable executable policy identity for this v1 bridge,
- decision key is at least 32 bytes and outside provider/observer control,
- external grant/evidence validation already succeeded,
- canonical request epoch and runtime epoch originate from trusted Koschei lifecycle state in production.

## FAILURE MODE

Authority integrity fails if the native enforcement chain itself can be bypassed or
if arbitrary code can obtain the decision key and impersonate the trusted issuer.

The Python implementation proves semantic binding and fail-closed checks; it does
not prove that production key custody or process isolation is physically
unbypassable. Native runtime integration must make the canonical basis -> decision
issuer the authoritative bridge.

## PI EXAMPLE

`Pi payment.observe evidence`
`-> sealed Koschei request: subscription.enable`
`-> request-bound native proof`
`-> native ALLOW`
`-> canonical authority basis`
`-> AuthorizationDecision(operation=subscription.enable)`
`-> single-use permit`

The Pi adapter cannot turn the payment into `treasury.withdraw`, and the decision
issuer no longer accepts a string/digest parameter that could manufacture that
wider authority.

## NEXT

Create the machine-verifiable **Proof Envelope** that commits the complete lineage:

`external grant/evidence`
`-> native MIR/request/bound proof`
`-> canonical authority basis`
`-> authorization decision`
`-> execution permit`
`-> consume/effect outcome`

Then move permit replay state and decision/permit key custody from Python bootstrap
objects into a runtime-owned monotonic/transactional boundary.


## IDENTITY CANONICALIZATION AND DELEGATION CONTINUITY GATE — 2026-09-19

Authorization identity is a semantic contract before it is a byte/digest contract.

A canonical serialization or matching digest MUST NOT by itself establish that two
security-critical identifiers denote the same subject, namespace, unit, schema, or
authority domain. The identity contract that gives those bytes meaning must already
be explicit and admitted.

Security-critical identifiers MUST NOT pass through a lossy host-number
representation. If an external identifier cannot be represented without loss under
the admitted identity/schema contract, the bridge MUST reject it rather than hash a
silently rounded/colliding representation.

For delegated external authority, provenance alone is insufficient. A valid chain
A -> B -> C proves where a delegation claim came from; it does not prove that C
remained inside A's original authority. Every admitted hop MUST preserve or attenuate
the preceding scope and lifetime. No hop may widen operation, subject, resource,
epoch/lifetime, or other authority dimension.

These requirements apply before external evidence is allowed to participate in the
canonical authority bridge. They do not grant external identity systems authority
over Koschei's native Khar/compiler enforcement.


## PROTOCOL NEGOTIATION / DOWNGRADE GATE — 2026-09-19

External protocol discovery and negotiation are pre-admission observations, not
authority.

When an external adapter relies on negotiated agent/authentication protocol state,
the admitted evidence MUST bind the exact protocol identity, version and all
security-relevant negotiated parameters. The later authorization/session path MUST
verify that binding rather than re-negotiate or infer a compatible profile.

If peers have no intersection that satisfies Koschei's required identity, evidence,
freshness, revocation, authority-scope and effect-verification guarantees, admission
MUST fail closed. A compatibility fallback may preserve or strengthen those
requirements; it MUST NOT weaken them.

A negotiation transcript/hash can provide binding evidence but does not create
authority. Likewise, external trust-domain or issuer metadata is evidence describing
a claimed trust relationship. Conflicting, ambiguous, stale or unresolved trust
paths MUST NOT be collapsed into an allow decision.

No negotiated protocol, fallback, issuer relationship or cross-domain metadata may
widen the operation/subject/resource/lifetime admitted by the canonical native
authority basis.
