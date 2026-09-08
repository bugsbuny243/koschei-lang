# KOSCHEI MIR AST FALLBACK INVENTORY V4

Status: compiler/runtime migration checkpoint
Branch: `feature/mir-or-return-normalization-v1`
Scope: Koschei Lang only

## Constitutional rule

A fact normalized into Verified MIR must not be re-derived from AST/source as a
second semantic authority. `MirAstFallback` is a migration boundary, not an
execution permission. The public checked runtime fails closed if such a boundary
reaches `MirExecutorV1`.

## Current explicit MIR coverage

The v4 path explicitly normalizes:

- literals, identifiers, unary and ordinary binary expressions;
- short-circuit `&&` / `||` as CFG;
- Lists when Typed HIR proves `List<T>`;
- member lookup and calls;
- identifier assignment;
- interpolated strings;
- `or return`;
- `or else` with failure-only fallback evaluation;
- a proven safe subset of `or { ... }` value handlers;
- Map/Struct literals with staged fail-fast construction;
- let / expression / return statements;
- ordinary if / while / List-for structural CFG;
- break / continue.

The phrase “structural CFG” does not claim complete statement-result convergence:
error-valued branch conditions remain a known semantic debt described below.

## Recently closed or reduced fallback boundaries

### `OrElseExpression` — normalized

`evaluate fallible once -> success test -> success payload / failure fallback -> join`

No eager fallback evaluation and no `MirAstFallback` are required.

### `OrBlockExpression` — partially normalized

The following handler forms now lower without AST fallback:

- empty block -> canonical `MirUnit`;
- expression-statement sequence -> final expression value;
- tail `let` -> canonical `MirUnit`;
- direct unconditional `return` -> function `MirReturn` with unreachable tail
  source not lowered.

Typed HIR now includes the handler's already-checked normal-exit value type in the
`OrBlockExpression` result type. It does not re-infer handler expressions.

Control-flow handlers (`if`, `while`, `for`) remain one whole
`MirAstFallback` boundary. They are not partially lowered before fallback.

## P0 semantic debt — branch/loop error-valued statement results

Current source semantics and generic MIR branch execution are not yet equivalent
when a condition evaluates to `KsError`.

Source `IfStatement` returns that error as the statement result; its enclosing
block may continue to later statements. Current `MirExecutorV1` treats a
`KsError` encountered at `MirBranch` as a function-level return. That is too
strong and cannot be used as canonical statement semantics.

This affects the confidence level of existing structural CFG for:

- ordinary `if`;
- `while`;
- short-circuit expressions when a branch predicate can itself become a runtime
  error value;
- future expression-valued control-flow blocks.

Target law:

**RUNTIME ERROR VALUE != FUNCTION RETURN**

Lowering must encode an explicit error-value continuation appropriate to the
source construct. Runtime must not infer it from Python object shape.

## Remaining concrete expression fallback boundaries

### P0 — control-flow `OrBlockExpression`

Prerequisite: resolve branch/loop statement-result error routing, then extend the
value-block lowering specified in `KOSCHEI_MIR_BLOCK_VALUE_SEMANTICS_V1.md`.

### P0 — `MatchExpression`

Variant selection, payload extraction, arm-local identity and exhaustiveness must
come from compiler-resolved canonical facts. `KOSCHEI_MIR_MATCH_SEMANTICS_V1.md`
defines the target. Proposed `MirVariantIs` / `MirVariantPayload` facts remain
unimplemented.

### P1 — `ListLiteral` without normalized `List<T>` type

Typed fact missing -> fail closed. MIR must not guess an item type.

### P1 — assignment target other than `Identifier`

Unsupported target shape must gain a canonical semantic rule or be rejected
before executable MIR. Host object shape is not assignment authority.

### P2 — non-List `ForStatement`

Current source runtime only supports List iteration. Invalid checked semantics
should eventually fail before MIR rather than leave an executable migration node.

### P2 — future unknown AST nodes

New AST constructs do not inherit execution support. They require explicit MIR
semantics or compiler rejection.

## Security classification

### PROTECTS AGAINST

- hiding where source-shaped migration boundaries remain;
- claiming full MIR convergence from structural CFG alone;
- partially lowering an OrBlock control-flow handler and then falling back;
- treating canonical Unit as a Python compiler object;
- prioritizing effect/control-flow-sensitive gaps before cosmetic work.

### DOES NOT PROTECT AGAINST

- Python TCB compromise;
- bugs in normalized instructions;
- forged/tampered MIR without sealing/registry checks;
- the known branch-error semantic debt itself;
- source/AST leakage elsewhere in the bootstrap compiler.

### ASSUMPTIONS

- Typed HIR is the checked type authority;
- `MirExecutorV1` rejects `MirAstFallback`;
- public checked execution passes MIR sealing and exact v4 registry validation;
- compiler-known privileged operation identity remains authoritative.

### FAILURE MODE

- a backend begins executing `MirAstFallback`;
- a runtime error value is upgraded into function return without source semantics;
- new syntax is treated as executable by Python-class resemblance;
- runtime reconstructs missing authority/type/variant facts from AST or host values.

## Next implementation order

1. pin and fix `MirBranch` error-valued statement semantics;
2. extend safe value-block CFG to `if`, then loops only after their result law is proven;
3. finish `OrBlockExpression` fallback removal;
4. expose compiler-resolved Match variant/exhaustiveness facts;
5. implement Match explicit CFG;
6. convert invalid List/for/assignment migration cases to compiler fail-closed;
7. integrate exact v4 registry membership into sealing/fingerprint validation;
8. only then consider removing generic `MirAstFallback` production entirely.

No new syntax is required.
