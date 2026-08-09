# Attested Maturity Evidence v3

`ks maturity` still accepts manually-authored core evidence for the **incubation** target, but reference and production maturity now require stronger provenance for several checks.

The following checks are derived from verified release and CI artifacts in `koschei.maturity-evidence.v3`:

```text
compiler_tests
repository_truth
capability_security
package_integrity
reproducible_builds
```

Legacy v1 evidence cannot self-assert `package_integrity` or `reproducible_builds`. Legacy v2 evidence remains readable, but manually supplied `compiler_tests`, `repository_truth`, and `capability_security` are not trusted for `reference` or `production` evaluation. Incubation compatibility is preserved.

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

## Re-verify

```bash
ks maturity-attest verify \
  --base-evidence configs/maturity/manual-reference.json \
  <same release/witness/report/proof/CI inputs> \
  --attested-evidence build/maturity/reference.attested.json
```

Verification recomputes the complete v3 payload and requires semantic byte-equivalent content.

```bash
ks maturity \
  --evidence build/maturity/reference.attested.json \
  --target reference
```

## Trust boundary

The current CI ZIP is hash-bound and structurally validated, but is not yet GitHub OIDC/provider-signed provenance. `ci_head_sha` is bound into the evidence rather than cryptographically vouched for inside the artifact.

`interpreter_native_parity` is intentionally **not** derived by v3 because the current repository-truth artifact does not contain an explicit parity attestation. That check remains a separate gap until the CI artifact format is extended to prove it directly.

A maturity attestation does not grant owner approval, publish packages, or authorize production integration.
