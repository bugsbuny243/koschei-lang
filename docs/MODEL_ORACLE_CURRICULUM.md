# Koschei Model Oracle Curriculum v1

Status: deterministic research curriculum contract  
Authority: pinned Koschei compiler revision  
Production model integration: not authorized by this artifact

## Purpose

The foundation corpus exports what the Koschei repository says. The model-oracle
curriculum adds a different guarantee: every training label in this artifact is
recomputed by the pinned Koschei compiler.

The v1 corpus is deliberately small. It establishes the contract before scale.
A seed is published only when the compiler produces exactly the expected
accept/reject result and, for rejected cases, exactly the expected Koschei
diagnostic code. Compiler drift therefore stops the build instead of silently
changing a training label.

## Build

From a clean checkout at the exact commit being attributed:

```bash
ks-model-curriculum build \
  --repo-root . \
  --source-commit "$(git rev-parse HEAD)" \
  --output build/koschei-model-curriculum-v1.json
```

Verify an existing artifact:

```bash
ks-model-curriculum verify build/koschei-model-curriculum-v1.json
```

The official `ks-model-curriculum build` path first requires the supplied commit
to equal Git `HEAD` and requires the complete non-ignored worktree to be clean.
This is deliberately stricter than foundation export because curriculum labels
depend not only on docs and examples, but also on the compiler and generator
implementation bytes.

The build then constructs the existing `koschei.language-foundation-corpus.v1`
artifact in memory and binds the curriculum to the resulting foundation corpus
SHA-256.

## What each case records

Each `koschei.model-oracle-curriculum.v1` case contains:

- stable case ID, family, curriculum level and task;
- one entry `.ks` path and all source files needed by the case;
- SHA-256 for every source file;
- compiler outcome: `ACCEPTED` or `REJECTED`;
- exact known diagnostic code and title for a rejection;
- mechanically derived capability manifest for an accepted case.

Accepted cases never carry a diagnostic. Rejected cases never carry a
capability manifest. The verifier rejects unknown diagnostics, duplicate case
IDs, duplicate or unsafe source paths, source-hash mismatches, distribution
mismatches and top-level digest mismatches.

## v1 curriculum coverage

The first contract covers all five levels defined by
`MODEL_TRAINING_CONTRACT.md`:

- L0: pure valid code and a type-safety rejection;
- L1: missing capability, narrowing, root denial, no re-widening, read-only
  operation denial and explicit delegation;
- L2: imported dependency authority misuse and ambient network acquisition;
- L3: a legitimate declared network boundary;
- L4: minimum-authority repair across a module boundary.

For the compiler revision this v1 contract is aligned to, rejected seeds exercise
`KS1301`, `KS1306`, `KS2401`, `KS2402`, `KS2403`, and `KS2404`. These labels are
not hand-authored model truth: the generator re-runs the compiler oracle and
fails closed if a future compiler revision changes any expected result.

This is a contract fixture, not a claim of sufficient model-training scale.
Future releases may expand from these seeds through deterministic mutation and
compiler-verified generation, while preserving family-level train/validation/
test isolation.

## Trust rule

The model never decides whether a curriculum program compiled. The compiler
does. The model never decides what capability surface an accepted program has.
The capability analyzer does.

```text
source case
    ↓
pinned parser / module graph / semantic checks
    ↓
accept ──→ mechanical capability manifest
  │
  └ reject ──→ exact known Koschei diagnostic
    ↓
verified immutable curriculum artifact
```

A later Sentinel consumer must pin the expected Koschei commit, foundation
corpus digest and curriculum digest through a trusted handoff. Model output is
never a replacement for those values or for a compiler result.
