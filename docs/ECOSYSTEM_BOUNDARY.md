# Koschei Language Ecosystem Boundary

Koschei is an independent capability-secure programming language. It belongs to the wider Koschei ecosystem, but its compiler, type system and runtime security rules are not controlled by a token, an AI model or the Web3 product.

## Mission

Build a genuinely new language that makes powerful software easier to write while making hidden authority harder to obtain.

The design direction is:

- no ambient disk, network, environment or process authority;
- explicit, narrow and inspectable capability values;
- simple error and absence handling;
- immutable data by default;
- deterministic diagnostics and backend parity;
- broad interoperability without silently weakening the capability model.

Koschei must not copy another language's grammar or identity merely to look familiar. Useful ideas may be studied, but every adopted mechanism must fit Koschei's own authority model, diagnostics and usability goals.

## The “safer than Rust” target

“100 times safer than Rust” is a research and engineering target, not a claim that may be published without evidence.

The target must be converted into reproducible measurements. Candidate benchmark dimensions include:

1. ambient-authority reach available to a dependency;
2. supply-chain blast radius after importing an untrusted package;
3. memory-safety and concurrency defects that survive compilation;
4. capability widening and delegation escapes;
5. interpreter/native backend semantic drift;
6. unsafe or foreign-code boundary size;
7. security-critical ceremony required for common programs;
8. diagnostic quality and successful remediation rate.

A “100x” result must name the benchmark, corpus, denominator and measurement method. Until that exists, the honest statement is that Koschei is designed to enforce stricter authority boundaries than mainstream ambient-authority languages.

## Interoperability contract

Koschei aims to work with existing ecosystems without becoming a thin syntax layer over any one of them.

Interoperability should be added through explicit contracts:

- stable generated Go and future C ABI adapters;
- JSON and HTTP interfaces guarded by network capabilities;
- process invocation guarded by process capabilities;
- package and lock-file metadata with integrity checks;
- future WASM or native FFI boundaries with declared authority;
- generated bindings that preserve type, error and capability information where possible.

Foreign code is not automatically trusted. An adapter must declare which authority crosses the boundary, how values are validated and which runtime owns memory and errors.

## Relationship to Koschei Web3 Hub

Repository: `https://github.com/bugsbuny243/Koschei-Web3-Hub`

Web3 Hub is a reference customer and stress test for the language, not the owner of language semantics. Future integration may include:

- writing bounded evidence-processing components in `.ks`;
- generating SDK or service adapters;
- using `ks caps` in CI to prove allowed authority;
- comparing Koschei and existing implementations for security ceremony and behavior parity.

No production Web3 component should be rewritten in Koschei until the required language feature, backend and runtime boundary is implemented and tested. Integration must be incremental and reversible.

## Relationship to Koschei Sentinel

Repository: `https://github.com/bugsbuny243/koschei-sentinel`

Sentinel may assist with documentation, examples, diagnostics research or security-test generation, but it cannot change compiler truth. Generated code and suggested fixes must pass the same parser, type, capability, MIR, backend and test gates as human-written changes.

## Relationship to KOSCH

Official mint:

```text
HHPpU9u56Bwxov12nf7DXUCuv6h1q5j1xgGS3yukpump
```

KOSCH is an ecosystem asset. Holdings must never:

- disable a compiler diagnostic;
- widen a capability;
- unlock an unsafe backend path;
- alter package integrity checks;
- change test or release requirements;
- buy a security certification.

Permitted relationships are external to compiler correctness, such as community coordination, transparent contribution programs or access to separately operated ecosystem services.

## Release gates for the interoperability vision

Before Koschei can honestly claim broad language interoperability, it needs:

1. a versioned FFI/ABI specification;
2. explicit capability transfer rules at every foreign boundary;
3. lock files and reproducible package resolution;
4. native/interpreter/foreign-adapter parity tests;
5. fuzzing and adversarial fixtures for boundary encoding;
6. migration and compatibility tests across releases;
7. documented unsupported and unsafe cases;
8. a benchmark suite comparing security and ceremony against multiple languages.

The ecosystem vision is ambitious. The implementation rule remains simple: no feature is presented as real until the repository can execute and test it.
