# Koschei Representation Separation V1

Status: **first executable canonical/observable boundary; not yet wired into every compiler/runtime path**

Canonical vision revision: **25 Aug 2026 — `GÖRÜNEN DÜNYA ≠ GERÇEK DÜNYA`**

## 1. Purpose

Koschei's primary representation law is:

> **OBSERVABLE WORLD != CANONICAL WORLD**

This specification turns that law into a narrow executable contract around
sealed native sigil MIR and Nur/Nyr v2.

The goal is not to claim that canonical semantics can never be recovered.
The goal is to ensure that the normal observer-facing execution representation
is not a faithful, stable copy of the canonical semantic world and that trusted
re-materialization requires an exact, scoped, time-bound capability.

## 2. Boundary

V1 defines four distinct objects:

1. **Canonical Semantic MIR** — compiler-sealed `NativeSigilMir`; trusted side.
2. **Canonical Semantic Seal** — trusted-side identity of that MIR.
3. **Observable Representation** — Nyr v2 projection plus an opaque keyed
   representation binding; observer side.
4. **Reconstruction Grant** — narrow capability allowing a trusted runtime to
   re-materialize the hidden canonical MIR for one exact context.

The observable representation MUST NOT carry:

- canonical sigil names;
- canonical subjects;
- semantic-domain labels;
- source locations;
- canonical MIR fingerprint;
- Universe plan digest;
- Veyra identity;
- authority-bearing capability material.

## 3. Representation derivation

The current v1 flow is:

```text
Native source
  -> canonical semantic checking
  -> sealed NativeSigilMir
  -> CanonicalSemanticSealV1            [trusted]
  -> Nur visibility envelope
  -> Nyr v2 non-faithful projection
  -> ObservableRepresentationV1         [observer-facing]
```

`ObservableRepresentationV1.representation_digest` is HMAC-bound to hidden
canonical state, Veyra, observer, session, epoch and the Nyr surface.

The canonical seal itself is not embedded in the observer-facing object.

## 4. Required invariants

### R1 — Non-faithful observation

The observable representation MUST NOT contain a direct canonical naming map.

### R2 — Context binding

The same canonical MIR projected under another Veyra, observer session or epoch
MUST produce a different observer-facing mapping where the underlying Nyr v2
mechanism provides rotation.

### R3 — Tamper non-promotion

Modifying an observable representation MUST NOT modify or become canonical
semantic state.

Trusted code verifies equivalence by reproducing the representation from hidden
canonical inputs.

### R4 — Reconstruction is not inversion

Authorized reconstruction MUST NOT mean "decode the Nyr surface."

The trusted runtime already possesses sealed canonical state. Reconstruction is
an authority decision controlling whether that state may be re-materialized for
the exact live representation context.

### R5 — Epoch death

An observable representation and its reconstruction grant expire before the
next visibility epoch.

An old epoch representation MUST NOT authorize re-materialization in a later
epoch.

### R6 — Veyra non-transferability

A reconstruction grant minted for one Veyra MUST NOT authorize another Veyra.

### R7 — Purpose binding

A grant minted for one purpose, such as `execute`, MUST NOT authorize another
purpose, such as `inspect`.

### R8 — Key separation

Nyr/representation veil keys and reconstruction authorization keys are separate
inputs.

Possession of an observer-facing representation alone is not a reconstruction
capability.

## 5. Deterministic authorized reconstruction

V1 uses:

```text
hidden canonical MIR
+ Veyra identity
+ observer/session/epoch context
+ grant identity
+ purpose
+ reconstruction key
= exact reconstruction authorization
```

The authorization is deterministic for the same trusted inputs, but the grant
is scoped to one epoch and one context.

This is deliberately different from a reusable bearer token.

## 6. Security analysis

### PROTECTS AGAINST

- direct faithful runtime projection of canonical sigil/subject names through
  this path;
- reuse of one Nyr mapping across a changed epoch/session/Veyra;
- promotion of a forged visible representation into canonical state;
- use of an expired representation as a current reconstruction authority;
- cross-Veyra reconstruction-grant reuse;
- purpose substitution;
- reconstruction without the separate reconstruction key.

### DOES NOT PROTECT AGAINST

- an attacker who fully compromises the trusted process while canonical MIR is
  materialized;
- memory disclosure from a component holding canonical state;
- side channels not covered by this representation;
- leakage of veil or reconstruction keys;
- malicious compiler code before/inside the trusted semantic boundary;
- hardware/OS compromise outside the assumptions of this v1 slice;
- semantic inference from repeated observations if other channels reveal enough
  correlated information.

### ASSUMPTIONS

- `NativeSigilMir.assert_sealed()` is trustworthy;
- Veyra identity sealing is trustworthy;
- Nur visibility input is trustworthy and authority-free;
- HMAC-SHA256 keys contain sufficient secret entropy and remain separated;
- trusted runtime canonical state is not directly exposed to the observer;
- epoch progression is monotonic in the caller's security domain.

### FAILURE MODES

- key reuse or disclosure can make mappings/linkage easier to correlate;
- caller-supplied stale epoch values can defeat expiry if epoch truth is not
  rooted in a trusted clock/state source;
- if canonical MIR is copied into logs, diagnostics, crash dumps, tracing or
  another runtime surface, this boundary is bypassed;
- if later execution paths skip this boundary and emit faithful MIR, the global
  Koschei claim is false even if this module remains correct.

## 7. What V1 does not claim

V1 does **not** claim:

- "source code can never be seen";
- "Koschei is unhackable";
- "Nyr is encryption of all program semantics";
- "all runtime execution is already ephemeral";
- "all compiler paths are already forced through this boundary";
- "the existing Six Power Domains gate is already integrated here."

This is the first enforceable representation-boundary slice.

## 8. Required next integration

After this slice is green:

1. make canonical semantic sealing an explicit compiler-stage contract;
2. make external MIR/debug/runtime rendering consume observer-safe
   representations by default;
3. bind trusted epoch truth to Continuity rather than caller convention;
4. bind representation/reconstruction admission into MIR/effect admission;
5. integrate Six Power Domains so reconstruction permission cannot synthesize
   unrelated Data/Compute/Network authority;
6. extend representation separation from sigil MIR to general function MIR;
7. add payload lineage:
   `Source Intent -> Verified IR -> Artifact -> Payload -> Execution`;
8. add adversarial regression cases for correlation, replay, stale mapping,
   cross-session laundering and canonical-state leakage through diagnostics.

## 9. Release gate

Koschei MUST NOT claim repository-wide representation separation until:

- every executable path that can expose semantic/runtime state is classified;
- faithful fallback representations are removed or explicitly trusted-only;
- stale epoch tests are driven by trusted Continuity state;
- release CI executes the representation-boundary adversarial suite;
- external red-team evidence exists for at least one realistic application.

Until then, status remains **experimental architecture with executable
invariants**, not a universal security guarantee.
