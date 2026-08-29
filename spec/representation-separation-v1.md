# Koschei Representation Separation V1

Status: **executable canonical/observable boundary with exact-request grants, shared Continuity liveness and opaque one-shot materialization; not yet repository-wide**

Canonical vision: **GÖRÜNEN DÜNYA ≠ GERÇEK DÜNYA / OBSERVABLE WORLD != CANONICAL WORLD**

## 1. Boundary

V1 distinguishes:

1. **Canonical Semantic MIR** — sealed `NativeSigilMir`; trusted side.
2. **Canonical Semantic Seal** — trusted identity of that MIR.
3. **Observable Representation** — non-faithful Nyr v2 surface.
4. **Continuity Epoch Authority** — one typed liveness truth used by observer, reconstruction and materialization gates.
5. **Exact-Request Reconstruction Grant** — one request/context/epoch materialization capability.
6. **Reconstruction Consumption Receipt** — authenticated evidence that one grant context was consumed.
7. **Canonical Materialization Handle** — opaque one-shot capability for the same request.
8. **Trusted Materialization Registry** — hidden custody of canonical MIR/raw request identity.
9. **Request-Bound Effect Gate** — resolves canonical state inside the trusted boundary and evaluates one exact request.

Observer-facing representation, reconstruction grant and materialization handle must not
carry canonical sigil names, canonical subjects, semantic-domain labels, source locations,
MIR fingerprint, Universe-plan digest, Veyra identity, canonical semantic seal or raw
canonical-request digest.

## 2. Representation derivation

```text
Native Koschei source intent
-> canonical semantic checking
-> sealed NativeSigilMir                 [canonical]
-> CanonicalSemanticSealV1              [trusted]
-> Nur visibility envelope
-> Nyr v2 non-faithful projection       [observable]
```

Nyr aliases are observer/session/epoch/Veyra scoped. Projection integrity does not imply
current liveness.

## 3. One Continuity truth

`ContinuityEpochAuthorityV1` is shared by sanctioned:

- Nyr observation;
- exact-request reconstruction;
- materialization effect admission.

There is no separate `epoch_source` callback on those gate constructors.

If shared Continuity advances from epoch E to E+1:

- an E-bound Nyr surface is stale;
- an E-bound canonical request/reconstruction is stale;
- an E-bound materialization handle is stale.

This gives one lifecycle answer rather than three caller-selected clocks.

The Python interface does not prove monotonic time. A malicious/rolled-back underlying
reader can cause all three gates to agree on stale reality.

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

The raw request digest is not stored in the grant. A grant for request A cannot authorize
request B even when all other visible context matches.

## 5. Single-use materialization

```text
exact-request grant
+ shared Continuity current epoch
-> live/equivalent reconstruction check
-> atomic grant consumption
-> ReconstructionConsumptionReceiptV1
-> opaque CanonicalMaterializationHandleV1
```

Canonical MIR stays inside `CanonicalMaterializationRegistryV1`.

The handle uses a separate keyed request binding and contains no raw canonical request
identity. One handle may resolve the hidden world only once through one authoritative
registry.

## 6. Request-bound execution

```text
opaque handle
+ same CanonicalEffectRequest
+ RequestBoundProof
+ NativeSigilProofBundle
+ shared Continuity current epoch
-> exact request/liveness check
-> atomic handle consumption
-> hidden MIR resolution inside trusted registry
-> ALLOW / DENY / CONTAIN
-> effect callback only for ALLOW
```

The callback receives the sealed request, not canonical MIR.

## 7. Required invariants

- **R1 Non-faithful observation:** visible Nyr is not a direct canonical naming map.
- **R2 Context rotation:** Veyra/session/epoch changes rotate visible mappings where Nyr provides rotation.
- **R3 Tamper non-promotion:** changing visible representation cannot become canonical state.
- **R4 Reconstruction is not inversion:** trusted runtime authorizes already-custodied hidden state; it does not decode Nyr into source.
- **R5 One Continuity truth:** observer/reconstruction/materialization sanctioned gates use the same typed lifecycle authority contract.
- **R6 Epoch death:** old surface/grant/request/handle cannot authorize a later epoch.
- **R7 Veyra/session non-transferability:** reconstruction context does not transfer across living Galaxies/sessions.
- **R8 Purpose binding:** `execute` does not become `inspect`.
- **R9 Exact request binding:** request binding begins at reconstruction-grant issuance and survives receipt/handle/effect admission.
- **R10 Single-use transition:** one grant context mints at most one handle per authoritative ledger; one handle resolves at most once per registry.
- **R11 Canonical non-export:** sanctioned reconstruction/effect APIs do not return `NativeSigilMir` to broad runtime.

## 8. PROTECTS AGAINST

- faithful canonical naming exposure through this Nyr path;
- replay of stale Nyr surfaces through the sanctioned observation gate;
- independent arbitrary epoch callbacks disagreeing across liveness boundaries;
- forged visible representation becoming canonical state;
- cross-Veyra/session/purpose substitution;
- widening a reconstruction grant to another canonical request;
- raw request digest exposure in grant/handle;
- repeated/concurrent reconstruction in one process-local ledger;
- repeated handle use in one process-local registry;
- moving native proof to another sealed request through this gate;
- ordinary broad-runtime receipt of canonical MIR through sanctioned APIs.

## 9. DOES NOT PROTECT AGAINST

- compromised or rolled-back underlying Continuity state;
- full trusted-process/registry compromise;
- direct Python use of lower-level/private helpers;
- process restart/fork/snapshot rollback of in-memory replay state;
- memory scraping, debugger/tracing, crash dumps or other leakage channels;
- leaked veil/reconstruction/receipt/materialization keys;
- malicious compiler/proof/request-binding logic inside the TCB;
- OS/hardware compromise outside this prototype;
- semantic inference through other correlated side channels.

## 10. ASSUMPTIONS

- MIR/Veyra/request/proof seals remain trustworthy;
- Nur visibility context is authentic, allowed and authority-free;
- one production Continuity source backs all sanctioned liveness gates;
- trust-role keys remain separated;
- production keeps raw MIR/request identity in a trusted compartment;
- durable/shared monotonic state is added where restart/fork/rollback matters.

## 11. FAILURE MODES

Shared Continuity solves internal time disagreement, not rollback. If the underlying state
is restored to an older valid epoch, all three gates can accept that stale reality.

Python privacy is conventional. Any sanctioned runtime/debug/backend surface that exports
faithful canonical MIR or bypasses these gates invalidates the repository-wide
representation-separation claim.

## 12. Non-claims

V1 does not claim source can never be seen, Koschei is unhackable, Nyr encrypts all
semantics, runtime execution is already fully ephemeral, or process/hardware isolation is
proven.

## 13. NEXT

1. Connect existing Khar/Galaxy/Matrix/Hara and relevant power-domain admission to the same exact request-bound execution path.
2. Move reconstruction/handle consumption to durable monotonic runtime custody.
3. Add compartment identity/revocation.
4. Make debugger/introspection/runtime rendering observer-safe by default.
5. Carry canonical custody into native execution.
6. Extend representation separation from sigil MIR to general function/closure MIR.
7. Add release validation proving sanctioned runtime APIs do not return raw MIR.

## 14. Release gate

Koschei must not claim repository-wide representation separation until every executable
surface that can reveal semantic/runtime state is classified, faithful fallback outputs
are removed or trusted-only, production Continuity is authoritative/rollback-aware,
canonical adversarial validation runs, and realistic external red-team evidence exists.
