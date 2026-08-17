# Bounded Persistence — Linux Native Go v1

## Purpose

This slice carries the exact-object persistence contract from the interpreter into the Linux native-Go backend. It does not broaden `PersistCaps`, turn it into `DiskCaps`, or promote the stdlib operation to `supported` before executed evidence and deadline semantics justify that claim.

## Authority identity

`PersistRoot.allow(exact_file, max_bytes, deadline_ms)` remains a narrowing operation. For a statically valid policy it produces a `PersistCaps` token even when the parent directory cannot currently be anchored. The token records that open failure and `load`/`commit` return it as KS3424.

This matches the interpreter model: temporary filesystem availability does not silently change the type/shape of a narrowing expression from `PersistCaps` into a backend-specific error union.

The native token stores:

- the canonical exact path policy;
- hard byte budget;
- cooperative sequence deadline;
- an anchored parent directory descriptor when available;
- the exact basename;
- an optional deferred parent-anchor error.

A Go finalizer closes the retained parent descriptor when the capability becomes unreachable. Operations duplicate the retained descriptor so an individual load/commit cannot close the token's anchor.

## Parent anchoring

Linux native v1 starts at `/` and opens each canonical parent component through `openat` with:

- `O_DIRECTORY`;
- `O_NOFOLLOW`;
- `O_CLOEXEC`.

A user-controlled parent symlink is therefore never followed. Later textual replacement of the original directory path does not retarget an already-created token.

## Final-object shape probing

A shape check must not block on a FIFO or perform normal data I/O on a device merely to discover what the target is.

Native v1 therefore probes the final object with Linux `O_PATH | O_NOFOLLOW | O_CLOEXEC`, then uses `fstat` and accepts only a regular file. A missing final object is allowed because the first commit may create it.

The real load open additionally uses `O_NONBLOCK | O_NOFOLLOW`; `fstat` is repeated after open. This closes the race where a target checked as regular is swapped to a FIFO before the data descriptor is opened.

## Load

Native load mirrors the interpreter contract:

1. compute one monotonic sequence deadline;
2. duplicate the anchored parent descriptor;
3. validate target shape;
4. descriptor-relative open of the exact basename;
5. `fstat` regular-file check;
6. reject a known size above `max_bytes`;
7. bounded read loop allowing at most `max_bytes + 1` bytes for overflow detection;
8. strict UTF-8 validation;
9. return `String`.

The deadline remains cooperative around syscalls. Native parity does not turn it into a safe syscall-preemption guarantee.

## Commit

Native commit mirrors the interpreter visibility/durability protocol:

1. require UTF-8 String payload;
2. reject payload above `max_bytes` before mutation;
3. duplicate anchored parent descriptor;
4. validate the current final object when present;
5. generate 128 bits of temporary-name randomness with `crypto/rand`;
6. create same-directory temp using `openat`, `O_EXCL`, `O_NOFOLLOW`, mode 0600;
7. explicit full-write loop;
8. `fsync(temp)`;
9. close temp descriptor;
10. descriptor-relative `Renameat(parent, temp, parent, exact_name)`;
11. `fsync(parent)`.

Pre-replace failures clean the temporary object best effort with descriptor-relative `Unlinkat` and do not mutate canonical state.

After `Renameat`, a deadline or parent-fsync failure returns KS3423 because the new state can already be visible while durability confirmation is uncertain.

## Linux-only boundary

This implementation is intentionally Linux-gated before native generation. The runtime uses Linux descriptor primitives, including `O_PATH`, and does not pretend that another target has identical semantics merely because similar function names exist.

Non-Linux persistence native generation remains KS4001 until an equivalent backend contract is designed and tested.

## Production-reference gate

The fourteen-realm production reference now requires, on Linux with Go available:

real TCP POST -> ServeCaps -> canonical JSON -> authority-free 11-module order worker -> PersistCaps atomic commit -> PersistCaps reload -> deterministic stdout/state file.

The native workspace artifact must preserve the same lock digest, stdout, HTTP response, persisted bytes and mode 0600 as the tested interpreter path.

## Standard-library truth

Source implementations now exist for interpreter and Linux native-Go, but `persist.allow/load/commit` remain `reserved` and backend support flags remain false.

Reasons:

- hosted CI has not executed the new parity gates while runner allocation is billing-blocked;
- `deadline_ms` still means a cooperative sequence deadline around syscalls, not safe preemption of a blocked kernel filesystem operation;
- native parity is Linux-only.

`bytes` remains the only budget advertised as enforced.

## Non-claims

This slice does not provide:

- database semantics;
- compare-and-swap;
- transaction isolation;
- lost-update prevention;
- multi-object transactions;
- at-rest encryption;
- syscall-preemptive deadlines;
- non-Linux native parity;
- universal crash/power-loss guarantees;
- production readiness.
