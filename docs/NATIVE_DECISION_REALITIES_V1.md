# Koschei Native Decision Reality v1

Status: experimental language slice stacked on Native Value Domains v1.

Decision is not modeled as statement-order control flow. A `settle` witness binds one
candidate reality into the resolved graph using a `truth` value:

```text
witness gate truth yes
witness accepted glyphs 2 ok
witness rejected glyphs 2 no
witness result settle gate accepted rejected
resolve result
```

`settle` has three inputs: condition, affirmative candidate, negative candidate. The
condition must be `truth`; both candidates must have the same value domain. There is no
implicit conversion and no fallthrough.

## Structural admission vs active realization

A decision has two deliberately different graphs:

1. **structural reality** contains the condition and both candidates. Every object in this
   reality is parsed, domain-checked, overflow/resource-checked, and must be reachable from
   the single resolve root. A malformed candidate cannot hide merely because it is not
   selected;
2. **active reality** contains the condition and only the selected candidate dependency
   path. Compatibility lowering materializes only this active reality.

V1 candidates are still pure and closed, so static admission can prove both candidate
realities completely. This separation is nevertheless part of the language contract so a
future effectful/runtime-dependent decision model is not forced to execute both candidates.

## Why this is not `if` / `else`

- `settle` is a witness operation, not a statement or block;
- source-line order is not execution order;
- there is no early return, fallthrough, branch body, label, pattern or jump;
- both candidates are statically admitted under one closed graph;
- exactly one candidate belongs to the active runtime realization;
- candidate domains must match before lowering.

The source therefore describes a value-reality choice, not a renamed mainstream branch.

## Originality collision review

The originally considered word `hinge` was rejected during collision review because it is
already used prominently in programming/tooling contexts. `settle` is registered with
Koschei originality provenance tied to deterministic execution and remains subject to the
repository collision guardrails.

This is not a mathematical claim that no software project anywhere has ever used the English
word `settle`; the originality contract is about design provenance and avoiding known borrowed
language surfaces.

## Object Space identity

Decision reality has its own sealed Object Space schema and 32-byte frontend identity. A
source is never upgraded from value-domain v1 to decision v1 because it happens to contain a
`settle`-looking line. Sealed metadata selects the frontend; malformed metadata fails closed.

V1 remains one authoritative Object Space source object. Multi-object typed decision transport
and runtime-dependent external truth are later language contracts.

## Current non-claims

V1 does not yet provide general imperative control flow, loops, runtime input, effectful branch
bodies, exceptions, pattern matching, or multi-object decision effects. It establishes the
native decision semantics those later features must preserve.