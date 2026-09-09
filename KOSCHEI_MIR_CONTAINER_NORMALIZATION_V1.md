# Koschei MIR Container Normalization V1

Status: experimental implementation contract for PR #273. Koschei Lang only.

## Problem

The public checked runtime now executes sealed MIR and rejects `MirAstFallback`. `MapLiteral` and `StructLiteral` therefore need normalized MIR semantics before they can execute on the canonical runtime path. This work must not create a second capability authority or permit capabilities to be laundered through ordinary containers.

## Canonical rules

### Map construction

A normalized map instruction binds an ordered tuple of `(key SSA, value SSA)` pairs. Keys and values are evaluated exactly once in source order. Construction fails closed if any key or value contains a capability. Duplicate-key behavior must remain identical to the existing Koschei runtime contract; normalization may not silently invent a different rule.

### Struct construction

A normalized struct instruction binds the declared canonical struct identity and an ordered tuple of `(field name, value SSA)` pairs. Each field expression is evaluated exactly once in source order. The declared field set/type contract remains compiler authority. Runtime construction must reject capability-bearing field values unless the existing semantic layer explicitly defines an authority-bearing struct contract; ordinary structs are not capability envelopes.

## Security invariants

1. Container construction does not mint, widen, clone, serialize, or hide `vor` authority.
2. A capability nested at any depth is rejected by the same canonical capability-containment predicate used for List values.
3. Runtime does not infer a stronger type or authority from Python `dict`/object shape.
4. Struct type identity comes from checked MIR/compiler metadata, not observer-provided runtime strings.
5. Evaluation order and single-evaluation behavior are preserved.
6. Unsupported or ambiguous container semantics fail closed; there is no AST execution fallback.

## PROTECTS AGAINST

- laundering a capability through a Map or ordinary Struct;
- runtime shape-based authority inference;
- AST fallback becoming a second execution authority;
- duplicate evaluation of effectful field/key/value expressions during lowering.

## DOES NOT PROTECT AGAINST

- a compromised compiler/runtime/TCB;
- a bug in the shared capability-containment predicate;
- malicious authority-bearing container types explicitly admitted by a future canonical semantic contract;
- memory/debugger/host-language compromise.

## ASSUMPTIONS

- typed HIR has already validated map key/value and struct field contracts;
- MIR SSA identity and ordering are trustworthy;
- `contains_capability` is fail-closed for nested runtime values;
- sealed MIR fingerprint validation occurs before execution.

## FAILURE MODE

Reject with a runtime/compiler error when capability containment is detected, struct identity/field contract is inconsistent, or the executor encounters an unsupported container representation. Never fall back to source AST.

## Implementation order

1. inspect and preserve existing duplicate-key and struct-construction semantics;
2. add canonical MIR instructions to `mir_ir.py` so they participate in fingerprint/use-def validation;
3. lower `MapLiteral` and `StructLiteral` without `MirAstFallback`;
4. execute them in `MirExecutorV1` through narrow runtime-value construction helpers only;
5. add adversarial capability-laundering, single-evaluation, field identity, and AST-fallback-count tests;
6. only then continue to `or else`, `or { ... }`, and `match` normalization.
