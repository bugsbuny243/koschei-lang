# KOSCHEI MIR BLOCK VALUE SEMANTICS V1

Status: semantic prerequisite / non-executable specification
Branch: `feature/mir-or-return-normalization-v1`
Scope: Koschei Lang only

## Why this exists

`OrBlockExpression` cannot be normalized correctly by simply sending its handler
through the existing statement-only `_lower_block()` path.

The legacy source runtime gives a `Block` a value: absent an early return, the
block evaluates to the result of its last executed statement. The current MIR
statement lowerer intentionally discards ordinary statement result values. Using
that lowerer unchanged for an expression-valued handler would therefore create a
second, incorrect semantic authority.

## Canonical law

**STATEMENT CONTROL FLOW != BLOCK VALUE**

A block used as an expression must carry one explicit canonical result fact in
MIR. Runtime/backends must not reconstruct that value from AST, Python object
shape, or “last instruction” heuristics.

## Required semantics

For a block used in value position:

1. statements execute in source order;
2. skipped control-flow paths do not execute;
3. an explicit `return` remains a function terminator and never becomes a block
   result;
4. when control reaches the end normally, the block result is the result of the
   last executed statement;
5. an empty block yields canonical Unit;
6. a `let` statement yields Unit as its statement result;
7. an expression statement yields its expression value;
8. `if` yields the selected branch block result, or Unit when no branch body is
   selected;
9. loop statement result semantics must match the already-checked source law;
10. a runtime error value propagates exactly as source semantics define; MIR must
    not invent a broader Result/Option rule.

## Proposed lowering shape

Do not add a magical `MirExecuteBlock` instruction.

Preferred shape:

`entry -> explicit statement CFG -> per-normal-exit result binding -> join -> load`

A compiler-only internal mutable binding may carry the block result across
exclusive CFG exits, as already used for short-circuit and `or else`, provided:

- every normal exit writes exactly one result;
- early function return never writes the block result;
- no unexecuted branch writes a value;
- the join reads only after a normal-exit write;
- validator-visible SSA use/def rules remain canonical.

## OrBlockExpression consequence

Only after block-value lowering exists may `OrBlockExpression` become:

`evaluate fallible once`
`-> MirFallibleIsSuccess`
`-> success: extract payload`
`-> failure: lower handler as value-block`
`-> bind exclusive result`
`-> join/load`

Handler scope must be lexical and isolated. Handler effects execute only on the
failure path.

## Security properties

### PROTECTS AGAINST

- silently discarding an expression-valued handler result;
- re-running handler AST inside sealed MIR;
- eager execution of failure-handler effects;
- backend-specific guesses about which statement produced a block value.

### DOES NOT PROTECT AGAINST

- bugs in the source semantic definition itself;
- Python TCB compromise;
- incorrect loop-result semantics if those are not separately normalized;
- forged MIR without sealing/registry validation.

### ASSUMPTIONS

- Typed HIR owns expression type facts;
- function `return` semantics remain distinct from block normal-exit semantics;
- public checked execution rejects AST fallback;
- MIR v4 registry remains fail-closed for unknown instructions.

### FAILURE MODE

- a normal CFG exit reaches the block-value join without writing a result;
- a skipped branch writes the result binding;
- an early return is converted into a block value;
- runtime derives block value from AST or host-language control flow.

## Implementation order

1. define/test value-producing lowering for expression statements and empty/let
   tails;
2. extend to `if` normal exits;
3. pin loop statement-result semantics before treating loop tails as values;
4. implement a `_lower_value_block()` helper that returns one MIR SSA value;
5. normalize `OrBlockExpression` using that helper;
6. adversarially test skipped effects, early return, lexical scope and nested
   fallible control flow.

No new source syntax is required.
