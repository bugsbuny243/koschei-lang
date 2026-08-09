# Attested Maturity Evidence v4

`ks maturity` still accepts manually-authored core evidence for the **incubation** target, but reference and production maturity require stronger provenance and live re-verification of the bound artifacts.

The following checks are derived from verified release and CI artifacts in `koschei.maturity-evidence.v4`:

```text
compiler_tests
repository_truth
capability_security
package_integrity
reproducible_builds
interpreter_native_parity
```

`interpreter_native_parity` is no longer accepted as a manually asserted v1 maturity check. Legacy v2/v3 evidence remains readable for history, but it cannot satisfy current attested reference or production trust. Incubation compatibility for the non-protected core checks is preserved.

## Explicit parity evidence

The repository-truth gate now runs representative Koschei programs through both execution paths:

```text
Koschei source
→ interpreter stdout
→ native build
→ native binary stdout
→ byte-for-byte equality
```

The passing cases cover multiple language surfaces, including control flow, collections, structs, algebraic types and modules. For each passing case the gate records the SHA-256 of the interpreter/native-identical output. Those deterministic case records are hashed into a single parity evidence digest.

`verify-report.txt` therefore contains an explicit line of the form:

```text
PASS  interpreter/native parity: 7 cases — PARITY SHA256: <sha256>
```

Maturity v4 requires at least five passing parity cases and binds both the case count and parity evidence SHA-256 into the attestation. A report with no parity evidence, too few cases, a malformed digest, or any interpreter/native mismatch fails closed.

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
- explicit interpreter/native parity evidence for at least five cases;
- a passing capability example;
- the KS2401 supply-chain rejection;
- a `no failures` summary.

Only after those checks does v4 derive the six protected/reference maturity checks above.

The attestation binds the manual evidence digest, release-proof digest, native artifact SHA-256, module-lock digest, CI artifact SHA-256, CI head SHA, verify-report SHA-256, test artifact SHA-256, test count, warning count, parity case count, parity evidence SHA-256, observed security signals, and a canonical attestation digest.

## Re-verify and decide reference/production maturity

A saved v4 JSON file is **not** trusted merely because its unkeyed SHA-256 digest is internally consistent. Reference and production decisions must re-verify every bound artifact in the same command:

```bash
ks maturity-attest verify \
  --base-evidence configs/maturity/manual-reference.json \
  <same release/witness/report/proof/CI inputs> \
  --attested-evidence build/maturity/reference.attested.json \
  --target reference
```

Verification recomputes the complete v4 payload from the supplied source trees, locks, build manifests, native artifact bytes, reproducibility report, release proof and CI ZIP. Only after the observed v4 payload matches that recomputed evidence does the command call the maturity gate with verified provenance.

Plain:

```bash
ks maturity --evidence build/maturity/reference.attested.json --target reference
```

is intentionally rejected for attested reference/production decisions because a standalone JSON file cannot prove its own provenance. `ks maturity` remains the direct path for incubation evidence.

## Trust boundary

The current CI ZIP is hash-bound and structurally validated, but is not yet GitHub OIDC/provider-signed provenance. `ci_head_sha` is bound into the evidence rather than cryptographically vouched for inside the artifact.

Parity evidence proves the selected release-gate programs produced byte-identical outputs in the interpreter and native backend on that CI run. It does **not** claim exhaustive semantic equivalence for every possible Koschei program; broader fuzzing and adversarial parity remain separate maturity requirements.

A maturity attestation does not grant owner approval, publish packages, or authorize production integration.
