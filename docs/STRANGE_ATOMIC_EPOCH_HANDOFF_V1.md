# Strange Atomic Epoch Handoff v1

**Status: local SQLite metadata preparation and activation prototype. NOT an
automatic process cutover and NOT privileged execution authority.**

This module addresses one missing lifecycle step: the current Continuity
journal can advance an epoch but does not pin which next-epoch native binary
the operator prepared. The opt-in handoff journal records a proposal during the
old epoch and commits the prepared candidate identity and next epoch in one
SQLite write transaction.

## Two-phase flow

**STAGE, during the old 120-second window**

- Bind the continuity identity, old epoch, exact next epoch (+1), old start
  +120 seconds, deployment, Veyra, MIR fingerprint, proposed source digest
  and SHA-256 of the exact supplied candidate bytes.
- MAC these values using a separately protected handoff key. Neither that key
  nor native bytes are stored in the journal.
- Atomically check the current old epoch/window and save one immutable staged
  candidate. Duplicate staging is rejected, including after process restart.
- A staged record has authority=false; it does not mean the candidate has
  valid compiler provenance, runtime attestation or signing rights.

**ACTIVATE, during the new 120-second window**

- Inside the *same* SQLite BEGIN IMMEDIATE transaction, check the existing
  Continuity head and the staged candidate, authenticate the stage HMAC,
  read fresh external trusted time and require the exact next window.
- Advance the Continuity epoch, mark the stage ACTIVATED and insert a durable
  old-epoch retirement tombstone atomically. Two competing local writers
  cannot both activate the same stage.
- Prior epoch-bound build/observation gates reject the old epoch after
  activation because they read the same durable Continuity head.
- A failed HMAC, premature/late clock, restart, alternate tenant or stale
  epoch leaves the transaction uncommitted.

## Security limitations — do not interpret this as a complete 120s swap

- The existing public Continuity advance method is still accessible; it can
  bypass the *optional* staged protocol. In production, a separate Trust
  Plane must own the only authorized epoch-writer endpoint.
- The candidate digest/bytes come from the caller. Stage MAC proves only
  possession of the caller-supplied key, NOT an independent source->binary
  build verification. HSM custody, secure builder/CI provenance and toolchain
  isolation remain external requirements.
- Metadata activation does **not** launch a new binary, stop the old worker,
  transfer a request, revoke a process credential, or complete a wallet
  signature. These require an independently enforced native runtime and
  Khar/Sathra signer gate with durable exactly-once recovery.
- A process may still act between supervisor polling checks. Zero-downtime
  cutover and atomic at-effect revocation are NOT implemented.
- SQLite survives ordinary restarts but is NOT protected against a privileged
  host restoring an old database. A forged clock can also defeat the window
  check. Cross-machine consensus is not provided.

## Tests

`python -m unittest discover -s tests -p 'test_strange_epoch_handoff_v1.py' -v`

Covers stage-before-boundary, activation at T=120, expired activation,
concurrent commit fencing, duplicate proposals, crash/restart persistence,
wrong key/candidate, tampering, other Continuity tenants and stale head
rejection.

Related: Issue #317 and existing Strange Continuity and supervised-native v1.
