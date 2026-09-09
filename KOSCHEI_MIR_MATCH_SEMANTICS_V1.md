# KOSCHEI MIR MATCH SEMANTICS V1

Status: semantic prerequisite / non-executable specification
Branch: `feature/mir-or-return-normalization-v1`
Scope: Koschei Lang only

## Constitutional goal

`MatchExpression` must not be executed by reopening source AST or by asking the
runtime to inspect arbitrary Python object shape and decide what an arm means.

**VARIANT OBSERVATION != AUTHORITY**

Variant identity is a canonical semantic fact. Runtime may compare a checked
value against a compiler-known variant identity, but it may not invent variant
names, arm order, payload authority or exhaustiveness.

## Canonical facts required

A normalized match site must bind:

- the scrutinee SSA value;
- the compiler-known enum/Option/Result semantic identity;
- ordered canonical arm variant identities;
- whether each arm binds a payload;
- the arm-local canonical binding identity;
- checked expression result type;
- checked exhaustiveness policy;
- source location only as diagnostic metadata, not authority.

## Proposed MIR facts

### `MirVariantIs`

Fields:

- `target`: Bool SSA;
- `source`: scrutinee SSA;
- `variant`: canonical variant identity;
- `type`: Bool;
- `location`.

Meaning: compare an already checked enum-like value with one compiler-selected
variant identity. It does not select an arm or authorize a payload extraction.

### `MirVariantPayload`

Fields:

- `target`: payload SSA;
- `source`: scrutinee SSA;
- `variant`: exact canonical variant identity proven on the predecessor path;
- `type`: checked payload type;
- `location`.

Meaning: extract payload only on a CFG path where the same variant was proven.
Execution on an unproven path is KS5002 fail-closed.

No generic `MirPythonMatch`, reflection instruction, or AST arm object is
permitted.

## Lowering law

`evaluate scrutinee exactly once`
`-> variant test for arm 1`
`-> selected arm CFG or next test`
`-> ...`
`-> selected arm writes one result binding`
`-> join/load`

Only one selected arm executes.

If an arm has a payload binding:

`proven variant path -> MirVariantPayload -> MirBind canonical arm-local name`

The binding lives only in that arm lexical scope.

## Exhaustiveness

Exhaustiveness is a compiler semantic fact, not a runtime discovery task.

Preferred rule:

- if the checked compiler report proves exhaustive: generated CFG may end in
  `MirUnreachable("checked exhaustive match exhausted")` after the final failed
  test;
- if source semantics permits non-exhaustive match: define one explicit
  fail-closed runtime error contract before implementation;
- MIR/runtime must not inspect the current enum declaration and silently decide a
  different exhaustiveness policy.

## Identity law

Variant display text is not sufficient identity.

Future-proof canonical identity should be derived from semantic declaration
identity plus variant identity, so two unrelated enums with the same visible
variant name do not alias.

Bootstrap v1 may carry a canonical string only if the compiler uniquely resolves
that string and seals it into MIR. This must remain migration debt, not a claim
that visible names are permanent identity.

## Capability law

Matching a capability-bearing payload does not create, widen or delegate
capability authority. Payload extraction merely reveals the already-contained
checked value on a proven variant path. Subsequent effect use remains governed by
normal capability/effect contracts.

## Security properties

### PROTECTS AGAINST

- runtime-selected arm meaning;
- payload extraction from the wrong variant;
- duplicate visible variant names becoming ambient identity;
- eager execution of unselected arms;
- AST execution inside sealed MIR;
- match result authority inferred from host object shape.

### DOES NOT PROTECT AGAINST

- compromised Python TCB;
- an incorrect compiler exhaustiveness report;
- leakage of canonical variant names from bootstrap representations;
- bugs in enum construction before match execution.

### ASSUMPTIONS

- enum/Option/Result construction is already type checked;
- compiler owns semantic variant resolution;
- MIR sealing and exact instruction registry validation run before execution;
- arm-local bindings use canonical MIR lexical identities.

### FAILURE MODE

- `MirVariantPayload` runs without predecessor proof for the same variant;
- two canonical declaration identities collapse to one visible string;
- unselected arm effects execute;
- runtime re-derives exhaustiveness from AST/declaration objects;
- match lowering evaluates the scrutinee more than once.

## Implementation order

1. expose compiler-resolved canonical variant identity for each arm;
2. add `MirVariantIs` and `MirVariantPayload` to the single v4 extension
   instruction authority and exact registry;
3. teach canonical validator/fingerprint ABI their `source` SSA use;
4. implement explicit arm CFG and arm-local payload binding;
5. executor supports only exact registered variant operations;
6. add adversarial tests for wrong-variant payload extraction, duplicate visible
   names, skipped arm effects and single scrutinee evaluation;
7. remove `MatchExpression` from fallback inventory only after those tests exist.

No new source syntax is required.
