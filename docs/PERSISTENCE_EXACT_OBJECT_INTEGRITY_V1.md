# Persistence Exact-Object Integrity v1

## Canonical policy spelling

Persistence authority is exact enough that the source literal itself must already name the canonical lexical path. V1 rejects rather than rewrites:

- leading/trailing whitespace;
- duplicate path separators;
- `.` / `..` lexical aliases;
- relative paths;
- the filesystem root.

This keeps source review, capability-manifest evidence and runtime identity aligned. A reviewer should not have to mentally apply `strip()` or `normpath()` to discover which object was actually authorized.

## Hard-link aliases

An existing persistence target must be a regular file with exactly one hard-link name. `load` and `commit` reject `st_nlink != 1` with KS3420.

Atomic replace already avoids mutating the prior inode in place, but rejecting hard-link aliases also prevents an exact-object token from quietly becoming a read capability for an inode intentionally exposed under another pathname.

## FIFO / special-file race

The interpreter performs a final regular-file shape check before data open, but a filesystem object can change between those operations. The real load descriptor therefore opens with `O_NONBLOCK | O_NOFOLLOW` and repeats `fstat` before reading.

If a previously regular target is swapped to a FIFO in the narrow race window, open does not wait indefinitely for a peer and the post-open regular-file check rejects the descriptor.

Platforms that cannot provide the required descriptor-relative, no-follow and nonblocking primitives do not receive a weaker persistence fallback.

## Scope

These rules strengthen exact-object identity. They do not provide transaction isolation, same-UID process isolation, CAS, or at-rest encryption.
