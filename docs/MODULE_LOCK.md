# Koschei Module Lock v1

`ks lock` records the exact source identity and import topology of a local Koschei module graph.

## Create a lockfile

```bash
ks lock create src/main.ks --output koschei.lock.json
```

The command parses and checks the complete reachable module graph before writing the lockfile. Every locked module contains:

- a project-relative `.ks` path;
- the SHA-256 digest of the exact file bytes;
- the import name to target-path mapping.

The lockfile also contains a deterministic digest covering the entrypoint and complete module graph.

An existing lockfile is not replaced silently. Regeneration requires the explicit `--force` flag.

## Verify a build input

```bash
ks lock verify src/main.ks --lock koschei.lock.json
```

Verification fails closed when:

- a module was added or removed;
- any source byte changed;
- an import target changed;
- a path escapes the project root;
- an unlocked module appears in the graph;
- the lockfile contains unknown fields;
- a module or lock digest is malformed or altered.

## Locked native build

A lockfile can be enforced as part of native compilation:

```bash
ks build src/main.ks \
  --locked \
  --lockfile koschei.lock.json \
  --output build/app
```

When `--locked` is present, Koschei verifies the complete source and import graph before generating Go or invoking the Go compiler. A mismatch therefore stops the build before a native artifact can be produced.

When `--lockfile` is omitted, the compiler expects `koschei.lock.json` beside the resolved entry source. Supplying `--lockfile` without `--locked` is rejected so a caller cannot accidentally provide a lock that is never enforced.

## Scope

Module Lock v1 secures the current local-file module system. It does not yet resolve remote packages or create a package registry. Future package resolution must preserve the same rules: immutable content identity, explicit dependency topology, project-root containment and reproducible verification before compilation.
