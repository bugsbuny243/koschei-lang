# KOSCHEI LANG — SOURCE OF TRUTH — 2026-08-29

Status: **canonical consolidation checkpoint / exact-request reconstruction applied / no new language invention**

This document exists to stop architectural drift. It consolidates the already-designed Koschei language, Universe, representation model, runtime direction, active PR deltas and next integration order. It does not replace `KOSCHEI_SIGIL_LEXICON_V1.md`, `KOSCHEI_GALAXY_CONSTITUTION_V1.md`, `KOSCHEI_CORE_MANIFEST_V0.md`, or `KOSCHEI_LANGUAGE_OWNERSHIP_V0.md`; it defines how they fit together.

## 1. Non-negotiable identity

Koschei Lang is not renamed Rust/Python/C/Go/JavaScript syntax. Originality must live in semantic admission, authority, evidence, lifecycle, controlled knowability, representation, identity, execution admission and verified lineage.

The native semantic roots are already designed and MUST NOT be re-invented:

- `ka` — admitted existence / genesis; recognition does not create privilege.
- `vor` — bounded power; authority is explicit, narrow, scoped and non-escalating.
- `shi` — witnessed reality; claim is not proof.
- `thal` — bounded survival; containment/recovery/rebirth cannot manufacture privilege.
- `nur` — controlled knowability; visibility/representation remain separate from authority and canonical identity.

These are semantic roots, not cosmetic keyword aliases.

## 2. Primary law — observable world != canonical world

### Canonical world

Contains the real trusted relations required for execution: canonical identity, semantic meaning, capability/authority graph, evidence lineage, lifecycle state, Veyra/Aevra/Matrix/Hara relations, request identity, MIR/IR identity and Continuity epoch state.

### Observable world

May contain only what a role needs to observe: rotating aliases, epoch/session/customer-specific Nyr mappings, opaque handles, bounded diagnostics and visibility-limited state.

The observable surface MUST NOT be the stable one-to-one power map of the canonical world.

This is not a claim that canonical state can never leak. Compromised trusted processes, leaked keys, debugger/crash dumps, side channels or bypass paths can still expose it. The rule is that sanctioned observer/runtime surfaces do not expose canonical reality as their default representation.

## 3. Canonical Universe vocabulary

- **Khar** — constitutional laws; not a secret super-user.
- **Aevra** — canonical program/entity identity greater than visible bytes.
- **Veyra** — customer-specific living Galaxy geometry.
- **Matrix** — controlled local execution reality.
- **Hara** — one Aevra's scoped horizon inside a Matrix.
- **Sathra** — one exact 6/6 critical concurrence event; not reusable authority.
- **Vormir** — irreversible cost for higher-power transitions.
- **Morth / Event Horizon / Black Hole** — terminal identity/authority/lifecycle sink semantics.
- **Survival branch selection / Doctor Strange** — deterministic Khar-safe future selection; not sovereign AI.
- **Skynet** — Continuity/epoch/lifecycle coordination concept; never policy sovereignty.
- **Avengers / Infinity Stones** — independent power/failure dimensions that must not collapse to one master authority.
- **Neo** — exceptional authorized transition/materialization role; never universal bypass.
- **Agent Smith** — spread/persistence/correlation/representation-learning adversary model.
- **Deus Ex Machina** — conservation/finality root concept; never hidden override credential.

Metaphors without enforceable technical responsibility do not belong in the architecture.

## 4. Compiler reality on main

Current authoritative compilation path:

`source -> lexer -> parser -> AST -> integrity -> Typed HIR -> typestate -> affine ownership -> effect contracts -> legacy compatibility bridge -> legacy semantic checker -> sealed MIR -> reference interpreter`

Known migration debt:

- `_parser_v09.py` remains active compatibility debt;
- Typed HIR and legacy semantic authority overlap;
- capability semantics are distributed across several modules;
- source-effect and MIR-effect computations are related but separate;
- MIR normalization still contains AST fallback.

The cleanup goal is fewer semantic authorities, not merely fewer files.

## 5. Target canonical pipeline

`ka/vor/shi/thal/nur source intent`
`-> canonical semantic checking`
`-> Verified/Native MIR`
`-> Library obligations`
`-> Khar / Universe composition`
`-> authority + evidence + lifecycle admission`
`-> canonical semantic seal`
`-> Nur/Nyr observer projection`
`-> exact-request reconstruction capability`
`-> single-use reconstruction`
`-> opaque materialization handle`
`-> trusted compartment resolution`
`-> exact request-bound effect admission`
`-> ALLOW / DENY / CONTAIN`
`-> execution evidence / finality where required`

No backend, adapter or recovery path may create a second semantic truth around this chain.

## 6. PR #263 — current primary core integration path

PR #263 owns the central `observable != canonical` execution boundary.

Current implemented bootstrap chain:

`sealed NativeSigilMir`
`-> non-faithful Nyr v2 representation`
`-> sealed CanonicalEffectRequest`
`-> exact-request ReconstructionGrantV1`
`-> trusted runtime epoch`
`-> atomic single-use reconstruction consumption`
`-> ReconstructionConsumptionReceiptV1`
`-> opaque CanonicalMaterializationHandleV1`
`-> exact CanonicalEffectRequest + RequestBoundProof`
`-> native ALLOW / DENY / CONTAIN`

### Exact-request reconstruction — APPLIED

The previous gap is closed in this branch:

- reconstruction grant issuance now requires the exact sealed `CanonicalEffectRequest`;
- the grant does NOT expose raw `CanonicalEffectRequest.digest`;
- an opaque HMAC request binding is scoped to request + Veyra + observer + session + visibility epoch;
- the grant context digest binds that request binding together with canonical world/context identity;
- request A grant cannot reconstruct request B even under the same MIR/Veyra/epoch/purpose;
- `ReconstructionConsumptionReceiptV1` cryptographically carries the opaque request binding;
- the materialization handle independently remains exact-request bound under its own key role;
- raw MIR is not returned by the sanctioned reconstruction gate.

This closes the old "purpose=execute is too broad" gap at reconstruction issuance.

## 7. PR #264 — next integration target

Purpose: Nyr v2 observer liveness/replay protection.

A correctly generated Nyr surface must still fail if it is stale, future/not-yet-live, contained, or runtime epoch truth fails.

This must NOT evolve as a second lifecycle authority. Its live-Nyr logic is to be absorbed into the same `nur` / Continuity truth used by #263 reconstruction and materialization.

Required invariant:

`same authoritative Continuity epoch -> observation liveness + reconstruction liveness + materialization liveness`

No caller-selected epoch and no separate epoch oracle per boundary.

## 8. PR #260 — constitutional/power-domain prototype

Identity / Authority / Data / Compute / Network / Continuity isolation remains valuable, but it must enter the single exact request-bound execution gate only where it closes a Khar/authority invariant. It must not become a parallel authority system.

## 9. PR #265 — feature growth frozen

Valuable Lang-core concepts include Verified IR identity, toolchain/build provenance, payload lineage, trust-anchor generation and provider-neutral witness/attestation contracts.

Provider/finality-specific growth is frozen until the core language/runtime pipeline converges. Later work should extract only what is required for:

`Source Intent -> Verified IR -> Artifact -> Payload -> Execution`

External adapters remain non-authoritative.

## 10. Immediate integration order

From this checkpoint, "continue" means:

1. **CURRENT:** absorb #264 Nyr liveness into #263 so one Continuity epoch truth drives observer/reconstruction/materialization liveness.
2. connect existing Khar/Galaxy/Matrix/Hara and relevant power-domain admission to that same exact request-bound execution gate;
3. consolidate one canonical capability contract across Typed HIR, affine ownership, effects, MIR and runtime;
4. finish MIR normalization and reduce semantic AST fallback;
5. only then extract relevant Verified IR/provenance primitives from #265;
6. move canonical MIR/replay/materialization custody into durable/native isolation;
7. classify debugger/introspection/runtime output as trusted-canonical or observer-safe;
8. run canonical validation/adversarial suites before ready/merge.

## 11. Stop rules

Until integration is complete:

- no new syntax family unless it closes a documented semantic gap;
- no second parser/type/effect/capability authority;
- no new security module merely because an attack can be named;
- no new provider-specific Lang-core feature;
- no claim that Python private fields provide physical isolation;
- no claim that rotating representation makes source impossible to see;
- no claim that `mergeable=true` means tests passed;
- no core merge without canonical validation evidence;
- no metaphor without a technical job.

## 12. Security honesty

### PROTECTS AGAINST — partially enforced current direction

- ambient authority through explicit capability semantics;
- observer representation being a faithful canonical naming map on the Nyr path;
- grant widening from one exact canonical request to another under #263;
- raw canonical request digest exposure in reconstruction grant/materialization handle;
- repeated/concurrent reconstruction in one process-local authoritative ledger;
- repeated materialization handle use in one process-local registry;
- selected stale representation replay where trusted liveness gates are used;
- external evidence becoming authority merely because it is external.

### DOES NOT PROTECT AGAINST

- full compromise of trusted process memory;
- debugger/crash dump/side-channel leaks;
- malicious compiler/runtime inside the trusted computing base;
- leaked trust-role keys;
- process/VM rollback where state is not independently monotonic;
- native/backend paths that bypass sanctioned gates;
- inference from every possible observation channel;
- physical independence without real external evidence.

### FAILURE MODE

The project fails architecturally if it becomes a collection of impressive disconnected security utilities. One compiler/runtime/execution truth is mandatory.

## 13. Validation checkpoint

Required canonical command remains:

`ks-local-validate --profile full --output /tmp/koschei-local-validation.json --evidence-dir /tmp/koschei-validation-evidence`

Tests committed in open PR work are NOT described as passed until a real validation/test execution receipt exists.

### SPEC STATE

Settled: `ka/vor/shi/thal/nur`, Khar, Aevra/Veyra, Matrix/Hara, Sathra, controlled knowability, rotating/non-faithful observer representation, capability-first authority, bounded survival/autonomy and observable != canonical law.

### COMPILER STATE

Functional compiler/interpreter/tooling exists; semantic-authority migration remains incomplete.

### RUNTIME STATE

Exact-request reconstruction + opaque materialization exists as open-PR Python bootstrap. Native/durable custody is not yet solved.

### SECURITY MODEL

`explicit authority + canonical identity + witnessed reality + bounded lifecycle + controlled knowability + exact request-bound execution`

### EXPERIMENTAL

Hardware isolation, durable global replay state, complete observer-safe tooling, physical failure-root independence and some external build/finality integrations.

### TESTED

No fresh `ks-local-validate --profile full` receipt is claimed for the current #263 branch.

### NEXT

**Unify Nyr observation liveness and reconstruction/materialization liveness under one Continuity epoch authority.**
