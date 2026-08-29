# KOSCHEI LANG — SOURCE OF TRUTH — 2026-08-29

Status: **canonical consolidation checkpoint / no new language invention**

This document exists to stop architectural drift. It consolidates the already-designed Koschei language, Universe, representation model, runtime direction, active PR deltas and next integration order. It does not replace detailed specs such as `KOSCHEI_SIGIL_LEXICON_V1.md`, `KOSCHEI_GALAXY_CONSTITUTION_V1.md`, `KOSCHEI_CORE_MANIFEST_V0.md`, or `KOSCHEI_LANGUAGE_OWNERSHIP_V0.md`; it defines how they fit together.

## 1. Non-negotiable identity

Koschei Lang is not a renamed Rust/Python/C/Go/JavaScript syntax.

Its originality must live in:

- semantic admission and identity;
- capability/authority physics;
- evidence and witnessed reality;
- containment/recovery/lifecycle;
- controlled knowability and representation separation;
- execution admission;
- time/epoch-scoped validity;
- verified build/payload lineage where required.

A future implementation that turns Koschei into familiar constructs with renamed keywords violates the architecture even if the syntax looks novel.

## 2. Canonical native semantic roots

The native semantic roots are already designed and are not to be re-invented:

- `ka` — admitted existence / genesis. Recognition does not create privilege.
- `vor` — bounded power. Authority must be explicit, narrow, scoped and non-escalating.
- `shi` — witnessed reality. Claim is not proof; evidence must carry lineage.
- `thal` — bounded survival. Containment, recovery and rebirth must not manufacture privilege.
- `nur` — controlled knowability. Visibility, aliases and representations must remain separate from authority and canonical identity.

These are semantic roots, not decorative keywords. The compact visible source may expand into a larger verified semantic plan.

## 3. Primary law: observable world != canonical world

Koschei has two intentionally different realities.

### Canonical world

Contains the real semantic relations required for trusted execution:

- canonical identity;
- semantic root meaning;
- authority/capability relationships;
- evidence lineage;
- lifecycle state;
- Universe/Veyra/Aevra identity;
- execution request identity;
- verified IR / MIR identity;
- current epoch and continuity state.

### Observable world

May contain only the representation required by an observer/runtime role:

- rotating aliases;
- epoch/session/customer-specific mappings;
- opaque handles;
- non-faithful Nyr surfaces;
- bounded diagnostics;
- visibility-limited state.

The observable representation must not become a stable one-to-one map of the canonical world.

This is not a claim that canonical state can never leak. A compromised trusted process, debugger, crash dump, side channel, leaked key or bypass path can still expose canonical state. The architecture requires that ordinary sanctioned runtime/observer surfaces do not expose it as the default execution representation.

## 4. Native Universe model

### Khar

Khar is the canonical constitutional law set. It is not a secret super-user or master credential. No debug/recovery/emergency path may silently weaken Khar.

### Aevra / Veyra

- Aevra = canonical program/entity identity greater than visible bytes.
- Veyra = customer-specific living Galaxy geometry in which Aevra relationships become valid.

`copy(bytes) != birth(Aevra)` is a design law.

### Matrix / Hara

- Matrix = controlled local execution reality inside one Veyra.
- Hara = one Aevra's scoped horizon inside that Matrix.

Sharing a Matrix does not imply sharing Hara, authority, knowledge or critical reach.

### Six Khar axes / 6-of-6 concurrence

Critical execution currently uses six independent constitutional axes:

- `khor` — locus/isolation;
- `sei` — intent/control direction;
- `rha` — executable reality;
- `vaal` — effect force;
- `teyr` — temporal epoch;
- `esh` — continuity/living identity.

For a critical Sathra event, partial concurrence is zero: `1/6` through `5/6` are not critical success.

### Sathra

Sathra is a one-event concurrence, not stored reusable super-authority.

### Vormir

Vormir is irreversible cost for higher-power transitions. Old and new critical reach must not coexist for free.

### Morth / Event Horizon / Black Hole

Morth is a path with no valid future. Event Horizon is the irreversible crossing. Black Hole is the terminal sink for dead identity/authority/stale lineage.

### Survival branch selection

Survival/alternate-future selection is deterministic Khar-bound physics, not an AI sovereign. Unsafe futures are rejected before ranking.

### Bounded autonomy

Automation may propose/rank within explicit bounds. It cannot rewrite Khar, create authority, synthesize missing axes or bypass finality.

## 5. Metaphor map — technical meaning only

These names are architectural thinking tools, not decoration:

- **Matrix** -> local controlled execution reality / observable-vs-canonical separation context.
- **Neo** -> exceptional authorized transition/materialization actor; never universal super-user.
- **Agent Smith** -> adversarial spread, persistence, correlation and representation-learning threat model.
- **Doctor Strange** -> deterministic safe-future / survival branch selection across bounded alternatives.
- **Skynet** -> runtime continuity/epoch/lifecycle coordination concept; not autonomous sovereignty.
- **Avengers / Infinity Stones** -> independent power dimensions/failure roots that must not collapse into one master authority.
- **Deus Ex Machina** -> constitutional conservation/finality root concept; not a hidden bypass credential.

If a metaphor has no enforceable technical job, do not add it to the architecture.

## 6. Current compiler spine on main

The current authoritative compilation path remains:

`source -> lexer -> parser -> AST -> integrity -> Typed HIR -> typestate -> affine ownership -> effect contracts -> legacy compatibility bridge -> legacy semantic checker -> sealed MIR -> reference interpreter`

The language core is real and usable, but carries migration debt:

- `_parser_v09.py` is still active compatibility debt;
- legacy semantic checking still overlaps newer Typed HIR authority;
- capability semantics are split across several modules;
- effect semantics have related but separate source/MIR computations;
- MIR still has AST fallback for incomplete normalization.

The safe consolidation target is fewer semantic authorities, not merely fewer files.

## 7. Intended canonical compiler/runtime architecture

The target architecture remains:

`Source Layer`
`-> Semantic Layer`
`-> Verified Intermediate Representation`
`-> Security / Capability Layer`
`-> Transformation / Representation Layer`
`-> Execution Representation`
`-> Runtime`

For native Koschei semantic roots, the more specific execution path is:

`ka/vor/shi/thal/nur source intent`
`-> canonical semantic checking`
`-> Native/Verified MIR`
`-> Library obligations`
`-> Universe/Khar composition`
`-> authority/evidence/lifecycle checks`
`-> canonical semantic seal`
`-> Nur/Nyr observer projection`
`-> exact authorized materialization`
`-> request-bound execution`
`-> execution evidence/finality`

## 8. Current main vs active PR reality

Main remains the integration baseline. The strongest new work is still distributed across open PRs and must not be described as merged production reality.

### PR #260 — Six real-world power domains

Purpose: Identity / Authority / Data / Compute / Network / Continuity isolation and explicit cross-domain permits.

Status: useful constitutional prototype, but not yet the single active execution path. It should be integrated only where it closes a Khar/authority gap rather than remain a parallel authority system.

### PR #263 — canonical/observable representation + opaque materialization

Purpose: enforce `observable world != canonical world` at the sanctioned reconstruction/execution boundary.

Current direction:

`sealed canonical MIR`
`-> non-faithful Nyr representation`
`-> reconstruction grant`
`-> trusted epoch`
`-> single-use reconstruction consumption`
`-> opaque materialization handle`
`-> exact CanonicalEffectRequest + RequestBoundProof`
`-> native ALLOW / DENY / CONTAIN`

This is the current **primary core integration PR** because it directly advances the central language/runtime law.

Known gap: reconstruction-grant issuance itself is still purpose-scoped and should become exact-request-bound.

### PR #264 — Nyr v2 liveness/replay hardening

Purpose: a correctly generated observer surface is still invalid after its live visibility epoch. Trusted epoch acquisition fails closed.

This belongs directly under the `nur` representation boundary and should be integrated with #263 rather than evolve as an independent subsystem.

### PR #265 — external evidence / build provenance / attestation / finality

Purpose: prove external/provider evidence, verifier build identity, trust generations, rollback witnesses and finality provenance without letting external facts become native authority.

Valuable Lang-core concepts inside it include:

- Verified IR build identity;
- toolchain/build provenance;
- payload/execution lineage;
- trust-anchor generation semantics;
- provider-neutral attestation/witness contracts.

However provider-specific/finality plumbing is not the language's central semantic identity. **Freeze feature growth here** until the core language/runtime execution pipeline is integrated. Later extract only the parts required by Lang's verified execution contract; keep external adapters non-authoritative.

## 9. One execution pipeline — the required end state

Koschei must converge to one answer to "how does a program execute?":

`Developer Source Intent`
`-> ka/vor/shi/thal/nur semantic roots`
`-> canonical identity + authority + evidence + lifecycle world`
`-> verified MIR / execution contract`
`-> Khar / power-domain admission`
`-> canonical semantic seal`
`-> rotating observer-safe Nyr representation`
`-> exact-request reconstruction capability`
`-> opaque materialization handle`
`-> trusted compartment resolution`
`-> exact request-bound effect admission`
`-> ALLOW / DENY / CONTAIN`
`-> execution evidence`
`-> payload/finality proof where required`

No second parallel authority system, second semantic truth, or backend-specific reinterpretation may bypass this chain.

## 10. Immediate integration order

From this checkpoint, "continue" means the following order unless a verified blocker forces a change:

1. **Finish PR #263 core semantics.** Bind reconstruction grant issuance itself to the exact `CanonicalEffectRequest`. Remove remaining sanctioned raw-MIR returns.
2. **Absorb PR #264 into the same Nur/representation lifecycle.** One trusted Continuity epoch authority must drive both observation liveness and reconstruction/materialization liveness.
3. **Connect existing Khar/Galaxy/Matrix/Hara and relevant power-domain rules to the same exact request-bound execution gate.** Do not invent a parallel execution gate.
4. **Consolidate capability authority.** One canonical capability contract must feed Typed HIR, affine ownership, effects, MIR and runtime.
5. **Finish MIR normalization.** Reduce/remove semantic AST fallback so all sanctioned execution consumes the same complete checked contract.
6. **Only then re-open #265 growth.** Extract Verified IR / provenance / attestation primitives required for `Source Intent -> Verified IR -> Artifact -> Payload -> Execution`; keep provider-specific adapters outside the semantic core.
7. **Durable/native custody.** Move reconstruction/materialization replay state and raw canonical MIR into a native/isolated runtime boundary; Python privacy is not a final security boundary.
8. **Observer-safe tooling.** Debugger/introspection/runtime diagnostics must classify whether they are trusted-canonical or observer-safe; no accidental faithful fallback.
9. **Canonical validation.** Run the full repository validator and adversarial suites before marking core PRs ready/merged.

## 11. Stop rules

Until the above integration is complete:

- no new programming-language syntax family unless it closes a documented semantic gap;
- no second parser/type/effect/capability authority;
- no new security-themed module merely because a new attack can be named;
- no new provider-specific feature inside Lang core;
- no claim that Python private fields provide isolation;
- no claim that rotating representation makes source "impossible to see";
- no claim that `mergeable=true` means tests passed;
- no merge of the core representation work without canonical validation evidence;
- no metaphor without an enforceable technical responsibility.

## 12. Security honesty

### PROTECTS AGAINST — intended / partially enforced today

- ambient authority through explicit capability semantics;
- stable canonical identity being identical to ordinary observer aliases;
- some stale Nyr representation replay;
- some cross-request/cross-context materialization substitution;
- some repeated in-process reconstruction/materialization use;
- evidence being treated as authority merely because it is external;
- selected build/provenance relabeling and trust-generation rollback in prototype paths.

### DOES NOT PROTECT AGAINST

- full compromise of a trusted process that holds raw canonical state;
- memory scraping, side channels, debugger/crash dump leaks;
- malicious compiler/runtime inside the trusted computing base;
- leaked keys/capabilities;
- process/VM rollback where state is not anchored independently;
- native/backend bypasses not yet routed through the canonical gates;
- inference from every possible observation channel;
- real hardware/physical independence unless external evidence proves it.

### ASSUMPTIONS

- canonical semantic checks fail closed;
- Khar cannot be silently substituted;
- capability/effect semantics converge to one contract;
- epoch/Continuity truth is authoritative and monotonic for the relevant security domain;
- canonical MIR is physically isolated in production, not merely conventionally private;
- external witnesses/attestation roots are independently protected where relied upon.

### FAILURE MODE

Koschei fails architecturally if the repository accumulates impressive security utilities while the language has multiple competing semantic/execution truths. The primary failure to avoid is **architecture fragmentation**.

## 13. Validation state at this checkpoint

Do not claim the open integration work is tested merely because tests were written or GitHub reports a PR mergeable.

Required canonical command remains:

`ks-local-validate --profile full --output /tmp/koschei-local-validation.json --evidence-dir /tmp/koschei-validation-evidence`

A successful receipt is required before describing the integrated open-PR state as validated.

## 14. Checkpoint

### SPEC STATE

Settled: native sigils `ka/vor/shi/thal/nur`; Khar/Galaxy/Aevra/Veyra; Matrix/Hara; six-axis concurrence; controlled knowability; non-faithful observer representation; capability-first authority; bounded survival/autonomy; observable != canonical law.

### COMPILER STATE

Functional language compiler/interpreter/tooling exists on main, but semantic authority migration remains incomplete. Typed HIR and legacy semantic authority still overlap; MIR normalization is incomplete.

### RUNTIME STATE

Reference interpreter and extensive security/runtime prototypes exist. The new representation/materialization path is still open-PR work and Python custody is not physical isolation.

### SECURITY MODEL

The strongest coherent identity is: **explicit authority + canonical identity + witnessed reality + bounded lifecycle + controlled knowability + request-bound execution**.

### EXPERIMENTAL

External attestation/witness providers, hardware isolation, durable global replay state, physical failure-root independence, complete observer-safe tooling and some build/finality integrations.

### TESTED

Main has an established test/validation system. This consolidation does not claim a fresh full-validation receipt for the current open-PR combination.

### NEXT

One active goal: **finish and validate the exact-request, trusted-epoch, opaque-materialization execution path, then integrate Nyr liveness and Khar/power-domain admission into that same path.**
