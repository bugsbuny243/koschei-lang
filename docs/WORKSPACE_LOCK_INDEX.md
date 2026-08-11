# Koschei Workspace Lock Index v1

Status: parse-free freshness verification for previously verified workspace locks. This is not a production-scale or Alibaba-scale readiness claim.

Large workspaces cannot afford to rebuild every package module graph and rerun semantic/MIR checks merely to prove that an already-created lock still describes the same source bytes.

Lock Index v1 turns that repeated proof into a direct content-hash verification after one authoritative full verification.

## Lifecycle

For one `workspace_digest`, Koschei stores:

```text
.koschei/cache/workspace-lock-index-v1/<workspace-digest>/manifest.json
```

When no entry exists, Koschei:

1. snapshots the exact `.ks` file set and SHA-256 bytes under every workspace member root;
2. runs the ordinary full package-aware workspace-lock verifier;
3. snapshots the source tree again;
4. refuses publication if source bytes changed during the full verification;
5. publishes an immutable index bound to the verified workspace digest;
6. re-verifies the published index.

A different valid workspace lock has a different `workspace_digest` and therefore a different index directory. Old indexes are not rewritten into new identities.

## Fast verification

On a hit, Koschei does **not** reconstruct every module graph merely to establish lock freshness. It verifies:

- the workspace manifest SHA-256;
- current deterministic dependency build order;
- exact workspace package set;
- each member path, version, entry, dependencies, and `koschei.toml` SHA-256;
- the exact `.ks` file set under all workspace member roots;
- SHA-256 of every indexed `.ks` file;
- index schema, workspace identity, canonical source ordering, source count, and index digest.

No mtime, inode timestamp, file size, or directory timestamp is authoritative. A file is considered unchanged only when its current SHA-256 equals the indexed SHA-256.

The source inventory is deliberately conservative. Adding an otherwise unused `.ks` file changes the exact source set and invalidates the current index. This may cause extra work but cannot cause stale source to be accepted.

## Why unchanged bytes are sufficient for the fast path

The workspace manifest and project manifests are independently re-hashed. Workspace package resolution is declared by those manifests. The index then proves that every Koschei source byte available under the member roots is unchanged from the source tree surrounding the successful full lock verification.

Therefore the previously verified import/module-lock result cannot have changed without at least one of these identities changing:

- workspace manifest;
- member manifest;
- exact source file set;
- source content hash.

If any changes, the current digest-scoped index cannot authorize the fast path.

## Fail-closed rules

The current index fails closed when:

- the entry or manifest is missing, malformed, or symlinked;
- any cache-path component is a symlink;
- unknown or duplicate JSON fields appear;
- index digest or workspace identity is wrong;
- a member manifest identity changes;
- a source disappears or is added;
- any source SHA-256 changes;
- a symlinked directory or non-regular `.ks` source appears in a member tree;
- the source inventory exceeds the explicit 2,000,000-file budget;
- the index JSON exceeds the 256 MiB parsing budget.

A corrupt entry for the current workspace digest is not silently repaired or treated as a cache miss. Delete the corrupt cache entry and perform a fresh full verification to create a new trusted optimization record.

## Pipeline after warm-up

For an unchanged workspace/package/toolchain, the native-build path becomes conceptually:

```text
parse workspace/project TOML
  -> hash manifests + exact workspace .ks inventory
  -> workspace-lock index hit
  -> analysis-cache hit for selected package
  -> native-cache hit
  -> create-only artifact + build sidecar
```

This removes the previous all-workspace parser/semantic/MIR repetition from lock freshness checks.

## Remaining scale work

The lock index still performs SHA-256 reads of every `.ks` source in the workspace on each freshness verification. That is intentionally stronger than trusting filesystem metadata, but on extremely large repositories it becomes an I/O cost.

Future acceleration may use hierarchical content trees, filesystem/watch hints, or remote CAS metadata only as **non-authoritative hints**. Before execution/build, security-relevant identities must still reduce to cryptographically verified content, not timestamps.
