# KOSCHEI MIR MATCH AUTHORITY CHECKPOINT V1

Status: compiler semantic prerequisite
Scope: Koschei Lang only

`MatchExpression` may move out of `MirAstFallback` only after the compiler exposes
canonical match facts that the runtime does not have to reconstruct from source
or host object shape.

## Closed in this checkpoint

`koschei.match_semantics_v1` projects, from already-checked Typed HIR and the
compiler declaration universe:

- checked scrutinee type;
- semantic enum identity;
- ordered canonical arm identities (`Enum::Variant` in bootstrap v1);
- checked payload-binding type;
- compiler-side exhaustiveness fact.

Unknown arm identities make `exhaustive=False`; they are never promoted from
visible text into authority. Duplicate visible variant names across different
enums remain separated by the checked scrutinee enum identity.

## Still P0

1. make these match facts part of the canonical MIR lowering input;
2. add exact-registry `MirVariantIs` and `MirVariantPayload` instructions;
3. validate SSA use and same-variant predecessor proof;
4. lower ordered arms to explicit CFG with one result binding;
5. add fail-closed executor support and adversarial wrong-variant tests;
6. only then remove `MatchExpression` from AST fallback inventory.

Bootstrap `Enum::Variant` strings are sealed compiler facts, not a claim that
display names are the permanent cross-module identity format.
