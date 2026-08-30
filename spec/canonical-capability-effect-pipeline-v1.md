# Canonical Capability / Effect Pipeline V1

Status: **compiler consolidation + compiler-bound privileged request bridge applied / normalized call-site MIR pending / validation receipt pending**

## Purpose

Koschei must not decide authority or effect identity twice at different compiler/runtime layers.

The checked module graph now produces one Typed-HIR-aware `EffectReport`, MIR consumes that exact checked report, and privileged request issuance can derive one exact capability call-site basis from sealed compiler MIR instead of accepting a runtime-selected capability type/method.

The sanctioned compiler/runtime authority chain is now:

```text
source / AST
-> Typed HIR
-> typestate
-> affine ownership
-> check_effect_contracts(...)
   -> capability_effect_contract_v1
   -> checked EffectReport
-> legacy compatibility semantic check
-> MIR lowering consumes exact checked EffectReport
-> sealed MIR capability-effect projection
-> derive one exact CompilerCapabilityEffectBasisV1 from sealed compiler MIR
-> privileged request operation := compiler basis canonical effect
-> compiler-bound RequestCapabilityDomainConstraintV1
-> Khar/Galaxy constitutional admission
```

MIR does not re-infer its capability effects through the old `effects.infer_effects(...)` path.

## One canonical capability contract

`capability_effect_contract_v1.py` remains the single canonical owner of:

- capability type set;
- root narrowing relationships;
- narrowed operations;
- capability method -> canonical effect identity;
- canonical capability effect set;
- power-domain classification used by deny-only request admission.

Typed type contracts import `CAPABILITY_TYPES` directly from this canonical module instead of routing sensitivity through legacy `semantic.py` capability aliases.

Affine ownership remains structural: `AffineResourceChecker` asks `TypeContractValidator.is_sensitive(...)`, and that validator classifies direct capability types from the canonical contract.

Effect checking uses `effect_for(...)` from the same contract.

## Checked EffectReport becomes the MIR source

`modules.check_graph(...)` computes one `EffectReport` per module after Typed HIR, typestate and affine checks.

Imported module effect reports are propagated in dependency order before the local report is finalized.

After every module succeeds, `check_graph(...)` passes both:

- `typed_reports`
- `effect_reports`

to MIR lowering.

`mir.lower_graph(...)` requires an effect report for every module and `mir.lower_module(...)` requires an effect report for every function. Missing report coverage fails closed with `MirIntegrityError`; MIR does not fall back to another inference engine.

## MIR v3 compatibility projection

The full `EffectReport` contains more than MIR v3 historically exposed, including:

- authority-bearing input/output;
- console/shared-memory/concurrency effects;
- unknown call classifications;
- imported-call metadata.

MIR v3's public `MirFunction.effects` field historically represents canonical capability effects. V1 preserves that ABI by projecting the already-checked report onto `CANONICAL_CAPABILITY_EFFECTS`.

This is a projection of one checked semantic result, not a second inference pass.

Examples:

```text
checked effects: authority.input + net.io
MIR capability effects: net.io
```

```text
checked effects: console.write
MIR capability effects: <empty>
```

The broader effect model can become first-class MIR only through an explicit versioned MIR change.

## Imported-effect preservation

Because MIR consumes the module graph's checked reports, canonical capability effects that arrive transitively through imported calls can be preserved in the caller MIR.

This closes the old AST-local blind spot where MIR did not own the module graph's already-resolved imported-effect truth.

## CompilerCapabilityEffectBasisV1

A function-level `MirFunction.effects == ("net.io",)` is not sufficient to identify one exact capability operation. Several canonical methods can share an effect, and a function may receive the effect transitively.

Therefore privileged request issuance does not select a capability type/method from the effect label alone.

`CompilerCapabilityEffectBasisV1` derives one exact call-site from sealed `MirGraph` + sealed Typed-HIR expression typing + the canonical capability contract.

Bootstrap V1 deliberately requires:

```text
one module
+ one function
+ no local function calls
+ no imported function calls
+ exactly one direct canonical capability call
+ function MIR effect set == exactly that call's effect
```

It then records:

- compiler MIR fingerprint;
- module/function identity;
- capability type;
- capability method;
- canonical effect;
- power domain;
- source call-site location;
- deterministic basis digest;
- `authority=False`.

Multiple direct capability calls fail closed as ambiguous. Local/imported indirection fails closed. This is intentionally restrictive until capability call-site identity is first-class normalized MIR.

## Compiler-bound privileged request issuance

`seal_compiler_bound_effect_request_v1(...)` removes runtime choice of the privileged operation.

The caller provides business/request evidence only. The compiler basis supplies:

- capability type;
- capability method;
- canonical effect;
- power domain;
- `CanonicalEffectRequest.operation`.

The flow is:

```text
sealed compiler MIR
-> CompilerCapabilityEffectBasisV1
-> operation := basis.canonical_effect
-> CanonicalEffectRequest
-> bind_request_capability_domain_v1(request, compiler_basis=basis)
-> RequestCapabilityDomainConstraintV1
```

The old sanctioned bootstrap shape:

```text
bind_request_capability_domain_v1(
    request,
    capability_type="ProcessCaps",
    capability_method="run",
)
```

is removed. Runtime/bootstrap code no longer chooses those authority facts.

## Integrity behavior

`MirGraph.assert_sealed()` does not call `effects.infer_effects(...)`.

It validates MIR structure/resources, rejects capability effects outside the canonical effect set, and verifies the graph fingerprint that seals program/type/function effect metadata.

`CompilerBoundEffectRequestV1.assert_sealed(...)` can re-derive its `CompilerCapabilityEffectBasisV1` from the supplied sealed compiler MIR and require exact equality before accepting the compiler-bound request bundle.

The compiler basis and request-domain constraint use deterministic structural seals, not a secret-key compiler signature. This does not make a malicious compiler trustworthy and does not physically prevent arbitrary Python object construction inside the TCB.

## Legacy `effects.py`

The old AST effect inferencer remains outside the sanctioned MIR lowering path. The file may remain temporarily for compatibility/tests until repository-wide consumers are proven absent.

A regression test patches `koschei.effects.infer_effects` to raise; checked MIR construction must still succeed.

## PROTECTS AGAINST

- MIR independently disagreeing with the compiler's already-checked capability/effect report because of a second AST inference algorithm;
- imported capability effects being lost merely because MIR performs module-local AST inference;
- Typed type sensitivity relying on a legacy capability-type alias instead of the canonical capability contract;
- MIR silently accepting arbitrary non-canonical capability effect labels;
- missing module/function effect reports falling back to permissive inference;
- runtime/bootstrap code selecting capability type/method independently of compiler output;
- caller-selected privileged operation labels diverging from compiler-derived canonical effect identity;
- ambiguous multiple capability call-sites being guessed into one privileged request;
- local/imported effect indirection being misrepresented as exact direct call-site provenance.

## DOES NOT PROTECT AGAINST

- a malicious compiler or TCB that forges the original `EffectReport`, compiler basis, or dependent policy together;
- direct Python construction/invocation of lower-level internal objects inside the trusted process;
- a bug shared by all consumers of `capability_effect_contract_v1`;
- host/process compromise, debugger inspection, memory scraping, crash dumps or side channels;
- semantic gaps in the legacy compatibility checker;
- executable AST fallback still present inside MIR;
- native/backend code that ignores sealed MIR effect metadata or bypasses compiler-bound request issuance;
- legitimate multi-call/transitive privileged functions, which bootstrap V1 rejects rather than models incompletely.

## ASSUMPTIONS

- `check_typed_hir(...)` produces trustworthy structural expression types;
- `TypeContractValidator` structural sensitivity is correct;
- `check_effect_contracts(...)` is the sole checked function-effect computation for the sanctioned compiler path;
- imported effect reports are resolved in dependency order;
- backends consume only sealed MIR obtained from `require_mir(...)`;
- compiler-bound request issuance is used for privileged runtime admission;
- `capability_effect_contract_v1` remains the canonical capability/effect source.

## FAILURE MODE

The consolidation fails if another compiler/backend path recomputes and overrides capability identity, if MIR lowering accepts missing reports and guesses, if runtime code can again select capability type/method independently of compiler evidence, or if legacy compatibility aliases regain semantic authority.

## TESTED STATUS

Regression tests are committed for:

- direct, local-transitive and imported capability effects in checked MIR;
- sealed MIR tamper detection;
- MIR construction while legacy `koschei.effects.infer_effects` is forced to raise;
- exact `NetCaps.get -> net.io -> Network` compiler-basis derivation;
- compiler basis revalidation against sealed compiler MIR;
- multiple direct capability call-sites failing closed;
- local-call indirection failing closed;
- imported-call indirection failing closed;
- compiler-bound privileged request issuance and materialization path;
- request relabeling and foreign request-domain constraints failing closed.

These tests are **written and committed, not claimed passed**. No fresh `ks-local-validate --profile full` receipt is claimed for the current #263 head.

## NEXT

1. make exact capability call-site identity first-class normalized MIR instead of deriving it by walking sealed AST fallback;
2. make interpreter/native/backend paths consume that same normalized call-site identity;
3. continue shrinking legacy semantic/AST compatibility authority;
4. move compiler/runtime provenance into a stronger native trust boundary;
5. run canonical and adversarial validation before PR #263 leaves draft.
