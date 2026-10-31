# Strange Reconciled Native Launch V1

**Status: optional, single-host Python integration. No hard execution/effect fencing.**

Earlier modules can explicitly activate a prebuilt next-epoch binary and run it
through a supervised sealed Linux memfd, and separately store a durable
single-attempt local launch record. This adapter sequences both.

## Contract

1. Check the typed canonical MIR and internally consistent pending native bytes.
2. Write one persistent `CLAIMED` record for the active epoch using the
   existing Continuity + activated-stage HMAC + retirement tombstone transaction.
3. Only if claim creation succeeds, invoke the existing activated prebuilt
   native launcher. It rechecks exact source/native identity, private seed and
   live epoch and uses the sealed Linux process supervisor.
4. On a runner exception known to the adapter, record `REPORTED_FAILED`
   using the protected handoff key. On nonzero exit, record failure and refuse
   a successful result.
5. On zero exit, report `REPORTED_OK` only if Continuity remains in the
   exact same active, unexpired epoch at report commit.
6. When a report cannot be committed, or when an unexpected interruption
   occurs, leave the attempt `CLAIMED` for manual operator investigation.
7. No automatic retry, and **never roll an epoch backward** to resume an
   already retired native representation.

The output wraps the local process observation and reported state with
`authority=False`. It cannot authorize a cryptocurrency signature, expose
Library content, or release an external resource.

## Regression tests

- Refuse an unactivated handoff without calling the runner.
- Permit only one wrapped run; duplicate and concurrent attempts fail.
- Persist a successful observed result, deny replay after completion.
- Persist an unsuccessful process exit or launch exception as failure.
- An unhandled interruption leaves `CLAIMED`, and restart cannot safely
  re-run the uncertain request.
- Expiry or epoch rotation after process return cannot be recorded as
  a current-epoch successful launch.
- Reject inconsistent native candidate bytes before consuming an attempt.

`python -m unittest discover -s tests -p 'test_strange_reconciled_native_launch_v1.py' -v`

## Security and deployment limitations

- Both this wrapper and its underlying runner remain publicly callable
  Python functions. Anyone able to call the raw runner can **bypass this
  optional journal**. Enforce the sole execution pathway in a separate
  privilege-isolated native Trust Plane to close this gap.
- SQLite reservation is not an operating-system process lock and cannot
  atomically commit with `fork`, `exec`, cgroup retirement or remote
  privileged effects. `REPORTED_OK` is still only local runner evidence.
- A process started before expiry may act between supervision polls. This
  interface does not transfer in-flight requests, restart failed workers,
  guarantee zero downtime or secure a network of distributed workers.
- Caller-supplied keys, Go executable pins and clock values are not hardware
  attestation, independent signer custody or complete toolchain provenance.
- Durable local SQLite cannot resist malicious filesystem rollback by a
  privileged host.

Related: PR #328, PR #329 and issue #317. 
