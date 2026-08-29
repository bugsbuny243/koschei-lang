# KOSCHEI LANG — SOURCE OF TRUTH — 2026-08-29

Status: **canonical consolidation checkpoint / exact-request dual-world execution + shared Continuity + deny-only power-domain constraint + constitutional Galaxy admission applied**

This document stops architectural drift. It consolidates the already-designed Koschei language, Universe, representation model, runtime direction, active PR deltas and next integration order. Detailed canonical meaning remains in `KOSCHEI_SIGIL_LEXICON_V1.md`, `KOSCHEI_GALAXY_CONSTITUTION_V1.md`, `KOSCHEI_CORE_MANIFEST_V0.md` and `KOSCHEI_LANGUAGE_OWNERSHIP_V0.md`.

## 1. Non-negotiable language identity

Koschei is not renamed Rust/Python/C/Go/JavaScript syntax. Its native semantic roots are already designed:

- `ka` — admitted existence / genesis; recognition does not create privilege.
- `vor` — bounded power; authority is explicit, narrow, scoped and non-escalating.
- `shi` — witnessed reality; claim is not proof.
- `thal` — bounded survival; containment/recovery/rebirth cannot manufacture privilege.
- `nur` — controlled knowability; visibility/representation remain separate from authority and canonical identity.

These are semantic roots, not cosmetic keyword aliases.

## 2. Primary law

**OBSERVABLE WORLD != CANONICAL WORLD**

Canonical world contains real identity, authority, evidence, lifecycle, Veyra/Aevra/Matrix/Hara relations, request identity, MIR/IR identity and Continuity state.

Observable world may contain only role-required rotating aliases, epoch/session/customer-specific Nyr mappings, opaque handles, bounded diagnostics and visibility-limited state.

The observer surface must not become a stable one-to-one operational power map of canonical reality.

This is not a claim that canonical state can never leak. Trusted-process compromise, leaked keys, debugger/crash dumps, side channels and bypass paths remain real threats.

## 3. Existing Universe vocabulary remains canonical

- **Khar** — public constitutional laws; never a hidden super-user.
- **Aevra** — canonical entity identity greater than visible bytes.
- **Veyra** — customer-specific living Galaxy geometry.
- **Matrix** — controlled local execution reality.
- **Hara** — one Aevra's scoped horizon inside Matrix.
- **Sathra** — exact 6/6 critical-event concurrence; not reusable authority.
- **Vormir** — irreversible cost for higher-power transitions.
- **Morth / Event Horizon / Black Hole** — terminal identity/authority/lifecycle semantics.
- **Doctor Strange** — deterministic Khar-safe survival branch selection.
- **Skynet** — Continuity/epoch/lifecycle coordination, never sovereign policy.
- **Avengers / Infinity Stones** — independent power/failure dimensions, not one master authority.
- **Neo** — exceptional authorized transition/materialization role, not universal bypass.
- **Agent Smith** — spread/persistence/correlation/representation-learning adversary.
- **Deus Ex Machina** — conservation/finality concept, not override credential.

Metaphors without enforceable technical responsibility are rejected.

## 4. Current compiler reality on main

`source -> lexer -> parser -> AST -> integrity -> Typed HIR -> typestate -> affine ownership -> effect contracts -> legacy compatibility bridge -> legacy semantic checker -> sealed MIR -> reference interpreter`

Known debt remains:

- `_parser_v09.py` compatibility authority;
- Typed HIR + legacy semantic overlap;
- distributed capability semantics;
- source/MIR effect computations;
- MIR AST fallback.

The cleanup goal is fewer semantic authorities, not merely fewer files.

## 5. Target canonical execution pipeline

```text
ka/vor/shi/thal/nur source intent
-> canonical semantic checking
-> Verified/Native MIR
-> Library obligations
-> canonical semantic seal
-> Nur/Nyr observer projection
-> sealed CanonicalEffectRequest
-> exact-request ReconstructionGrantV1
-> one Continuity liveness truth
-> atomic reconstruction consumption
-> opaque CanonicalMaterializationHandleV1
-> exact request + Veyra materialization check
-> exact-request RequestCapabilityDomainConstraintV1
   -> canonical capability type + method
   -> canonical effect identity
   -> request.operation == canonical effect
   -> same power domain or fail closed
-> existing Khar/Galaxy constitutional admission
   -> canonical Khar
   -> living Aevra
   -> current Matrix/Hara
   -> exact 6/6 Sathra
   -> failure-root independence
   -> exact RequestBoundProof
   -> durable atomic claim/finality
-> ALLOW / DENY / CONTAIN
-> effect only on ALLOW
```

No backend, adapter, observer, materialization or recovery path may create a second semantic truth around this chain.

## 6. PR #263 — PRIMARY CORE INTEGRATION PATH

Current sanctioned bootstrap chain:

```text
sealed NativeSigilMir [canonical]
-> non-faithful Nyr v2 [observer]
-> sealed CanonicalEffectRequest
-> exact-request ReconstructionGrantV1
-> shared ContinuityEpochAuthorityV1
-> atomic ReconstructionConsumptionLedgerV1
-> ReconstructionConsumptionReceiptV1
-> opaque CanonicalMaterializationHandleV1
-> shared ContinuityEpochAuthorityV1
-> exact request + reconstruction Veyra binding
-> RequestCapabilityDomainConstraintV1 [deny-only / authority=false]
-> canonical capability method/effect same-domain check
-> enforce_galaxy_critical_effect(...)
-> Khar + living Aevra + current Matrix/Hara
-> 6/6 Sathra + failure-root independence
-> exact request-bound native proof
-> durable AtomicExecutionCoordinator claim/finality
-> ALLOW / DENY / CONTAIN
```

### Exact-request reconstruction — APPLIED

- grant issuance requires the exact sealed `CanonicalEffectRequest`;
- raw request digest is absent from the grant;
- opaque grant request binding is scoped to request + Veyra + observer + session + epoch;
- request-A grant cannot reconstruct request-B;
- request binding survives authenticated consumption provenance;
- materialization handle independently remains exact-request bound;
- sanctioned reconstruction returns no raw MIR.

### Shared Continuity liveness — APPLIED

PR #264 liveness semantics are absorbed into #263 rather than becoming another lifecycle authority.

- `ContinuityEpochAuthorityV1` supplies one typed fail-closed epoch interface;
- `NyrObservationGateV1`, reconstruction and materialization consume that same contract;
- sanctioned gate constructors expose no raw `epoch_source`;
- one backing epoch advance invalidates old Nyr observation, old reconstruction and a held materialization handle together;
- one failed Continuity reader fails all three boundaries closed.

Important non-claim: the Python Continuity identity seal does not prove reader honesty, monotonic hardware time or rollback resistance. Shared truth eliminates internal clock disagreement; it does not manufacture trustworthy time.

### Constitutional Galaxy execution — APPLIED

The old architectural bypass is closed on the #263 sanctioned materialization path. `CanonicalMaterializationEffectGateV1` no longer directly invokes a weaker request-bound native effect gate.

Instead:

- reconstruction Veyra is sealed into trusted registry state and keyed materialization binding;
- another Veyra/Galaxy cannot reuse the handle;
- exact request + Veyra + current Continuity are checked before canonical state is released;
- the handle is then burned one-shot;
- execution delegates to existing `enforce_galaxy_critical_effect()`;
- canonical Khar, living Aevra, current Matrix/Hara, exact Sathra, failure-root independence, exact request proof and durable atomic execution remain the authoritative critical-effect physics;
- `GalaxyMaterializationContextV1` is only a non-authoritative transport bundle for those already-existing inputs.

This is convergence, not another authority system.

### Cross-domain default-deny — APPLIED

The useful invariant from PR #260 has been extracted without importing its grant/permit authority model.

- `capability_effect_contract_v1` remains the one canonical capability/effect source of truth;
- canonical capability types/effects are classified into Identity / Authority / Data / Compute / Network / Continuity power domains only for negative enforcement;
- `authority.derive` remains relative to the source capability domain, so narrowing does not create ambient global authority;
- `RequestCapabilityDomainConstraintV1` is exact-request bound, `deny_only=True`, `authority=False`;
- the constraint can never emit ALLOW or create a cross-domain edge;
- request `operation` must equal the canonical capability effect identity, preventing caller-selected relabeling;
- unknown/unclassified capability relationships fail closed;
- a capability-contract edit that crosses domains fails before materialization is consumed;
- foreign request constraints fail before one-shot handle consumption;
- the existing Khar/Galaxy gate remains the only critical-effect admission authority.

PR #260's `PowerGrant` and `CrossDomainPermit` are intentionally **not** part of this path.

## 7. PR #264 — SEMANTICS ABSORBED, NO NEW FEATURE GROWTH

Its Nyr replay/liveness rules now live in #263 under shared Continuity. Do not evolve #264 as a parallel epoch authority. Keep it open until explicit PR cleanup/closure is requested.

## 8. PR #260 — DEFAULT-DENY LAW EXTRACTED, PARALLEL AUTHORITY REJECTED

Identity / Authority / Data / Compute / Network / Continuity remain useful architectural classification dimensions.

The only currently accepted extraction is the same-domain negative invariant now implemented in #263. Do not merge #260 wholesale and do not introduce `PowerGrant` / `CrossDomainPermit` beside `vor`, the canonical capability contract, or Khar/Galaxy admission.

If a future real product requirement needs a legitimate cross-domain transition, it must be designed as a native constitutional exact-request transition rather than a reusable side permit.

## 9. PR #265 — FEATURE GROWTH FROZEN

Retain Lang-core value from Verified IR identity, toolchain/build provenance, payload lineage, trust-anchor generation and provider-neutral witness/attestation contracts. Provider/finality-specific growth remains frozen until core execution converges.

External adapters remain non-authoritative.

## 10. Immediate integration order

From this checkpoint, `Devam` means:

1. **CURRENT NEXT:** consolidate the same canonical capability basis across Typed HIR, affine ownership, effect contracts, MIR and runtime without creating another taxonomy;
2. finish MIR normalization/reduce semantic AST fallback;
3. then extract only relevant Verified IR/provenance primitives from #265;
4. move canonical MIR/replay/materialization custody into durable/native isolation;
5. classify debugger/introspection/runtime output as trusted-canonical or observer-safe;
6. run canonical/adversarial validation before ready/merge.

## 11. Stop rules

- no new syntax family unless closing a documented semantic gap;
- no second parser/type/effect/capability authority;
- no new security module merely because an attack can be named;
- no second privileged execution path around Galaxy/Khar;
- no reusable cross-domain side permit around canonical capability semantics;
- no provider-specific Lang-core growth;
- no claim that Python privacy is physical isolation;
- no claim rotating representation makes source impossible to see;
- no claim shared Continuity is rollback-resistant time;
- no claim `mergeable=true` means tests passed;
- no core merge without canonical validation evidence;
- no metaphor without technical responsibility.

## 12. Security honesty

### PROTECTS AGAINST — current sanctioned direction

- faithful canonical naming exposure through the Nyr path;
- stale Nyr replay through sanctioned observation;
- separate arbitrary epoch callbacks drifting across observer/reconstruction/materialization;
- grant widening from one canonical request to another;
- moving a materialization handle to another Veyra/Galaxy;
- caller-selected privileged operation names being relabeled as a different canonical capability effect at domain admission;
- accidental canonical capability-contract drift from one power domain to another;
- unknown capability/effect domain relationships silently passing privileged materialization;
- foreign request domain constraints burning a valid materialization handle;
- bypassing Khar/Matrix/Hara/Sathra admission through the sanctioned materialization effect path;
- repeated/concurrent reconstruction in one process-local ledger;
- repeated materialization use in one process-local registry;
- critical-event replay covered by the existing durable Galaxy atomic coordinator;
- external evidence becoming authority merely because it is external.

### DOES NOT PROTECT AGAINST

- compromised/rolled-back underlying Continuity state;
- full trusted-process memory compromise;
- direct Python invocation of lower-level/private helpers;
- debugger/crash dump/side-channel leakage;
- malicious compiler/runtime or Galaxy dependencies inside the TCB;
- a malicious TCB deliberately changing canonical capability semantics and dependent policy together;
- leaked trust-role keys;
- restart/VM rollback of in-memory reconstruction/materialization state;
- native/backend paths that bypass sanctioned gates;
- a privileged callback violating the effect identity promised by a malicious trusted implementation;
- claimed physical failure-root independence without genuinely independent evidence.

### ASSUMPTIONS

- `capability_effect_contract_v1` remains the single canonical capability/effect source of truth;
- canonical MIR, Veyra/Aevra, Matrix/Hara, request/proof/Sathra seals and durable Galaxy stores are trustworthy;
- production preserves one sanctioned privileged execution ABI;
- compiler/runtime generation of request capability-domain constraints is part of the trusted semantic pipeline;
- production Continuity is supplied by a stronger rollback-aware runtime mechanism when rollback matters;
- materialization registry/raw MIR remains inside a trusted compartment.

### FAILURE MODE

The architecture fails if privileged execution can choose a weaker path than the Khar/Galaxy route, if observer-visible objects become authority, if capability/domain systems evolve as competing truths, or if another compiler/runtime layer can independently relabel capability effects after the canonical contract is checked.

## 13. Validation checkpoint

Canonical command:

`ks-local-validate --profile full --output /tmp/koschei-local-validation.json --evidence-dir /tmp/koschei-validation-evidence`

Tests committed in the open PR are **not** described as passed until actual execution evidence exists.

### SPEC STATE

Settled: `ka/vor/shi/thal/nur`, Khar, Aevra/Veyra, Matrix/Hara, Sathra, controlled knowability, non-faithful rotating observer representation, exact-request reconstruction, one Continuity liveness contract, deny-only request-bound capability power-domain enforcement and constitutional Galaxy execution on the sanctioned materialization path.

### COMPILER STATE

Functional compiler/interpreter/tooling exists. `capability_effect_contract_v1` now also owns canonical power-domain classification for existing capability types/effects. Typed HIR/effect contracts already consume parts of this canonical capability contract; affine ownership/MIR/runtime consolidation remains incomplete.

### RUNTIME STATE

Open-PR Python bootstrap has exact-request reconstruction, live-Nyr observation, shared Continuity, opaque Veyra/request-bound materialization, exact-request same-domain capability constraint, and delegation into the existing durable Galaxy critical-effect gate. Native canonical custody and rollback-resistant Continuity remain unsolved.

### SECURITY MODEL

`explicit authority + canonical capability/effect identity + same-domain default-deny + canonical identity + witnessed reality + bounded lifecycle + controlled knowability + one Continuity truth + exact-request materialization + one constitutional critical-effect path`

### EXPERIMENTAL

Hardware/native isolation, rollback-resistant Continuity, durable global reconstruction replay state, complete observer-safe tooling, physical failure-root independence, constitutional cross-domain transitions if ever justified, and external build/finality integration.

### TESTED

New and updated regression tests are committed, including domain-drift and request-relabeling adversarial cases, but no fresh `ks-local-validate --profile full` receipt is claimed for current #263 HEAD.

### NEXT

**Consolidate this same canonical capability basis across Typed HIR, affine ownership, effect contracts, MIR and runtime; remove remaining compatibility authority rather than adding another domain/capability system.**
