# Persistence Parent Integrity v1

Exact-object persistence uses a same-directory temporary object followed by an atomic rename. That protocol has a directory-entry integrity precondition: another Unix identity must not have unrestricted rename/unlink authority in the anchored parent while commit is in progress.

## Runtime rule

Every `PersistCaps.load` and `PersistCaps.commit` duplicates the retained parent directory descriptor and checks the current directory mode with `fstat`.

The operation fails closed with KS3420 when the parent is group- or world-writable **and does not have the sticky bit**.

A sticky shared directory remains admissible. Unix sticky semantics prevent another identity from freely removing or replacing entries it does not own, which is the relevant name-integrity property for the random temp + rename protocol.

The check is repeated on every operation, so widening parent permissions after token creation is detected before persistence I/O mutates canonical state.

## Threat boundary

This rule protects against ordinary cross-identity directory-entry races represented by POSIX mode/sticky semantics. It does not claim isolation from a malicious process running as the **same Unix identity**, because that process can generally exercise the same ownership privileges. It also does not turn v1 into a transaction/CAS system when multiple explicitly authorized Koschei writers target the same object.

If a deployment requires stronger same-UID/process isolation, the persistence object must live behind a stronger OS boundary or a future brokered persistence authority.

## Why not ban `/tmp` outright

World-writable is not equivalent to uncontrolled rename authority when the sticky bit is correctly set. Rejecting every shared directory would incorrectly exclude standard sticky temporary-directory semantics without improving the actual invariant. The runtime therefore tests the property that matters rather than matching a path name.
