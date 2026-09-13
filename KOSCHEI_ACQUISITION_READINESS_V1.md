# Koschei Acquisition Readiness Gate v1

Status: **ACTIVE DUE-DILIGENCE CHECKLIST — NOT A CLAIM OF SALE READINESS**

Purpose: make technical acquisition readiness evidence-driven. A gate may be marked VERIFIED only when the repository or an independently reproducible artifact proves it. Marketing language, roadmap intent, or developer memory is not evidence.

## Status vocabulary

- **VERIFIED** — current repository/artifact supplies direct evidence.
- **PARTIAL** — meaningful implementation exists but buyer-grade closure is incomplete.
- **BLOCKER** — unresolved issue can materially break execution, security, provenance, transferability, or reproducibility.
- **NEEDS_EXTERNAL_EVIDENCE** — cannot be proven from source alone and needs an independently retained receipt, legal record, infrastructure attestation, or reproducible build output.

## P0 technical transfer gates

| Gate | Status | Current evidence | Closure requirement |
| --- | --- | --- | --- |
| Canonical compiler security authority | PARTIAL | Physics/Khar/Galaxy/MIR authority layers exist; Physics registry explicitly carries `authority=False` | Close remaining Laws 6/8/10/11/12 without creating parallel semantic authority |
| Match semantic single-truth path | PARTIAL | `TypedMatchResolution`, `MirVariantIs`, `MirVariantPayload`, CFG proof validation, fail-closed runtime boundary, and `mir_canonical_lowering_v1.py` exist | Production `mir.py` must explicitly import/use the canonical lowering entry-point; then pin with regression tests and validation receipt |
| Production MIR lowering entry-point | BLOCKER | `mir.py` calls `lower_function_blocks_v1(...)`; current import section does not explicitly bind that symbol | Wire `koschei.mir_canonical_lowering_v1.lower_function_blocks_v1` explicitly and prove supported `MatchExpression` no longer enters AST fallback |
| Fresh full validation evidence | NEEDS_EXTERNAL_EVIDENCE | `ks-local-validate` is packaged as the local validation command | Produce and retain a fresh full-profile validation receipt for the exact acquisition candidate commit |
| Protected release branch | NEEDS_EXTERNAL_EVIDENCE | Current connector cannot read private-repository branch-protection/ruleset endpoints | Buyer data room must contain branch/ruleset export or equivalent administrative screenshot/API evidence showing required protections |
| Reproducible acquisition candidate | BLOCKER | Current package metadata is `0.10.0`; public GitHub release remains `v0.9.0` prerelease with no assets | Cut a version-consistent candidate with immutable commit/tag identity, checksums, build recipe, validation receipt, and release artifacts |
| Dependency attack surface | VERIFIED_SLICE | `pyproject.toml` declares zero runtime Python dependencies for compiler core | Add generated SBOM covering repository/build/native/tooling dependencies, not only Python runtime dependencies |
| Native/backend semantic parity | PARTIAL | Sealed MIR/native structures exist | Produce cross-consumer parity tests for interpreter/native/backend fingerprint and authorization semantics |
| Fail-closed execution proofs | PARTIAL | Canonical proof/evidence mechanisms and variant CFG proof validation exist | Make proof-producing execution structurally authoritative on critical effect paths and retain verification fixtures |
| Rollback/continuity resistance | PARTIAL | Continuity semantics exist | Bind accepted state to rollback-aware monotonic/external evidence appropriate to deployment model |
| Independent physical trust root | PARTIAL | Logical authority separation exists | Document and demonstrate deployment profile using TPM/TEE/HSM/isolated verifier/transparency or explicitly scope the product as software-only |

## P0 IP and transferability gates

| Gate | Status | Current evidence | Closure requirement |
| --- | --- | --- | --- |
| Current code license | VERIFIED_SLICE | Repository `LICENSE` states current/future code is proprietary and confidential unless separately licensed | Counsel/owner should confirm acquisition agreement transfers all relevant rights and confidential materials |
| Historical public licensing | PARTIAL | `LICENSE` explicitly states earlier publicly released MIT revisions remain under their historical terms | Produce a revision/tag map identifying exactly which historical commits were MIT-public and which code lineage is proprietary |
| Chain of title | NEEDS_EXTERNAL_EVIDENCE | Repository metadata names an author/copyright holder, but source control alone cannot prove complete legal ownership | Collect contributor/contractor assignments, employment/IP agreements if applicable, and signed owner attestation |
| Third-party code/license inventory | BLOCKER | License notice acknowledges third-party components may exist, but this gate has no complete inventory yet | Generate SBOM + NOTICE/attribution inventory + provenance for vendored/native/model/tooling components |
| Trademark/domain/account transfer | NEEDS_EXTERNAL_EVIDENCE | Not provable from source | Inventory names, domains, package registries, social accounts, signing identities, cloud accounts, and transfer procedures |

## P1 commercial engineering gates

1. **Version coherence** — package version, tag, release notes, binaries, manifests, SBOM and receipts must refer to one immutable candidate.
2. **Build reproducibility** — clean-room build instructions must reproduce buyer-visible artifacts from the candidate commit.
3. **Benchmark dossier** — publish deterministic compiler/runtime/security benchmarks with hardware/toolchain metadata and raw results; do not use unsupported superlatives.
4. **Threat-model dossier** — document protected assets, trust boundaries, attacker capabilities, fail-closed assumptions and residual risk.
5. **Security regression corpus** — pin authority-confusion, provenance-substitution, rollback, malformed-proof, host-shape impersonation and semantic-divergence tests.
6. **Operational handover** — document release signing, emergency revocation, disclosure intake, key rotation, build custody and recovery procedures.
7. **Architecture map** — map KA/VOR/SHI/THAL/NUR, Khar, Galaxy, Continuity, evidence, MIR and backend boundaries to enforceable code owners and tests.
8. **API/ABI stability statement** — identify stable, experimental and internal surfaces; acquisition buyer must know what can be changed without semantic breakage.

## Candidate acceptance rule

An acquisition candidate is **not buyer-ready** until all P0 `BLOCKER` items are closed and every `NEEDS_EXTERNAL_EVIDENCE` item has an artifact retained outside the mutable working tree. A passing test count alone is insufficient.

The final candidate record must bind at minimum:

- repository full name;
- immutable commit SHA;
- version and tag;
- source/archive hashes;
- compiler/runtime build hashes;
- SBOM hash;
- full validation receipt hash;
- benchmark dossier hash;
- threat-model version/hash;
- release-signing identity or an explicit statement that signing is not yet deployed;
- licensing/chain-of-title evidence index;
- date and toolchain/environment metadata.

## Immediate execution order

1. Fix explicit production MIR lowering wiring and add regression coverage.
2. Run/retain full validation evidence for the exact head.
3. Generate third-party/SBOM inventory and historical-license revision map.
4. Align package/release/tag identity for the next candidate; do not overwrite historical `v0.9.0` evidence.
5. Add buyer-facing reproducible build and benchmark dossier.
6. Close remaining Physics Laws 6/8/10/11/12 with evidence, not labels.

This document is a technical due-diligence control, not legal advice and not a valuation statement.
