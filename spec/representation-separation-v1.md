# Koschei Representation Separation V1

Status: **executable canonical/observable boundary with exact-request grant + single-use materialization; not yet wired into every runtime path**

Canonical vision revision: **25 Aug 2026 — `GÖRÜNEN DÜNYA ≠ GERÇEK DÜNYA`**

## 1. Purpose

Koschei's primary representation law is:

> **OBSERVABLE WORLD != CANONICAL WORLD**

This specification turns that law into an executable contract around sealed native sigil
MIR, Nur/Nyr v2 and trusted canonical materialization.

The goal is not to claim that canonical semantics can never be recovered. The goal is to
ensure that normal observer/runtime surfaces do not receive a faithful stable copy of the
canonical semantic world and that crossing back into that world requires narrow,
time-bound, exact-request-bound runtime authority.

## 2. Boundary

V1 now distinguishes:

1. **Canonical Semantic MIR** — sealed `NativeSigilMir`; trusted compartment.
2. **Canonical Semantic Seal** — trusted identity of that MIR.
3. **Observable Representation** — non-faithful Nyr v2 surface; observer side.
4. **Exact-Request Reconstruction Grant** — scoped permission to request materialization for one sealed request.
5. **Reconstruction Consumption Receipt** — proof one exact-request grant context was consumed.
6. **Canonical Materialization Handle** — opaque one-shot capability for that same sealed request.
7. **Trusted Materialization Registry** — hidden custody of canonical MIR and raw request identity.
8. **Request-Bound Effect Gate** — consumes the handle and evaluates one exact effect without exporting MIR.

The observer-facing representation, reconstruction grant and materialization handle MUST
NOT carry canonical sigil names, canonical subjects, semantic-domain labels, source
locations, MIR fingerprints, Universe-plan digest, Veyra identity, canonical semantic seal
digest or raw canonical-request digest.

## 3. Representation derivation

```text
Native source
  -> canonical semantic checking
  -> sealed NativeSigilMir                         [trusted]
  -> CanonicalSemanticSealV1                      [trusted]
  -> Nur visibility envelope
  -> Nyr v2 non-faithful projection
  -> ObservableRepresentationV1                   [observer]
```

`ObservableRepresentationV1.representation_digest` is HMAC-bound to hidden canonical
state, Veyra, observer, session, epoch and Nyr surface. The canonical seal itself is not
embedded in the observer-facing object.

## 4. Exact-request reconstruction

```text
ObservableRepresentationV1
+ hidden MIR
+ sealed CanonicalEffectRequest
+ Veyra / observer / session / epoch
+ reconstruction key
-> opaque request binding
-> ReconstructionGrantV1
```

Grant issuance requires the exact `CanonicalEffectRequest`. The grant stores an opaque
HMAC request binding rather than the raw canonical request digest. That binding is scoped
to the current Veyra, observer, session and visibility epoch, reducing direct correlation
across customer/session contexts.

The grant context digest binds the opaque request binding together with canonical semantic
seal, Veyra, observer/session, epoch/expiry, grant id and purpose.

## 5. Materialization path

```text
ObservableRepresentationV1
+ hidden MIR
+ exact-request ReconstructionGrantV1
+ same sealed CanonicalEffectRequest
+ trusted epoch
-> validate exact live context/request
-> consume reconstruction context once
-> ReconstructionConsumptionReceiptV1
-> CanonicalMaterializationHandleV1              [runtime-safe]
-> trusted registry retains hidden MIR + raw request identity
```

The consumption receipt carries the opaque grant request binding as authenticated
provenance. The handle uses a separate materialization-key request binding and contains no
raw request digest, canonical MIR identity or naming map.

## 6. Request-bound execution

```text
CanonicalMaterializationHandleV1
+ same CanonicalEffectRequest
+ RequestBoundProof
+ NativeSigilProofBundle
+ trusted epoch
-> recompute keyed materialization request binding
-> consume handle once
-> resolve hidden MIR inside trusted registry
-> verify exact request/proof/MIR binding
-> ALLOW / DENY / CONTAIN
-> effect callback only for ALLOW
```

The callback receives the sealed request, not canonical MIR.

## 7. Required invariants

### R1 — Non-faithful observation
The observable representation MUST NOT contain a direct canonical naming map.

### R2 — Context rotation
Another Veyra/session/epoch SHOULD produce another visible mapping where Nyr rotation
provides it.

### R3 — Tamper non-promotion
Changing visible representation MUST NOT modify or become canonical semantic state.

### R4 — Reconstruction is not inversion
Trusted reconstruction uses already-custodied hidden MIR; it does not decode Nyr back into
source/canonical semantics.

### R5 — Epoch death
Old representation, grant, request or handle MUST NOT authorize a later epoch.

### R6 — Veyra/session non-transferability
A reconstruction grant minted in one hidden/visibility context MUST NOT transfer to
another.

### R7 — Purpose binding
An `execute` reconstruction MUST NOT become `inspect` authority.

### R8 — Exact request binding starts at grant issuance
A grant minted for request A MUST NOT authorize request B even if MIR, Veyra, epoch and
purpose match. The raw canonical request digest MUST NOT be exposed in the grant.

### R9 — Single-use materialization
One grant context may mint at most one handle through one authoritative ledger; one handle
may resolve hidden MIR at most once through one authoritative registry.

### R10 — Exact request binding survives materialization
The materialization handle MUST remain keyed-bound to the same sealed
`CanonicalEffectRequest` while keeping the raw request identity on the trusted side.
Cross-request substitution MUST fail before hidden MIR is released to effect evaluation.

### R11 — Canonical non-export
Sanctioned reconstruction/effect APIs MUST NOT return `NativeSigilMir` to the broad runtime.

## 8. PROTECTS AGAINST

- faithful exposure of canonical sigil/subject/domain names through this path;
- stale visible mappings authorizing later-epoch materialization;
- forged visible representations becoming canonical state;
- cross-Veyra/session/purpose substitution;
- widening a reconstruction grant from one canonical request to another request;
- direct correlation through a raw canonical-request digest carried in the grant or handle;
- repeated/concurrent reconstruction through one authoritative ledger;
- authenticated-consumption receipt request-binding tamper;
- repeated handle use through one authoritative registry;
- changing effect id/subject/operation/payload/identity/epoch/nonce after grant/handle minting;
- moving one native proof to another sealed request through the materialization gate;
- ordinary broad-runtime receipt of canonical MIR from sanctioned APIs.

## 9. DOES NOT PROTECT AGAINST

- full compromise of the trusted process/registry while canonical MIR is resident;
- direct Python imports of low-level reconstruction/private registry helpers;
- process restart/fork/snapshot rollback of in-memory replay/materialization state;
- memory scraping, crash dumps, debugger/tracing or unclassified canonical-output paths;
- leaked veil/reconstruction/receipt/materialization keys;
- malicious compiler/native proof/request-binding code inside the trusted boundary;
- OS/hardware compromise outside this prototype's assumptions;
- semantic inference through correlated side channels.

## 10. ASSUMPTIONS

- `NativeSigilMir.assert_sealed()`, Veyra, canonical request and request-bound proof logic remain trustworthy;
- Nur visibility input is allowed and authority-free;
- reconstruction/materialization trust-role keys remain separated and secret;
- production epoch truth comes from authoritative Koschei Continuity state;
- production keeps registry/raw MIR/raw request identity inside a compartment inaccessible to observer APIs;
- production provides durable/shared monotonic replay state where multiple processes or restarts matter.

## 11. FAILURE MODES

- Python privacy is conventional, not physical; callers with trusted-process access can inspect registry internals;
- restart/fork/rollback can forget in-memory consumption state;
- canonical MIR leaked through logs/diagnostics/crash dumps bypasses the boundary;
- any sanctioned runtime API that returns faithful MIR invalidates the repository-wide representation-separation claim;
- a compromised compiler/proof boundary can produce internally consistent but malicious canonical reality.

## 12. What V1 does not claim

V1 does **not** claim:

- source code can never be seen;
- Koschei is unhackable;
- Nyr encrypts all semantics;
- all runtime execution is already ephemeral;
- all compiler/runtime/debug paths already preserve the boundary;
- process/hardware isolation is proven by this Python prototype.

## 13. Required next integration

1. replace callable epoch sources with one sealed Continuity epoch authority;
2. absorb PR #264 Nyr observation liveness into the same Continuity/representation lifecycle;
3. move reconstruction/handle consumption to durable monotonic runtime custody;
4. add compartment identity and revocation to materialization handles;
5. make debugger/introspection/runtime rendering observer-safe by default;
6. carry registry custody into native execution so raw MIR never crosses the compartment ABI;
7. extend representation separation from sigil MIR to general function/closure MIR;
8. add release validation proving sanctioned runtime APIs do not return raw MIR;
9. add adversarial tests for correlation, replay, cross-session laundering and diagnostic leakage.

## 14. Release gate

Koschei MUST NOT claim repository-wide representation separation until every executable
surface that can reveal semantic/runtime state is classified, faithful fallback outputs are
removed or trusted-only, Continuity drives epoch truth, canonical validation executes the
adversarial suite, and at least one realistic external red-team exercise exists.

Until then the status remains **experimental architecture with executable invariants**, not
a universal security guarantee.
