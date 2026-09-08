# KOSCHEI MIR BLOCK VALUE SEMANTICS V1

Status: active semantic migration checkpoint
Branch: `feature/mir-or-return-normalization-v1`
Scope: Koschei Lang only

## Why this exists

`OrBlockExpression` cannot be normalized correctly by simply sending its handler
through the statement-only `_lower_block()` path.

The source runtime gives a `Block` a value: absent an early function return, the
block evaluates to the result of its last executed statement. Ordinary MIR
statement lowering intentionally discards statement result values. Reusing it
unchanged in value position would therefore create a second semantic authority.

## Canonical laws

**STATEMENT CONTROL FLOW != BLOCK VALUE**

**RUNTIME ERROR VALUE != FUNCTION RETURN**

A block used as an expression must carry one explicit canonical result fact in
MIR. Runtime/backends must not reconstruct that value from AST, Python object
shape, or “last instruction” heuristics.

A `KsError` observed while evaluating a statement condition is still a language
value under the current source runtime law. It must not be silently upgraded into
a function return merely because the backend uses a branch terminator.

## Required source semantics

For a block used in value position:

1. statements execute in source order;
2. skipped control-flow paths do not execute;
3. explicit `return` remains a function terminator and never becomes a block result;
4. normal block exit yields the last executed statement result;
5. an empty block yields canonical Unit;
6. `let` yields Unit as its statement result;
7. an expression statement yields its expression value;
8. `if` yields the selected branch block result, or Unit when no branch is selected;
9. loop statement result semantics must match the existing source runtime exactly;
10. runtime error values propagate as statement/block values according to source
    control flow and must not be reinterpreted as implicit function returns.

## Implemented safe subset

The current MIR migration implements a deliberately narrow value-block subset for
`OrBlockExpression`:

- empty handler -> `MirUnit`;
- expression-statement sequences -> the final expression SSA value;
- tail `let` -> `MirUnit`;
- direct unconditional `return` -> ordinary `MirReturn`; unreachable tail source
  statements are not lowered.

`MirUnit` is a representation-only MIR fact. The compiler does not embed the
Python runtime `KsUnit` object into sealed IR; the executor materializes canonical
Koschei Unit from the instruction.

Typed HIR now computes `OrBlockExpression` result type from both:

`success_type(fallible)`

and the handler's already-checked normal-exit value type. The projection reads
existing Typed-HIR expression facts and does not re-infer expressions as a second
type authority. An unconditional handler return has no normal block value and
therefore does not pollute the OrBlock expression type.

## Deliberately unsupported control-flow handlers

An `OrBlockExpression` whose handler contains `if`, `while`, `for`, or another
unproven control-flow statement remains one `MirAstFallback` migration boundary.
The compiler does not partially lower the handler before falling back.

Reason: the current MIR executor handles `MirBranch` with a `KsError` condition by
returning that error from the function. The source interpreter instead makes the
error the statement result; an enclosing block may then continue to later
statements. Until branch/loop statement-result error routing is normalized, using
those CFG constructs in expression-valued handlers would silently change language
semantics.

## Target branch-error normalization

A future canonical CFG must distinguish:

- branch predicate success -> normal true/false control flow;
- predicate runtime error -> statement result/error-value path;
- explicit source `return` -> function terminator.

Do not solve this by making `MirBranch` inspect Python object shape and guess the
source construct. The lowering must encode the correct error-value continuation
explicitly from canonical semantics.

## Security properties

### PROTECTS AGAINST

- discarding an expression-valued handler result;
- embedding a host-language Unit sentinel into compiler IR;
- re-running handler AST inside sealed MIR for the implemented subset;
- eager failure-handler effects;
- treating a runtime error value as an implicit function return in newly
  normalized value-block control flow;
- backend-specific guesses about which statement produced the block value.

### DOES NOT PROTECT AGAINST

- the still-known generic `MirBranch`/`KsError` divergence outside the safe subset;
- bugs in source semantics;
- Python TCB compromise;
- forged MIR without sealing/registry validation;
- unnormalized Match semantics.

### ASSUMPTIONS

- Typed HIR remains the type-fact authority;
- function return and block normal exit remain distinct;
- public checked execution rejects `MirAstFallback`;
- exact MIR v4 registry membership is checked before public execution.

### FAILURE MODE

- a normal join is reached without a defined result value;
- a skipped branch writes a value;
- an early function return is converted into a block value;
- a control-flow handler is partially lowered and then falls back;
- runtime derives block value/error continuation from AST or host object shape.

## Next implementation order

1. pin source-vs-MIR semantics for error-valued `if`/loop conditions;
2. introduce explicit statement-result/error continuation in CFG lowering;
3. only then extend value-block support to `if` normal exits;
4. pin loop result semantics before value-position loops;
5. expand `OrBlockExpression` normalization over the proven control-flow subset;
6. adversarially test skipped effects, early return, lexical scope and nested
   fallible control flow.

No new source syntax is required.
