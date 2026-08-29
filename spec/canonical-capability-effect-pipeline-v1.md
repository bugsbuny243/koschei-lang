# Canonical Capability / Effect Pipeline V1

Status: **compiler consolidation applied on the checked module-graph path / compatibility cleanup remains / validation receipt pending**

## Purpose

Koschei must not decide authority or effect identity twice at different compiler layers.

Before this slice the checked module graph already produced a Typed-HIR-aware `EffectReport`, but MIR independently called the older AST-oriented `effects.infer_effects(...)` and recomputed capability effects again. Even though both paths referenced canonical capability names, two independent computations after semantic checking created two possible semantic truths.

The sanctioned compiler path is now:

```text
source / AST
-> Typed HIR
-> typestate
-> affine ownership
-> check_effect_contracts(...)
   -> capability_effect_contract_v1
   -> checked EffectReport
-> legacy compatibility semantic check
-> MIR lowering consumes the exact checked EffectReport
-> sealed MIR capability-effect projection
-> backend
```

MIR no longer re-infers its capability effects from source AST on this path.

## One canonical capability contract

`capability_effect_contract_v1.py` remains the single canonical owner of:

- capability type set;
- root narrowing relationships;
- narrowed operations;
- capability method -> canonical effect identity;
- canonical capability effect set;
- power-domain classification used by deny-only request admission.

Typed type contracts now import `CAPABILITY_TYPES` directly from this canonical module instead of routing capability sensitivity through the legacy `semantic.py` compatibility surface.

Affine ownership remains structural: `AffineResourceChecker` asks `TypeContractValidator.is_sensitive(...)`, and that validator now ultimately classifies direct capability types from the canonical contract.

Effect inference already uses `effect_for(...)` from the canonical contract.

## Checked EffectReport becomes the MIR source

`modules.check_graph(...)` computes one `EffectReport` per module after Typed HIR, typestate and affine checks.

Imported module effect reports are propagated in dependency order before the local report is finalized.

After every module succeeds, `check_graph(...)` passes both:

- `typed_reports`
- `effect_reports`

to MIR lowering.

`mir.lower_graph(...)` now requires an effect report for every module and `mir.lower_module(...)` requires an effect report for every function. Missing report coverage fails closed with `MirIntegrityError` rather than falling back to another inference engine.

## MIR v3 compatibility projection

The full `EffectReport` contains more than MIR v3 historically exposed, including facts such as:

- authority-bearing input/output;
- console/shared-memory/concurrency effects;
- unknown call classifications;
- imported-call metadata.

MIR v3's public `MirFunction.effects` field historically represents canonical capability effects. V1 preserves that ABI by projecting the already-checked report onto `CANONICAL_CAPABILITY_EFFECTS`.

This is a projection of one checked semantic result, not a second inference pass.

Examples:

```text
checked effects: authority.input + net.io
MIR capability effects: net.io
```

```text
checked effects: console.write
MIR capability effects: <empty>
```

The broader effect model can become a first-class MIR contract in a future versioned MIR change. It must not be silently smuggled into MIR v3 with changed meaning.

## Imported-effect preservation

Because MIR now consumes the module graph's checked reports, canonical capability effects that arrive transitively through imported calls can be preserved in the caller MIR.

This closes a blind spot in the old AST-local MIR inference path, which did not own the module graph's already-resolved imported-effect truth.

## Integrity behavior

`MirGraph.assert_sealed()` no longer calls `effects.infer_effects(...)`.

Instead it:

1. validates MIR block structure;
2. validates deterministic resource metadata;
3. rejects any MIR capability effect outside `CANONICAL_CAPABILITY_EFFECTS`;
4. verifies the graph fingerprint, which already seals function call/effect metadata together with the checked source/type graph.

Changing sealed MIR effect metadata without updating the graph seal therefore remains detectable.

The structural seal is not a secret-key authenticity mechanism and does not make a malicious compiler trustworthy.

## Legacy `effects.py`

This slice removes the old AST effect inferencer from the sanctioned MIR lowering path. The source file may remain temporarily for compatibility or tests until repository-wide consumers are proven absent and deletion is safe.

Do not treat its continued file presence as a second approved semantic authority.

A regression test patches `koschei.effects.infer_effects` to raise if called; checked MIR construction must still succeed.

## PROTECTS AGAINST

- MIR independently disagreeing with the compiler's already-checked capability/effect report because of a second AST inference algorithm;
- imported capability effects being lost merely because MIR performs only module-local AST inference;
- Typed type sensitivity relying on a legacy capability-type alias instead of the canonical capability contract;
- MIR silently accepting arbitrary non-canonical capability effect labels;
- missing module/function effect reports falling back to permissive inference during sanctioned lowering.

## DOES NOT PROTECT AGAINST

- a malicious compiler or TCB that forges the original `EffectReport`;
- a bug shared by all consumers of `capability_effect_contract_v1`;
- lower-level/private Python APIs that construct MIR outside the sanctioned checked module-graph path;
- host/process compromise, debugger inspection, memory scraping, crash dumps or side channels;
- semantic gaps in the legacy compatibility checker that run after effect checking;
- unnormalized AST fallback instructions still present inside MIR;
- native/backend code that ignores sealed MIR effect metadata.

## ASSUMPTIONS

- `check_typed_hir(...)` produces trustworthy structural expression types;
- `TypeContractValidator` structural sensitivity is correct;
- `check_effect_contracts(...)` is the sole checked function-effect computation for the sanctioned compiler path;
- imported effect reports are resolved in dependency order;
- backends consume only sealed MIR obtained from `require_mir(...)`;
- `capability_effect_contract_v1` remains the canonical capability/effect source.

## FAILURE MODE

The consolidation fails if another compiler/backend path recomputes capability effects independently and is allowed to override the checked report, if MIR lowering accepts missing reports and guesses, or if legacy compatibility aliases regain semantic authority instead of remaining consumers/adapters.

## TESTED STATUS

Regression tests are committed for:

- existing direct and local-transitive capability effects;
- sealed MIR tamper detection;
- MIR construction succeeding while legacy `koschei.effects.infer_effects` is forced to raise;
- an imported `net.io` capability effect propagating into caller MIR through the checked `EffectReport`.

These tests are **written and committed, not claimed passed**. Current GitHub head has no status-check or workflow-run evidence, and no fresh `ks-local-validate --profile full` receipt has been produced in this connector-only session.

## NEXT

1. inspect remaining legacy `semantic.py` capability aliases and make them compatibility consumers only;
2. bind compiler-produced capability basis to `CanonicalEffectRequest` / `RequestCapabilityDomainConstraintV1` instead of constructing that relationship only in Python bootstrap integration code;
3. normalize MIR further and reduce executable AST fallback;
4. prove interpreter/native backends consume the same sealed capability/effect identity;
5. run canonical and adversarial validation before PR #263 leaves draft.
