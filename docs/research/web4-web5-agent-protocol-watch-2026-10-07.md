# Web4/Web5 Agent Protocol Watch — 2026-10-07

## OpenA2A AIP -04 — 6 October 2026

OpenA2A AIP -04 is a new individual IETF Internet-Draft revision with architecture-relevant changes for Koschei Lang.

### New signals

- Behavioral trust now uses `behaviorTier`, separating it from the companion Agent Trust Protocol's provenance-oriented `trustLevel`.
- Evidence sufficiency is explicit: if `includedWeight` is below 0.50, the agent is `unscored`; the score is null and no trust credential is issued.
- Published assessments carry `algorithmVersion`.
- Capability grammar is centralized into one shared vocabulary.
- `declaredPurpose` is structured signed metadata, but the draft explicitly says it must not be treated as an authorization input.
- Provider-scoped identity uses `did:web`; ecosystem-scoped trust uses `did:opena2a`; identifier verification remains method-agnostic.

### Koschei Lang impact

Recommended provider-independent separations:

```text
DeclaredPurpose != AuthorizationGrant
CapabilityDeclaration != CapabilityPermission
BehavioralTrust != ProvenanceTrust
TrustScore != AuthorizationDecision
InsufficientEvidence != LowTrust
IdentityIdentifier != IdentityProvider
```

Candidate primitives:

- `EvidenceCoverage`
- `AssessmentStatus = Scored | Unscored(reason)`
- `AssessmentAlgorithmVersion`
- `BehavioralTrustEvidence`
- `ProvenanceTrustEvidence`
- `DeclaredPurposeAttestation`
- `CapabilityDescriptor` versus `CapabilityGrant`
- `IdentifierAdapter`

### Recommendation

Keep OpenA2A trust scores, VC/DID forms and identity-provider details as typed evidence through adapters. Koschei Lang policy semantics should remain provider-independent. Model `unscored` as a first-class state instead of converting missing evidence into a numeric score.

### Status

OpenA2A AIP -04 is dated 6 October 2026 and remains work in progress, not an adopted IETF standard.

Source: IETF Datatracker, draft-fane-opena2a-aip-04.
