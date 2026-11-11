# Koschei Language — Web3 Incubation Gates

Status: `incubation_only`  
Production Web3 integration: disabled

Koschei is not currently part of the Koschei Web3 Hub runtime, build, deployment or incident-recovery path. The language must mature as an independent programming-language project before any production Web3 component is proposed.

## Current allowed relationship

During incubation, Web3 Hub may be used only as an offline source of difficult engineering cases:

- compiler and capability-security fixtures;
- standalone `.ks` reference programs;
- interoperability prototypes;
- authority-manifest tests with `ks caps`;
- security and ergonomics benchmarks;
- interpreter/native/adapter parity experiments;
- reversible non-production proofs of concept.

This relationship does not make the language a Web3 dependency.

## Currently forbidden

Until every relevant gate passes and the owner explicitly approves a future integration, no production Web3 change may:

- rewrite a Go or JavaScript component in Koschei;
- require `ks`, the Koschei compiler or the Koschei runtime during deployment;
- execute `.ks` code in an API request, worker, migration or alert path;
- make Web3 startup or recovery depend on the language toolchain;
- describe the live Web3 product as secured by Koschei language code;
- weaken capability rules to simplify interoperability;
- use KOSCH holdings to bypass any technical or release gate.

## Maturity gates

A future production reference component may be proposed only after the gates relevant to that component have reproducible evidence.

### 1. Language stability

- syntax and type-system behavior required by the component are frozen under a documented compatibility policy;
- capability semantics are stable and versioned;
- error, `Option`, `Result`, collection and control-flow contracts are complete for the use case;
- no unsupported AST fallback is required by the chosen backend path.

### 2. Build and dependency integrity

- package resolution and lock files are implemented;
- builds are reproducible from an immutable dependency graph;
- compiler, runtime and generated artifacts have verifiable digests;
- upgrades have migration and rollback tests.

### 3. Runtime and backend confidence

- interpreter and native behavior are equivalent for the selected component;
- generated Go or future ABI adapters preserve types, errors and declared authority;
- cross-platform behavior is tested where the component requires it;
- resource limits, failure behavior and observability are documented.

### 4. Security evidence

- capability widening and delegation attacks are covered by adversarial tests;
- disk, network, environment and process escapes fail as designed;
- parser, type checker, MIR, runtime and adapter boundaries are fuzzed;
- foreign code cannot silently receive authority not declared by the Koschei boundary;
- public comparative claims are supported by a reproducible benchmark rather than ambition alone.

### 5. Real-program maturity

- multiple substantial standalone programs run successfully without Web3 Hub;
- the language has users or test applications beyond a single internal demo;
- diagnostics and documentation allow failures to be corrected reliably;
- performance and operational limitations are measured honestly.

### 6. Reference-component acceptance

- the candidate component is small, replaceable and non-critical;
- its existing implementation remains available for rollback;
- external behavior and data contracts match;
- authority is no wider than the existing implementation;
- production adoption is separately reviewed and explicitly approved by the owner.

## Future rollout order

Passing the gates does not trigger integration automatically. Any future attempt follows this order:

```text
standalone fixture
    ↓
non-production reference service
    ↓
behavior and security parity
    ↓
shadow execution with no production authority
    ↓
small reversible component
    ↓
separate owner approval
```

A broad Web3 rewrite is not an acceptable first integration.

## Sentinel and KOSCH boundaries

Sentinel-generated code is only a suggestion and must pass every normal compiler and repository gate. KOSCH holdings cannot disable diagnostics, widen capabilities, change release criteria or authorize premature integration.

## Final rule

Koschei language earns a place in Web3 Hub by first becoming a mature, independently useful and measurably secure programming language. Shared branding or ecosystem membership is not production integration.
