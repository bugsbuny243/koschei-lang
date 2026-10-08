# Koschei Lang — security-language design intelligence | 2026-10-08

**Research window:** approximately 2026-10-07 18:00 to 2026-10-08 18:00 Europe/Istanbul. **Scope:** architecture-level evidence only; no speculative protocol syntax baked into the compiler.

## 1. W3C Verifiable Credential threat models — five new Group Note Drafts
**Published:** 2026-10-08 by W3C VC Working Group. **Status:** informative **draft notes**, not Recommendations.

New models for Recognized Entities, Data Integrity, VCALM, Barcode and Render Method highlight important boundaries:
- `SignedCredential` != `TrustedIssuer` != `RecognizedIssuer<Scope>` != `AuthorizedAction<Effect>`.
- `ProofValid` != `StatusFresh` != `PrivacyPreserved`: list/status lookups can leak verification metadata; cached recognition can be stale.
- `SignedClaims` != `RenderedClaims`: unsigned barcode fields or untrusted render templates can misrepresent an otherwise valid credential.
- `CredentialIssued` != `CredentialUsableNow`: issuer, holder, verifier, revocation and challenge contexts change independently.

**Opportunity:** protocol-neutral library types that make transitions and provenance explicit.
**Threat:** treating a credential's cryptographic signature as a blanket capability; promoting untrusted rendered data into an authorized effect.
**Competitor gap (design hypothesis):** a typed evidence/authority API can reduce implicit trust conversions common in loosely typed integrations.
**Product idea:** design-review-only interfaces `verify_signature(input)->VerifiedProof`, `resolve_recognition(VerifiedProof,TrustAnchor,Freshness)->RecognizedClaim`, `authorize(RecognizedClaim,Policy,Action)->ActionPermit`, `execute(ActionPermit)->EffectReceipt`. Each stage may fail; no implicit conversion, no permanent authorization inferred from historical status.
**Acceptance criteria:** expired issuer recognition, untrusted publisher, mismatched signed/rendered fields, stale status cache, cross-context proof reuse, multi-protocol verifier confusion.

## 2. W3C SHACL 1.2 Core / SPARQL 1.2 RL drafts — semantic validation and derivation
**Published:** 2026-10-08. **Status:** W3C Working Drafts; neither is a new W3C Recommendation. Existing SHACL 2017 remains a Recommendation.

SHACL defines RDF shapes and validation constraints. SPARQL-RL proposes Datalog-style rule inference, dependency analysis and stratification. The relevant design insight is to separate *validated shape*, *derived proposition* and *observed fact*.

**Opportunity:** a future `koschei.graph`/evidence-library adapter with `SourceFact<T>`, `ValidatedGraph<T>`, `DerivedFact<T,RuleSetId>`, `ObservedEffect<T,Receipt>`.
**Threat:** rule derivations can amplify untrusted inputs or exhaust resources; inferred graph edges may be mistakenly used as cryptographic or chain-finality evidence.
**Competitor gap (hypothesis):** explicit provenance and effect typing can make reasoning pipelines more auditable than untyped triples.
**Product idea:** bounded, deterministic, versioned rule-evaluation adapter in a sandbox, recording `ruleset_hash`, `source_graph_hash`, `derivation_trace`, `confidence/proof_kind`; do not implement SPARQL-RL in language core while draft semantics evolve.
**Acceptance criteria:** no `DerivedFact`→`ObservedFact` implicit cast; validation errors preserved; imported rules scoped; provenance remains attached after transformations.

## Design decision
No language grammar or runtime behavior change is authorized from today's research. Record concepts for review; preserve existing working features and backward compatibility. Implement adapters only after a concrete design proposal, conformance tests and threat model.

## Status and terminology
Real standards: VC Data Model v2.0; SHACL 2017. Today's W3C Group Note Drafts and Working Drafts are not final standards. Web4–Web8 generation names remain non-standard branding/visions, not accepted IETF/W3C protocol generations.

## Primary sources (all dated 2026-10-08)
- https://www.w3.org/news/2026/first-draft-notes-verifiable-credential-threat-models/
- https://www.w3.org/TR/vc-recognized-entities-threat-model-1.0/
- https://www.w3.org/TR/vc-data-integrity-threat-model-1.1/
- https://www.w3.org/TR/vcalm-threat-model-1.0/
- https://www.w3.org/TR/vc-barcodes-threat-model-1.0/
- https://www.w3.org/TR/vc-render-method-threat-model-1.0/
- https://www.w3.org/TR/shacl12-core/
- https://www.w3.org/TR/sparql12-rl/
