# Koschei Workspace Analysis Cache v1

Status: compiler-analysis acceleration for locked workspace native builds. This is not a production-scale or Alibaba-scale readiness claim.

The native cache avoids repeated Go compilation. Analysis Cache v1 removes the next repeated step for an unchanged selected package: Koschei semantic checking, sealed MIR construction, and Go backend generation.

## What is cached

A successful native workspace build may create:

```text
.koschei/cache/workspace-analysis-v1/<analysis-key>/
├── main.go
└── manifest.json
```

The cache deliberately stores **plain deterministic backend source and metadata only**. It does not store or deserialize Python `pickle`, Python bytecode, executable callbacks, AST objects, typed-HIR objects, or MIR Python objects.

A cache miss performs the ordinary package graph load, integrity checks, typed-HIR checks, legacy semantic compatibility check, sealed MIR lowering, MIR integrity verification, and Go generation. Only after those gates pass is the resulting `main.go` eligible for publication into the immutable analysis cache.

## Analysis identity

The canonical `koschei.workspace-analysis-cache-key.v1` identity binds:

- selected package name;
- selected package `koschei.toml` SHA-256 from the verified workspace lock;
- selected package module-lock digest, including imported source closure and import topology;
- a conservative Koschei compiler implementation digest.

The compiler implementation digest hashes every installed `koschei/**/*.py` source file, including its path, and also binds the Python implementation and exact Python major/minor/micro version. This is intentionally conservative: an unrelated compiler-source edit may cause a miss, but changed compiler code cannot silently consume analysis produced by an older implementation.

## Hit verification

Before an analysis cache hit is accepted:

1. the current workspace lock is proven fresh, using the digest-scoped workspace lock index when available or the authoritative full verifier on an index miss;
2. the selected package must still exist in that verified lock;
3. its package-manifest digest and module-lock digest must match the analysis identity;
4. the current compiler implementation digest must match;
5. the cache entry must be a real directory, not a symlink;
6. `manifest.json` and `main.go` must be real files and no extra files may exist;
7. duplicate/unknown JSON fields are rejected;
8. the directory name, manifest key, and recomputed key must agree;
9. `main.go` is re-hashed and must match the recorded SHA-256;
10. MIR version and MIR fingerprint metadata must be structurally valid.

A corrupt, incomplete, stale, forged, or tampered analysis entry fails closed. Koschei does not silently repair or trust it.

## Warm build pipeline

After the workspace lock has already passed one full package-aware verification and its source index exists, a repeated native package build is conceptually:

```text
workspace/project TOML load
  -> workspace lock-index freshness proof
     -> manifest SHA-256 + exact .ks file set + source SHA-256
  -> analysis identity
     -> analysis miss: semantic + MIR + codegen -> immutable main.go cache
     -> analysis hit: verified cached main.go
  -> native cache identity
     -> native miss: Go build
     -> native hit: verified cached binary
  -> create-only user artifact + workspace-build sidecar
```

On a new workspace digest, the lock-index layer intentionally falls back to the full package graph/semantic/module-lock verifier before it may publish a new freshness index.

`ks-workspace run` intentionally does **not** use Analysis Cache v1. The interpreter requires the real sealed in-memory MIR graph. v1 does not reconstruct Python MIR objects from cache data because doing so would create a much larger deserialization/security surface. `run` still benefits from the workspace lock-index fast freshness proof before it performs the selected program's real analysis.

## Deliberate boundary

With Workspace Lock Index v1, repeated lock freshness no longer requires reparsing and semantically checking every workspace package. The index still hashes the complete current `.ks` inventory on each proof; this is a deliberate cryptographic content check rather than an mtime/size shortcut.

The next scale gates are therefore higher-level: hierarchical content-addressed source trees/CAS for very large workspaces, structured concurrency/backpressure, bounded network-service runtime primitives, durable transactional storage/recovery, and production observability. Any future filesystem/watch acceleration must remain a hint; timestamps cannot become security authority.
