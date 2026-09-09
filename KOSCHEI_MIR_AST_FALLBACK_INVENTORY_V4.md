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
- short-circuit `&&` / `||` with explicit Error routing;
- Lists when Typed HIR proves `List<T>`;
- member lookup and calls;
- identifier assignment;
- interpolated strings;
- `or return`;
- `or else` with failure-only fallback evaluation;
- Map/Struct literals with staged fail-fast construction;
- let / expression / return statements;
- statement-context `if` / `while` condition Error continuation;
- a value-producing `or { ... }` subset including value-position `if` / nested
  `else if` with explicit Error-result path;
- break / continue on the already-normalized loop path.

## Recently closed or reduced fallback boundaries

### `OrElseExpression` — normalized

`evaluate fallible once -> success test -> success payload / failure fallback -> join`

No eager fallback evaluation and no `MirAstFallback` are required.

### `OrBlockExpression` — value-if normalized

The following handler forms lower without AST fallback:

- empty block -> canonical `MirUnit`;
- expression/let sequence -> final normal value / Unit;
- direct unconditional `return` -> function `MirReturn`;
- tail `if` / nested `else if` when all participating blocks stay inside the
  currently proven value-block subset;
- Error-valued `if` condition -> explicit handler result, not function return.

Typed HIR and MIR now share one canonical normal-exit block type projection from
already-checked HIR expression facts. MIR does not re-run type inference.

## Remaining P0 semantic debt

### P0 — loop statement value continuity

Source `while` / `for` statements have a result. Zero iterations yield Unit;
executed iterations expose the last body value; an Error-valued body result
terminates the loop statement while the enclosing block may continue.

Current statement-only loop lowering still needs explicit body-result binding.
Therefore value-position `while` / `for` inside `or { ... }` remain one whole
migration boundary.

Permanent law:

**LOOP CONTROL FLOW != LOOP STATEMENT VALUE**

The shared `checked_block_normal_type(...)` projection is now available for this
next step; MIR must consume that checked fact rather than inventing a second type
projection.

### P0 — `for` iterable Error continuation

If the checked type system admits an Error-valued iterable path, it must be routed
explicitly before iterator construction. Runtime object shape must not decide
whether the value is iterable or an Error continuation.

### P0 — `MatchExpression`

Variant selection, payload extraction, arm-local identity and exhaustiveness must
come from compiler-resolved canonical facts. `KOSCHEI_MIR_MATCH_SEMANTICS_V1.md`
defines the target. Proposed `MirVariantIs` / `MirVariantPayload` facts remain
unimplemented.

## Conditional / edge fallback boundaries

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
- treating AST and normalized MIR as co-equal execution authorities;
- implicit function return from Error-valued branch predicates;
- runtime inference of value-if result identity;
- re-running type inference for block-result semantics.

### DOES NOT PROTECT AGAINST

- Python TCB compromise;
- bugs in normalized instructions;
- forged/tampered MIR without sealing/registry checks;
- unresolved loop-body result continuity;
- unresolved Match identity/exhaustiveness;
- source/AST leakage elsewhere in the bootstrap compiler.

### ASSUMPTIONS

- Typed HIR remains the checked type authority;
- `MirExecutorV1` rejects `MirAstFallback`;
- public checked execution passes MIR sealing and exact v4 registry validation;
- compiler-known privileged operation identity remains authoritative.

### FAILURE MODE

- loop body Error is silently treated as an ordinary iteration result;
- a value-block join is reachable without the selected path binding a value;
- a backend begins executing `MirAstFallback`;
- runtime reconstructs variant/type/authority facts from host objects.

## Next implementation order

1. bind loop body normal-exit value using `checked_block_normal_type(...)`;
2. make body Error terminate the loop statement and continue the enclosing block;
3. normalize value-position `while` / `for` and close remaining OrBlock loop
   fallback;
4. make `for` iterable Error continuation explicit where the checked type permits;
5. expose compiler-resolved Match variant/exhaustiveness facts;
6. implement Match explicit CFG;
7. integrate exact v4 registry membership into sealing/fingerprint validation;
8. convert semantically-invalid fallback production to compiler fail-closed;
9. run canonical full validation before merge.

No new source syntax is required.