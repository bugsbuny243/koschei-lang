# Attested Maturity Evidence v2

`ks maturity` historically accepted manually-authored boolean evidence. That remains useful for incubation checks, but two security-sensitive claims are now protected:

```text
package_integrity
reproducible_builds
```

A `koschei.maturity-evidence.v1` file may no longer set either protected check to `true`. Those checks must come from `koschei.maturity-evidence.v2`, created by `ks maturity-attest` after verifying a real release-proof chain.

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

The command re-verifies both native builds, both locks, both manifests, sealed MIR identity, the reproducibility report, and the release proof before deriving:

```text
package_integrity = true
reproducible_builds = true
```

It also hashes the complete `koschei-verify-report` ZIP and parses `verify-report.txt`. The report must contain a passing test suite, sealed MIR proof, capability example, KS2401 supply-chain rejection, and a `no failures` summary.

The v2 evidence binds:

- the manual v1 evidence digest;
- release-proof digest;
- release artifact SHA-256;
- module-lock digest;
- CI artifact ZIP SHA-256;
- CI head commit SHA;
- verify-report SHA-256;
- test artifact SHA-256 and test count;
- warning count;
- observed repository-truth, sealed-MIR, and capability-security signals;
- the complete attestation digest.

## Re-verify

```bash
ks maturity-attest verify \
  --base-evidence configs/maturity/manual-reference.json \
  <same release/witness/report/proof/CI inputs> \
  --attested-evidence build/maturity/reference.attested.json
```

Verification recomputes the entire expected v2 payload and requires byte-equivalent semantic content.

The resulting v2 evidence can be evaluated normally:

```bash
ks maturity \
  --evidence build/maturity/reference.attested.json \
  --target reference
```

## Trust boundary

The CI ZIP is hashed and its report is structurally validated, but this v1 attestation format does **not** claim GitHub OIDC/provider-signed provenance. The `ci_head_sha` is bound into the evidence, not cryptographically vouched for by GitHub inside the artifact. A future provider-signed CI attestation can strengthen that boundary.

A maturity attestation does not grant owner approval, publish packages, or authorize production integration. Production still requires every separate maturity check, including explicit owner approval.
