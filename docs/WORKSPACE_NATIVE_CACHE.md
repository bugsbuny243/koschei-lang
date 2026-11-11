# Koschei Workspace Native Cache v1

Status: incremental native-build foundation for large Koschei workspaces. This is not a production-scale or Alibaba-scale readiness claim.

`ks-workspace build` uses an immutable content-addressed native cache under:

```text
.koschei/cache/workspace-native-v1/<cache-key>/
```

The cache removes repeated Go compilation when the selected package build identity is unchanged. It is an optimization only; every build still verifies the complete current workspace lock and reruns compiler/capability checks before a hit may be used.

## Cache identity

The canonical `koschei.workspace-native-cache-key.v1` payload binds:

- selected package name;
- selected member module-lock digest, including the imported workspace-package source closure actually present in that graph;
- sealed MIR version;
- sealed MIR fingerprint;
- SHA-256 of the generated Go source;
- local Go toolchain version;
- `GOOS`;
- `GOARCH`;
- `GOEXPERIMENT`;
- `CGO_ENABLED=0`.

The cache key is SHA-256 over canonical JSON for that payload.

The **complete workspace digest is intentionally not part of the native cache key**. It is still verified before every build and still bound into the final user-visible build manifest. Excluding it from the cache key means an unrelated package may change without forcing a native rebuild of a selected package whose source/dependency closure, MIR and generated code are unchanged.

A source change in the selected package or one of its imported package dependencies changes the selected module-lock/MIR/code identity and therefore gets a different key. A MIR or code-generation change changes the MIR or generated-Go identity. A target/toolchain change changes the toolchain identity. Those cases cannot reuse an older cache entry.

The test suite proves both sides of this invalidation rule: dependency-closure changes produce a new key, while a valid locked change to an unrelated workspace package preserves the selected package cache key and produces a hit.

## Hermetic native-build settings

Cache misses build with:

```text
CGO_ENABLED=0
GOFLAGS=""
GOENV=off
GOTOOLCHAIN=local
go build -trimpath -buildvcs=false -ldflags=-buildid=
```

`GOTOOLCHAIN=local` prevents the build command from silently downloading a different Go toolchain. The generated program has no external Go module dependency.

The test suite builds the same locked package into two independent empty cache roots and requires byte-identical native artifacts for the same local toolchain identity.

## Immutable cache entry

A successful entry contains exactly:

```text
artifact
manifest.json
```

The `koschei.workspace-native-cache.v1` manifest binds the complete package-local cache identity, cache key and artifact SHA-256.

On a cache hit Koschei verifies:

- entry is a real directory, not a symlink;
- artifact and manifest are real files, not symlinks;
- there are no unexpected files;
- JSON has no duplicate members or unknown fields;
- manifest identity equals the currently computed build identity;
- manifest key equals the directory name and recomputed cache key;
- artifact SHA-256 matches the manifest.

A corrupt, incomplete, forged or tampered entry fails closed. Koschei does not silently treat corrupt cache state as trusted output.

## Publication

A verified cached artifact is copied to the requested build destination using create-only semantics. Existing build outputs are not silently replaced.

The normal `koschei.workspace-build.v1` sidecar is still emitted and verified after publication. That final sidecar binds the **current complete workspace digest**, current workspace-manifest SHA-256, selected package module-lock digest and MIR fingerprint whether the native artifact was a cache hit or miss.

This split is deliberate: the cache asks "can these exact package bytes/MIR/code/toolchain reuse the same native artifact?" while the final build manifest answers "under which complete currently verified workspace was this artifact published?"

## Large-codebase effect

This gate avoids repeating the expensive native backend step for an unchanged selected package closure. A change to an unrelated workspace package does not invalidate the selected package's native cache.

It does not yet make workspace checking itself incremental: parsing, semantic/capability checks and MIR construction still run before the cache key is accepted.

The next incremental gate is a compiler analysis cache keyed by source/module-lock/compiler-contract identity, with dependency-aware invalidation. That cache must never allow stale semantic or capability results to survive a source or policy change.
