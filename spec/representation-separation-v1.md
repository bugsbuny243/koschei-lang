# Koschei Representation Separation V1

Status: **executable canonical/observable boundary with compiler-bound exact requests, shared Continuity, opaque one-shot materialization and constitutional Galaxy execution; not yet repository-wide**

Canonical vision: **GÖRÜNEN DÜNYA ≠ GERÇEK DÜNYA / OBSERVABLE WORLD != CANONICAL WORLD**

## 1. Boundary

V1 distinguishes:

1. **Checked Compiler MIR** — sealed `MirGraph`; trusted compiler authority/effect evidence.
2. **Compiler Capability Basis** — one exact direct capability call derived from checked compiler MIR; non-authoritative provenance.
3. **Canonical Semantic MIR** — sealed `NativeSigilMir`; trusted canonical Universe state.
4. **Canonical Semantic Seal** — trusted identity of canonical semantic MIR.
5. **Observable Representation** — non-faithful Nyr v2 surface.
6. **Continuity Epoch Authority** — one typed liveness truth used by observer, reconstruction and materialization.
7. **Compiler-Bound Canonical Effect Request** — request whose privileged operation is derived from compiler capability evidence rather than caller naming.
8. **Exact-Request Reconstruction Grant** — one request/context/epoch materialization capability.
9. **Reconstruction Consumption Receipt** — authenticated evidence that one grant context was consumed.
10. **Canonical Materialization Handle** — opaque one-shot request/Veyra-bound capability.
11. **Trusted Materialization Registry** — hidden custody of canonical MIR/raw request/Veyra relation.
12. **Compiler-Bound Domain Constraint** — deny-only exact-request check tying request operation to compiler capability type/method/effect/domain.
13. **Galaxy Constitutional Effect Path** — existing Khar/Aevra/Matrix/Hara/Sathra/durable-claim critical execution authority.

Observer-facing representation, reconstruction grant and materialization handle must not carry canonical sigil names, canonical subjects, semantic-domain labels, source locations, MIR fingerprint, Universe-plan digest, Veyra identity, canonical semantic seal or raw canonical-request digest.

Compiler capability provenance is trusted-side evidence and must not become observer authority.

## 2. Representation derivation

```text
Native Koschei source intent
-> canonical semantic checking
-> sealed NativeSigilMir                 [canonical]
-> CanonicalSemanticSealV1              [trusted]
-> Nur visibility envelope
-> Nyr v2 non-faithful projection       [observable]
```

Nyr aliases are observer/session/epoch/Veyra scoped. Projection integrity does not imply current liveness.

## 3. Compiler-bound authority identity

The ordinary checked compiler path derives canonical capability effects from `capability_effect_contract_v1`, seals the checked `EffectReport` into `MirGraph`, and no longer lets MIR independently re-infer capability effects using the older AST effect engine.

For privileged bootstrap request issuance, `CompilerCapabilityEffectBasisV1` derives one exact direct capability call from sealed compiler MIR. V1 accepts only one unambiguous leaf function with exactly one direct canonical capability call and no local/imported call indirection.

`seal_compiler_bound_effect_request_v1(...)` sets:

`CanonicalEffectRequest.operation = compiler_basis.canonical_effect`

The caller does not choose capability type, capability method, power domain, or privileged operation label.

Ambiguous or transitive shapes fail closed instead of being guessed.

## 4. One Continuity truth

`ContinuityEpochAuthorityV1` is shared by sanctioned Nyr observation, exact-request reconstruction and materialization effect admission. There is no separate raw `epoch_source` on those gate constructors.

If shared Continuity advances from E to E+1, an E-bound Nyr surface, reconstruction request and materialization handle all become stale.

The Python interface does not prove monotonic time. A malicious or rolled-back underlying reader can cause all three gates to agree on stale reality.

## 5. Exact-request reconstruction

```text
ObservableRepresentationV1
+ hidden MIR
+ compiler-bound CanonicalEffectRequest
+ Veyra / observer / session / visibility epoch
+ reconstruction key
-> opaque request binding
-> ReconstructionGrantV1
```

The raw request digest is not stored in the grant. A grant for request A cannot authorize request B even when all other context matches.

## 6. Single-use materialization

```text
exact-request grant
+ shared Continuity current epoch
-> live/equivalent reconstruction check
-> atomic grant consumption
-> ReconstructionConsumptionReceiptV1
-> opaque CanonicalMaterializationHandleV1
```

Canonical MIR stays inside `CanonicalMaterializationRegistryV1`. The registry also retains the reconstruction Veyra relation. The handle uses a separate keyed request+Veyra binding while exposing neither raw request nor raw Veyra identity.

## 7. Compiler-bound constitutional request execution

```text
CompilerCapabilityEffectBasisV1
+ exact CanonicalEffectRequest
-> RequestCapabilityDomainConstraintV1
   [compiler_bound=True / deny_only=True / authority=False]

opaque materialization handle
+ same CanonicalEffectRequest
+ same reconstruction Veyra via Galaxy context
+ compiler-bound domain constraint
+ RequestBoundProof
+ NativeSigilProofBundle
+ shared Continuity current epoch
-> domain/request provenance check
-> exact request/Veyra/liveness check
-> atomic handle consumption
-> hidden MIR resolution inside trusted registry
-> enforce_galaxy_critical_effect(...)
   -> canonical Khar
   -> living Aevra
   -> current Matrix/Hara
   -> exact 6/6 Sathra
   -> failure-root independence
   -> exact request-bound proof
   -> durable atomic claim/finality
-> ALLOW / DENY / CONTAIN
```

The sanctioned materialization gate does not directly call a weaker native effect helper. The callback receives the sealed request, never canonical MIR.

`GalaxyMaterializationContextV1` is not authority. It is only a typed transport bundle for existing Galaxy constitutional inputs.

PR #260 `PowerGrant` / `CrossDomainPermit` are not part of this path. Only the same-domain default-deny invariant was extracted.

## 8. Required invariants

- **R1 Non-faithful observation:** visible Nyr is not a direct canonical naming map.
- **R2 Context rotation:** Veyra/session/epoch changes rotate visible mappings where Nyr provides rotation.
- **R3 Tamper non-promotion:** changing visible representation cannot become canonical state.
- **R4 Reconstruction is not inversion:** trusted runtime authorizes already-custodied hidden state; it does not decode Nyr into source.
- **R5 One Continuity truth:** observer/reconstruction/materialization use the same typed lifecycle authority contract.
- **R6 Epoch death:** old surface/grant/request/handle cannot authorize a later epoch.
- **R7 Veyra/session non-transferability:** reconstruction/materialization context does not transfer across living Galaxies/sessions.
- **R8 Purpose binding:** `execute` does not become `inspect`.
- **R9 Exact request binding:** request binding begins at grant issuance and survives receipt/handle/effect admission.
- **R10 Single-use transition:** one grant context mints at most one handle per authoritative ledger; one handle resolves at most once per registry.
- **R11 Canonical non-export:** sanctioned reconstruction/effect APIs do not return `NativeSigilMir` to broad runtime.
- **R12 Constitutional non-bypass:** privileged materialized execution must enter the existing Khar/Galaxy critical-effect path; no weaker sanctioned sibling path may exist.
- **R13 Critical-event one-shot:** once Galaxy execution reaches its durable atomic claim, exact critical-event replay remains rejected by the existing coordinator.
- **R14 Compiler authority binding:** sanctioned privileged request operation/capability identity comes from checked compiler evidence, not runtime-selected relabeling.
- **R15 Ambiguity fails closed:** until call-site identity is first-class normalized MIR, multiple/transitive/imported capability provenance cannot be guessed into one privileged request.
- **R16 Domain constraint is deny-only:** compiler/domain provenance can reject execution but cannot create ALLOW or authority by itself.

## 9. PROTECTS AGAINST

- faithful canonical naming exposure through this Nyr path;
- replay of stale Nyr surfaces through sanctioned observation;
- independent arbitrary epoch callbacks disagreeing across liveness boundaries;
- forged visible representation becoming canonical state;
- runtime-selected privileged operation/capability relabeling after compiler checking;
- ambiguous capability call-sites being guessed into one privileged authority identity in bootstrap V1;
- accidental capability-contract cross-domain drift;
- cross-Veyra/session/purpose substitution;
- widening a reconstruction grant to another canonical request;
- raw request digest or Veyra identity exposure in grant/handle;
- repeated/concurrent reconstruction in one process-local ledger;
- repeated handle use in one process-local registry;
- bypassing Khar/Aevra/Matrix/Hara/Sathra admission through sanctioned materialization;
- exact critical-event replay covered by Galaxy's durable coordinator;
- ordinary broad-runtime receipt of canonical MIR through sanctioned APIs.

## 10. DOES NOT PROTECT AGAINST

- compromised or rolled-back underlying Continuity state;
- full trusted-process/registry compromise;
- direct Python use/construction of lower-level helpers or internal dataclasses;
- deterministic compiler-basis object forgery by code already executing inside the Python TCB;
- process restart/fork/snapshot rollback of in-memory reconstruction/materialization state;
- memory scraping, debugger/tracing, crash dumps or other leakage channels;
- leaked veil/reconstruction/receipt/materialization keys;
- malicious compiler/proof/Galaxy logic inside the TCB;
- false failure-root-independence claims backed by correlated infrastructure;
- OS/hardware compromise outside this prototype;
- semantic inference through other side channels;
- native/backend paths that ignore compiler-bound provenance;
- legitimate multi-call/transitive privileged functions, which bootstrap V1 currently rejects.

## 11. ASSUMPTIONS

- checked compiler `MirGraph` + Typed-HIR evidence are trustworthy compiler products;
- `capability_effect_contract_v1` remains the single canonical capability/effect source;
- compiler-bound request issuance is used instead of low-level manual Python constructors;
- NativeSigilMir/Veyra/Aevra/Matrix/Hara/request/proof/Sathra seals remain trustworthy;
- Nur visibility context is authentic, allowed and authority-free;
- one production Continuity source backs all sanctioned liveness gates;
- durable Galaxy stores preserve their claimed atomic/current-state semantics;
- trust-role keys remain separated;
- production keeps raw MIR/request/Veyra relation in a trusted compartment;
- durable/shared monotonic reconstruction state is added where restart/fork/rollback matters.

## 12. FAILURE MODES

Shared Continuity solves internal time disagreement, not rollback. Python privacy is conventional. Deterministic compiler provenance seals are not secret-key authenticity. Any sanctioned runtime/debug/backend surface that exports faithful canonical state, independently relabels compiler-known authority, or skips Galaxy/Khar invalidates the repository-wide separation claim.

## 13. Non-claims

V1 does not claim source can never be seen, Koschei is unhackable, Nyr encrypts all semantics, runtime execution is fully ephemeral, compiler basis objects are physically unforgeable inside the Python TCB, failure roots are physically independent merely because a proof object exists, or process/hardware isolation is proven.

## 14. NEXT

1. Make exact capability call-site identity a first-class normalized MIR fact instead of deriving it by walking sealed AST fallback.
2. Prove interpreter/native/backend consumers use the same normalized capability call-site identity.
3. Continue shrinking legacy semantic/AST compatibility authority.
4. Move compiler/runtime provenance and canonical custody into stronger native/durable isolation.
5. Make debugger/introspection/runtime rendering observer-safe by default.
6. Add release validation proving sanctioned privileged execution cannot bypass Galaxy/Khar.

## 15. Release gate

Koschei must not claim repository-wide representation separation until every executable surface that can reveal semantic/runtime state is classified, faithful fallback outputs are removed or trusted-only, compiler/runtime provenance crosses a stronger trust boundary, production Continuity is authoritative/rollback-aware, sanctioned privileged paths converge on Galaxy/Khar, canonical adversarial validation runs, and realistic external red-team evidence exists.
