# Koschei Native Reusable Realities v1

Status: experimental language slice stacked on Native Decision Realities v1.

## Goal

Make source reuse a property of authenticated object reality rather than adding a
mainstream function/call/parameter/template grammar.

A reusable object is one immutable witness graph with numbered `conduit` inputs:

```text
witness left conduit 0
witness right conduit 1
witness total sum left right
resolve total
```

The source object is stored once. A sealed realization record binds that exact
canonical object identity and artifact digest to one ordered Int64 input vector.
The same source object may have many realization records with different inputs.

A root reality consumes those realized values through its own conduit slots:

```text
witness first conduit 0
witness second conduit 1
witness total sum first second
resolve total
```

For the first acceptance example:

- realization A of the same reusable object receives `[40, 2]` and resolves `42`;
- realization B receives `[10, 5]` and resolves `15`;
- the root resolves `57`.

Only two source objects exist: one root and one reusable object. There is no copied
source for the two realizations.

## Why this is not a function rename

The native source contains no function declaration, call expression, parameter
list, semantic module name, target object name, or template declaration.

Realization authority lives in sealed Object Space metadata. Each realization
binds:

- random realization identity;
- root conduit slot;
- exact reusable object identity;
- exact reusable artifact digest;
- exact reusable frontend identity;
- ordered input vector;
- Object Space epoch interval;
- witness ceiling;
- absolute input/output ceilings;
- authority/effect ceilings.

V1 accepts only zero authority and zero effects.

## Canonical reusable contract

A reusable object must expose at least one conduit and at most 64. Input conduit
slots must be contiguous from zero. This gives the sealed ordered input vector one
unambiguous meaning without source-level parameter names becoming cross-object
authority.

V1 inputs and outputs are signed Int64/Whole reality. Rich native value-domain
reuse is a later extension after the reuse identity model is proven.

## Multiple realizations of one object

Unlike Native Relationships v1, which deliberately admitted one edge per leaf,
Reusable Realities v1 allows many realization records to reference the same
canonical reusable object. Duplicate realization identities and duplicate root
output slots still fail closed.

Every authoritative non-root reusable object must participate in at least one
realization; dormant/orphan physical objects are rejected.

## Scale gate

The first large gate uses:

- one root source object;
- one reusable source object;
- 2048 realization records, all referencing the same reusable object;
- two inputs per realization;
- 2048 root conduit witnesses;
- 2047 root aggregation witnesses;
- 4095 root witnesses total.

The test therefore pressures reuse near the current native witness ceiling without
copying the reusable source 2048 times.

## Non-claims

V1 is not yet a general function system. It does not provide recursive realization
DAGs, runtime-dependent inputs, rich value-domain inputs, polymorphism, effects,
authority-bearing reusable realities, or dynamic dispatch.

Those features must extend the sealed realization contract rather than falling
back to conventional function/module/call authority.
