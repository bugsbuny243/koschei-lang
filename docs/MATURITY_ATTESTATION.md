# Attested Maturity Evidence v5

`ks maturity` still accepts manually-authored core evidence for the **incubation** target, but reference and production maturity require stronger provenance and live re-verification of the bound artifacts.

The following checks are derived from verified release and CI artifacts in `koschei.maturity-evidence.v5`:

```text
compiler_tests
repository_truth
capability_security
package_integrity
reproducible_builds
interpreter_native_parity
fuzzing
```

`interpreter_native_parity` and `fuzzing` are not accepted as manually asserted v1 maturity checks. Legacy v2/v3/v4 evidence remains readable for history, but current fuzzing trust requires live-reverified v5 evidence. Incubation compatibility for non-protected core checks is preserved.

## Explicit fixed-corpus parity evidence

The repository-truth gate runs representative Koschei programs through both execution paths:

```text
Koschei source bytes
→ interpreter raw stdout bytes
→ native build
→ native binary raw stdout bytes
→ cmp byte-for-byte equality
```

The fixed passing cases cover multiple language surfaces, including control flow, collections, structs, algebraic types and modules. stdout is captured to files rather than shell variables, so trailing newlines and all other bytes remain part of the comparison. A non-zero exit, unexpected stderr, build failure or any stdout-byte difference fails the parity case.

For each passing fixed case the gate records the source-file SHA-256 together with the SHA-256 of the interpreter/native-identical stdout bytes. Those deterministic records are hashed into one parity evidence digest.

`verify-report.txt` contains a line of the form:

```text
PASS  interpreter/native parity: 7 cases — PARITY SHA256: <sha256>
```

v5 requires at least five passing fixed parity cases and binds their case count and evidence SHA-256 into the attestation.

## Deterministic differential fuzz evidence

The release gate also runs a deterministic grammar-generated corpus through both execution paths. The current v1 generator uses an explicit seed and bounded templates for arithmetic, branching, loops and ordinary functions.

```text
seed + generator version
→ generated Koschei source bytes
→ interpreter raw stdout bytes
→ native build
→ native raw stdout bytes
→ byte-identical comparison
→ per-case source/output SHA-256
→ canonical corpus SHA-256
→ fuzz report SHA-256
```

The repository-truth gate currently requires 16 generated cases with seed `20260809`. Each generated case fails closed on an interpreter error, native build error, native execution error, unexpected runtime stderr, timeout, or stdout-byte difference.

The gate emits:

```text
PASS  differential fuzz: 16 cases seed 20260809 — FUZZ SHA256: <sha256> — CORPUS SHA256: <sha256>
```

Maturity v5 requires at least 16 passing generated cases and binds the case count, seed, fuzz report SHA-256 and corpus SHA-256 into the attestation. A standalone evidence JSON cannot self-assert this check.

This is a bounded differential corpus, not a proof of exhaustive semantic equivalence. The separate `adversarial_capability_tests` maturity check is **not** derived from this fuzz result and remains an independent production requirement.

## Run the differential corpus directly

```bash
ks differential-fuzz \
  --seed 20260809 \
  --cases 16 \
  --output build/fuzz/differential.json
```

The report uses `koschei.differential-fuzz-report.v1` and records the generator version, seed, per-case source/output hashes, corpus digest and report digest. It always states:

```text
adversarial_capability_tests_observed = false
production_integration_allowed = false
```

## Create attested evidence

```bash
ks maturity-attest create \
  --base-evidence configs/maturity/manual-reference.json \
  --release-source build-a/src/main.ks \
  --release-lockfile build-a/koschei.lock.json \
  --release-manifest build-a/app.build.json \
  --release-artifact build-a/app \
  --witness-source build-b/src/main.ks \
  --witness-lockfile build-b/koschei.lock.json \
  --witness-manifest build-b/app.build.json \
  --witness-artifact build-b/app \
  --report build/reproducibility/app.report.json \
  --proof build/release/app.release-proof.json \
  --ci-artifact koschei-verify-report.zip \
  --ci-head-sha <40-character-git-sha> \
  --output build/maturity/reference.attested.json
```

The command re-verifies both native builds, both locks, both manifests, sealed MIR identity, the reproducibility report and the release proof. It also hashes and structurally validates `koschei-verify-report.zip` and requires its `verify-report.txt` to contain:

- a passing non-empty unit-test suite;
- a sealed MIR identity check;
- explicit interpreter/native parity evidence for at least five fixed cases;
- deterministic differential fuzz evidence for at least 16 generated cases;
- a passing capability example;
- the KS2401 supply-chain rejection;
- a `no failures` summary.

Only after those checks does v5 derive the protected checks above.

The attestation binds the manual evidence digest, release-proof digest, native artifact SHA-256, module-lock digest, CI artifact SHA-256, CI head SHA, verify-report SHA-256, test artifact SHA-256, test count, warning count, parity case count/digest, fuzz case count/seed/report digest/corpus digest, observed security signals and a canonical attestation digest.

## Re-verify and decide reference/production maturity

A saved v5 JSON file is **not** trusted merely because its unkeyed SHA-256 digest is internally consistent. Reference and production decisions must re-verify every bound artifact in the same command:

```bash
ks maturity-attest verify \
  --base-evidence configs/maturity/manual-reference.json \
  <same release/witness/report/proof/CI inputs> \
  --attested-evidence build/maturity/reference.attested.json \
  --target reference
```

Verification recomputes the complete v5 payload from the supplied source trees, locks, build manifests, native artifact bytes, reproducibility report, release proof and CI ZIP. Only after the observed v5 payload matches that recomputed evidence does the command call the maturity gate with verified provenance.

Plain:

```bash
ks maturity --evidence build/maturity/reference.attested.json --target reference
```

is intentionally rejected for attested reference/production decisions because a standalone JSON file cannot prove its own provenance. `ks maturity` remains the direct path for incubation evidence.

## Trust boundary

The current CI ZIP is hash-bound and structurally validated, but is not yet GitHub OIDC/provider-signed provenance. `ci_head_sha` is bound into the evidence rather than cryptographically vouched for inside the artifact.

Fixed parity evidence proves the selected release-gate programs produced byte-identical raw stdout in the interpreter and native backend on that CI run. Differential fuzz evidence expands that coverage with deterministic generated programs, but it still does **not** prove every possible Koschei program or every security-sensitive capability path.

A maturity attestation does not grant owner approval, publish packages, satisfy `adversarial_capability_tests`, or authorize production integration.
