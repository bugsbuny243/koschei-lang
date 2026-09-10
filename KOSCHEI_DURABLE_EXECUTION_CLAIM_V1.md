# KOSCHEI_DURABLE_EXECUTION_CLAIM_V1

Status: Experimental / additive / local durable acceptance candidate

## Purpose

The bootstrap `AuthorizationStateLedgerV1` and `ExecutionPermitLedgerV1` prove useful invariants inside one process, but they do not survive restart and they do not serialize an authorization-head change against a permit claim in one durable transaction.

This package adds a local durable boundary without changing strict `AuthorizationDecisionV1` or `ExecutionPermitV1` objects.

```text
Canonical request + exact intent/scope binding
  -> fresh delegation verification
  -> sealed AuthorizationState
  -> BEGIN IMMEDIATE
       require exact current durable state head
       require active state / exact intent binding
       insert unique permit execution claim
     COMMIT
  -> existing permit-consumption receipt chain
  -> effect callback
  -> existing measured effect receipt
```

The callback is unreachable until the durable claim has committed.

## Storage contract

`DurableAuthorizationStoreV1` uses Python's standard-library SQLite driver only.

The database path is explicit trusted-host input. It is not selected from project files, parser output, model/Sentinel output, tool metadata, or caller-controlled authority fields.

Required local durability settings:

- `journal_mode=WAL`
- `synchronous=FULL`
- `BEGIN IMMEDIATE` for authorization transitions and execution claims
- schema-version validation
- required-column validation
- unique `permit_digest` execution claims
- compare-and-swap style current-head validation

A malformed, unsupported, unavailable, or non-file store fails closed.

## Atomic ordering

Authorization transitions and execution claims use the same writer-serialized store.

If a revocation transition commits first, an execution claim carrying the previous state digest fails because it is no longer the current durable monotonic head.

If the execution claim commits first, a later revocation cannot retroactively erase that committed local admission. The later transition may prevent future claims but does not cancel an effect already admitted.

Therefore the property established here is:

```text
AUTHORIZED_AT_DURABLE_CLAIM
```

not:

```text
AUTHORIZED_FOREVER
REMOTE_EFFECT_ROLLBACK
```

## Restart and replay

Execution claims survive process restart. Reopening the same store and presenting the same permit digest is rejected as replay.

A crash after durable claim commit and before effect completion is intentionally fail-closed: the permit stays claimed. Automatic retry is not performed because doing so could duplicate a non-idempotent external effect.

This is local at-most-once admission, not remote exactly-once settlement.

## Direct-call safety

Exact request identity, intent, grant scope, operation, request digest and execution epoch binding is enforced inside the durable claim primitive itself. A caller cannot bypass those checks merely by skipping the higher-level durable effect wrapper.

Sentinel/model output cannot enter this authority path.

## Evidence

`DurableExecutionClaimReceiptV1` HMAC-binds:

- permit digest
- authorization-state digest
- fresh execution-snapshot digest
- authorization-decision digest
- external-evidence digest
- canonical request digest
- operation
- execution epoch

The receipt carries `authority = false`; it is evidence of local durable admission, not ambient authority.

## Explicit non-claims

This package does not by itself prove:

- multi-host or multi-replica consensus;
- provider-side revocation freshness after the local delegation check;
- remote side-effect settlement/finality;
- remote exactly-once execution;
- rollback of an effect after a later revocation;
- broker/worker OS confinement;
- seccomp, namespaces, cgroups, filesystem/network sandboxing, or remote attestation;
- full LANG-01 / LANG-02 completion;
- full T01-T14 acceptance.

Those remain independent security gates.

## Candidate acceptance cases

The dependency-free `unittest` suite now participates directly in the repository's canonical `python3 -m unittest discover -s tests` step and covers:

1. durable authorization head survives reopen;
2. durable execution claim survives reopen;
3. replay after reopen is rejected;
4. committed revocation head rejects an old-state claim;
5. stale transition compare-and-swap is rejected;
6. two concurrent local claimers produce exactly one winner;
7. effect callback observes the claim as committed before it runs;
8. restart replay is rejected before callback;
9. invalid effect key does not burn a claim;
10. direct primitive calls cannot bypass exact intent binding;
11. unsupported schema version fails closed;
12. directory/non-file store path fails closed.

The tests are wired into the canonical runner without requiring `pytest` or another test dependency. They remain candidate evidence until `ks-local-validate --profile full` is actually executed in a full checkout/toolchain environment and its external validation receipt is retained.
