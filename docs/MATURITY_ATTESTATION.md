# Attested Maturity Evidence v3

`ks maturity` still accepts manually-authored core evidence for the **incubation** target, but reference and production maturity now require stronger provenance and live re-verification of the bound artifacts.

The following checks are derived from verified release and CI artifacts in `koschei.maturity-evidence.v3`:

```text
compiler_tests
repository_truth
capability_security
package_integrity
reproducible_builds
```

Legacy v1 evidence cannot self-assert `package_integrity` or `reproducible_builds`. Legacy v2 evidence remains readable, but it cannot satisfy the attested checks for reference or production. Incubation compatibility is preserved.

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

The command re-verifies both native builds, both locks, both manifests, sealed MIR identity, the reproducibility report, and the release proof. It also hashes and structurally validates `koschei-verify-report.zip` and requires its `verify-report.txt` to contain:

- a passing non-empty unit-test suite;
- a sealed MIR identity check;
- a passing capability example;
- the KS2401 supply-chain rejection;
- a `no failures` summary.

Only after those checks does v3 derive the five protected maturity checks above.

The attestation binds the manual evidence digest, release-proof digest, native artifact SHA-256, module-lock digest, CI artifact SHA-256, CI head SHA, verify-report SHA-256, test artifact SHA-256, test count, warning count, observed security signals, and a canonical attestation digest.

## Re-verify and decide reference/production maturity

A saved v3 JSON file is **not** trusted merely because its unkeyed SHA-256 digest is internally consistent. Reference and production decisions must re-verify every bound artifact in the same command:

```bash
ks maturity-attest verify \
  --base-evidence configs/maturity/manual-reference.json \
  <same release/witness/report/proof/CI inputs> \
  --attested-evidence build/maturity/reference.attested.json \
  --target reference
```

Verification recomputes the complete v3 payload from the supplied source trees, locks, build manifests, native artifact bytes, reproducibility report, release proof and CI ZIP. Only after the observed v3 payload matches that recomputed evidence does the command call the maturity gate with verified provenance.

Plain:

```bash
ks maturity --evidence build/maturity/reference.attested.json --target reference
```

is intentionally rejected for attested reference/production decisions because a standalone JSON file cannot prove its own provenance. `ks maturity` remains the direct path for incubation evidence.

## Trust boundary

The current CI ZIP is hash-bound and structurally validated, but is not yet GitHub OIDC/provider-signed provenance. `ci_head_sha` is bound into the evidence rather than cryptographically vouched for inside the artifact.

`interpreter_native_parity` is intentionally **not** derived by v3 because the current repository-truth artifact does not contain an explicit parity attestation. That check remains a separate gap until the CI artifact format is extended to prove it directly.

A maturity attestation does not grant owner approval, publish packages, or authorize production integration.
