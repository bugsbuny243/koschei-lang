# Koschei Representation Separation V1

Status: **executable canonical/observable boundary with single-use exact-request materialization; not yet wired into every runtime path**

Canonical vision revision: **25 Aug 2026 — `GÖRÜNEN DÜNYA ≠ GERÇEK DÜNYA`**

## 1. Purpose

Koschei's primary representation law is:

> **OBSERVABLE WORLD != CANONICAL WORLD**

This specification turns that law into an executable contract around sealed native sigil
MIR, Nur/Nyr v2 and trusted canonical materialization.

The goal is not to claim that canonical semantics can never be recovered. The goal is to
ensure that normal observer/runtime surfaces do not receive a faithful stable copy of the
canonical semantic world and that crossing back into that world requires narrow,
time-bound, request-bound runtime authority.

## 2. Boundary

V1 now distinguishes:

1. **Canonical Semantic MIR** — sealed `NativeSigilMir`; trusted compartment.
2. **Canonical Semantic Seal** — trusted identity of that MIR.
3. **Observable Representation** — non-faithful Nyr v2 surface; observer side.
4. **Reconstruction Grant** — scoped permission to request materialization.
5. **Reconstruction Consumption Receipt** — proof one grant context was consumed.
6. **Canonical Materialization Handle** — opaque one-shot capability for one exact sealed request.
7. **Trusted Materialization Registry** — hidden custody of canonical MIR and raw request identity.
8. **Request-Bound Effect Gate** — consumes the handle and evaluates one exact effect without exporting MIR.

The observer-facing representation and materialization handle MUST NOT carry canonical
sigil names, canonical subjects, semantic-domain labels, source locations, MIR
fingerprints, Universe-plan digest, Veyra identity, canonical semantic seal digest or raw
canonical-request digest.

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

## 4. Materialization path

```text
ObservableRepresentationV1
+ hidden MIR
+ ReconstructionGrantV1
+ sealed CanonicalEffectRequest
+ trusted epoch
-> validate exact live context
-> consume reconstruction context once
-> ReconstructionConsumptionReceiptV1
-> CanonicalMaterializationHandleV1              [runtime-safe]
-> trusted registry retains hidden MIR + raw request digest
```

The handle contains a random opaque id and a materialization-key HMAC of the sealed
request digest, but no raw request digest, canonical MIR identity or naming map.

## 5. Request-bound execution

```text
CanonicalMaterializationHandleV1
+ same CanonicalEffectRequest
+ RequestBoundProof
+ NativeSigilProofBundle
+ trusted epoch
-> recompute keyed request binding
-> consume handle once
-> resolve hidden MIR inside trusted registry
-> verify exact request/proof/MIR binding
-> ALLOW / DENY / CONTAIN
-> effect callback only for ALLOW
```

The callback receives the sealed request, not canonical MIR.

## 6. Required invariants

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

### R8 — Single-use materialization
One grant context may mint at most one handle through one authoritative ledger; one handle
may resolve hidden MIR at most once through one authoritative registry.

### R9 — Exact request binding
A materialization handle MUST be keyed-bound to one sealed `CanonicalEffectRequest` while
keeping the raw canonical request digest on the trusted side. Cross-request substitution
MUST fail before hidden MIR is released to effect evaluation.

### R10 — Canonical non-export
Sanctioned reconstruction/effect APIs MUST NOT return `NativeSigilMir` to the broad runtime.

## 7. PROTECTS AGAINST

- faithful exposure of canonical sigil/subject/domain names through this path;
- stale visible mappings authorizing later-epoch materialization;
- forged visible representations becoming canonical state;
- cross-Veyra/session/purpose substitution;
- repeated/concurrent reconstruction through one authoritative ledger;
- repeated handle use through one authoritative registry;
- direct correlation through a raw canonical-request digest carried in the handle;
- changing effect id/subject/operation/payload/identity/epoch/nonce after handle minting;
- moving one native proof to another sealed request through the materialization gate;
- ordinary broad-runtime receipt of canonical MIR from sanctioned APIs.

## 8. DOES NOT PROTECT AGAINST

- full compromise of the trusted process/registry while canonical MIR is resident;
- direct Python imports of low-level reconstruction/private registry helpers;
- process restart/fork/snapshot rollback of in-memory replay/materialization state;
- memory scraping, crash dumps, debugger/tracing or unclassified canonical-output paths;
- leaked veil/reconstruction/receipt/materialization keys;
- malicious compiler/native proof/request-binding code inside the trusted boundary;
- OS/hardware compromise outside this prototype's assumptions;
- semantic inference through correlated side channels or leaked materialization keys.

## 9. ASSUMPTIONS

- `NativeSigilMir.assert_sealed()`, Veyra, canonical request and request-bound proof logic remain trustworthy;
- Nur visibility input is allowed and authority-free;
- trust-role keys remain separated and secret;
- production epoch truth comes from authoritative Koschei Continuity state;
- production keeps registry/raw MIR/raw request identity inside a compartment inaccessible to observer APIs;
- production provides durable/shared monotonic replay state where multiple processes or restarts matter.

## 10. FAILURE MODES

- Python privacy is conventional, not physical; callers with trusted-process access can inspect registry internals;
- restart/fork/rollback can forget in-memory consumption state;
- canonical MIR leaked through logs/diagnostics/crash dumps bypasses the boundary;
- any sanctioned runtime API that returns faithful MIR invalidates the repository-wide representation-separation claim;
- a compromised compiler/proof boundary can produce internally consistent but malicious canonical reality.

## 11. What V1 does not claim

V1 does **not** claim:

- source code can never be seen;
- Koschei is unhackable;
- Nyr encrypts all semantics;
- all runtime execution is already ephemeral;
- all compiler/runtime/debug paths already preserve the boundary;
- process/hardware isolation is proven by this Python prototype.

## 12. Required next integration

1. replace callable epoch sources with sealed Continuity epoch authority;
2. move reconstruction/handle consumption to durable monotonic runtime custody;
3. add compartment identity and revocation to materialization handles;
4. make debugger/introspection/runtime rendering observer-safe by default;
5. carry registry custody into native execution so raw MIR never crosses the compartment ABI;
6. extend representation separation from sigil MIR to general function/closure MIR;
7. add release validation proving sanctioned runtime APIs do not return raw MIR;
8. add adversarial tests for correlation, replay, cross-session laundering and diagnostic leakage.

## 13. Release gate

Koschei MUST NOT claim repository-wide representation separation until every executable
surface that can reveal semantic/runtime state is classified, faithful fallback outputs are
removed or trusted-only, Continuity drives epoch truth, canonical validation executes the
adversarial suite, and at least one realistic external red-team exercise exists.

Until then the status remains **experimental architecture with executable invariants**, not
a universal security guarantee.
