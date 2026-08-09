# Koschei Reproducibility Comparison v1

`ks build-compare` compares two independently produced native builds only after each build passes the complete source, lock, MIR, manifest, and artifact verification chain.

```bash
ks build-compare \
  --left-source build-a/src/main.ks \
  --left-lockfile build-a/koschei.lock.json \
  --left-manifest build-a/app.build.json \
  --left-artifact build-a/app \
  --right-source build-b/src/main.ks \
  --right-lockfile build-b/koschei.lock.json \
  --right-manifest build-b/app.build.json \
  --right-artifact build-b/app \
  --output build/reproducibility/app.report.json
```

Before comparison, both sides independently verify:

- strict `koschei.native-build-manifest.v1` schema and digest;
- native artifact name, size, and SHA-256;
- current source/import graph against its lockfile;
- module-lock digest;
- sealed MIR version and fingerprint.

## Result states

### `byte_identical`

The builds have the same:

- module-lock digest;
- MIR version and fingerprint;
- Koschei compiler version;
- native backend;
- exact Go toolchain identity;
- native artifact SHA-256.

The command exits with code `0` and records `byte_reproducible = true`.

### `artifact_mismatch`

All security-relevant inputs and the exact toolchain match, but the native artifact SHA-256 differs. The builds are comparable but not byte reproducible. The command exits with code `3`.

### `not_comparable`

At least one input identity differs: source lock, MIR, compiler version, backend, or toolchain. No byte-reproducibility claim is made. The command exits with code `2` and lists the mismatched fields.

Invalid, stale, or tampered artifacts fail before comparison with exit code `1`.

## Report integrity

The report uses `koschei.reproducibility-report.v1` and contains:

- both build-manifest digests;
- both native artifact SHA-256 values;
- input mismatch names;
- a shared-input digest when the builds are comparable;
- a digest over the complete report payload.

Existing reports are never overwritten silently.

## Verify a saved report

A report can later be checked against the exact two source trees, lockfiles, manifests, and native artifacts it claims to describe:

```bash
ks build-compare-verify \
  --report build/reproducibility/app.report.json \
  --left-source build-a/src/main.ks \
  --left-lockfile build-a/koschei.lock.json \
  --left-manifest build-a/app.build.json \
  --left-artifact build-a/app \
  --right-source build-b/src/main.ks \
  --right-lockfile build-b/koschei.lock.json \
  --right-manifest build-b/app.build.json \
  --right-artifact build-b/app
```

Verification strictly parses the report, rejects unknown fields and inconsistent status combinations, checks its digest, independently re-verifies both builds, recomputes the expected reproducibility result, and requires the complete report payload to match. A valid report from a different build pair is rejected.

This command measures reproducibility honestly. It does not claim two builds are equivalent when their source graph, MIR, compiler, backend, or toolchain differs.
