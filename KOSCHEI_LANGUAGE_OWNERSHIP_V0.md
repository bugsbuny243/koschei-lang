# Koschei Language Ownership Map v0

Status: **architecture inventory, non-destructive**.

This document answers one question: for each user-visible Koschei language feature, which module currently owns its syntax, static meaning, checked representation, and execution meaning?

The goal is to prevent a feature from being governed by multiple hidden authorities without an explicit migration plan.

**Native-execution boundary:** `KOSCHEI_NATIVE_EXECUTION_BOUNDARY_V1.md` is mandatory for every backend/runtime change. Host implementations (including Go/Python/container tooling) are bootstrap or conformance machinery only and may not become Koschei semantic authority.

## Canonical pipeline today

`source -> lexer -> parser -> AST -> integrity -> Typed HIR -> typestate -> affine ownership -> effect contracts -> legacy generic bridge -> legacy semantic checker -> sealed MIR -> reference interpreter`

`koschei/modules.py::check_graph` is the current orchestration authority for that order. It invalidates stale MIR, runs the new V5 checks first, then prepares a legacy compatibility view, runs the legacy semantic checker, and only after all checks succeed lowers the original graph into sealed MIR.

That pipeline means Koschei currently has **one compilation path but more than one semantic authority**.

## Ownership matrix

| Feature | Syntax / surface owner | Structural/type owner | Static semantic owner | MIR/execution owner | Current risk |
|---|---|---|---|---|---|
| Lexical vocabulary | `lexer.py` | token stream | `lexer.py` | n/a | low |
| Base expressions/statements | `_parser_v09.py` + `ast_nodes.py` | `ast_nodes.py` | `semantic.py` + Typed HIR for typed expressions | `mir_ir.py` with AST fallback + `interpreter.py` | **dual authority** |
| `fn` declarations | `_parser_v09.py` / `parser.py` | `ast_nodes.py` / `generic_nodes.py` | `semantic.py`, `typed_hir.py`, `type_contracts.py` | `mir.py`, `mir_ir.py`, `interpreter.py` | **dual authority** |
| Generic functions/structs/enums | `parser.py` | `generic_nodes.py` | `type_system.py`, `type_contracts.py`, `typed_hir.py` | original generic AST remains in MIR/runtime | medium; compatibility bridge remains |
| `List` / `Map` typed operations | parser inherited surface | `type_system.py` | `_typed_expr.py`, `_typed_ops.py`, `type_contracts.py`; legacy semantic sees erased compatibility view | interpreter/runtime | **split semantic implementation** |
| `Option` / `Result` | inherited parser + AST | `type_system.py` | Typed HIR/type contracts plus legacy semantic compatibility | MIR/interpreter | **dual authority** |
| `or return` / `or {}` / fallback `or` | `parser.py` + inherited parser precedence | AST nodes | `_typed_expr.py`, `typed_hir.py`, legacy semantic | MIR lowering / interpreter | **dual authority** |
| `if` / `while` / `for` control flow | `_parser_v09.py` | `ast_nodes.py` | `integrity.py`, `typed_hir.py`, legacy semantic | `mir_ir.py`; AST fallback where lowering incomplete | **multiple validators** |
| `match` / enum exhaustiveness | parser + AST | generic/base enum nodes + type system | Typed HIR + legacy semantic | sealed MIR contract; host adapters are parity-only | **dual authority being consolidated** |
| Modules/imports | parser import declaration | `modules.py` graph | `modules.py` + imported semantic/type/effect propagation | MIR module graph | medium |
| Capability types and narrowing | source types/method calls | `semantic.py` constants + `type_system.py` representation | `semantic.py`, `_typed_ops.py`, affine checker, effect contracts | MIR effects + interpreter capability operations | **highest dual-authority risk** |
| `pure fn` | `parser.py` (`PURE`) | declaration flag | `effect_contracts_v1.py`; legacy semantic still validates surrounding calls/types | MIR effect seal | medium |
| `stateful struct` | `parser.py` | `generic_nodes.py` | `typestate_resources_v1.py` + Typed HIR/type contracts | generic AST/MIR/interpreter | medium |
| `transition fn` | contextual syntax in `parser.py` | `generic_nodes.py` | `typestate_resources_v1.py` + affine ownership | MIR/interpreter | medium |
| Affine/move-only authority values | no new mandatory token surface | structural types | `affine_resources_v1.py` | runtime assumes checked program | medium |
| Effect inference | no direct syntax except `pure` promise | typed AST / MIR metadata | `effects.py` + `effect_contracts_v1.py` | `mir.py` seals inferred effects | **two related effect engines** |
| Entrypoint `main` | ordinary function syntax | function declaration | `modules.py::require_entrypoint` | CLI/native execution surface | low |

## Confirmed dual-authority hotspots

### 1. Typed HIR vs legacy semantic checker

`check_graph` first runs `check_typed_hir`, typestate, affine ownership and effect contracts. It then calls `prepare_legacy_analysis(...)` and finally `semantic_check(...)` on a compatibility-transformed program.

This means accepted-program semantics are currently the intersection of two systems:

1. the V5 structural type/resource/effect checks;
2. the v0.9 semantic checker operating on an erased/specialized compatibility view.

That arrangement is useful during migration, but it must be temporary. A language rule that exists in only one side can become invisible to the other side.

### 2. Generic semantics are authoritative before being erased

`legacy_types.py` intentionally erases or preserves selected V5 type structure so the old checker can continue to operate. The old checker must therefore be treated as a compatibility verifier, **not** as the canonical owner of generic meaning.

Canonical direction:

`structural TypeNode + Typed HIR -> compatibility projection -> legacy checker`

Never the reverse.

### 3. Capability semantics are split across several modules

Today capability meaning is distributed among:

- `semantic.py`: capability names, root/narrowed methods, ambient-authority rejection and legacy call rules;
- `_typed_ops.py`: typed method results for root/capability operations;
- `affine_resources_v1.py`: ownership transfer and post-move invalidity for authority-bearing values;
- `effect_contracts_v1.py`: source-level effect promises;
- `effects.py`: MIR effect summary/inference;
- interpreter/runtime: actual side effects.

This is the most important consolidation target. The system is secure only if all those layers agree on one capability contract.

### 4. Effect inference has two engines with different jobs

`effect_contracts_v1.py` enforces source promises such as `pure fn` and propagates imported/local call effects during checking.

`effects.py` independently derives fail-closed effect summaries that are sealed into MIR and revalidated by `MirGraph.assert_sealed()`.

That duplication can be useful as defense in depth, but only if their relationship is explicit: source checker = acceptance authority, MIR inference = independent post-check seal/consistency proof. They must not silently define different effect taxonomies.

### 5. MIR is not yet the complete execution semantics

`mir_ir.py` explicitly has `MirAstFallback` for constructs that are not fully normalized. `mir.py` still stores original declarations/program AST alongside typed information.

Therefore the current target is not "delete AST after parsing." The safe migration is:

`AST -> complete typed HIR -> normalized MIR -> no semantic AST fallback in execution`

Only after parity tests prove that boundary should AST fallback be removed.

## Canonical owner decisions from this point forward

These are architectural rules for future changes:

1. **Grammar ownership:** `lexer.py` + current `parser.py`; `_parser_v09.py` is compatibility debt, not a permanent second grammar authority.
2. **Structural type ownership:** `type_system.py` + `type_contracts.py`.
3. **Expression typing ownership:** `typed_hir.py` + `_typed_expr.py` + `_typed_ops.py` until those helpers are folded into a visible typed-semantics package.
4. **Capability semantic ownership:** must converge into one explicit capability contract consumed by Typed HIR, affine/effect checking, MIR and runtime.
5. **Generic meaning:** V5 structural types are canonical; `legacy_generics.py` / `legacy_types.py` are one-way compatibility bridges only.
6. **Effect promise ownership:** `effect_contracts_v1.py`; MIR effect inference is a consistency seal, not an alternate source language definition.
7. **Ownership/resource semantics:** `affine_resources_v1.py` and `typestate_resources_v1.py` are compiler-semantic passes and remain language core until their rules are represented in a unified typed semantic IR.
8. **Executable contract:** sealed MIR is the backend boundary. Native backends and adapters may not reinterpret source semantics. Host backends are conformance adapters only; `KOSCHEI_NATIVE_EXECUTION_BOUNDARY_V1.md` defines this boundary.
9. **Reference execution:** `interpreter.py` remains the semantic oracle only for behavior not yet fully normalized into MIR; the end-state is execution directly from complete Koschei MIR semantics.
10. **Native terminology:** architecture/production claims use "Koschei-native" only for execution whose meaning is owned by the sealed Koschei execution contract; implementation in a host language does not make a path Koschei-native.

## Consolidation order

Do not move hundreds of files yet. Consolidate authority in this order:

### Phase A — freeze feature ownership

- Add a test/fixture category per row in this ownership matrix.
- Every new language feature must declare syntax owner, static owner, MIR meaning and runtime meaning.
- No new `library_*` or platform module may become a language authority accidentally.

### Phase B — remove the legacy semantic bridge from generic authority

- Move any still-missing scope/immutability/error/capability rule from `semantic.py` into the structural Typed HIR path.
- Make `legacy_generics.py` and `legacy_types.py` parity-only.
- Prove acceptance/rejection parity before removing them from `check_graph`.

### Phase C — unify capability contracts

Create one canonical capability description that defines:

- root capabilities;
- narrowing operations;
- permitted operations;
- effect names;
- affine/borrow behavior;
- runtime authority mapping.

All compiler passes derive from that contract instead of maintaining parallel hard-coded tables.

### Phase D — unify effects

Keep two computations if desired for independent verification, but define one stable effect taxonomy and add a mandatory equality/consistency gate before MIR sealing.

### Phase E — finish MIR normalization

Reduce `MirAstFallback` feature by feature until every executable source construct has a normalized MIR meaning. Then interpreter/native backends consume the same complete contract.

### Phase F — directory reorganization

Only after A-E are evidenced by tests should files be moved into `lang/core`, `lang/runtime`, `security`, `library`, `tooling`, `adapters`, and `legacy`.

## Immediate stop rules

Until consolidation is complete:

- do not add a second parser facade;
- do not add another generic/type system;
- do not add a third effect inference table;
- do not add capability methods in only one checker;
- do not let a backend accept AST/source that bypasses `check_graph` + sealed MIR;
- do not allow a host backend to resolve or manufacture a compiler-owned Koschei fact;
- do not call a Go/Python/container implementation Koschei-native merely because it executes or packages sealed data;
- do not delete legacy bridges until parity evidence exists;
- do not count platform/security modules as evidence that the language itself became more expressive.

## What this reveals

The repository is not "293 modules of language." It is a functioning language core surrounded by a rapidly growing security/platform system **and** a partially completed compiler migration.

The biggest architectural debt is not module count. It is that some language facts are still represented twice: once in the newer structural pipeline and once in the legacy checker/AST execution path.

The next cleanup work should therefore reduce **semantic authorities**, not merely reduce file count.