# Strange Durable Continuity V1

Status: **implemented local SQLite state prototype, NOT Trust Plane / production root**

The Koschei Library/Universe representation contract needs *one active epoch*
to survive a service restart and reject stale competing publishers. This module
stores a non-secret Continuity identity, epoch and 120-second window start in a
local SQLite database using WAL, synchronous=FULL, and BEGIN IMMEDIATE.

## Contract

- Initialization is single-use per Continuity identity.
- Advancing uses compare-and-swap against the exact stored epoch.
- Epochs strictly increase. Missed 120-second windows may be skipped after
  restart; the new start must correspond exactly to the epoch gap.
- No transition is issued for a future/expired window according to the
  **externally trusted** `observed_seconds` supplied by the caller.
- Two SQLite connections against the same database path cannot both commit
  the same expected-epoch transition.
- `require_active_window` also compares the caller's claimed epoch **and start** against the canonical SQLite snapshot, preventing a caller from substituting a new start within the same epoch. It is a snapshot check, **not an atomic side-effect gate**.
- A typed `ContinuityEpochAuthorityV1` reader can retrieve the stored epoch;
  existing Strange build/attestation gates can reject old epochs.
- No secret data or executable code is stored in the journal.

## Critical non-claims

- SQLite is **not hardware attestation, monotonic trusted time, independent key
  custody, multi-node consensus or a tamperproof storage root**. A privileged
  host that rolls back the database can roll back this local journal.
- The timestamp is a supplied value: this code cannot prove it came from an
  authentic clock.
- Access control to advance epochs is enforced by deployment/file permissions,
  **not** by this Python API. Production needs a non-exportable authorized
  publisher and a separate trusted continuity/attestation root.
- No running binary is retired or replaced by this module. Cutover, signer
  enforcement, process attestation and atomic release remain incomplete.
- Even an authentic, current representation is NOT signing authority.

## Tests

`python -m unittest discover -s tests -p 'test_strange_durable_continuity_v1.py' -v`

Verifies crash/restart persistence, duplicate initialization denial, strict
epoch schedule, catch-up across skipped windows, rejected stale concurrent
writers, invalid inputs and compatibility with Strange's 120s build window.

Related: Issue #317, PR #318 (epoch-bound source), PR #319 (native evidence).
