# KOSCHEI MIR AST FALLBACK INVENTORY V4

Status: compiler/runtime migration checkpoint
Branch: `feature/mir-or-return-normalization-v1`
Scope: Koschei Lang only

## Constitutional rule

A fact that is already normalized into Verified MIR must not be re-derived from
AST/source as a second semantic authority. `MirAstFallback` is therefore a
migration boundary, not an execution permission. The public checked runtime
fails closed if such a boundary reaches `MirExecutorV1`.

## Current explicit MIR coverage

The current v4 lowering explicitly normalizes:

- literals and identifiers;
- unary and ordinary binary expressions;
- short-circuit `&&` / `||` as CFG;
- Lists when their typed result is `List<T>`;
- member lookup and calls;
- identifier assignment;
- interpolated strings;
- `or return`;
- Map literals with fail-fast staged construction;
- Struct literals with fail-fast staged construction;
- let / expression / return statements;
- if / while;
- List-backed for loops;
- break / continue.

## Remaining concrete expression fallback boundaries

### P0 — `OrElseExpression`

Why it matters:

- it is fallible control flow;
- fallback evaluation must occur only on the failure path;
- eager lowering could execute effects that source semantics would skip;
- it must reuse the same fallible-success law as `or return` without creating a
  second Result/Option authority.

Required normalization shape:

`evaluate fallible once -> success test -> success payload / failure fallback -> join`

### P0 — `OrBlockExpression`

Why it matters:

- the handler is a full Block, not a single value;
- handler effects must occur only on failure;
- block-local bindings and early return semantics must remain exact;
- naive AST reuse would reopen source execution authority inside sealed MIR.

Required normalization shape:

`evaluate fallible once -> success test -> success payload / failure CFG block -> join`

The failure block must be lowered with normal MIR lexical-scope and terminator
rules. No AST handler execution is permitted.

### P0 — `MatchExpression`

Why it matters:

- variant selection is control flow;
- payload extraction is conditional;
- arm-local binding identity must be canonical;
- only the selected arm may evaluate;
- capability-bearing values must not gain authority from Python object shape or
  runtime-selected dispatch.

Required work before implementation:

1. define canonical enum/Option/Result variant-test MIR fact;
2. define payload extraction with proof that the selected variant matches;
3. define exhaustive/non-exhaustive failure semantics from the checked compiler
   report rather than runtime guessing;
4. lower each arm to explicit CFG;
5. preserve arm-local lexical binding identity.

Do not add Match-specific runtime authority before these semantics are fixed.

## Conditional / edge fallback boundaries

### P1 — `ListLiteral` without normalized `List<T>` type

The base lowerer emits a fallback if Typed HIR does not expose a single
`List<T>` item type. This should normally be rejected or normalized earlier.
The MIR layer must not guess an element type.

Target law: **typed fact missing -> fail closed**, not AST fallback execution.

### P1 — assignment target other than `Identifier`

Current explicit lowering supports assignment only when the checked target is an
Identifier. Any other assignment shape reaches expression fallback.

Target law: unsupported assignment targets must either gain a dedicated
canonical semantic rule or be rejected before executable MIR. Runtime object
shape must not decide assignment authority.

### P2 — non-List `ForStatement`

The current statement lowerer emits `MirAstFallback` when the iterable type is
not normalized as `List<T>`. Since current source runtime only supports List
iteration, this is primarily a compiler convergence issue.

Target law: if checked semantics says the loop is invalid, MIR lowering should
fail closed rather than preserve an executable AST migration node.

### P2 — future unknown AST node classes

The generic fallback branches remain a forward-compatibility migration guard.
Adding a new AST node must not silently grant execution support. New constructs
require explicit MIR semantics or compiler rejection.

## Security classification

### PROTECTS AGAINST

- identifying where sealed MIR can still contain source-shaped migration facts;
- accidental assumption that all syntax already has canonical executable MIR;
- prioritizing control-flow/effect-sensitive fallback removal before cosmetic
  normalization work.

### DOES NOT PROTECT AGAINST

- compromise of the Python TCB;
- bugs in already-normalized MIR instructions;
- forged/tampered MIR by itself; sealing and the v4 instruction registry remain
  separate required checks;
- leakage of source or AST held elsewhere in the bootstrap compiler process.

### ASSUMPTIONS

- Typed HIR remains the checked source of type facts;
- `MirExecutorV1` continues to reject `MirAstFallback`;
- public checked execution continues to pass MIR sealing and the exact v4
  instruction registry gate before execution;
- compiler-known privileged operation identity remains authoritative.

### FAILURE MODE

- a future backend starts executing `MirAstFallback`;
- a new AST construct is treated as executable because its Python object shape
  resembles an existing construct;
- fallible/match lowering evaluates a skipped branch eagerly;
- runtime reconstructs missing type/variant/authority facts from AST or Python
  values rather than failing closed.

## Next implementation order

1. normalize `OrElseExpression` using the existing fallible-success primitives;
2. normalize `OrBlockExpression` with explicit failure-handler CFG;
3. specify Match variant-test/payload semantics before adding instructions;
4. convert invalid List/non-List-for/non-Identifier-assignment fallback cases to
   compiler fail-closed where they are semantically invalid;
5. only then consider removing generic `MirAstFallback` production entirely.

No new syntax is required for this work.
