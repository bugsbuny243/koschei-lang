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
