# Bounded Persistence — Linux Native Go v1

## Purpose

This slice carries the exact-object persistence contract from the interpreter into the Linux native-Go backend. It does not broaden `PersistCaps`, turn it into `DiskCaps`, or promote the stdlib operation to `supported` beyond the guarantees actually executed.

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

Linux native v1 starts at `/` and opens each canonical parent component through `openat` with `O_DIRECTORY`, `O_NOFOLLOW` and `O_CLOEXEC`. A user-controlled parent symlink is therefore never followed. Later textual replacement of the original directory path does not retarget an already-created token.

## Final-object shape probing

Native v1 probes the final object with Linux `O_PATH | O_NOFOLLOW | O_CLOEXEC`, then uses `fstat` and accepts only a regular file. A missing final object is allowed because the first commit may create it.

The real load open additionally uses `O_NONBLOCK | O_NOFOLLOW`; `fstat` is repeated after open. This closes the race where a target checked as regular is swapped to a FIFO before the data descriptor is opened.

## Load

Native load mirrors the interpreter contract: one monotonic sequence deadline, duplicated anchored parent descriptor, target-shape validation, descriptor-relative exact-basename open, regular-file `fstat`, hard known-size rejection above `max_bytes`, bounded reads, strict UTF-8 and explicit String-or-error behavior.

The deadline remains cooperative around syscalls. Linux native parity does not turn it into a safe syscall-preemption guarantee.

## Commit

Native commit mirrors the interpreter visibility/durability protocol: UTF-8 admission, byte-budget rejection before mutation, anchored parent descriptor, target validation, 128-bit temporary-name randomness from `crypto/rand`, same-directory `openat(O_CREAT|O_EXCL|O_NOFOLLOW)` with mode 0600, full-write loop, `fsync(temp)`, descriptor-relative `Renameat`, and `fsync(parent)`.

Pre-replace failures clean the temporary object best effort and do not mutate canonical state. After `Renameat`, a deadline or parent-fsync failure returns KS3423 because the new state can already be visible while durability confirmation is uncertain.

## Linux-only boundary

This implementation is intentionally Linux-gated. Non-Linux persistence native generation remains KS4001 until an equivalent descriptor and durability contract is designed and executed there.

## Production-reference gate

The fourteen-realm production reference has been executed on Linux through the full path:

real TCP POST -> ServeCaps -> canonical JSON -> authority-free 11-module order worker -> PersistCaps atomic commit -> PersistCaps reload -> deterministic stdout/state file.

The native workspace artifact is required to preserve the same workspace digest, stdout, HTTP response, persisted bytes and mode 0600 as the interpreter path.

## Executed evidence

The current-main reconstruction was validated on Railway using source head `d00ad6b3fa2fbffb5f108d6bd5f23c10461269df` and validation commit `e9f7fe74eb326a24e6ef9d84b9888b62a48a613f`.

Deployment `88244cd0-2538-403c-bcea-cf1411a59344` completed with `SUCCESS` on Go 1.24.13 linux/amd64 and Python 3.13.15. The persistence, native adversarial, production HTTP, production system and direct-MIR suite ran 49 tests with no skips and finished `OK`.

Executed gates include native exact-state commit/load, hard byte rejection without old-state mutation, parent/final symlink rejection, hard-link rejection, missing-parent authority alignment, parent permission integrity, locked native HTTP+persistence parity, source-drift fail-closed behavior, 32-realm direct-MIR/native build gates and the inherited persistence security contract.

## Standard-library truth

Source implementations and executed parity evidence now exist for the interpreter and Linux native-Go backend, but `persist.allow/load/commit` remain `reserved` and backend support flags remain false.

They are not promoted because:

- `deadline_ms` is still a cooperative sequence deadline around syscalls, not safe preemption of a blocked kernel filesystem operation;
- native parity is Linux-only;
- the current contract does not claim database/CAS/transaction semantics.

`bytes` remains the only budget advertised as enforced.

## Non-claims

This slice does not provide database semantics, compare-and-swap, transaction isolation, lost-update prevention, multi-object transactions, at-rest encryption, syscall-preemptive deadlines, non-Linux native parity, universal crash/power-loss guarantees or production readiness.
