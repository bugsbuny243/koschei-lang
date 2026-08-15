# Koschei Native Reality Project v1

Status: **experimental migration slice; not the default project format**

## Goal

The legacy project model still treats a human-readable manifest and entry path as
program identity (`koschei.toml`, `[package]`, `src/main.ks`). Native Reality v1
introduces a different authority model instead of renaming those conventions.

A Native Reality project has no plaintext package manifest, no semantic entry
filename, and no `src/` tree. Its authoritative surface is:

```text
.koschei/
  reality
  matter/
    <128-bit epoch alias>
```

The alias carries no component role. The canonical root is identified inside an
authenticated binary reality envelope by a random project id and root object id.

## Authenticated reality envelope

`.koschei/reality` is a fixed-size binary envelope. v1 binds:

- schema version;
- 128-bit project identity;
- 128-bit canonical root object identity;
- local policy digest;
- SHA-256 of the exact canonical source bytes;
- monotonic epoch;
- 128-bit physical epoch alias.

The envelope is authenticated with HMAC-SHA256 using an external 256-bit Reality
Seal Key. The seal key is deliberately **not stored in the project tree**.
Possession of project files alone is therefore insufficient to forge a new
canonical reality.

A plain checksum is not accepted as authority: an attacker with filesystem write
access could otherwise edit both metadata and checksum.

## Trusted temporal context

Loading a reality requires three independent inputs:

1. the external Reality Seal Key;
2. the expected project id; and
3. the expected epoch.

The project id blocks cross-project substitution even if an operator mistakenly
reuses a seal key. The expected epoch blocks replay of an older valid sealed
reality when the trusted session/broker has already advanced.

The trusted epoch cannot be learned solely from the untrusted project tree; doing
so would make rollback detection circular. A later session broker/Trust Plane must
hold the current project-id/epoch context outside the source tree.

## Authenticated source advance

A direct write to the active file in `.koschei/matter/` is **not an edit**. It
invalidates the artifact digest and the next trusted load fails closed.

`advance_native_reality_source()` is the v1 write boundary. A successful source
change is one temporal transition:

1. authenticate the existing reality against the external seal key, expected
   project id and expected epoch;
2. validate the replacement UTF-8/source-size limits and parse it before any
   filesystem mutation;
3. reject imports before mutation because v1 has no authenticated object-edge
   table;
4. hash the replacement bytes;
5. write and fsync the replacement under a fresh 128-bit opaque alias;
6. construct epoch `N+1` with the same project id and root object id but the new
   artifact digest and alias;
7. HMAC-seal the new reality and atomically switch authority to it; and
8. remove the old now-unreferenced alias on a best-effort basis.

A parse failure, import-policy failure, wrong project id, wrong epoch or wrong
seal key therefore occurs before the authority switch. Tests assert that rejected
edits leave the old reality bytes and source alias authoritative.

The edit preserves **object identity**, not physical identity. This is deliberate:
the same canonical program object evolves through authenticated epochs instead of
being defined by one permanent human-readable file path.

## Epoch rotation

Rotation keeps canonical identity and source digest stable while changing the
physical locator:

```text
epoch 1  root object -> 6a...f2
epoch 2  root object -> 91...0c
epoch 3  root object -> b4...77
```

The implementation uses copy-switch-cleanup ordering:

1. write and fsync the new opaque source alias;
2. write and fsync a newly authenticated reality envelope;
3. atomically replace the old envelope;
4. remove the now-unreferenced old alias.

A crash before the envelope switch leaves the previous reality valid. A crash
after the switch may leave an unreferenced stale copy, but never makes that stale
copy authoritative again.

## Read hardening

Reality and source files are read fail-closed:

- a project-root final-component symlink is rejected rather than normalized away;
- reality/matter directory symlinks are rejected;
- source and reality final-component symlinks are rejected;
- non-regular files are rejected;
- `O_NOFOLLOW` is used where the platform provides it;
- `lstat`/`fstat` identity is compared to detect replacement races;
- source size is bounded to 4 MiB;
- the reality envelope has an exact byte length;
- source bytes must be valid UTF-8;
- source SHA-256 must match the authenticated envelope.

The parser receives the already verified source bytes. It does not reopen the
source path between verification and parse.

## Why v1 rejects imports

Native Reality v1 has one authenticated root object. It intentionally rejects any
`import` declaration with `KS5701` because there is not yet an authenticated
multi-object edge table in this format.

Creation and authenticated source advance both reject importing source before
creating/switching project authority. The graph loader retains the same defensive
check for malformed or older inputs.

Falling back to `name.ks` beside the opaque object would immediately restore the
very filename/path authority this design removes. Multi-object support must first
bind object ids, artifact hashes, requested authority and edges inside an
authenticated structure.

## Originality contract

The static layout `.koschei`, `.koschei/reality`, and `.koschei/matter` is tested
through the Koschei Originality Contract with explicit provenance bound to:

- protected-source reality; and
- temporal-source identity.

The physical object alias is random 128-bit lowercase hex and is not a semantic
scaffold path.

This does **not** claim that the current source grammar inside the object is
already Koschei-native. The default example still contains legacy grammar while
the grammar migration is underway. Project identity and grammar originality are
separate migration gates.

## Security boundaries and non-claims

Native Reality v1 is not a claim of an unbreakable system. In particular it does
not by itself protect against:

- a process that already possesses the Reality Seal Key;
- arbitrary inspection of plaintext source after an authorized read;
- a compromised compiler or kernel inside the trusted computing base;
- stale-source remnants that an operating system fails to delete physically;
- symlinks or mount substitutions in untrusted ancestor directories outside the
  admitted project-root final component;
- disclosure through runtime behavior or generated binaries.

Source objects in v1 are still plaintext at rest. HMAC authenticates authority;
it does not encrypt bytes. At-rest confidentiality requires a separate design
with key custody that does not reintroduce ambient read authority.

The purpose of v1 is narrower and testable: remove semantic file paths and
plaintext package manifests from project authority, authenticate the canonical
root, bind it to a trusted temporal context, and make filename fallback fail
closed.

## Next required slice

Before this can replace the legacy default project model:

1. add an authenticated multi-object edge table without semantic path fallback;
2. integrate the Trust Plane/session broker for seal-key and monotonic epoch
   custody;
3. wire `check`, `run`, `mir`, capability analysis and build to the native reality
   loader;
4. design at-rest source confidentiality without storing the decryption key beside
   the source objects;
5. migrate the grammar itself away from legacy mainstream-shaped syntax; and
6. retire the old scaffold through the originality ratchet only after full test
   parity is proven.
