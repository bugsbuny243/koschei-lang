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
| Match semantic single-truth path | PARTIAL | `TypedMatchResolution`, `MirVariantConstruct`, `MirVariantIs`, `MirVariantPayload`, CFG proof validation, exact v4 registry sealing, fail-closed AST fallback guard, native runtime execution and strict MIR-Go generation now share exact `Owner::Variant` identity | Run the exact-head full validation profile and retain the receipt; extend the same no-second-authority discipline to any remaining semantic fallback boundaries |
| Production MIR lowering entry-point | PARTIAL | `mir.py` explicitly imports the canonical lowering entry-point; Match and checked variant construction are projected into executable MIR without backend owner guessing | Run under the full validation profile and retain the receipt for the exact candidate commit |
| Fresh full validation evidence | NEEDS_EXTERNAL_EVIDENCE | `ks-local-validate` now runs the pytest suite, repository truth, adversarial lab and a reproducible-input SBOM gate; evidence is bound to candidate commit/environment | Produce and retain a fresh full-profile validation receipt for the exact acquisition candidate commit |
| Protected release branch | BLOCKER | Repository branch metadata reports `main` as `protected=false` with required status checks off | Enable and retain evidence for an appropriate protected release/main policy before buyer-ready status |
| Reproducible acquisition candidate | BLOCKER | `Dockerfile.production` pins Docker Official Image roots by digest; Debian resolution is bound to a dated snapshot; Python release tooling is hash-locked; deterministic ZIP packaging exists; `tools/reproducible_artifact_receipt_v1.py` requires two byte-identical artifacts; candidate manifest verifies validation/SBOM/reproducibility evidence semantically | Execute two independent clean production builds for the same exact commit, retain a byte-equality receipt, then cut a coherent `v0.10.0` candidate artifact/release |
| Dependency attack surface | PARTIAL | Compiler core declares zero runtime Python dependencies; native Go module has no external `require`; production container roots and Python build artifacts are now lock-bound in source | Execute the production SBOM gate and retain resolved Debian package inventory/licenses for the exact candidate |
| Native/backend semantic parity | PARTIAL | Option/Result and single-module user-enum Match/variant construction/test/payload now have source→sealed MIR→native runtime and strict MIR-Go parity regressions | Run those regressions in canonical validation; expand native-build coverage for imports, structs and remaining collection/iteration surfaces |
| Fail-closed execution proofs | PARTIAL | Canonical proof/evidence mechanisms, variant true-edge proof validation and exact MIR-v4 registry admission exist | Make proof-producing execution structurally authoritative on critical effect paths and retain verification fixtures |
| Rollback/continuity resistance | PARTIAL | Continuity semantics exist | Bind accepted state to rollback-aware monotonic/external evidence appropriate to deployment model |
| Independent physical trust root | PARTIAL | Logical authority separation exists | Document and demonstrate deployment profile using TPM/TEE/HSM/isolated verifier/transparency or explicitly scope the product as software-only |

## P0 IP and transferability gates

| Gate | Status | Current evidence | Closure requirement |
| --- | --- | --- | --- |
| Current code license | VERIFIED_SLICE | Repository `LICENSE` states current/future code is proprietary and confidential unless separately licensed | Counsel/owner should confirm acquisition agreement transfers all relevant rights and confidential materials |
| Historical public licensing | PARTIAL | `KOSCHEI_LICENSE_LINEAGE_V1.md` records the repository boundary: parent `30086337...` still carries MIT; transition commit `661798a8...` replaces it with proprietary terms while preserving historical grants | Retain public release/publication history showing which historical revisions were actually distributed under MIT |
| Chain of title | NEEDS_EXTERNAL_EVIDENCE | Repository metadata names an author/copyright holder, but source control alone cannot prove complete legal ownership | Collect contributor/contractor assignments, employment/IP agreements if applicable, and signed owner attestation |
| Third-party code/license inventory | PARTIAL | Production base images are digest-pinned, Python release tooling is hash-locked, Debian resolution is snapshot-bound, and the SBOM generator verifies lock/Dockerfile parity | Retain the generated exact-candidate SBOM, resolved Debian package list, NOTICE/attribution inventory and clean-room build evidence |
| Trademark/domain/account transfer | NEEDS_EXTERNAL_EVIDENCE | Not provable from source | Inventory names, domains, package registries, social accounts, signing identities, cloud accounts, and transfer procedures |

## P1 commercial engineering gates

1. **Version coherence** — package version, tag, release notes, binaries, manifests, SBOM and receipts must refer to one immutable candidate.
2. **Build reproducibility** — two independent clean builds must produce byte-identical candidate artifacts; input pinning alone is insufficient.
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
- production container/dependency lock hashes;
- exact-candidate SBOM hash;
- full validation receipt hash;
- two-build reproducibility receipt hash;
- benchmark dossier hash;
- threat-model version/hash;
- release-signing identity or an explicit statement that signing is not yet deployed;
- licensing/chain-of-title evidence index;
- date and toolchain/environment metadata.

`tools/acquisition_candidate_manifest_v1.py` is the fail-closed binder for this evidence set. It validates the internal commit/version/digest claims of the validation, SBOM and reproducibility receipts before binding them. It is a packaging/provenance mechanism, not a readiness oracle.

## Immediate execution order

1. Run `ks-local-validate --profile full` on a clean checkout of the exact candidate head and retain the external receipt/evidence directory.
2. Build `Dockerfile.production` twice independently for that exact commit and require a byte-identical artifact receipt.
3. Retain the generated exact-candidate SBOM plus resolved Debian package/license inventory.
4. Align package/tag/release identity as `v0.10.0`; do not overwrite historical `v0.9.0` evidence.
5. Close remaining Physics Laws 6/8/10/11/12 with evidence, not labels, and expand strict native-build parity beyond the current Match/variant slice.
6. Enable release/main protection appropriate to the final candidate and retain administrative evidence.
7. Deploy or explicitly scope production signing custody, then seal the final candidate manifest.

This document is a technical due-diligence control, not legal advice and not a valuation statement.
