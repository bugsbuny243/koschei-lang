# KOSCHEI LANG — SOURCE OF TRUTH — 2026-08-29

Status: **canonical consolidation checkpoint / exact-request reconstruction + shared Continuity liveness applied / no new language invention**

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

This is not a claim that canonical state can never leak. Trusted-process compromise, keys, debugger/crash dumps, side channels or bypass paths remain real threats.

## 3. Existing Universe vocabulary remains canonical

- **Khar** — constitutional laws; never a hidden super-user.
- **Aevra** — canonical entity identity greater than visible bytes.
- **Veyra** — customer-specific living Galaxy geometry.
- **Matrix** — controlled local execution reality.
- **Hara** — one Aevra's scoped horizon inside Matrix.
- **Sathra** — exact 6/6 critical event concurrence; not reusable authority.
- **Vormir** — irreversible cost for higher-power transition.
- **Morth / Event Horizon / Black Hole** — terminal identity/authority/lifecycle semantics.
- **Doctor Strange** — deterministic Khar-safe survival branch selection.
- **Skynet** — Continuity/epoch/lifecycle coordination, never sovereign policy.
- **Avengers / Infinity Stones** — independent power/failure dimensions, not one master authority.
- **Neo** — exceptional authorized transition/materialization role, not universal bypass.
- **Agent Smith** — spread/persistence/correlation/representation-learning adversary.
- **Deus Ex Machina** — conservation/finality concept, not override credential.

Metaphors without an enforceable technical responsibility are rejected.

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
-> Khar / Universe composition
-> authority + evidence + lifecycle admission
-> canonical semantic seal
-> Nur/Nyr observer projection
-> exact-request reconstruction capability
-> shared Continuity liveness
-> single-use reconstruction
-> opaque materialization handle
-> trusted compartment resolution
-> exact request-bound effect admission
-> ALLOW / DENY / CONTAIN
-> execution evidence / finality where required
```

No backend, adapter, observer or recovery path may create a second semantic truth around this chain.

## 6. PR #263 — PRIMARY CORE INTEGRATION PATH

Current branch semantics:

```text
sealed NativeSigilMir
-> non-faithful Nyr v2 representation
-> sealed CanonicalEffectRequest
-> exact-request ReconstructionGrantV1
-> shared ContinuityEpochAuthorityV1
-> atomic reconstruction consumption
-> ReconstructionConsumptionReceiptV1
-> opaque CanonicalMaterializationHandleV1
-> same shared ContinuityEpochAuthorityV1
-> exact CanonicalEffectRequest + RequestBoundProof
-> ALLOW / DENY / CONTAIN
```

### Exact-request reconstruction — APPLIED

- grant issuance requires exact sealed `CanonicalEffectRequest`;
- raw request digest is absent from grant;
- opaque grant request binding is scoped to request + Veyra + observer + session + epoch;
- request-A grant cannot reconstruct request-B;
- request binding survives authenticated consumption provenance;
- materialization handle independently remains exact-request bound;
- sanctioned reconstruction returns no raw MIR.

### Shared Continuity liveness — APPLIED

PR #264 liveness semantics are now absorbed into #263 rather than becoming another lifecycle authority.

Added:

- `ContinuityEpochAuthorityV1` — one typed fail-closed runtime epoch interface;
- `require_live_nyr_surface_v2` — integrity + operational liveness;
- `NyrObservationGateV1` — observer-safe render only after shared Continuity liveness;
- `RepresentationReconstructionGateV1` now requires `continuity`, not raw `epoch_source`;
- `CanonicalMaterializationEffectGateV1` now requires the same Continuity contract;
- regression proving one backing epoch advance invalidates old Nyr observation, old reconstruction and held materialization handle together;
- regression proving one failed Continuity reader fails all three boundaries closed;
- signature regression proving sanctioned gates expose `continuity` and no raw `epoch_source`.

Important non-claim: the Python Continuity identity seal does not prove reader honesty, monotonic hardware time or rollback resistance. Shared truth eliminates internal clock drift; it does not manufacture trustworthy time.

## 7. PR #264 — SEMANTICS ABSORBED, NO NEW FEATURE GROWTH

Its Nyr replay/liveness rules now live in #263 under the shared Continuity model. Do not evolve #264 as a parallel epoch authority. Keep it open until explicit PR cleanup/closure is requested.

## 8. PR #260 — constitutional/power-domain prototype

Identity / Authority / Data / Compute / Network / Continuity isolation remains valuable. It must enter the single exact request-bound Khar execution path only where it closes a constitutional authority gap. It must not become a second authority model.

## 9. PR #265 — FEATURE GROWTH FROZEN

Retain Lang-core value from Verified IR identity, toolchain/build provenance, payload lineage, trust-anchor generation and provider-neutral witness/attestation contracts. Provider/finality-specific growth remains frozen until core execution converges.

External adapters remain non-authoritative.

## 10. Immediate integration order

From this checkpoint, `Devam` means:

1. **CURRENT NEXT:** connect existing Khar/Galaxy/Matrix/Hara and only the relevant power-domain admission to the exact request-bound #263 execution gate, without creating parallel authority.
2. consolidate one canonical capability contract across Typed HIR, affine ownership, effects, MIR and runtime;
3. finish MIR normalization/reduce semantic AST fallback;
4. then extract only relevant Verified IR/provenance primitives from #265;
5. move canonical MIR/replay/materialization custody into durable/native isolation;
6. classify debugger/introspection/runtime output as trusted-canonical or observer-safe;
7. run canonical/adversarial validation before ready/merge.

## 11. Stop rules

- no new syntax family unless closing a documented semantic gap;
- no second parser/type/effect/capability authority;
- no new security module merely because an attack can be named;
- no provider-specific Lang-core growth;
- no claim that Python privacy is physical isolation;
- no claim rotating representation makes source impossible to see;
- no claim shared Continuity is rollback-resistant time;
- no claim `mergeable=true` means tests passed;
- no core merge without canonical validation evidence;
- no metaphor without technical responsibility.

## 12. Security honesty

### PROTECTS AGAINST — current sanctioned direction

- ambient authority through explicit capability semantics;
- faithful canonical naming map on the Nyr observer path;
- stale Nyr replay through sanctioned observation;
- separate arbitrary epoch callbacks drifting across observer/reconstruction/materialization;
- grant widening from one canonical request to another;
- raw canonical request digest exposure in grant/handle;
- repeated/concurrent reconstruction in one process-local ledger;
- repeated materialization use in one process-local registry;
- external evidence becoming authority merely because it is external.

### DOES NOT PROTECT AGAINST

- compromised/rolled-back underlying Continuity state;
- full trusted-process memory compromise;
- debugger/crash dump/side-channel leakage;
- malicious compiler/runtime inside TCB;
- leaked trust-role keys;
- restart/VM rollback where state is not independently monotonic;
- native/backend paths bypassing sanctioned gates;
- physical independence without external evidence.

### FAILURE MODE

The architecture fails if it becomes disconnected security utilities. One compiler/runtime/execution truth is mandatory.

## 13. Validation checkpoint

Canonical command:

`ks-local-validate --profile full --output /tmp/koschei-local-validation.json --evidence-dir /tmp/koschei-validation-evidence`

Tests committed in the open PR are **not** described as passed until actual execution evidence exists.

### SPEC STATE

Settled: `ka/vor/shi/thal/nur`, Khar, Aevra/Veyra, Matrix/Hara, Sathra, controlled knowability, non-faithful rotating observer representation, capability-first authority, bounded survival/autonomy, exact-request reconstruction and shared Continuity liveness contract.

### COMPILER STATE

Functional compiler/interpreter/tooling exists; semantic-authority migration remains incomplete.

### RUNTIME STATE

Open-PR Python bootstrap now has exact-request reconstruction, live-Nyr observation, shared Continuity liveness and opaque materialization. Native/durable custody and monotonic Continuity remain unsolved.

### SECURITY MODEL

`explicit authority + canonical identity + witnessed reality + bounded lifecycle + controlled knowability + one Continuity truth + exact request-bound execution`

### EXPERIMENTAL

Hardware/native isolation, rollback-resistant Continuity, durable global replay state, complete observer-safe tooling, physical failure-root independence and external build/finality integration.

### TESTED

No fresh `ks-local-validate --profile full` receipt is claimed for current #263 HEAD.

### NEXT

**Bind existing Khar/Galaxy/Matrix/Hara constitutional admission into the same exact request-bound execution path, without parallel authority.**
