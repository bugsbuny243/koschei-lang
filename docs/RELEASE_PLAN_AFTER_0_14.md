# Koschei Lang — proposed release plan after 0.14.0

Status: **planning proposal**, not a release announcement, guarantee or date commitment.
Source of truth for shipped functionality: \`pyproject.toml\`, \`CHANGELOG.md\`, tests, and artifacts from the exact tagged release.
This plan is an incremental interpretation of \`docs/v5-roadmap.md\` and \`docs/stdlib-roadmap-v5.md\`, not a replacement for either.

## What 0.14.0 has shipped (13 November 2026)

- Capability-scoped disk/network/env/process access.
- \`ks check\`, \`ks run\` and a Go-backed \`ks build\` path.
- Non-capturing lambdas and faster canonical MIR interpretation.
- Generic structs work under \`ks run\`, but native compilation still refuses them.
- SQLite database capability is present under \`ks run\` (0.13.0), not the native build.
- JSON \`Data\` reading is present in the interpreter (0.11.0), not in native builds.
- Windows and Linux native executables exist, but this is not universal platform certification.
- Pre-1.0: no claim of independent security certification, full self-hosting, production WASM/WASI, or native/interpreter parity for every feature.

## Proposed next series (numbers tentative)

### 0.15.0 — language/backend parity

**Primary outcomes:** bring typed generic structs and supported data operations to native parity, or explicitly reject the feature in both paths until the contract is defined.

Acceptance gates:
- Identical expected output, errors, types and capability decisions for matching \`ks run\` and \`ks build\` programs.
- Regression tests for nested and mismatched generic instantiations, JSON edge cases and SQLite policy.
- Native build cannot silently substitute a less secure feature or alternate semantics.
- Exact commit passes focused and canonical validation receipts.

### 0.16.0 — bounded Core Library security

**Primary outcomes:** fulfill the earlier gates in \`docs/stdlib-roadmap-v5.md\`: bounded structured data, scalar/output parity, and budgets for file/network operations.

Acceptance gates:
- Bytes, timeouts, row counts, depth, steps and error outcomes are explicit and enforced by every supported backend.
- Capability/secret values cannot be laundered through output, serialization or collections.
- Malformed and resource-exhausting inputs fail closed and never produce partial file commits.
- Statuses in the standard-library catalog remain \`reserved\` until contractual proof exists.

### 0.17.0 — developer-grade secure services (proposal)

**Primary outcomes:** capability-bound HTTP services, bounded JSON+database operations, clearer diagnostics, guides, examples and tool integration.

Acceptance gates:
- Real HTTP request/response size, connection, time and origin limits.
- Typed tests for authorization, input validation and adverse network behavior.
- At least one complete bilingual, documented, reproducibly tested secure service example.
- Do not conflate locally working services with independently reviewed production readiness.

### 0.18.0 and later — portability and ecosystem (proposal)

**Primary outcomes:** supported Windows/Linux/macOS targets, WASM/WASI implementation and compatibility checks if feasible, reproducibility, signed capability-declared dependencies, and safer tooling.

Acceptance gates:
- Platform-specific integration evidence, not just executable file format or cross-compilation.
- No backend bypass or weaker capability policy.
- Verified artifact provenance and repeatable builds.
- Maintain distinct published versus experimental platform support labels.

## 1.0 release gates, not a scheduled date

1. Stable documented language semantics and compatibility policy.
2. Native/interpreter/security-tooling equivalence for supported features.
3. Reproducible bootstrap/self-hosting direction proven or explicitly scoped, never claimed without evidence.
4. Formalized ownership/region model where needed for native safety.
5. Bounded and versioned secure standard-library contracts.
6. Signed/capability-declared dependency model and supply-chain verification.
7. Platform validation, security fuzzing and independent security review.

## Release protocol for any 0.x milestone

1. Freeze scope and list unsupported features.
2. Implement and document behavior, including both execution paths.
3. Run unit, malicious-input, resource-budget and cross-platform integration tests.
4. Produce exact-commit validation receipts and artifact checksums.
5. Publish changelog and update version metadata only after validation.
6. Package release artifacts and verify customer installation/download before updating Polar license benefits.
7. Explain commercial update entitlement accurately: individual commercial licenses include releases made in the 12 months after purchase; no future version or date is promised.
8. Update the website's current-version and roadmap labels only after the release exists.

No milestone here should trigger re-enabling the paused public Playground. Untrusted hosted execution requires a separate, successful sandbox and admission review.
