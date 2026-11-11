# Koschei Lang research — 2026-10-09

Design-only notes; no compiler/runtime modifications.

## Motivation
Agent identity proofs must not silently become executable authority. Post-quantum signature implementation support must not silently become an active network security guarantee.

## Candidate research
SAIP-12: https://datatracker.ietf.org/doc/draft-jovancevic-saip/12/ (individual Internet-Draft, not standard; verify revision details).
Cosmos Ledger Security 2026.1 PQ announcement: independent release and deployment verification pending.
OpenA2A AIP-04 dated October 6: background, outside last 24 hours.

## Language architecture opportunities
Conceptual, not implemented:
- VerifiedIdentity<Proof,Issuer> is evidence of identity, not permission.
- DelegatedAuthority<Principal,Scope,Expiry> is explicitly granted and revocable.
- AuthorizedEffect<Policy,Target> requires checked authority.
- CryptoPolicy<Scheme,KeyEpoch,Network> captures current cryptographic configuration.
- SignedArtifact<PolicySnapshot> supports historical verification without applying today's policy retroactively.
- ObservedFinality<Network,Height,Evidence> is separate from proposed execution.

## Threat / competitive hypothesis / product experiment
Threat: implicit coercions from signed data or reputation to authority; stale crypto policy after network upgrades.
Hypothesis: type/effect systems that track chain finality and delegated authority may differentiate Koschei Lang; not an established competitor deficiency.
Experiment: static checker that rejects identity-to-authority implicit conversions, mismatched key epochs and unsupported claims of finalized effects. Preserve compatibility with existing language features.

## Standards hygiene
Web4–Web8 labels are not universal ratified W3C/IETF internet generations. IETF drafts and vendor protocols remain explicitly provisional.
