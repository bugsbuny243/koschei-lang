# Koschei Originality Contract v1

Status: **migration ratchet active; Koschei-native surface not complete**

## Purpose

Koschei must not become a familiar language with renamed keywords, nor a
conventional project tree with a different logo. This contract turns that design
rule into a repository gate.

The gate deliberately distinguishes two things:

1. **legacy compatibility debt** — syntax and project conventions that already
   exist and must keep working while the compiler is migrated; and
2. **Koschei-native surface** — any new syntax, grammar marker, manifest concept,
   file name, directory name, or canonical project path.

Existing debt is not approval or precedent. It is a frozen baseline that must
shrink.

## What v1 enforces

`koschei/originality_contract_v1.py` records the current legacy surface and a
retirement ratchet.

The test suite verifies the live Python lexer, native Go lexer, punctuation
surface, `ks new` scaffold, and manifest vocabulary against that baseline.

A change fails the contract when it:

- silently adds a new keyword;
- silently adds a new one-, two-, or three-character ASCII punctuation token;
- removes legacy syntax without recording that retirement;
- reuses a blocked mainstream keyword for new Koschei syntax;
- adds a canonical scaffold path without Koschei design provenance;
- adds a new path whose components reuse conventional layout names such as
  `src`, `lib`, `bin`, `build`, `dist`, `target`, or `main`;
- adds mainstream-shaped manifest vocabulary such as `dependencies` or
  `workspace`; or
- registers a new surface item without binding it to a Koschei security/execution
  invariant and completing an external-collision review.

The normal unittest discovery already run by the repository CI executes this
gate; no separate best-effort script is required.

## What v1 does not claim

This is **not** a mathematical proof that no language in history has ever used a
given character or word. A finite repository cannot prove global non-collision
against every existing or future language.

It instead provides a fail-closed engineering rule: inherited surface is
explicit debt, common borrowed spellings are blocked, and new surface requires
reviewable Koschei-native provenance.

The v1 punctuation probe covers atomic ASCII tokens up to three characters.
Future native grammar work must extend the contract when Koschei intentionally
introduces non-ASCII or longer lexical forms.

## Current debt

At the time this contract was introduced, the compiler still uses mainstream-like
keywords including `fn`, `let`, `mut`, `return`, `if`, `else`, `for`, `while`,
`struct`, `enum`, `match`, and `import`. It also uses common operator/delimiter
forms.

`ks new` still emits:

- `.gitignore`
- `README.md`
- `koschei.toml`
- `src/`
- `src/main.ks`

and the manifest still contains mainstream-shaped vocabulary such as `package`,
`name`, `version`, `entry`, and `capabilities`.

These are all **legacy migration debt**. They must not be described as the final
Koschei language or project model.

## Migration rule

A legacy item can disappear only when the same change adds it to the matching
`RETIRED_LEGACY_*` ratchet. A retired item is rejected if it becomes active
again.

A new Koschei-native item must have `SurfaceProvenance` containing:

- a registered Koschei invariant;
- a substantive design rationale; and
- an explicit collision-review result.

The accepted invariants in v1 are tied to Koschei's own architecture: explicit
and minimal authority, deterministic execution, event-horizon isolation,
protected/temporal source reality, resource linearity, and verifiable effects.

## Repository layout versus Koschei project layout

This policy governs the **canonical surface exposed to Koschei programmers and
generated Koschei projects**.

The compiler implementation itself currently lives in a conventional Git
repository and uses Python, Go, GitHub Actions, `tests/`, `docs/`, and other host
tooling. Those implementation-host names are not a declaration that Koschei
projects should copy them.

Host-tool compatibility and Koschei language identity are separate boundaries.

## Dataset/export consequence

Compiler-oracle datasets must not accidentally teach today's legacy syntax as an
eternal design requirement. Until the migration is complete, training records
should carry a surface-generation/family marker so evaluation can distinguish:

- legacy compatibility behavior;
- Koschei-native behavior; and
- migration/repair examples.

The canonical exporter must remain commit/SHA bound.

## Maturity condition

`Language production maturity` and `Koschei-native surface maturity` are
different gates.

The originality gate may only become green when:

1. active legacy keyword debt is zero;
2. active legacy punctuation debt is zero or every retained primitive has an
   explicit Koschei-native justification;
3. the conventional scaffold and manifest debt is retired;
4. Python and native frontends agree on the new grammar;
5. formatter, LSP, diagnostics, examples, golden tests, and dataset generation
   use the same canonical surface; and
6. the replacement grammar is tested semantically, not merely renamed.

**Renaming `fn` to another word while preserving the same borrowed grammar does
not satisfy this contract.**
