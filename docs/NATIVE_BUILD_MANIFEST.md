# Koschei Native Build Manifest v1

A locked native build can emit a machine-readable artifact identity:

```bash
ks build src/main.ks \
  --locked \
  --lockfile koschei.lock.json \
  --output build/app \
  --build-manifest build/app.build.json
```

The compiler verifies the complete module lock before generating Go or invoking the native toolchain. After a successful build, the manifest binds:

- module-lock digest;
- sealed MIR version and fingerprint;
- Koschei compiler version;
- backend identity and exact Go toolchain string;
- native artifact name and byte size;
- native artifact SHA-256;
- digest of the complete manifest payload.

`--build-manifest` requires `--locked`. An existing manifest is never overwritten silently, and a lock mismatch produces neither a native artifact nor a manifest.

## Verify an existing artifact

```bash
ks build-verify src/main.ks \
  --artifact build/app \
  --manifest build/app.build.json \
  --lockfile koschei.lock.json
```

Verification independently checks:

- the manifest schema contains no unknown fields;
- the manifest digest matches its contents;
- the artifact name, size and SHA-256 match the manifest;
- the current source and import graph still match the original module lock;
- the module-lock digest matches the build manifest;
- the current sealed MIR version and fingerprint match the build manifest.

The command fails closed when the binary, manifest, source graph, lockfile, or MIR identity changed. It does not modify the artifact or regenerate any input.

The manifest is an artifact identity and reproducibility input. It does not claim that binaries built with different toolchain versions must be byte-identical; instead it records the toolchain and all security-relevant source identities needed to compare builds honestly.
