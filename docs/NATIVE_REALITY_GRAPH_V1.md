# Koschei Native Reality Graph v1

Status: **experimental stacked foundation; not the default project model**

This layer extends Native Reality v1 from one canonical source object to a
multi-object program without restoring semantic filenames or sibling-path imports.

## Persistent shape

The project still exposes only the Native Reality container:

```text
.koschei/
  reality
  matter/
    <opaque 128-bit alias>
    <opaque 128-bit alias>
    <opaque keyed graph-capsule alias>
```

Logical labels such as `app`, `wallet`, `policy`, `settlement`, or `util` are not
persisted as filenames or graph fields. They may exist inside an authorized source
view and in process memory while a source file is parsed.

## Object identity

Every source object has:

- a random 128-bit canonical object id;
- SHA-256 of the exact source bytes; and
- a random 128-bit physical epoch alias.

Compiler `ModuleGraph` keys use `koschei-object:<object-id>`. Filesystem paths are
only diagnostic/source locators. Typed/effect analysis and MIR lowering are keyed
by the authenticated graph identity rather than reconstructing identity from the
physical path.

MIR additionally verifies that each `MirModule.key` equals the key under which it
is stored. Rotating physical aliases therefore does not silently change module
identity or the MIR fingerprint.

## Graph capsule

The authenticated binary capsule binds:

- schema version;
- project id;
- epoch;
- root object id and root artifact digest;
- canonical sorted object records; and
- canonical sorted dependency-edge records.

The capsule is HMAC-SHA256 authenticated with a domain-separated key derived from
the external Reality Seal Key and project id. Object/edge counts and total byte
size are bounded. Duplicate ids, duplicate aliases, duplicate edge slots, unknown
object references, noncanonical record ordering and target-digest mismatches fail
closed.

The graph capsule itself is stored under a keyed 128-bit alias derived from the
external seal key, project id and epoch. Its next physical name cannot be computed
from project files alone.

## Keyed import slots

Source still uses the current legacy `import name` grammar during the grammar
migration. The persistent graph does **not** store `name`.

For each importing object the loader derives a 256-bit keyed slot tag from:

- project id;
- importing object id; and
- the import name visible in the authorized source bytes.

The graph stores only that slot tag, target object id and expected target digest.
Resolution succeeds only when the source-derived keyed slot exactly matches an
authenticated edge.

A validly HMAC-sealed capsule containing an extra edge that no source import uses
is rejected. Source imports and authenticated edge slots must correspond exactly;
there is no hidden dormant dependency surface.

## Topology admission

Creation parses every supplied source before creating project state. It rejects:

- missing import targets (`KS1601`);
- duplicate imports (`KS1603`);
- dependency cycles (`KS5718`); and
- authenticated but unreachable/orphan source objects (`KS5718`).

Loading repeats structural checks after source-byte verification. There is never a
fallback to `name.ks`, a sibling directory, or another semantic path.

## Compiler identity correction

The legacy compiler historically used `str(module.path)` as an internal key for
some typed/effect reports. That happened to work because ordinary `ModuleGraph`
keys were paths. It is unsafe for an object-identity graph: imported effect lookup
could miss a dependency if graph identity and locator identity diverged.

Graph v1 changes the compiler contract:

- `ModuleGraph` key is semantic analysis identity;
- `Module.path` is a diagnostic/source locator only;
- typed/effect reports are keyed by the real graph key; and
- MIR modules are lowered and sealed with that same graph key.

Legacy path projects keep their existing behavior because their graph keys remain
path strings.

## Whole-graph epoch rotation

`rotate_native_reality_graph_epoch()` advances the complete physical reality as
one authenticated transition.

Under the exclusive reality transition lock it:

1. re-authenticates the current reality against external key, project id and
   expected epoch;
2. authenticates and parses the current graph capsule and every source object;
3. rejects hidden edges/cycles/malformed source before creating the next epoch;
4. writes every source object under a new random alias;
5. writes a new graph capsule under the next epoch's keyed capsule alias;
6. fsyncs new matter;
7. HMAC-seals a new reality envelope whose root alias points into the new epoch;
8. atomically switches the reality envelope as the commit point; and
9. removes old aliases/capsule on a best-effort basis.

Canonical project id, source object ids, source digests and dependency semantics
remain stable when this is a pure rotation. Physical source aliases and graph
capsule alias change together.

If the commit switch fails, newly written aliases and capsule are removed and the
old reality remains authoritative. A caller that retries with an old expected
epoch after a successful switch is rejected as stale.

## Security boundaries and non-claims

Graph v1 improves authority integrity and removes semantic names from persistent
graph metadata, but it is **not source encryption**.

In this revision:

- source objects are still plaintext at rest;
- the capsule is authenticated but not encrypted;
- an observer who identifies and parses the capsule can infer object/edge counts
  and graph connectivity even though logical import names are absent;
- canonical object ids remain stable across pure epoch rotation and therefore can
  be correlated if an attacker obtains multiple decoded capsules;
- a process already holding the Reality Seal Key remains inside the trusted
  boundary; and
- a compromised kernel/compiler can defeat assumptions below the project layer.

At-rest source/topology confidentiality needs a separate encryption and key-custody
layer. We do not label HMAC, opaque filenames, or rotation as confidentiality they
do not provide.

## Acceptance gates

- No logical source label is a physical source filename.
- Graph capsule bytes do not contain the test logical labels.
- Wrong-key, capsule-tamper, source-tamper and cross-project substitution fail.
- Missing target, cycle and orphan graphs fail before project creation.
- A correctly sealed but unused hidden edge fails on load.
- Full compiler check and MIR lowering work with non-path object graph keys.
- MIR module identity equals authenticated graph identity.
- Changing only diagnostic/physical paths does not change MIR fingerprint.
- Whole-graph epoch rotation changes every physical source alias and the capsule
  alias while preserving canonical object identities/digests.
- A failed reality switch leaves the previous epoch authoritative.

## Next required slice

1. authenticated source editing for a selected object while rebuilding dependent
   target-digest bindings;
2. Trust Plane/session custody for seal keys and monotonic epoch state;
3. wire public `ks check/run/mir/caps/build` flows to trusted Native Reality
   context rather than exposing raw key arguments;
4. at-rest source and topology encryption; and
5. grammar migration so logical imports themselves no longer depend on the legacy
   mainstream-shaped language surface.
