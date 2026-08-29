# Request-Bound Capability Power-Domain Constraint V1

Status: **implemented bootstrap prototype / deny-only invariant / native compiler derivation pending**

## Purpose

Koschei already has one canonical capability/effect authority in `capability_effect_contract_v1` and one constitutional privileged execution path through Khar/Galaxy. The experimental six-domain prototype in PR #260 contains one useful law that belongs in that existing model:

> Authority present in one power domain must not silently become authority in another power domain.

This specification extracts only that law. It does **not** import `PowerGrant`, `CrossDomainPermit`, or a second authorization system.

## Canonical power domains

The six names remain architectural classification dimensions:

- Identity
- Authority
- Data
- Compute
- Network
- Continuity

V1 only classifies capability types/effects that already exist in the canonical capability contract. Identity and Continuity are reserved domains but are not synthesized into new capability types by this slice.

Current canonical classifications include:

- `NetRoot` / `NetCaps` -> Network
- `DiskRoot` / `DiskCaps` / `DiskReadCaps` -> Data
- `EnvRoot` / `EnvCaps` -> Data
- `ProcessRoot` / `ProcessCaps` -> Compute
- `SystemCaps` -> Authority classification only; it is not a direct I/O capability

Canonical effects classify as:

- `net.io` -> Network
- `disk.read` / `disk.write` / `env.read` -> Data
- `process.exec` -> Compute

`authority.derive` is relative to the capability being narrowed. `NetRoot.allow` remains in Network, `DiskRoot.allow` remains in Data, and so on. Narrowing does not teleport authority into one ambient global authority domain.

## Deny-only law

`capability_effect_contract_v1.require_capability_method_same_power_domain(...)` is a negative invariant:

1. capability type must be canonical;
2. method must be canonical for that capability;
3. canonical effect is derived from the existing contract;
4. source capability power domain is derived from the same contract;
5. target effect power domain is derived from the same contract;
6. unknown/unclassified combinations fail closed;
7. source and target domains must be equal.

The function returns canonical effect/domain metadata only after those checks. It does not create permission.

A future contract edit such as conceptually mapping `NetCaps.get` to `disk.read` must therefore fail closed as Network -> Data escalation.

## Exact-request binding

`RequestCapabilityDomainConstraintV1` binds the deny-only result to one exact `CanonicalEffectRequest`.

The constraint contains:

- exact canonical request digest;
- canonical capability type;
- canonical capability method;
- canonical effect identity;
- derived power domain;
- deterministic integrity digest;
- `deny_only=True`;
- `authority=False`.

It cannot emit ALLOW, mint authority, delegate authority, or create a cross-domain edge.

The request's own `operation` field must equal the canonical effect identity derived from the capability contract. This prevents a caller from sealing `signer.execute` while separately claiming that the request should be treated as `process.exec` for domain admission.

Therefore the sanctioned privileged request identity is mechanically aligned as:

```text
canonical capability type + method
-> canonical effect
-> request.operation == canonical effect
-> same-domain negative invariant
-> exact request-bound constraint
```

## Galaxy integration

`CanonicalMaterializationEffectGateV1` now requires `RequestCapabilityDomainConstraintV1`.

Order:

```text
exact request-bound domain constraint
-> validate deny-only flags
-> validate canonical capability/method/effect identity
-> validate same power domain
-> validate exact request binding
-> shared Continuity current epoch
-> one-shot materialization consume
-> existing enforce_galaxy_critical_effect(...)
-> Khar / Aevra / Matrix / Hara / Sathra / request proof / atomic finality
-> ALLOW / DENY / CONTAIN
```

The domain constraint is checked before one-shot materialization state is consumed. A malformed or foreign constraint therefore cannot burn an otherwise valid materialization handle.

The constraint is re-checked immediately before the privileged transition so canonical contract drift fails closed.

## No cross-domain permit in V1

There is deliberately no `CrossDomainPermit` equivalent in the sanctioned path.

If Koschei later requires a legitimate cross-domain transition, it must be designed as a native constitutional transition bound to exact source authority, target effect, request, epoch, irreversible cost/evidence where appropriate, and Khar/Galaxy admission. It must not appear as a reusable side permit that bypasses `vor` or the canonical capability contract.

## PROTECTS AGAINST

- accidental capability-contract edits that map one capability domain to an effect in another domain;
- unknown or unclassified capability/effect relationships silently passing domain admission;
- request A's domain constraint being reused for request B;
- caller-chosen request operation names relabeling a different canonical capability effect;
- introducing PR #260's parallel grant/permit authority model into the sanctioned #263 execution path;
- malformed/foreign domain constraints consuming a valid materialization handle before rejection.

## DOES NOT PROTECT AGAINST

- malicious trusted compiler/runtime code that deliberately changes the canonical capability contract and all dependent policy together;
- direct Python invocation of lower-level execution helpers that bypass `CanonicalMaterializationEffectGateV1`;
- host/process compromise, debugger access, memory scraping, crash dumps, side channels, or leaked keys;
- native/backend paths that do not consume the same constraint;
- a privileged callback performing behavior different from the effect identity promised by a malicious TCB implementation;
- future legitimate cross-domain transitions, which are intentionally not implemented by this slice.

## ASSUMPTIONS

- `capability_effect_contract_v1` remains the single canonical capability/effect source of truth;
- `CanonicalEffectRequest` sealing and request-bound proof logic remain trustworthy;
- production privileged execution enters through one sanctioned Khar/Galaxy ABI;
- compiler/runtime generation of the capability-domain constraint is part of the trusted semantic pipeline;
- unknown domain classifications remain fail closed.

## FAILURE MODE

The model fails if another subsystem can independently decide capability domains/effects, if a cross-domain permit system grows beside the canonical capability contract, or if privileged execution can skip the domain constraint and still reach a weaker execution path.

The current Python bootstrap also cannot physically prevent callers from importing lower-level helpers. Native compartment/API enforcement remains required.

## TESTED STATUS

Regression tests are committed for:

- exact-request binding and `deny_only=True` / `authority=False`;
- canonical Process capability -> `process.exec` -> Compute classification;
- simulated canonical-contract drift from Network capability to Data effect failing closed;
- foreign request constraint rejection before materialization handle consumption;
- non-canonical request operation relabeling rejection;
- shared Continuity tests remaining on the domain-constrained Galaxy path.

These tests are **written and committed, not claimed passed** until a real `ks-local-validate --profile full` receipt exists for the current PR head.

## NEXT

1. make Typed HIR / affine ownership / MIR expose or derive this same canonical capability basis without a parallel taxonomy;
2. remove remaining compatibility capability authorities where safe;
3. ensure native/backend privileged execution consumes the same request-bound negative invariant;
4. only then consider whether any real product requirement justifies a constitutional cross-domain transition primitive.
