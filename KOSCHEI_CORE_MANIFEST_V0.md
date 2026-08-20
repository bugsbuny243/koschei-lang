# Koschei Core Manifest v0

Status: **architecture inventory, non-destructive**.

This file exists to keep the programming language visible while the repository grows around it. It does not move or delete modules. It identifies the current language-authoritative spine first; import/dependency analysis must be completed before any directory reorganization.

## Rule

A module is part of the **language core** only when changing it can change one or more of these facts:

- what `.ks` source is lexically valid;
- what `.ks` syntax means structurally;
- what programs are accepted or rejected by semantic/type/effect/resource rules;
- how modules compose into one checked program;
- what backend-independent executable contract is produced;
- how that checked contract executes in the reference runtime.

Security infrastructure, recovery systems, deployment tooling, release evidence, private-library orchestration, deception/visibility systems, CI helpers and backend adapters are important, but they are **not the language definition** merely because they live in `koschei/`.

## Current language-authoritative spine — 20 modules

### Source surface and syntax

1. `koschei/lexer.py` — `.ks` token vocabulary and lexical scanner.
2. `koschei/ast_nodes.py` — base source-language AST and source locations.
3. `koschei/generic_nodes.py` — generic/typestate AST extensions.
4. `koschei/_parser_v09.py` — inherited parser implementation still used by the current parser facade.
5. `koschei/parser.py` — current parser facade and current high-assurance/generic declarations.

### Semantic/type authority

6. `koschei/semantic.py` — scopes, immutability, errors, capability semantics and legacy semantic authority.
7. `koschei/type_system.py` — structural type representation.
8. `koschei/type_contracts.py` — structural type contracts and generic inference.
9. `koschei/_typed_ops.py` — typed-operation registration used by Typed HIR.
10. `koschei/typed_hir.py` — backend-independent typed analysis.
11. `koschei/integrity.py` — backend-independent source/control-flow integrity checks.
12. `koschei/legacy_generics.py` — compatibility bridge required while legacy semantic analysis and Typed HIR coexist.
13. `koschei/effects.py` — fail-closed capability/effect inference sealed into MIR.
14. `koschei/effect_contracts_v1.py` — enforceable source-level effect contracts such as `pure fn`.
15. `koschei/affine_resources_v1.py` — compiler-enforced affine ownership for authority-bearing values.
16. `koschei/typestate_resources_v1.py` — compiler-enforced state transition/resource invariants.

### Program graph and executable contract

17. `koschei/modules.py` — module loading, dependency graph and orchestration of language checks/lowering.
18. `koschei/mir_ir.py` — normalized backend-independent MIR/control-flow representation.
19. `koschei/mir.py` — sealed checked MIR graph and lowering contract.
20. `koschei/interpreter.py` — reference execution semantics for checked Koschei programs.

These 20 modules are the **current core spine**, not a claim that every dependency beneath them has already been proven non-authoritative. The next inventory step is to recursively map imports from these modules and either (a) promote an omitted semantic dependency into this manifest or (b) classify it as support infrastructure.

## Close support, but not language authority by default

Examples include:

- `koschei/runtime_budget.py` — execution resource policy;
- `koschei/capabilities.py` — capability-manifest reporting/analysis surface;
- `koschei/diagnostics.py` — diagnostic catalog/rendering;
- `koschei/formatter.py` — canonical source formatting;
- `koschei/project.py` — project creation/path resolution;
- `koschei/cli.py`, `koschei/cli_entry.py` — command surfaces;
- `koschei/lsp_v5.py` — editor protocol integration.

These may be essential product modules without defining the language itself.

## Backend / bootstrap adapters — explicitly non-canonical

Examples include `koschei/codegen_go.py`, `koschei/mir_go_native.py` and other implementation-language adapters. They may execute a checked contract, but they do not get to redefine Koschei semantics. A backend disagreement with the language-authoritative spine is a backend bug.

## Private library / security platform — explicitly separate from the language core

`koschei/library_*` modules, recovery/quorum/fencing/attestation/containment/visibility/adversary-learning layers and similar platform modules are **not** added to this core manifest merely because Koschei products may rely on them.

The intended architecture boundary is:

`Koschei language core` → defines/validates program meaning

`Koschei execution/runtime` → executes the checked meaning

`Koschei private library/security platform` → provides hidden technology, policy, evidence, containment and service capabilities behind controlled interfaces

The private platform may expose capabilities to the language; it must not silently rewrite the language grammar or semantics.

## Anti-bloat rule

From this manifest forward:

1. A new security/library/recovery module does **not** become language core automatically.
2. A new language feature must identify which core module owns its grammar, structural representation, semantic rule, type/effect rule and MIR/execution meaning.
3. If a feature requires a new language-authoritative module, this manifest must be updated in the same change.
4. Compatibility modules must carry an explicit migration/removal condition; they must not become permanent invisible language layers by accident.
5. Directory moves are forbidden until the recursive core dependency map and import-cycle plan are complete.

## Next structural target

After dependency verification, reorganize without changing semantics into a visible shape similar to:

- `koschei/lang/core/` — lexer, AST, parser, semantic/type/effect/resource authority
- `koschei/lang/runtime/` — MIR execution and bounded runtime policy
- `koschei/library/` — private Koschei library technology/semantic system
- `koschei/security/` — recovery, attestation, containment, visibility and related platform defenses
- `koschei/adapters/` — Go/native/foreign/bootstrap adapters
- `koschei/tooling/` — CLI, LSP, formatter, project and diagnostics surfaces
- `koschei/experimental/` / `koschei/legacy/` — explicitly non-canonical work

That reorganization must be evidence-driven and test-preserving; this manifest is the map before the move.
