# Koschei Release Proof v1

`ks release-proof` seals one native release candidate only after the release build and an independent witness build both pass the full native verification chain and an existing reproducibility report is revalidated against those exact builds.

## Create a proof

```bash
ks release-proof create \
  --release-source build-a/src/main.ks \
  --release-lockfile build-a/koschei.lock.json \
  --release-manifest build-a/app.build.json \
  --release-artifact build-a/app \
  --witness-source build-b/src/main.ks \
  --witness-lockfile build-b/koschei.lock.json \
  --witness-manifest build-b/app.build.json \
  --witness-artifact build-b/app \
  --report build/reproducibility/app.report.json \
  --output build/release/app.release-proof.json
```

The command independently verifies both builds before trusting the reproducibility report:

- source/import graph against each module lock;
- module-lock digest;
- sealed MIR version and fingerprint;
- native build-manifest schema and digest;
- native artifact name, size and SHA-256;
- compiler version;
- native backend and exact Go toolchain identity;
- the saved reproducibility report against those exact verified builds.

A release proof is created only when the report is `byte_identical`, `byte_reproducible = true`, has no input mismatches, and both artifact names match.

The proof binds:

```text
module lock digest
MIR version + fingerprint
compiler version
backend + exact toolchain
release manifest digest
witness manifest digest
release artifact SHA-256
witness artifact SHA-256
reproducibility report digest
shared reproducibility-input digest
```

The release and witness artifact SHA-256 values must be identical.

## Verify an existing proof

```bash
ks release-proof verify \
  --release-source build-a/src/main.ks \
  --release-lockfile build-a/koschei.lock.json \
  --release-manifest build-a/app.build.json \
  --release-artifact build-a/app \
  --witness-source build-b/src/main.ks \
  --witness-lockfile build-b/koschei.lock.json \
  --witness-manifest build-b/app.build.json \
  --witness-artifact build-b/app \
  --report build/reproducibility/app.report.json \
  --proof build/release/app.release-proof.json
```

Verification rebuilds the expected proof from the supplied verified artifacts and report and requires the complete saved proof payload to match.

## Authority boundary

`koschei.release-proof.v1` is release-candidate evidence, not publication authority. Every proof is permanently marked:

```text
state = verified_reproducible_release_candidate
authority = release_candidate_evidence_only
byte_reproducible = true
owner_approval_required = true
automatic_publish_allowed = false
package_registry_write_allowed = false
production_integration_allowed = false
```

An existing proof is never overwritten silently. A proof by itself cannot publish a package, write to a registry, authorize production integration, or replace the separate maturity and owner-approval gates.
