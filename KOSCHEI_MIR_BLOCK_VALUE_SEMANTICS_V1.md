# KOSCHEI MIR BLOCK VALUE SEMANTICS V1

Status: semantic prerequisite / partial implementation
Branch: `feature/mir-or-return-normalization-v1`
Scope: Koschei Lang only

## Canonical law

**STATEMENT CONTROL FLOW != BLOCK VALUE**

A block used as an expression must carry one explicit canonical result fact in
MIR. Runtime/backends must not reconstruct that value from AST, Python object
shape, or “last instruction” heuristics.

A second permanent law now follows from source/runtime comparison:

**RUNTIME ERROR VALUE != FUNCTION RETURN**

A `KsError` produced while evaluating a statement condition is a statement
result under current source semantics. It must not be silently upgraded into a
function return merely because the executor sees an error-shaped host value.

## Required semantics

For a block used in value position:

1. statements execute in source order;
2. skipped control-flow paths do not execute;
3. explicit `return` remains a function terminator and never becomes a block result;
4. normal block exit yields the result of the last executed statement;
5. empty block yields canonical Unit;
6. `let` yields Unit;
7. expression statement yields its expression value;
8. `if` yields selected branch result, or Unit if no body is selected;
9. loop statement result semantics must match source law;
10. runtime error values propagate exactly as source semantics define.

## Implemented statement-context progress

Ordinary statement-context `if` and `while` now lower condition errors explicitly:

`condition -> MirIsRuntimeError -> error continuation / ordinary Bool decision`

For statement context, the error continuation reaches the enclosing statement
join/loop exit instead of returning from the function. Generic executor branch
handling remains fail-closed if an unnormalized `KsError` predicate reaches it.

Short-circuit `&&` / `||` similarly uses an explicit `MirIsRuntimeError` gate so
an error-valued left operand becomes the expression result and the RHS remains
skipped.

This does **not** yet make value-position `if`/loop blocks complete. Value-mode
control flow must preserve the selected statement result, including an error
value, in an explicit result binding before those constructs can be admitted to
`OrBlockExpression` lowering.

## Current OrBlock subset

Normalized without AST fallback:

- empty handler -> `MirUnit`;
- expression-statement sequence -> final expression result;
- tail `let` -> `MirUnit`;
- direct unconditional handler `return` -> function `MirReturn`.

Handlers containing `if`, `while`, `for` or another unproven value-mode control
flow construct remain one whole `OrBlockExpression` migration boundary. Partial
lowering followed by AST fallback is forbidden.

## Security properties

### PROTECTS AGAINST

- silently discarding an expression-valued handler result;
- converting condition errors into implicit function returns;
- re-running normalized handler AST inside sealed MIR;
- eager execution of skipped control-flow effects;
- backend guesses about block-result identity.

### DOES NOT PROTECT AGAINST

- unresolved value-position `if`/loop result semantics;
- unresolved `for` iterable-error result continuity;
- Python TCB compromise;
- forged MIR without sealing/registry validation.

### ASSUMPTIONS

- Typed HIR owns checked expression type facts;
- function return semantics remain distinct from statement/block normal-exit semantics;
- public checked execution rejects AST fallback;
- MIR v4 registry remains fail-closed for unknown instructions.

### FAILURE MODE

- a normal value-block exit reaches its join without defining a result;
- skipped branch effects execute;
- condition Error becomes function return;
- runtime reconstructs continuation from host object shape.

## Next implementation order

1. define value-position `if` result binding with explicit error-result path;
2. extend the same law to loop statement-result/value semantics;
3. normalize `for` iterable Error continuation;
4. admit proven control-flow handlers into `_lower_value_block()`;
5. remove remaining `OrBlockExpression` fallback;
6. adversarially test nested fallible/effectful paths.

No new source syntax is required.
