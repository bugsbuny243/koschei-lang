# Web4 / Web5 / Web6 Research — 2026-09-18

Status: current technical intake for Koschei Lang. Research evidence is input to design review, not automatic semantic authority.

## Web4 — high-signal

### IETF draft-reilly-web4-00 (26 Aug 2026)
An active individual Internet-Draft proposes a testable Web4 profile built on the existing Web: independently verifiable permanence evidence, a first-class machine channel, recorded/bounded/revocable agent authority, and disclosed human control over agent-curated presentation.

Koschei relevance: HIGH. The bounded/revocable authority and independently verifiable evidence model aligns with Koschei's Authority Conservation, Evidence, Proof-Carrying Execution, and No Sovereign Component laws. Treat as external draft input only; it does not become Koschei canonical truth.

Source: https://datatracker.ietf.org/doc/draft-reilly-web4/

### Web4 Delegated Authority (12 Sep 2026)
A new Experimental individual Internet-Draft, draft-jacobs-web4-delegated-authority-00, defines signed, bounded, time-limited and revocable authority mandates for agents/nodes, with governed actions linked to their authority.

Koschei relevance: VERY HIGH. Compare its mandate/revocation model against Khar/Sathra and Koschei entitlement/admission boundaries. Do not import JWT/host representation or any authority mechanism blindly; only semantic invariants that survive Koschei constitutional review are candidates.

Source: https://datatracker.ietf.org/doc/draft-jacobs-web4-delegated-authority/

## Agent authorization adjacent to Web4/Web5

### AI Agent Authentication and Authorization — draft-klrc-aiagent-auth-03 (6 Jul 2026)
The draft applies existing WIMSE and OAuth-family standards to AI-agent authentication/authorization rather than defining a replacement protocol.

Koschei relevance: HIGH for external interoperability boundary, LOW as internal authority. OAuth/WIMSE credentials may prove external admission facts but MUST NOT manufacture Khar/compiler capability authority.

Source: https://datatracker.ietf.org/doc/draft-klrc-aiagent-auth/

### Agent Identity Protocol — draft-singla-agent-identity-protocol-03 (10 Jun 2026)
Active individual Standards-Track-intended draft combining DIDs, capability-based authorization, cryptographic delegation chains and deterministic validation for autonomous agents.

Koschei relevance: HIGH. Candidate comparison target for exact identity, delegation attenuation, revocation and deterministic validation. It is an Internet-Draft, not an IETF standard.

Source: https://datatracker.ietf.org/doc/draft-singla-agent-identity-protocol/

### OpenA2A Agent Authorization Protocol — draft-fane-opena2a-aap-01 (22 Jul 2026)
Active individual draft covering agent identity assertions, scoped capability grants, cross-agent delegation, behavioral attestation, federation and revocation propagation.

Koschei relevance: MEDIUM/HIGH as an interoperability and adversarial-comparison target. No automatic adoption.

Source: https://datatracker.ietf.org/doc/draft-fane-opena2a-aap/

## Web5 — identity signal

### W3C DID Methods note (2 Sep 2026)
W3C published an updated Group Note collecting known DID methods.

Koschei relevance: MEDIUM. Useful for external identity/wallet/agent admission adapters. DID resolution MUST remain outside canonical Koschei compiler authority unless a future Koschei-native identity contract explicitly admits verified facts.

Source: https://www.w3.org/TR/2026/NOTE-did-extensions-methods-20260902/

### W3C VC lifecycle work (1 Sep 2026 meeting)
VCWG discussion includes credential lifecycle management, threat-model work and progress toward a Candidate Recommendation stage for current VC lifecycle work.

Koschei relevance: MEDIUM. Revocation/expiry/audit lifecycle should be compared with Koschei proof envelopes and product entitlement receipts.

Source: https://lists.w3.org/Archives/Public/public-vc-wg/2026Sep/0002.html

## Web6 — classification warning

Searches did not find an IETF/W3C consensus standard named Web6. A project calling itself OASIS WEB6 advertises an AI abstraction/orchestration layer with DID/VC identity and multiple agent protocols, but this is project/vendor material, not evidence of a Web6 Internet standard.

Koschei relevance: WATCH ONLY. Individual implementation ideas can be evaluated independently, but the label "Web6" MUST NOT be treated as a standards maturity claim.

Source: https://web6.oasisomniverse.one/

## 2026-09-18 Koschei impact decision

1. Add **bounded + time-limited + revocable delegation** to the comparison checklist for Khar/Sathra authority proofs.
2. Preserve the hard boundary: external DID/OAuth/WIMSE/AIP evidence may enter only as verified admission facts; it cannot manufacture Koschei authority.
3. Entitlement/session work should bind expiry and revocation evidence explicitly.
4. Keep deterministic validation and exact identity as required properties for agent interoperability.
5. No Web4/Web5/Web6 draft becomes canonical language semantics merely because it is new.
6. No credible standards evidence found today that justifies a new canonical "Web6" language layer.

## Source maturity

- W3C Group Note: published W3C note, not the same as a W3C Recommendation.
- IETF items above: Internet-Drafts; drafts may change or expire and are not IETF standards merely by publication.
- OASIS WEB6 item: project/vendor claim; watch-only.


## 2026-09-19 delta

### Agent Registry Protocol (ARPA) — draft-sankarshan-agent-registry-protocol-00 (17 Sep 2026)
A new individual Standards-Track-intended Internet-Draft defines an HTTP/JSON registry protocol for resolving who operates a software agent, its deployment, typed relationships, bounded delegated authority, lifecycle status, and evidence supporting a reliance decision.

Koschei relevance: VERY HIGH as an external comparison target. The useful invariant is not the HTTP/JSON representation; it is the explicit binding between exact agent/deployment identity, bounded authority, lifecycle/revocation state, and evidence. External ARPA records MUST remain admission evidence and MUST NOT manufacture Khar/compiler authority.

Source: https://www.ietf.org/archive/id/draft-sankarshan-agent-registry-protocol-00.html

### W3C DID / Controlled Identifiers maintenance transition discussion (10–12 Sep 2026)
W3C DID and Verifiable Credentials participants are discussing moving long-term Controlled Identifiers maintenance toward the DID WG while coordinating an overlap period with VCWG.

Koschei relevance: MEDIUM. This reinforces the need to bind external identity evidence to an explicit specification/version and verifier policy rather than assuming a permanent maintainer or static registry. No Koschei canonical semantic change follows from this governance discussion.

Source: https://lists.w3.org/Archives/Public/public-vc-wg/2026Sep/0030.html

### Agent Web Protocol v0.2 — community project signal
AWP publishes a /.well-known/agent.json discovery surface for machine-readable capabilities, authentication requirements, typed actions, and references to sibling agent protocols.

Koschei relevance: WATCH/HIGH for external service discovery. Treat the manifest as untrusted observable input until verified and admitted. Discovery MUST NOT equal authority; advertised capability MUST NOT equal Koschei capability.

Source: https://www.agentwebprotocol.org/

### Web6 status re-check
No new IETF/W3C consensus specification named Web6 was identified in the 2026-09-19 scan. Continue watch-only classification for the label itself.

## 2026-09-19 Koschei delta decision

1. Add exact **agent + deployment + authority + lifecycle + evidence** binding to the external-agent admission comparison checklist.
2. External registry/discovery documents are observable claims, never canonical authority by themselves.
3. Bind accepted external identity evidence to specification/version and verifier policy so maintenance transitions cannot silently alter Koschei admission meaning.
4. Keep revocation/current-lifecycle verification mandatory before converting delegated-agent evidence into any external service admission.
5. No new Web6 language semantic layer is justified by today's standards evidence.


## 2026-09-19 05:57+03 delta

### IETF Agent Communication Protocols (agentproto) proposed WG review
On 17 Sep 2026 the IESG announced review of a proposed Agent Communication Protocols working group. The announcement explicitly frames agent protocols around delegated user authority and auditability concerns. This is a proposed WG under review, not an established standard.

Koschei relevance: HIGH. Track protocol-layer separation between dialog/communication and authority. Koschei MUST continue to bind an external agent action to the exact delegated authority/evidence rather than treating protocol participation as authority.

Source: https://mailarchive.ietf.org/arch/msg/ietf-announce/PLF82HzLpIZQecDl0rzIm1FTxb4/

### Independent Determinability of Agent Actions — draft-wadkins-agentproto-action-determinability-00
The 10 Sep 2026 individual Internet-Draft separates authorization, enforcement, execution and intended effect into distinct transitions and requires enough preserved evidence for an independent evaluator to determine the claimed transition later.

Koschei relevance: VERY HIGH. This maps directly onto Koschei's observable-vs-canonical separation and proof-carrying execution. A declared request or authorization MUST NOT stand in for an executed effect. Future Koschei external-action receipts should bind governing revision + material action + resulting effect evidence.

Source: https://www.ietf.org/archive/id/draft-wadkins-agentproto-action-determinability-00.html

### W3C AIKR / Agent Identity trust-layer discussion — declared vs resolved facts
September discussion highlights a concrete failure class: checking a declared scope against another declared identifier can prove internal consistency while failing to prove the actual resolved/executed target. Participants distinguish consistency checks from evidence checks that recompute or resolve the real target.

Koschei relevance: VERY HIGH as adversarial design input, but this is Community Group discussion rather than W3C Recommendation. Add a hard rule for external adapters: **no declared slot is accepted as the corresponding executed fact**. Effect evidence must be resolved/recomputed and bound to the authority decision.

Sources:
- https://lists.w3.org/Archives/Public/public-aikr/2026Sep/0029.html
- https://lists.w3.org/Archives/Public/public-aikr/2026Sep/0028.html

## 2026-09-19 05:57+03 Koschei delta decision

1. Preserve four distinct external-action facts: authorization, enforcement decision, execution, effect.
2. A protocol declaration/manifest/request is observable evidence, never proof of the executed target/effect by itself.
3. Future external-action proof envelopes must bind the exact governing revision in force at decision time.
4. Evidence referenced but unavailable must fail closed where the claim depends on it; silent degradation to unchecked state is forbidden.
5. Agent communication protocol participation cannot manufacture Khar or compiler authority.


## 2026-09-19 identity/canonicalization delta

### W3C AIKR / Agent Identity discussion — canonicalization false-match risk
A 17 Sep 2026 Community Group discussion records an important conformance failure: numeric identifier values outside the exact interoperable integer range can collapse to the same canonical JSON representation in some processing paths, producing a silent false identity match rather than a visible mismatch. The discussion also notes that canonical bytes alone cannot establish semantic equality when units, namespaces, or schema references differ.

Koschei relevance: VERY HIGH as adversarial input. Canonical serialization MUST NOT be treated as semantic identity by itself. Security-critical identifiers need a domain/type/schema contract before byte-level canonicalization, and unsafe numeric identifier domains must fail closed rather than pass through a lossy host-number representation.

Source: https://lists.w3.org/Archives/Public/public-aikr/2026Sep/0027.html

### Authority continuity across delegation
September AIKR/Agent Identity discussion separately emphasizes that a traceable A -> B -> C delegation chain proves provenance but does not by itself prove that authority remained within the original principal's scope.

Koschei relevance: VERY HIGH. Every delegation hop must preserve or attenuate authority; provenance alone is insufficient. A downstream agent/tool may never widen scope merely because its own identity and delegation link are valid.

Sources:
- https://lists.w3.org/Archives/Public/public-aikr/2026Sep/0012.html
- https://lists.w3.org/Archives/Public/public-aikr/2026Sep/0017.html

## 2026-09-19 identity/canonicalization decision

1. Separate semantic identity from serialization canonicalization.
2. Security identifiers require explicit namespace/schema/type meaning before equality is admitted.
3. Reject identifier representations that can undergo lossy host-number conversion.
4. Delegation validity requires authority continuity/attenuation at every hop; a complete provenance chain is not sufficient.
5. These Community Group discussions are design/adversarial evidence, not W3C Recommendations and not automatic Koschei semantic authority.


## 2026-09-19 protocol-negotiation delta

### Agent Protocol Negotiation Protocol (APNP) — draft-cui-agent-protocol-negotiation-protocol-00 (16 Sep 2026)
A new individual Internet-Draft proposes a negotiation layer for heterogeneous agent protocols. It defines capability advertisement, intersection, deterministic protocol selection, downgrade protection, and a negotiation transcript hash intended to bind the selected protocol and parameters to the later session.

Koschei relevance: VERY HIGH as an interoperability/adversarial target. The key invariant is that discovery/negotiation cannot silently weaken the security profile. Any external-agent adapter must bind the exact negotiated protocol/version/parameters to the admitted session/evidence and fail closed when no acceptable intersection exists. A fallback must never widen authority or erase required verification.

Source: https://www.ietf.org/archive/id/draft-cui-agent-protocol-negotiation-protocol-00.html

### OAuth authorization across trust domains — draft-parecki-oauth-trust-domain-00 (8 Sep 2026)
This individual Internet-Draft addresses OAuth authorization when clients and resource servers span different trust domains, introducing explicit trust-domain and authorization-server relationship metadata.

Koschei relevance: MEDIUM/HIGH for external admission adapters. Trust-domain metadata is observable external policy evidence, not Koschei authority. Cross-domain authorization must bind the exact issuer/domain relationship used at decision time and reject ambiguous or conflicting trust paths.

Source: https://www.ietf.org/archive/id/draft-parecki-oauth-trust-domain-00.html

## 2026-09-19 protocol-negotiation decision

1. Bind exact external protocol name, version and security-relevant negotiated parameters to session/evidence identity.
2. No acceptable protocol intersection = DENY; do not invent a permissive fallback.
3. Negotiation fallback may preserve or strengthen requirements but must never weaken required identity, authority, evidence, freshness, revocation or effect-verification guarantees.
4. Cross-domain trust metadata is evidence only and cannot manufacture Khar/compiler authority.
5. Ambiguous/conflicting external trust paths fail closed.


## 2026-09-19 federation/evidence delta

### Web4 Federation Policy Advertisement — draft-jacobs-web4-federation-policy-00 (12 Sep 2026)
This individual IETF Internet-Draft defines machine-readable federation policy advertisements covering authority, versions/profiles, evidence formats, retention, challenges/appeals, revocation, disclosure, jurisdiction, proof and status.

Koschei impact: advertised policy is observable external evidence, never canonical authority. Admission must bind the exact policy/profile/version/status used at decision time; stale, revoked, ambiguous or unsupported policy fails closed.

### Web4 Evidence Receipts — draft-jacobs-web4-evidence-receipts-00 (12 Sep 2026)
This individual draft defines durable cryptographically verifiable receipts for assessment, authority, policy, claim and node-lifecycle events without requiring protected evidence itself to be published.

Koschei impact: strengthens the existing receipt architecture. A receipt proves only its explicitly bound event/state and must not be promoted to execution/effect/finality proof. Protected evidence may remain private while its integrity/provenance commitment is independently verifiable.

### Web4 Claims and Verification — draft-jacobs-web4-claims-verification-00 (12 Sep 2026)
This individual draft explicitly separates claims, evidence, assessments, assertions, verification events, challenges, supersession, suspension, expiration, revocation and receipts.

Koschei impact: preserve these state distinctions rather than collapsing them into a generic "verified" boolean. Revocation/suspension/expiration/supersession are lifecycle facts and must be checked at the authorization/effect boundary.

Sources:
- https://www.ietf.org/archive/id/draft-jacobs-web4-federation-policy-00.html
- https://www.ietf.org/archive/id/draft-jacobs-web4-evidence-receipts-00.html
- https://www.ietf.org/archive/id/draft-jacobs-web4-claims-verification-00.html

### Web5/Web6 recheck
No new primary IETF/W3C consensus Web5/Web6 technical standard was found in this delta. Do not manufacture semantics from labels alone.

## 2026-09-19 federation/evidence decision

1. External federation policy must bind exact profile/version/status and remains non-authoritative.
2. Receipt type must state exactly what fact it proves; no receipt-type promotion.
3. claim != evidence != assessment != verification != execution != effect != finality.
4. suspension, expiration, revocation and supersession are first-class lifecycle gates.
5. private evidence may use verifiable commitments, but unavailable evidence required for a decision remains fail-closed.


## 2026-09-20 subagent identity / evidence availability delta

### W3C Agent Identity CG discussion — delegated subagents (18 Sep 2026)
A new community-group issue asks whether a top-level agent identity assertion also covers delegated subagents and what minimum per-run record is required to make that claim independently checkable afterwards.

Koschei relevance: HIGH. Parent identity must not be silently inherited as child identity or child authority. Every delegated execution hop needs an exact subject/deployment/run binding and an auditable parent-child relationship. Missing child evidence fails closed.

Source: https://lists.w3.org/Archives/Public/public-agent-identity/2026Sep/0033.html

### W3C AIKR discussion — carried vs referenced evidence (17 Sep 2026)
The current community discussion distinguishes declared consistency from recomputed/resolved evidence and notes a failure mode where referenced evidence becomes unavailable. An unavailable reference can otherwise turn a verification step into an unchecked step without any explicit false statement.

Koschei relevance: HIGH. Evidence availability is part of the verification contract. A required external receipt/evidence reference that cannot be resolved must never degrade into success. Receipts should record whether critical evidence is carried or referenced and bind the resolution policy used at decision time.

Source: https://lists.w3.org/Archives/Public/public-aikr/2026Sep/0028.html

These are community discussions, not W3C Recommendations.

## 2026-09-20 decision

1. Parent-agent identity does not imply child/subagent identity or authority.
2. Delegated execution evidence binds exact parent, child, deployment/run and authority attenuation.
3. Required referenced evidence becoming unavailable = DENY / unverifiable, never implicit success.
4. Verification records bind evidence mode (carried/reference) and the resolution policy/version.
5. None of these external identity/evidence facts mint Khar or compiler authority.
