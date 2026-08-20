# Koschei Core Dependency Map v0

Status: **verified architecture inventory, non-destructive**.

This map follows the current public compiler path and recursively classifies dependencies that can affect source acceptance, typing/effects/resources, module composition, MIR meaning, or reference execution. It is a map before any directory move.

## Public checked-program path

```text
.ks source
  -> lexer.py
  -> parser.py
       -> _parser_v09.py
       -> generic_nodes.py
       -> ast_nodes.py
  -> modules.py / check_graph()
       -> integrity.py
       -> typed_hir.py
            -> _typed_expr.py
                 -> _typed_ops.py
            -> type_contracts.py
            -> type_system.py
       -> effect_contracts_v1.py
       -> affine_resources_v1.py
       -> typestate_resources_v1.py
       -> legacy_generics.py
            -> legacy_types.py
       -> semantic.py
  -> mir.py
       -> mir_ir.py
       -> effects.py
       -> typed/type contracts above
  -> interpreter.py
```

The native/Go path is downstream from sealed MIR and is intentionally not language-authoritative.

## Newly discovered recursive core dependencies

### `koschei/_typed_expr.py`

`typed_hir.py` imports `infer_expression` lazily from `_typed_expr.py`; `_typed_expr.py` determines the structural type of literals, calls, members, collections, `match`, `or` forms and other expressions. Changing this module can therefore change whether a program type-checks and what type is sealed into MIR. It is language authority, not an implementation helper.

### `koschei/legacy_types.py`

`legacy_generics.py` directly imports `erase_function`, `erase_imports` and `erase_program` from `legacy_types.py`. This bridge controls how V5 structural generic types are projected into the still-active v0.9 semantic pass. While that pass remains in the checked-program pipeline, changing this erasure can change semantic acceptance/rejection. It is therefore temporarily language-authoritative until the legacy semantic compatibility path is removed.

## Verified direct dependency classes

### Syntax layer

- `lexer.py` -> `ast_nodes.py` only indirectly through parser consumers; the lexer owns tokens.
- `_parser_v09.py` -> `ast_nodes.py`, `lexer.py`.
- `parser.py` -> `_parser_v09.py`, `ast_nodes.py`, `generic_nodes.py`, `lexer.py`.
- `generic_nodes.py` -> `ast_nodes.py`.

### Typed/semantic layer

- `type_system.py` -> `ast_nodes.py`.
- `type_contracts.py` -> `ast_nodes.py`, `semantic.py`, `type_system.py`.
- `_typed_ops.py` -> `ast_nodes.py`, `semantic.py`, `type_contracts.py`, `type_system.py`.
- `_typed_expr.py` -> `_typed_ops.py`, `ast_nodes.py`, `type_system.py`, with a lazy `type_contracts.py` dependency for function typing.
- `typed_hir.py` -> `_typed_ops.py`, `_typed_expr.py` (lazy), `ast_nodes.py`, `semantic.py`, `type_contracts.py`, `type_system.py`.
- `legacy_types.py` -> `ast_nodes.py`, `semantic.py`, `type_system.py`.
- `legacy_generics.py` -> `ast_nodes.py`, `generic_nodes.py`, `legacy_types.py`, `semantic.py`, `type_contracts.py`, `type_system.py`.
- `effect_contracts_v1.py` -> `ast_nodes.py`, `semantic.py`, `type_contracts.py`, `type_system.py`, `typed_hir.py`.
- `affine_resources_v1.py` -> `ast_nodes.py`, `semantic.py`, `type_contracts.py`, `type_system.py`, `typed_hir.py`.
- `typestate_resources_v1.py` -> `ast_nodes.py`, `semantic.py`, `type_contracts.py`, `type_system.py`, `typed_hir.py`.
- `integrity.py` -> `ast_nodes.py`, `semantic.py`.

### Graph/MIR layer

- `modules.py` orchestrates parser + integrity + Typed HIR + effect contracts + affine resources + typestate + legacy compatibility + semantic analysis, then lowers the checked graph into MIR.
- `effects.py` derives fail-closed direct/call-propagated effects from source declarations and capability-bearing calls.
- `mir_ir.py` owns normalized MIR control-flow/instruction lowering and imports source AST/type information only to lower it.
- `mir.py` seals typed modules, effects, control-flow/resource contracts and the deterministic fingerprint.

### Reference execution

- `interpreter.py` is the reference execution semantics for the accepted language and still consumes AST declaration payloads carried by sealed MIR.

## Support dependency that is deliberately not promoted

`mir.py` imports `diagnostics.py` only to register/render the `KS5002` MIR-integrity diagnostic. The diagnostic catalog does not decide program semantics or MIR structure. It remains tooling/support authority unless future code begins consulting diagnostic data to accept/reject programs.

## Important architecture debt now visible

1. **Typed HIR is split across three semantic files:** `typed_hir.py`, `_typed_expr.py`, `_typed_ops.py`. The underscore names make two language-authoritative modules look private/auxiliary even though they define typing behavior.
2. **The legacy bridge is two files deep:** `legacy_generics.py` -> `legacy_types.py` -> old semantic checker. This is temporary migration architecture and needs an explicit deletion condition.
3. **The reference runtime still carries AST payloads inside MIR.** `mir.py` explicitly describes this as an incremental migration. Until MIR fully owns executable semantics, AST/parser-era structures remain coupled to runtime behavior.
4. **`semantic.py` still contains capability rules while newer structural passes sit beside it.** This is a dual-authority risk: future language work can accidentally implement a rule in only one layer.
5. **Backend adapters must stay downstream.** Go/native generators may implement sealed meaning but must never become the place where a Koschei rule exists only because a backend happens to enforce it.

## Core count after recursive correction

The previous 20-module spine omitted two active recursive semantic dependencies. The current verified language-authoritative spine is therefore **22 modules**:

```text
lexer.py
ast_nodes.py
generic_nodes.py
_parser_v09.py
parser.py
semantic.py
type_system.py
type_contracts.py
_typed_ops.py
_typed_expr.py
typed_hir.py
integrity.py
legacy_types.py
legacy_generics.py
effects.py
effect_contracts_v1.py
affine_resources_v1.py
typestate_resources_v1.py
modules.py
mir_ir.py
mir.py
interpreter.py
```

## Next safe refactor target

Do **not** move these files yet. First establish a compatibility-preserving namespace plan and tests around the public imports. The first cleanup should be conceptual, not physical:

- mark the 22 modules as `LANGUAGE_AUTHORITY` in architecture documentation;
- mark `_parser_v09.py`, `legacy_types.py`, and `legacy_generics.py` as migration debt with removal criteria;
- define one owner for each language rule (grammar, types, effects, ownership, typestate, MIR semantics);
- only after that, move modules in small batches with import shims and full test parity.

This keeps repository cleanup from silently changing the language while making the actual Koschei compiler visible again.