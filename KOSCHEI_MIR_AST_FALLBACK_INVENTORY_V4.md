# KOSCHEI MIR AST FALLBACK INVENTORY V4

Status: compiler/runtime migration checkpoint
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
- statement-context `if` / `while` / `for` Error continuation;
- a value-producing `or { ... }` subset including value-position `if`, nested
  `else if`, `while`, and `for` with explicit Error-result paths;
- break / continue on the already-normalized loop path.

## Recently closed or reduced fallback boundaries

### `OrElseExpression` — normalized

`evaluate fallible once -> success test -> success payload / failure fallback -> join`

No eager fallback evaluation and no `MirAstFallback` are required.

### `OrBlockExpression` — value control flow normalized

The following handler forms lower without AST fallback:

- empty block -> canonical `MirUnit`;
- expression/let sequence -> final normal value / Unit;
- direct unconditional `return` -> function `MirReturn`;
- tail `if` / nested `else if` when all participating blocks stay inside the
  currently proven value-block subset;
- tail `while` with zero-iteration Unit, last-body-value continuity, and explicit
  condition/body Error result routing;
- tail `for` over a checked List success type with zero-iteration Unit,
  last-body-value continuity, iterable Error routing before iterator creation,
  and body Error loop termination;
- Error-valued control predicates/iterables become explicit handler results, not
  implicit function returns.

Typed HIR and MIR share one canonical normal-exit block type projection from
already-checked HIR expression facts. MIR does not re-run type inference.

## Remaining P0 semantic debt

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
must fail closed rather than let runtime object shape become iteration authority.

### P2 — future unknown AST nodes

New AST constructs do not inherit execution support. They require explicit MIR
semantics or compiler rejection.

## Security classification

### PROTECTS AGAINST

- hiding where source-shaped migration boundaries remain;
- treating AST and normalized MIR as co-equal execution authorities;
- implicit function return from Error-valued branch predicates or loop inputs;
- runtime inference of value-control-flow result identity;
- re-running type inference for block-result semantics;
- constructing a `for` iterator before an Error-valued iterable path is routed.

### DOES NOT PROTECT AGAINST

- Python TCB compromise;
- bugs in normalized instructions;
- forged/tampered MIR without sealing/registry checks;
- unresolved Match identity/exhaustiveness;
- source/AST leakage elsewhere in the bootstrap compiler.

### ASSUMPTIONS

- Typed HIR remains the checked type authority;
- `MirExecutorV1` rejects `MirAstFallback`;
- public checked execution passes MIR sealing and exact v4 registry validation;
- compiler-known privileged operation identity remains authoritative.

### FAILURE MODE

- a value-block join is reachable without the selected path binding a value;
- a backend begins executing `MirAstFallback`;
- runtime reconstructs variant/type/authority facts from host objects;
- a checked List/Error union reaches iterator construction before Error routing.

## Next implementation order

1. expose compiler-resolved Match variant/exhaustiveness facts;
2. implement Match explicit CFG;
3. integrate exact v4 registry membership into sealing/fingerprint validation;
4. convert semantically-invalid fallback production to compiler fail-closed;
5. run canonical full validation before merge.

No new source syntax is required.
