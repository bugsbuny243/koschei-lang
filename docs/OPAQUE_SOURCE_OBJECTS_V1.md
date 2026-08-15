# Opaque Source Objects v1

Koschei protected projects MUST NOT rely on human-readable physical filenames or directory paths as authoritative program identity.

## Security goal

A filesystem listing must not directly reveal which source object implements authentication, custody, policy, compiler stages, network access, wallet logic, storage, settlement, or other sensitive responsibilities.

This is defense-in-depth, not a claim that filenames alone provide confidentiality. Runtime behavior, memory access, debug data, binaries, and authorized views remain separate attack surfaces.

## Core rule

For protected projects:

- physical source storage uses opaque object identifiers;
- logical developer names exist only in an authorized workspace view;
- physical path is never semantic identity;
- dependency and capability edges are resolved from signed object metadata, not directory layout;
- protected builds reject fallback to semantic filenames or plaintext path-based imports.

Example physical storage:

```text
objects/
  7Q2A9M4K
  P19MX8D4
  44PFR8CZ
  1VNE7F2C
```

These identifiers carry no role information.

## Object identity

Each protected source object has a stable canonical identity independent of its current physical filename:

```text
object_id        = random 128-bit identifier or stronger
artifact_hash    = hash(canonical protected object)
policy_hash      = hash(authoritative local policy binding)
epoch_alias      = opaque physical alias for the current storage epoch
```

`epoch_alias` is not authority. It can rotate without changing `object_id` or `artifact_hash`.

## Authorized logical view

A trusted workspace broker may present a human-readable logical view to an authorized developer. The logical label is not stored as a normal plaintext filename beside the source object.

The mapping between logical labels and opaque object ids is protected separately and is never accepted by the compiler as an authority grant.

## Rotating aliases

Protected storage MAY rotate physical aliases by epoch:

```text
epoch N     object A -> 7Q2A9M4K
epoch N+1   object A -> X8D4P19M
epoch N+2   object A -> R8CZ44PF
```

Rotation MUST preserve canonical object identity and artifact hash.

Alias derivation MUST NOT expose encryption keys and MUST NOT use a human-readable time code as the canonical encryption key.

## Dependency graph

Protected projects use an explicit signed object graph. Edges bind object ids, expected artifact hashes, and requested capabilities. The graph, not the directory tree, determines program structure.

A source object cannot gain authority because it is placed under a privileged directory or given a privileged logical label.

## Decoy compatibility

Opaque storage composes with the compromise-decoy plane:

- decoy objects use the same opaque naming surface;
- decoy provenance is cryptographically distinguishable to trusted build/sign/deploy paths;
- unauthorized reads may resolve to non-authoritative decoy objects;
- the trusted compiler never accepts decoy provenance as canonical source.

## Fail-closed rules

A protected build fails if:

1. a semantic filename/path is required to resolve authority;
2. an object id is missing or malformed;
3. artifact hash does not match;
4. local policy binding does not match;
5. a physical alias is treated as canonical identity;
6. a decoy object reaches the canonical compiler path;
7. an unprotected plaintext fallback is attempted.

## Explicit non-goals

Opaque names do not by themselves stop:

- arbitrary memory inspection by a compromised kernel/hypervisor;
- an authorized user copying visible source;
- behavioral reverse engineering of a running program;
- a malicious compiler already inside the trusted computing base.

The feature reduces structural information leakage and removes predictable filenames/paths as a free architecture map.

## Acceptance gates

- Renaming every physical object alias leaves canonical program identity unchanged.
- A directory listing reveals no semantic component names for protected source.
- Build resolution works from object graph identity, not filenames.
- Changing one object hash fails closed.
- Changing one policy binding fails closed.
- Rotating aliases changes physical names without changing canonical artifact identity.
- Decoy objects cannot be signed or deployed as canonical source.
