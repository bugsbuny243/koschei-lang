# KOSCHEI LANG — SOURCE OF TRUTH — 2026-08-29

Status: **canonical consolidation checkpoint / exact-request dual-world execution + shared Continuity + compiler-bound deny-only power-domain constraint + constitutional Galaxy admission applied**

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

## 4. Current compiler reality

Checked module-graph path:

`source -> lexer -> parser -> AST -> integrity -> Typed HIR -> typestate -> affine ownership -> canonical effect contracts -> legacy compatibility consumer -> sealed MIR -> reference interpreter/backend`

Important convergence now applied on #263:

- `capability_effect_contract_v1` is the canonical capability/effect source;
- Typed type sensitivity reads canonical `CAPABILITY_TYPES` directly;
- affine ownership consumes structural sensitivity derived from that same contract;
- `check_effect_contracts(...)` produces the checked module-graph `EffectReport`;
- MIR consumes that exact checked report rather than re-running legacy AST effect inference;
- imported canonical capability effects survive into caller MIR through the checked report;
- the old `effects.infer_effects(...)` is not an approved MIR semantic authority on the sanctioned compiler path.

Known debt remains:

- `_parser_v09.py` compatibility authority;
- Typed HIR + legacy semantic overlap;
- executable MIR AST fallback;
- compiler capability call-site identity is not yet first-class normalized MIR;
- some legacy compatibility aliases remain, though the sanctioned checker reinstalls them from the canonical contract;
- native compiler/runtime custody and provenance are not physically isolated.

The cleanup goal is fewer semantic authorities, not merely fewer files.

## 5. Target canonical execution pipeline

```text
ka/vor/shi/thal/nur source intent
-> canonical semantic checking
-> checked compiler MIR / capability-effect basis
-> Verified/Native sigil MIR
-> Library obligations
-> canonical semantic seal
-> Nur/Nyr observer projection
-> compiler-derived privileged request operation
-> sealed CanonicalEffectRequest
-> exact-request ReconstructionGrantV1
-> one Continuity liveness truth
-> atomic reconstruction consumption
-> opaque CanonicalMaterializationHandleV1
-> exact request + Veyra materialization check
-> compiler-bound RequestCapabilityDomainConstraintV1
   -> exact compiler capability type + method
   -> canonical effect identity
   -> request.operation == compiler-derived canonical effect
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
sealed checked compiler MirGraph
-> one exact leaf capability call
-> CompilerCapabilityEffectBasisV1
-> operation := compiler basis canonical effect
-> sealed NativeSigilMir [canonical]
-> CanonicalEffectRequest
-> compiler-bound RequestCapabilityDomainConstraintV1
-> non-faithful Nyr v2 [observer]
-> exact-request ReconstructionGrantV1
-> shared ContinuityEpochAuthorityV1
-> atomic ReconstructionConsumptionLedgerV1
-> ReconstructionConsumptionReceiptV1
-> opaque CanonicalMaterializationHandleV1
-> shared ContinuityEpochAuthorityV1
-> exact request + reconstruction Veyra binding
-> compiler-bound same-domain negative check
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

The old architectural bypass is closed on the #263 sanctioned materialization path. `CanonicalMaterializationEffectGateV1` delegates privileged execution to the existing Galaxy critical-effect path rather than a weaker parallel native gate.

- reconstruction Veyra is sealed into trusted registry state and keyed materialization binding;
- another Veyra/Galaxy cannot reuse the handle;
- exact request + Veyra + current Continuity are checked before canonical state is released;
- the handle is then burned one-shot;
- execution delegates to existing `enforce_galaxy_critical_effect()`;
- canonical Khar, living Aevra, current Matrix/Hara, exact Sathra, failure-root independence, exact request proof and durable atomic execution remain the authoritative critical-effect physics;
- `GalaxyMaterializationContextV1` is only a non-authoritative transport bundle for those already-existing inputs.

### Cross-domain default-deny — APPLIED

The useful invariant from PR #260 has been extracted without importing its grant/permit authority model.

- `capability_effect_contract_v1` remains the one canonical capability/effect source of truth;
- canonical capability types/effects are classified into Identity / Authority / Data / Compute / Network / Continuity power domains only for negative enforcement;
- `authority.derive` remains relative to the source capability domain;
- unknown/unclassified capability relationships fail closed;
- a capability-contract edit that crosses domains fails closed;
- the existing Khar/Galaxy gate remains the only critical-effect admission authority.

PR #260's `PowerGrant` and `CrossDomainPermit` are intentionally **not** part of this path.

### Compiler-bound privileged request — APPLIED BOOTSTRAP

Runtime integration no longer writes `ProcessCaps.run`, `NetCaps.get`, or another capability pair by hand when constructing the sanctioned request-domain relation.

`CompilerCapabilityEffectBasisV1` is derived from sealed compiler MIR and V1 requires:

- one unambiguous module;
- one unambiguous function;
- leaf function with no local calls;
- no imported calls;
- exactly one direct canonical capability call-site;
- MIR canonical capability effect set equal to exactly that effect;
- same-domain canonical contract validation.

`seal_compiler_bound_effect_request_v1(...)` then derives `CanonicalEffectRequest.operation` from the compiler basis. The caller supplies request/payload/identity/epoch/nonce evidence but does not supply privileged operation, capability type, capability method, or power domain.

`bind_request_capability_domain_v1(...)` now accepts only `compiler_basis=`. Its old manual capability-type/method interface is gone from the sanctioned bootstrap API.

The resulting constraint is:

- exact-request bound;
- compiler-basis bound;
- `compiler_bound=True`;
- `deny_only=True`;
- `authority=False`.

Ambiguous multiple capability call-sites and local/imported call indirection fail closed rather than being guessed into one authority identity.

Important non-claim: compiler basis/constraint seals are deterministic structural seals, not a secret-key compiler signature. Issuance can re-derive the basis from sealed `MirGraph`; the later materialization gate does not carry broad compiler MIR through the observer/runtime surface. Direct arbitrary Python dataclass construction inside the TCB therefore remains a known bootstrap bypass class until native compiler/runtime ABI isolation exists.

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

1. **CURRENT NEXT:** make exact capability call-site identity a first-class normalized MIR fact instead of deriving compiler provenance by walking sealed AST fallback;
2. prove interpreter/native/backend consumers use that same normalized call-site capability identity;
3. continue reducing legacy semantic/AST compatibility authority;
4. then extract only relevant Verified IR/provenance primitives from #265;
5. move compiler/runtime provenance plus canonical MIR/replay/materialization custody into durable/native isolation;
6. classify debugger/introspection/runtime output as trusted-canonical or observer-safe;
7. run canonical/adversarial validation before ready/merge.

## 11. Stop rules

- no new syntax family unless closing a documented semantic gap;
- no second parser/type/effect/capability authority;
- no runtime-selected capability type/method after compiler authority identity is known;
- no guessing through ambiguous multi-call/transitive capability provenance;
- no new security module merely because an attack can be named;
- no second privileged execution path around Galaxy/Khar;
- no reusable cross-domain side permit around canonical capability semantics;
- no provider-specific Lang-core growth;
- no claim that Python privacy is physical isolation;
- no claim rotating representation makes source impossible to see;
- no claim shared Continuity is rollback-resistant time;
- no claim deterministic compiler seals are unforgeable signatures;
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
- runtime/bootstrap callers independently selecting capability type/method for privileged request admission;
- caller-selected privileged operation labels diverging from the compiler-derived canonical effect;
- ambiguous multiple capability call-sites being silently guessed into one authority identity;
- accidental canonical capability-contract drift from one power domain to another;
- unknown capability/effect domain relationships silently passing privileged materialization;
- foreign request domain constraints burning a valid materialization handle;
- MIR independently disagreeing with the compiler's checked capability effect because of legacy AST-local re-inference;
- imported capability effects disappearing from caller MIR merely because MIR lacks module-graph effect context;
- bypassing Khar/Matrix/Hara/Sathra admission through the sanctioned materialization effect path;
- repeated/concurrent reconstruction in one process-local ledger;
- repeated materialization use in one process-local registry;
- critical-event replay covered by the existing durable Galaxy atomic coordinator;
- external evidence becoming authority merely because it is external.

### DOES NOT PROTECT AGAINST

- compromised/rolled-back underlying Continuity state;
- full trusted-process memory compromise;
- direct Python invocation/construction of lower-level internal helpers/dataclasses inside the TCB;
- debugger/crash dump/side-channel leakage;
- malicious compiler/runtime or Galaxy dependencies inside the TCB;
- a malicious TCB deliberately changing canonical capability semantics and dependent policy together;
- deterministic compiler-basis object forgery by an attacker already executing inside the trusted Python process;
- leaked trust-role keys;
- restart/VM rollback of in-memory reconstruction/materialization state;
- native/backend paths that bypass sanctioned gates or ignore sealed MIR capability metadata;
- a privileged callback violating the effect identity promised by a malicious trusted implementation;
- legitimate multi-call/transitive privileged functions, which compiler-basis V1 currently rejects rather than models incompletely;
- claimed physical failure-root independence without genuinely independent evidence.

### ASSUMPTIONS

- `capability_effect_contract_v1` remains the single canonical capability/effect source of truth;
- checked `MirGraph` and Typed-HIR evidence are trustworthy compiler products;
- canonical NativeSigilMir, Veyra/Aevra, Matrix/Hara, request/proof/Sathra seals and durable Galaxy stores are trustworthy;
- production preserves one sanctioned privileged execution ABI;
- compiler-bound request issuance is used instead of direct low-level Python constructors;
- production Continuity is supplied by a stronger rollback-aware runtime mechanism when rollback matters;
- materialization registry/raw canonical state remains inside a trusted compartment.

### FAILURE MODE

The architecture fails if runtime code can independently relabel compiler-known capability authority, if privileged execution can choose a weaker path than Khar/Galaxy, if observer-visible objects become authority, if capability/domain systems evolve as competing truths, or if another compiler/runtime layer independently recomputes and overrides canonical capability identity.

## 13. Validation checkpoint

Canonical command:

`ks-local-validate --profile full --output /tmp/koschei-local-validation.json --evidence-dir /tmp/koschei-validation-evidence`

Tests committed in the open PR are **not** described as passed until actual execution evidence exists.

### SPEC STATE

Settled: `ka/vor/shi/thal/nur`, Khar, Aevra/Veyra, Matrix/Hara, Sathra, controlled knowability, non-faithful rotating observer representation, exact-request reconstruction, one Continuity liveness contract, compiler-bound deny-only capability power-domain enforcement and constitutional Galaxy execution on the sanctioned materialization path.

### COMPILER STATE

Functional compiler/interpreter/tooling exists. Typed type sensitivity, affine ownership and effect checking converge on the canonical capability contract; checked `EffectReport` is now the MIR capability-effect source. `CompilerCapabilityEffectBasisV1` can bind one exact leaf capability call from sealed compiler MIR into privileged request issuance. First-class normalized MIR call-site capability identity remains pending.

### RUNTIME STATE

Open-PR Python bootstrap has exact-request reconstruction, live-Nyr observation, shared Continuity, opaque Veyra/request-bound materialization, compiler-bound exact-request same-domain capability constraint, and delegation into the existing durable Galaxy critical-effect gate. Native compiler/runtime provenance custody and rollback-resistant Continuity remain unsolved.

### SECURITY MODEL

`explicit authority + compiler-derived canonical capability/effect identity + same-domain default-deny + canonical identity + witnessed reality + bounded lifecycle + controlled knowability + one Continuity truth + exact-request materialization + one constitutional critical-effect path`

### EXPERIMENTAL

First-class MIR call-site effect identities, hardware/native isolation, rollback-resistant Continuity, durable global reconstruction replay state, complete observer-safe tooling, physical failure-root independence, constitutional cross-domain transitions if ever justified, and external build/finality integration.

### TESTED

New and updated regression tests are committed for compiler-basis derivation, ambiguous-call fail-closed behavior, request compiler binding, domain drift and request relabeling. No fresh `ks-local-validate --profile full` receipt is claimed for current #263 HEAD.

### NEXT

**Make exact canonical capability call-site identity a first-class normalized MIR fact and remove the remaining AST-walk provenance bridge before broadening privileged function shapes.**
