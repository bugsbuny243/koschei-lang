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
- `or else` as explicit success/failure CFG with failure-only fallback evaluation;
- Map literals with fail-fast staged construction;
- Struct literals with fail-fast staged construction;
- let / expression / return statements;
- if / while;
- List-backed for loops;
- break / continue.

## Recently closed fallback boundary

### `OrElseExpression` — normalized

Current shape:

`evaluate fallible once -> success test -> success payload / failure fallback -> join`

Both exclusive branches define the same compiler-internal result binding and the
join reads that binding. No eager fallback evaluation and no `MirAstFallback`
are required for this construct.

Validation tests are committed but no PASS claim is made until tests actually run.

## Remaining concrete expression fallback boundaries

### P0 — `OrBlockExpression`

Why it matters:

- the handler is a full Block, not a single value;
- handler effects must occur only on failure;
- block-local bindings and early return semantics must remain exact;
- source semantics gives the handler block a value, while the current MIR
  statement lowerer discards ordinary statement results;
- naive `_lower_block()` reuse would therefore silently change semantics.

Prerequisite is now specified in:

`KOSCHEI_MIR_BLOCK_VALUE_SEMANTICS_V1.md`

Required normalization shape after that prerequisite is implemented:

`evaluate fallible once -> success test -> success payload / failure value-block CFG -> join`

The failure handler must use canonical value-producing block lowering. No AST
handler execution or “last MIR instruction” guessing is permitted.

### P0 — `MatchExpression`

Why it matters:

- variant selection is control flow;
- payload extraction is conditional;
- arm-local binding identity must be canonical;
- only the selected arm may evaluate;
- capability-bearing values must not gain authority from Python object shape or
  runtime-selected dispatch.

Canonical semantics are now specified in:

`KOSCHEI_MIR_MATCH_SEMANTICS_V1.md`

The proposed normalized facts are `MirVariantIs` and `MirVariantPayload`, but
these are NOT implemented yet. They must bind compiler-resolved canonical variant
identity and remain representation facts, not runtime authority.

Do not add Match-specific runtime authority before compiler-resolved variant
identity and exhaustiveness facts are available.

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

1. implement canonical value-producing block lowering from
   `KOSCHEI_MIR_BLOCK_VALUE_SEMANTICS_V1.md`;
2. normalize `OrBlockExpression` on top of that primitive;
3. expose compiler-resolved canonical variant identity/exhaustiveness facts;
4. implement Match only after those facts satisfy
   `KOSCHEI_MIR_MATCH_SEMANTICS_V1.md`;
5. convert invalid List/non-List-for/non-Identifier-assignment fallback cases to
   compiler fail-closed where they are semantically invalid;
6. integrate exact v4 registry membership into sealing/fingerprint validation so
   public runtime is not the only complete-registry consumer;
7. only then consider removing generic `MirAstFallback` production entirely.

No new syntax is required for this work.
