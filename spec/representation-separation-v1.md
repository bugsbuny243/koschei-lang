# Koschei Representation Separation V1

Status: **executable canonical/observable boundary with exact-request grants, shared Continuity, opaque one-shot materialization and constitutional Galaxy execution; not yet repository-wide**

Canonical vision: **GÖRÜNEN DÜNYA ≠ GERÇEK DÜNYA / OBSERVABLE WORLD != CANONICAL WORLD**

## 1. Boundary

V1 distinguishes:

1. **Canonical Semantic MIR** — sealed `NativeSigilMir`; trusted side.
2. **Canonical Semantic Seal** — trusted identity of that MIR.
3. **Observable Representation** — non-faithful Nyr v2 surface.
4. **Continuity Epoch Authority** — one typed liveness truth used by observer, reconstruction and materialization.
5. **Exact-Request Reconstruction Grant** — one request/context/epoch materialization capability.
6. **Reconstruction Consumption Receipt** — authenticated evidence that one grant context was consumed.
7. **Canonical Materialization Handle** — opaque one-shot request/Veyra-bound capability.
8. **Trusted Materialization Registry** — hidden custody of canonical MIR/raw request/Veyra relation.
9. **Galaxy Constitutional Effect Path** — the existing Khar/Aevra/Matrix/Hara/Sathra/durable-claim critical execution authority.

Observer-facing representation, reconstruction grant and materialization handle must not carry canonical sigil names, canonical subjects, semantic-domain labels, source locations, MIR fingerprint, Universe-plan digest, Veyra identity, canonical semantic seal or raw canonical-request digest.

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

## 3. One Continuity truth

`ContinuityEpochAuthorityV1` is shared by sanctioned Nyr observation, exact-request reconstruction and materialization effect admission. There is no separate raw `epoch_source` on those gate constructors.

If shared Continuity advances from E to E+1, an E-bound Nyr surface, reconstruction request and materialization handle all become stale.

The Python interface does not prove monotonic time. A malicious or rolled-back underlying reader can cause all three gates to agree on stale reality.

## 4. Exact-request reconstruction

```text
ObservableRepresentationV1
+ hidden MIR
+ sealed CanonicalEffectRequest
+ Veyra / observer / session / visibility epoch
+ reconstruction key
-> opaque request binding
-> ReconstructionGrantV1
```

The raw request digest is not stored in the grant. A grant for request A cannot authorize request B even when all other context matches.

## 5. Single-use materialization

```text
exact-request grant
+ shared Continuity current epoch
-> live/equivalent reconstruction check
-> atomic grant consumption
-> ReconstructionConsumptionReceiptV1
-> opaque CanonicalMaterializationHandleV1
```

Canonical MIR stays inside `CanonicalMaterializationRegistryV1`. The registry also retains the reconstruction Veyra relation. The handle uses a separate keyed request+Veyra binding while exposing neither raw request nor raw Veyra identity.

## 6. Constitutional request-bound execution

```text
opaque materialization handle
+ same CanonicalEffectRequest
+ same reconstruction Veyra via Galaxy context
+ RequestBoundProof
+ NativeSigilProofBundle
+ shared Continuity current epoch
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

## 7. Required invariants

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

## 8. PROTECTS AGAINST

- faithful canonical naming exposure through this Nyr path;
- replay of stale Nyr surfaces through sanctioned observation;
- independent arbitrary epoch callbacks disagreeing across liveness boundaries;
- forged visible representation becoming canonical state;
- cross-Veyra/session/purpose substitution;
- widening a reconstruction grant to another canonical request;
- raw request digest or Veyra identity exposure in grant/handle;
- repeated/concurrent reconstruction in one process-local ledger;
- repeated handle use in one process-local registry;
- bypassing Khar/Aevra/Matrix/Hara/Sathra admission through sanctioned materialization;
- exact critical-event replay covered by Galaxy's durable coordinator;
- ordinary broad-runtime receipt of canonical MIR through sanctioned APIs.

## 9. DOES NOT PROTECT AGAINST

- compromised or rolled-back underlying Continuity state;
- full trusted-process/registry compromise;
- direct Python use of lower-level/private helpers;
- process restart/fork/snapshot rollback of in-memory reconstruction/materialization state;
- memory scraping, debugger/tracing, crash dumps or other leakage channels;
- leaked veil/reconstruction/receipt/materialization keys;
- malicious compiler/proof/Galaxy logic inside the TCB;
- false failure-root-independence claims backed by correlated infrastructure;
- OS/hardware compromise outside this prototype;
- semantic inference through other side channels.

## 10. ASSUMPTIONS

- MIR/Veyra/Aevra/Matrix/Hara/request/proof/Sathra seals remain trustworthy;
- Nur visibility context is authentic, allowed and authority-free;
- one production Continuity source backs all sanctioned liveness gates;
- durable Galaxy stores preserve their claimed atomic/current-state semantics;
- trust-role keys remain separated;
- production keeps raw MIR/request/Veyra relation in a trusted compartment;
- durable/shared monotonic reconstruction state is added where restart/fork/rollback matters.

## 11. FAILURE MODES

Shared Continuity solves internal time disagreement, not rollback. Python privacy is conventional. Any sanctioned runtime/debug/backend surface that exports faithful canonical state or any privileged execution route that skips Galaxy/Khar invalidates the repository-wide separation claim.

## 12. Non-claims

V1 does not claim source can never be seen, Koschei is unhackable, Nyr encrypts all semantics, runtime execution is fully ephemeral, failure roots are physically independent merely because a proof object exists, or process/hardware isolation is proven.

## 13. NEXT

1. Inspect PR #260 and extract only the minimal request-bound cross-domain default-deny invariant that closes a real Galaxy capability-escalation gap.
2. Consolidate that invariant with the canonical compiler/MIR/runtime capability model instead of creating another permit authority.
3. Move reconstruction/handle consumption to durable monotonic runtime custody.
4. Make debugger/introspection/runtime rendering observer-safe by default.
5. Carry canonical custody into native execution.
6. Add release validation proving sanctioned privileged execution cannot bypass Galaxy/Khar.

## 14. Release gate

Koschei must not claim repository-wide representation separation until every executable surface that can reveal semantic/runtime state is classified, faithful fallback outputs are removed or trusted-only, production Continuity is authoritative/rollback-aware, sanctioned privileged paths converge on Galaxy/Khar, canonical adversarial validation runs, and realistic external red-team evidence exists.
