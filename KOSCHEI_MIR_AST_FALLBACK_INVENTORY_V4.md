# KOSCHEI MIR AST FALLBACK INVENTORY V4

Status: production migration checkpoint
Scope: Koschei Lang only

## Constitutional rule

A fact normalized into Verified MIR must not be re-derived from AST/source as a
second semantic authority. `MirAstFallback` is a migration boundary, not an
execution permission. Once compiler-owned canonical execution facts exist, the
public runtime fails closed instead of returning to AST compatibility.

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
- compiler-owned Map method calls (`get`, `set`, `keys`, `contains`) lowered
  to exact sealed MIR opcodes rather than generic member dispatch;
- let / expression / return statements;
- statement-context `if` / `while` / `for` Error continuation;
- a value-producing `or { ... }` subset including value-position `if`, nested
  `else if`, `while`, and `for` with explicit Error-result paths;
- break / continue on the already-normalized loop path;
- compiler-resolved `MatchExpression` with explicit CFG;
- exact canonical variant construction/test/payload facts using
  `Owner::Variant` identity;
- expression and checked value-block Match arms, including arm-local return
  termination.

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

### `MatchExpression` — normalized canonical path

Typed HIR is the owner of Match identity, arm order, payload type and
exhaustiveness. Executable MIR emits:

- `MirVariantConstruct` for checked variant materialization;
- `MirVariantIs` for exact `Owner::Variant` observation;
- `MirVariantPayload` only on a CFG true-edge proven for that exact source SSA
  and canonical variant identity.

The scrutinee is evaluated exactly once. The final miss edge of a
compiler-proven exhaustive Match is `MirUnreachable`; runtime/backends do not
invent a default arm.

Canonical variant facts are consumed by direct native MIR execution. The strict
single-module MIR-Go backend also carries the same sealed identity into generated
Go and checks owner + variant + payload presence before extraction. Unsupported
native/backend shapes remain fail-closed; they do not reopen source AST.

The exact MIR v4 instruction registry is now part of block/seal validation.
Dataclass-shaped unregistered opcodes do not inherit execution authority.

## Remaining semantic / backend boundaries

### P1 — `ListLiteral` without normalized `List<T>` type

Typed fact missing -> fail closed. MIR must not guess an item type.

### P1 — assignment target other than `Identifier`

Unsupported target shape must gain a canonical semantic rule or be rejected
before executable MIR. Host object shape is not assignment authority.

### P1 — native-binary coverage is narrower than direct MIR runtime

Strict MIR-Go intentionally remains a supported subset. The direct sealed MIR
runtime now carries compiler-owned Struct construction and Map
construction/get/set/keys/contains semantics. Imports, remaining List/member
surfaces and strict binary adapter parity still require explicit closure before
`ks build` can claim full-language native binary coverage. Unsupported programs
fail closed rather than falling back to the ambient legacy AST-Go backend.

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
- runtime/backend reconstruction of Match owner identity;
- payload extraction without exact true-edge variant proof;
- unregistered MIR instruction classes entering the sealed v4 universe;
- implicit function return from Error-valued branch predicates or loop inputs;
- runtime inference of value-control-flow result identity;
- re-running type inference for block-result semantics;
- constructing a `for` iterator before an Error-valued iterable path is routed.

### DOES NOT PROTECT AGAINST

- Python TCB compromise;
- bugs in registered normalized instructions or code generators;
- rollback/physical key-custody failures outside the MIR semantic boundary;
- unsupported native-binary language features;
- deployment/release provenance that has not received a fresh exact-head full
  validation receipt.

### ASSUMPTIONS

- Typed HIR remains the checked type authority;
- public checked execution passes MIR sealing and exact v4 registry validation;
- `Owner::Variant` owner names are unambiguous in the admitted execution domain;
- compiler-known privileged operation identity remains authoritative;
- unsupported backend features fail closed.

### FAILURE MODE

- a value-block join is reachable without the selected path binding a value;
- a backend begins executing `MirAstFallback`;
- runtime reconstructs variant/type/authority facts from host objects;
- an unregistered opcode passes seal validation;
- a checked List/Error union reaches iterator construction before Error routing.

## Next implementation order

1. run canonical `ks-local-validate --profile full` on an exact clean head and
   retain its external receipt/evidence;
2. close remaining strict native parity for imports, List/member surfaces and
   production-supported binary features rather than using legacy AST-Go
   fallback;
3. pin reproducible build/toolchain/SBOM inputs;
4. align package, tag, release artifact and checksum identity;
5. close release branch/ruleset and provenance gates.

No new source syntax is required for the Match/variant path.
