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
| Match semantic single-truth path | PARTIAL | `TypedMatchResolution`, `MirVariantIs`, `MirVariantPayload`, CFG proof validation, fail-closed runtime boundary, canonical Match lowering, production canonical entry-point wiring and production-path no-fallback regression coverage exist | Execute the production regressions under the full validation profile and preserve parity across sealed consumers |
| Production MIR lowering entry-point | PARTIAL | `mir.py` explicitly imports `koschei.mir_canonical_lowering_v1.lower_function_blocks_v1`; regression tests pin module identity and Match no-fallback intent | Run under the full validation profile and retain the receipt for the exact candidate commit |
| Fresh full validation evidence | NEEDS_EXTERNAL_EVIDENCE | `ks-local-validate` is canonical; the manual workflow now binds candidate commit, Python/Go versions and receipt SHA-256 to uploaded evidence | Produce and retain a fresh full-profile validation receipt for the exact acquisition candidate commit |
| Protected release branch | BLOCKER | Repository branch metadata reports `main` as `protected=false` with required status checks off | Enable and retain evidence for an appropriate protected release/main policy before buyer-ready status |
| Reproducible acquisition candidate | BLOCKER | Package metadata is `0.10.0`; public GitHub release remains `v0.9.0` prerelease with no assets. `tools/acquisition_candidate_manifest_v1.py` now fail-closes on tag/version mismatch, dirty tree, missing evidence and absent signing scope | Produce the evidence set, use immutable dependency/build pins, generate the candidate manifest, cut a coherent tag/release and retain checksums/artifacts |
| Dependency attack surface | VERIFIED_SLICE | `pyproject.toml` declares zero runtime Python dependencies for compiler core; `native/go.mod` has no external `require` entries | Generate a complete hash-bound SBOM covering build/container/OS/native/tooling/model surfaces |
| Native/backend semantic parity | PARTIAL | Sealed MIR/native structures exist | Produce cross-consumer parity tests for interpreter/native/backend fingerprint and authorization semantics |
| Fail-closed execution proofs | PARTIAL | Canonical proof/evidence mechanisms and variant CFG proof validation exist | Make proof-producing execution structurally authoritative on critical effect paths and retain verification fixtures |
| Rollback/continuity resistance | PARTIAL | Continuity semantics exist | Bind accepted state to rollback-aware monotonic/external evidence appropriate to deployment model |
| Independent physical trust root | PARTIAL | Logical authority separation exists | Document and demonstrate deployment profile using TPM/TEE/HSM/isolated verifier/transparency or explicitly scope the product as software-only |

## P0 IP and transferability gates

| Gate | Status | Current evidence | Closure requirement |
| --- | --- | --- | --- |
| Current code license | VERIFIED_SLICE | Repository `LICENSE` states current/future code is proprietary and confidential unless separately licensed | Counsel/owner should confirm acquisition agreement transfers all relevant rights and confidential materials |
| Historical public licensing | PARTIAL | `KOSCHEI_LICENSE_LINEAGE_V1.md` records the repository boundary: parent `30086337...` still carries MIT; transition commit `661798a8...` replaces it with proprietary terms while preserving historical grants | Retain public release/publication history showing which historical revisions were actually distributed under MIT |
| Chain of title | NEEDS_EXTERNAL_EVIDENCE | Repository metadata names an author/copyright holder, but source control alone cannot prove complete legal ownership | Collect contributor/contractor assignments, employment/IP agreements if applicable, and signed owner attestation |
| Third-party code/license inventory | PARTIAL | `KOSCHEI_THIRD_PARTY_PROVENANCE_V1.md` records Python, Go, container, OS and packaging surfaces and identifies current unpinned build dependencies | Generate SBOM + NOTICE/attribution inventory + immutable provenance for the exact candidate |
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

`tools/acquisition_candidate_manifest_v1.py` is the fail-closed binder for this evidence set. It is a packaging/provenance mechanism, not a readiness oracle.

## Immediate execution order

1. Execute canonical Match production lowering under the full validation profile and retain the exact-head receipt.
2. Produce the complete hash-bound SBOM/NOTICE from the existing third-party inventory.
3. Pin acquisition build inputs and align package/release/tag identity for `0.10.0`; do not overwrite historical `v0.9.0` evidence.
4. Add buyer-facing reproducible build, benchmark dossier and threat model artifacts, then seal them with the candidate manifest.
5. Close remaining Physics Laws 6/8/10/11/12 with evidence, not labels.
6. Enable release/main protection appropriate to the final acquisition candidate and retain administrative evidence.

This document is a technical due-diligence control, not legal advice and not a valuation statement.
