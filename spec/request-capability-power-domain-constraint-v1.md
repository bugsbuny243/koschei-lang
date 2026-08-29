# Request-Bound Capability Power-Domain Constraint V1

Status: **implemented bootstrap prototype / compiler-derived leaf capability basis / deny-only invariant / native enforcement pending**

## Purpose

Koschei already has one canonical capability/effect authority in `capability_effect_contract_v1` and one constitutional privileged execution path through Khar/Galaxy. The experimental six-domain prototype in PR #260 contains one useful law that belongs in that existing model:

> Authority present in one power domain must not silently become authority in another power domain.

This specification extracts only that law. It does **not** import `PowerGrant`, `CrossDomainPermit`, or a second authorization system.

The important hardening in this revision is that runtime/bootstrap code no longer chooses a capability type/method pair for privileged admission. That relationship is derived from already sealed compiler MIR.

## Canonical power domains

The six names remain architectural classification dimensions:

- Identity
- Authority
- Data
- Compute
- Network
- Continuity

V1 only classifies capability types/effects that already exist in the canonical capability contract. Identity and Continuity are reserved domains but are not synthesized into new capability types by this slice.

Current canonical classifications include:

- `NetRoot` / `NetCaps` -> Network
- `DiskRoot` / `DiskCaps` / `DiskReadCaps` -> Data
- `EnvRoot` / `EnvCaps` -> Data
- `ProcessRoot` / `ProcessCaps` -> Compute
- `SystemCaps` -> Authority classification only; it is not a direct I/O capability

Canonical effects classify as:

- `net.io` -> Network
- `disk.read` / `disk.write` / `env.read` -> Data
- `process.exec` -> Compute

`authority.derive` is relative to the capability being narrowed. `NetRoot.allow` remains in Network, `DiskRoot.allow` remains in Data, and so on. Narrowing does not teleport authority into one ambient global authority domain.

## Deny-only law

`capability_effect_contract_v1.require_capability_method_same_power_domain(...)` is a negative invariant:

1. capability type must be canonical;
2. method must be canonical for that capability;
3. canonical effect is derived from the existing contract;
4. source capability power domain is derived from the same contract;
5. target effect power domain is derived from the same contract;
6. unknown/unclassified combinations fail closed;
7. source and target domains must be equal.

The function returns canonical effect/domain metadata only after those checks. It does not create permission.

A future contract edit such as conceptually mapping `NetCaps.get` to `disk.read` must therefore fail closed as Network -> Data escalation.

## Compiler capability basis

`CompilerCapabilityEffectBasisV1` is derived from sealed `MirGraph` plus its sealed Typed-HIR evidence.

V1 deliberately accepts only a narrow shape:

```text
one sealed compiler MirGraph
-> one unambiguous module
-> one unambiguous function
-> no local function calls
-> no imported function calls
-> exactly one direct canonical capability call-site
-> MirFunction.effects == exactly that canonical effect
-> same-domain canonical contract check
-> CompilerCapabilityEffectBasisV1
```

The basis records:

- compiler MIR fingerprint;
- module/function identity;
- exact capability type;
- exact capability method;
- canonical effect;
- power domain;
- source call-site line/column;
- deterministic basis digest;
- `direct_call=True`;
- `authority=False`.

This strict leaf-function rule is intentional. A broad function-level `net.io` summary does not tell us whether the privileged operation came from `NetCaps.get`, `post`, `request`, an imported function, or several call-sites. V1 refuses to guess. Explicit MIR call-site effect identities can relax this safely later.

The basis is a compiler provenance fact, not permission.

## Compiler-bound request issuance

`seal_compiler_bound_effect_request_v1(...)` is the sanctioned bootstrap issuance path.

The caller supplies business/request evidence:

- effect id;
- protected `vor` subject;
- payload digest;
- identity digest;
- epoch;
- nonce/replay digest.

The caller does **not** supply:

- `CanonicalEffectRequest.operation`;
- capability type;
- capability method;
- power domain.

Those fields come from `CompilerCapabilityEffectBasisV1`.

The issuance chain is:

```text
sealed compiler MIR
-> derive exact CompilerCapabilityEffectBasisV1
-> operation := compiler_basis.canonical_effect
-> seal CanonicalEffectRequest against native sigil MIR
-> bind RequestCapabilityDomainConstraintV1 to exact request + compiler basis
```

`CompilerBoundEffectRequestV1.assert_sealed(...)` can re-derive the basis from the supplied sealed compiler MIR and require exact equality.

## Exact-request constraint

`RequestCapabilityDomainConstraintV1` now contains a sealed `compiler_basis` and is marked:

- `compiler_bound=True`;
- `deny_only=True`;
- `authority=False`.

`bind_request_capability_domain_v1(...)` no longer accepts `capability_type=` or `capability_method=`. It accepts only `compiler_basis=`.

The constraint verifies:

- exact request digest;
- compiler basis seal;
- capability type/method/effect/domain equal the compiler basis;
- request operation equals the compiler-derived canonical effect;
- deterministic constraint seal.

It cannot emit ALLOW, mint authority, delegate authority, or create a cross-domain edge.

## Galaxy integration

`CanonicalMaterializationEffectGateV1` requires `RequestCapabilityDomainConstraintV1` and checks it before touching one-shot materialization state.

Order:

```text
compiler-derived exact capability basis
-> compiler-bound exact request
-> compiler-bound deny-only domain constraint
-> validate exact request + same-domain identity
-> shared Continuity current epoch
-> one-shot materialization consume
-> existing enforce_galaxy_critical_effect(...)
-> Khar / Aevra / Matrix / Hara / Sathra / request proof / atomic finality
-> ALLOW / DENY / CONTAIN
```

A malformed or foreign constraint therefore cannot burn an otherwise valid materialization handle.

The constraint is re-checked immediately before the privileged transition so canonical contract drift fails closed.

## Important bootstrap boundary

The compiler basis and constraint use deterministic structural seals, not a secret-key compiler signature.

At sanctioned issuance, `CompilerBoundEffectRequestV1.assert_sealed(...)` re-derives the basis from sealed compiler MIR. At the later materialization gate, the embedded basis self-seal and canonical capability contract are checked, but the full compiler `MirGraph` is not carried through the observer/runtime surface.

Therefore this prototype does **not** claim to stop a malicious caller already able to construct arbitrary internal Python dataclasses or invoke lower-level helpers inside the TCB. That remains part of the known Python bootstrap bypass class. A native compartment / compiler-runtime ABI must eventually make compiler-issued provenance non-forgeable across the trust boundary without exposing canonical MIR broadly.

## No cross-domain permit in V1

There is deliberately no `CrossDomainPermit` equivalent in the sanctioned path.

If Koschei later requires a legitimate cross-domain transition, it must be designed as a native constitutional transition bound to exact source authority, target effect, request, epoch, irreversible cost/evidence where appropriate, and Khar/Galaxy admission. It must not appear as a reusable side permit that bypasses `vor` or the canonical capability contract.

## PROTECTS AGAINST

- runtime/bootstrap callers selecting `ProcessCaps.run`, `NetCaps.get`, or another capability pair independently of compiler output;
- caller-selected privileged operation labels diverging from the compiler-derived canonical effect;
- ambiguous multiple capability call-sites being guessed into one request authority;
- local/imported call indirection being silently treated as exact call-site provenance in V1;
- accidental capability-contract edits that map one capability domain to an effect in another domain;
- unknown or unclassified capability/effect relationships silently passing domain admission;
- request A's domain constraint being reused for request B;
- introducing PR #260's parallel grant/permit authority model into the sanctioned #263 execution path;
- malformed/foreign domain constraints consuming a valid materialization handle before rejection.

## DOES NOT PROTECT AGAINST

- malicious code already inside the Python TCB directly forging internal dataclasses or invoking lower-level helpers;
- a malicious trusted compiler/runtime changing canonical capability semantics and all dependent checks together;
- host/process compromise, debugger access, memory scraping, crash dumps, side channels, or leaked keys;
- native/backend paths that do not consume the same compiler-bound request provenance;
- a privileged callback performing behavior different from the effect identity promised by a malicious TCB implementation;
- legitimate multi-call/transitive privileged functions, which V1 intentionally rejects rather than models incompletely;
- future legitimate cross-domain transitions, which are intentionally not implemented by this slice.

## ASSUMPTIONS

- `capability_effect_contract_v1` remains the single canonical capability/effect source of truth;
- sealed `MirGraph` and its Typed-HIR evidence are trustworthy compiler products;
- `CanonicalEffectRequest` sealing and request-bound proof logic remain trustworthy;
- production privileged execution enters through one sanctioned Khar/Galaxy ABI;
- compiler-bound request issuance is used instead of direct low-level Python constructors;
- unknown domain classifications remain fail closed.

## FAILURE MODE

The model fails if runtime code regains the ability to choose capability type/method independently of compiler evidence, if another subsystem can independently decide capability domains/effects, if a cross-domain permit system grows beside the canonical capability contract, or if privileged execution can skip the compiler-bound domain constraint and still reach a weaker execution path.

## TESTED STATUS

Regression tests are committed for:

- exact `NetCaps.get -> net.io -> Network` basis derivation from sealed compiler MIR;
- basis revalidation against the compiler MIR fingerprint/content;
- multiple direct capability call-sites failing closed as ambiguous;
- local-call indirection failing closed;
- imported-call indirection failing closed;
- compiler-bound exact request / `deny_only=True` / `authority=False`;
- simulated canonical-contract drift from Network capability to Data effect failing closed;
- foreign request constraint rejection before materialization handle consumption;
- non-canonical request-operation relabeling rejection;
- shared Continuity tests remaining on the compiler-bound domain-constrained Galaxy path.

These tests are **written and committed, not claimed passed** until a real `ks-local-validate --profile full` receipt exists for the current PR head.

## NEXT

1. carry compiler capability call-site identity as first-class normalized MIR instead of re-walking sealed AST fallback for provenance;
2. make the native/runtime ABI verify compiler-issued basis without relying on forgeable Python dataclass construction;
3. remove remaining compatibility capability authorities where safe;
4. ensure native/backend privileged execution consumes the same compiler-bound request provenance;
5. only then consider whether any real product requirement justifies a constitutional cross-domain transition primitive.
