# Bounded Exact-Object Persistence v1

## Status

Experimental bootstrap runtime contract. This is not a database API, not a transaction manager, and not a claim of production persistence readiness.

The current public spelling is compatibility vocabulary:

```text
let state = caps.persist.allow("/absolute/state/object", 65536, 2000)
let committed = state.commit(payload) or return
let current = state.load() or return
```

The spelling does not define final Koschei-native grammar.

## Why `DiskCaps.write(path, value)` is not the persistence boundary

General disk authority is too broad for a component that should own one state object. A `DiskCaps` holder can choose paths repeatedly and belongs to a larger read/write/list/delete authority family. Existing generic disk read/write also remains `reserved` because cross-backend byte/deadline budgets are incomplete.

Persistence v1 therefore introduces a narrower authority:

```text
PersistRoot.allow(exact_file, max_bytes, deadline_ms) -> PersistCaps
```

The exact file path is selected only during narrowing. `PersistCaps.load()` and `PersistCaps.commit()` accept no path argument. A component that receives a `PersistCaps` token cannot use that token to select a sibling file or turn it into `DiskCaps`.

## Authority policy

V1 requires all policy fields to be compile-time literals:

- one absolute exact-file path;
- `max_bytes` from 1 through 16 MiB;
- `deadline_ms` from 1 through 120000 ms.

Relative paths, dynamic paths, dynamic budgets and the filesystem root are rejected.

The capability manifest records the exact canonical path and both budgets under the `persist` domain.

## Descriptor anchor

The interpreter token opens the target's parent directory at token construction. It starts from `/` and opens every directory component with descriptor-relative `O_DIRECTORY | O_NOFOLLOW` operations.

The token retains that directory descriptor and the final basename separately. Later `load` and `commit` operations duplicate the already-open parent descriptor. They do not re-resolve the original parent path.

Consequences:

- a symlink in any parent component is not followed;
- replacing the textual parent path after token creation does not retarget the token;
- a final target symlink is rejected;
- when the final target exists, it must be a regular file.

The security identity is the anchored parent object plus exact basename, not a fresh path lookup on every call.

## Load contract

`load()`:

1. duplicates the anchored parent descriptor;
2. rejects symlink/non-regular target shape;
3. opens the exact basename with `O_NOFOLLOW`;
4. verifies the opened descriptor is a regular file;
5. rejects an already-known size above `max_bytes`;
6. reads in bounded chunks and permits at most `max_bytes + 1` bytes to distinguish exact-limit EOF from overflow;
7. rejects payloads above `max_bytes`;
8. requires strict UTF-8.

The complete file is currently returned as `String`; streaming persistence is not part of v1.

## Commit protocol

`commit(String)` first UTF-8 encodes the payload and rejects it before filesystem mutation if it exceeds `max_bytes`.

For an admitted payload, the protocol is:

1. duplicate anchored parent descriptor;
2. verify the current target, if present, is a non-symlink regular file;
3. create an unpredictable same-directory temp object with `O_CREAT | O_EXCL | O_NOFOLLOW`, mode `0600`;
4. write the entire payload with an explicit partial-write loop;
5. `fsync(temp)`;
6. close the temp descriptor;
7. atomically replace the exact canonical basename from the same anchored directory;
8. `fsync(parent directory)`.

The canonical state file is never opened with truncate-in-place semantics by this primitive.

## Commit point and error meaning

The atomic replacement is the **visibility commit point**.

### Before replacement

Failures during temp creation, writing or temp `fsync` are ordinary failed commits:

- the prior canonical state remains authoritative;
- the temp object is cleaned up best effort;
- the operation returns an I/O/deadline/budget error.

### After replacement

After atomic replacement, the new state may already be visible. If parent-directory `fsync` cannot be completed or confirmed, the runtime returns:

`KS3423 — persistence commit state is uncertain`

This is intentionally different from rollback failure. The caller must not blindly retry a non-idempotent higher-level operation merely because it received KS3423. It should load/reconcile the exact state object or apply an application-level idempotency/version protocol.

## Error classes

- `KS2420` — exact persistence policy could not be statically sealed;
- `KS2421` — path/budget policy is outside the v1 security envelope;
- `KS3420` — target/UTF-8/object contract violation;
- `KS3421` — byte budget exceeded;
- `KS3422` — cooperative persistence sequence deadline expired;
- `KS3423` — atomic replacement occurred but durability confirmation is uncertain;
- `KS3424` — descriptor/filesystem/fsync/replace operation failed closed.

## Deadline truth

The interpreter computes one monotonic deadline per `load` or `commit` sequence and checks it before and after filesystem operations.

This is **not** a guarantee that Python can preempt a kernel filesystem syscall that blocks indefinitely. No unsafe thread termination is introduced to pretend otherwise.

Therefore the stdlib persistence catalog declares `bytes` as enforced but does not declare `deadline` enforced, and all persistence operations remain `reserved`.

A future fully supported deadline contract needs an OS/backend strategy that can enforce the same semantics without weakening another backend.

## Concurrent writer truth

Atomic replacement prevents a torn canonical file. It does **not** provide:

- compare-and-swap;
- optimistic version checking;
- serializable transactions;
- lost-update prevention;
- multi-object atomicity.

Two separately authorized writers may race and the last successfully installed complete object can win. Applications requiring stronger semantics need a later versioned/CAS or transactional capability contract.

## Native backend truth

Native persistence parity is not implemented in this slice. Programs that use `PersistRoot` or `PersistCaps` must fail native generation with `KS4001` rather than silently falling back to general disk writes or a weaker durability protocol.

The native workspace build path is also covered because sealed MIR generation ultimately flattens the checked graph into `GoCodegen`, preserving persistence parameter types and `caps.persist` member access before backend validation.

Until native implementation and real cross-backend tests execute, the stdlib `persist` family remains `partial` and its operations remain `reserved`.

## Production-reference role

`production_reference_v1` contains a separate `state_store` realm. It accepts an already-narrowed `PersistCaps`; it does not choose a path itself.

The `http_ingress` composition realm owns both Serve and Persist authority, calls the authority-free order-processing core, passes the exact state token into `state_store`, then reloads the committed state for verification.

This models authority flow rather than ambient filesystem access.

## Non-claims

Bounded Persistence v1 does not claim:

- database semantics;
- crash-proof durability on every filesystem/hardware configuration;
- power-loss guarantees beyond the stated `fsync` protocol;
- syscall-preemptive deadlines;
- cross-platform native parity;
- concurrent transaction isolation;
- CAS/versioned writes;
- multi-file transactions;
- encrypted state at rest;
- secret-data redaction;
- production readiness.

Those require separate contracts and separate evidence.
