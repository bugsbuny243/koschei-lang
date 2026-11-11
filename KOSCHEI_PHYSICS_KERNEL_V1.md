# Koschei Physics Kernel v1

Status: **canonical registry bootstrap / enforcement mapping checkpoint**

This document maps the twelve public Physics laws to the existing Koschei enforcement spine. It does **not** create a second constitution, second authority source, second parser/type/effect truth, or a privileged bypass around Khar/Galaxy.

`koschei/physics_kernel_v1.py` is an authority-free public registry. Existing compiler, MIR, Khar, Galaxy, Continuity, evidence, authorization, finality and observer boundaries remain the enforcement owners.

## Canonical rule

A Physics law may be called **enforced** only when a concrete sanctioned path rejects a violating state and a corresponding test/evidence path exists. A design document alone is not enforcement.

Statuses used here:

- `ENFORCED_SLICE` — concrete fail-closed path and tests exist for the stated slice.
- `PARTIAL` — meaningful enforcement exists, but a named bypass/trust assumption remains.
- `CONFLICT` — more than one semantic authority or compatibility path still exists.
- `DESIGN_ONLY` — specification exists without a canonical enforced path.

## Twelve-law enforcement map

| # | Physics law | Primary semantic relation | Current enforcement owners | Status | Named gap / production blocker |
|---|---|---|---|---|---|
| 1 | `physics.existence.provenance-required` | `ka` | `galaxy_identity_v1.py`, authenticated frontend/Object Space identity, Aevra/Veyra birth, native-MIR binding | `PARTIAL` | Trusted-process/native custody can still be forged or bypassed inside the Python TCB until compiler/runtime provenance is isolated. |
| 2 | `physics.authority.conservation` | `vor` | `capability_effect_contract_v1`, affine ownership, `canonical_authority_basis_v1.py`, compiler-bound request/domain constraint, Khar/Galaxy critical-effect gate | `ENFORCED_SLICE` | Physical custody of decision/runtime keys and trusted issuer compartment is still deployment work. |
| 3 | `physics.evidence.claim-is-not-proof` | `shi` | request-bound proofs, `execution_proof_envelope_v1.py`, effect/finality receipts, implementation witness verification | `ENFORCED_SLICE` | False evidence admitted before a boundary and compromised trust roots remain outside the software proof. |
| 4 | `physics.knowledge.not-authority` | `nur` | `nur_nyr_projection_v1.py`, authority-free proof/envelope/report objects, bounded autonomy `authority=False` | `ENFORCED_SLICE` | Debugger/crash-dump/side-channel surfaces are not yet comprehensively classified as canonical vs observer-safe. |
| 5 | `physics.observable.not-canonical` | `nur` / Universe | Nyr projection, protected-source/rotating observer surfaces, Galaxy `No Golden Tray` law | `ENFORCED_SLICE` | Does not prove canonical state can never leak; host-memory and deployment metadata remain threat surfaces. |
| 6 | `physics.semantic.conservation` | compiler → MIR → runtime | Typed HIR, canonical capability/effect contract, sealed MIR, MIR fingerprints, compiler-owned resolution facts, backend parity work | `PARTIAL` | Legacy semantic/AST compatibility authority and executable AST fallback are not fully removed; all consumers are not yet proven to consume one normalized capability call-site fact. |
| 7 | `physics.ambiguity.fail-closed` | all roots | ambiguous capability-call rejection, same-domain negative invariant, exact-request binding, 6/6 Sathra, epoch/liveness checks | `ENFORCED_SLICE` | Any remaining compatibility route capable of guessing an unmigrated semantic fact must be removed or classified fail-closed. |
| 8 | `physics.survival.no-privilege-manufacture` | `thal` | Continuity epoch authority, reconstruction one-shot consumption, Vormir sacrifice, Morth/Black Hole, deterministic survival selection | `PARTIAL` | Shared Continuity removes internal clock disagreement but does not prove honest monotonic hardware time or rollback resistance. |
| 9 | `physics.finality.no-silent-reversal` | `thal` / Sathra | atomic one-shot execution claim, durable current-Hara tombstone, Morth Event Horizon, finality receipts | `ENFORCED_SLICE` | Durable-state rollback/fork remains a deployment/root-of-trust problem where storage monotonicity is not externally anchored. |
| 10 | `physics.semantic.one-canonical-truth` | compiler/runtime | canonical capability/effect contract and checked `EffectReport` feeding MIR | `CONFLICT` | `_parser_v09.py`, Typed HIR + legacy semantic overlap, executable MIR AST fallback, and compatibility aliases are explicit debt. This law is not production-closed. |
| 11 | `physics.execution.proof-carrying` | `shi` / execution | `ExecutionProofEnvelopeV1`, `EffectExecutionReceiptV1`, finality verification/attestation envelopes, Reality Evidence Ledger work | `ENFORCED_SLICE` | Proof does not prevent a caller from bypassing the sanctioned execution path; native/runtime isolation must make bypass structurally unavailable. |
| 12 | `physics.component.no-sovereign-bypass` | Khar / Galaxy | Khar non-weakening, no golden master, failure-root separation, bounded autonomy, Sentinel observer boundary, witnessed execution | `PARTIAL` | Software separation does not by itself prove physical independence. External measured host/isolated verifier/HSM/TEE-style roots remain deployment-specific. |

## Current highest-priority closure order

1. **Law 10 — One Canonical Truth:** remove/contain legacy parser and AST semantic authority; normalize capability call-site identity in MIR; make interpreter/native/backend consume the same fact.
2. **Law 6 — Semantic Conservation:** prove the same normalized security meaning survives source → HIR → MIR → interpreter/native/backend; fail closed on unmigrated constructs.
3. **Law 8 — Bounded Survival:** bind Continuity to a rollback-aware durable monotonic source where the production threat model requires rollback resistance.
4. **Law 12 — No Sovereign Component:** bind external implementation witnesses to genuinely independent deployment roots without turning any one witness into a master credential.
5. **Law 11 — Proof-Carrying Execution:** make sanctioned proof-producing execution structurally authoritative so direct lower-level effect bypass is not a supported production path.

## Relationship to Khar

Physics v1 is deliberately **not yet included in `CANONICAL_KHAR_LAWS_V1`**. Doing that now would be circular: several Physics laws describe invariants whose enforcement still spans multiple modules and known compatibility debt.

Promotion rule:

`Physics registry -> evidence map -> adversarial validation -> canonical enforcement ownership -> Khar successor protocol`

Khar v1 must not be silently rewritten. If Physics becomes constitution-bound, that must use an explicit successor-constitution mechanism rather than mutating the meaning of existing Khar v1.

## Semantic roots and cosmology

The current Source of Truth defines five native developer-facing semantic roots: `ka`, `vor`, `shi`, `thal`, `nur`.

Universe vocabulary such as Khar, Aevra, Veyra, Matrix, Hara, Sathra, Vormir, Morth/Event Horizon/Black Hole, Doctor Strange, Skynet, Avengers/Infinity Stones, Neo, Agent Smith and Deus Ex Machina remains active canonical architecture where it has enforceable technical responsibility.

A sixth symbolic Stone/axis such as `SOL` must **not** be silently promoted into the compiler's native semantic-root set until its exact canonical semantics and enforcement ownership are specified and tested. Cosmology may be richer than source-language roots; the implementation must preserve that distinction.

## Non-claims

Physics v1 does not claim:

- production readiness;
- formal proof of all twelve laws;
- physical root independence;
- rollback-resistant time merely from shared Continuity;
- immunity to trusted-process compromise or side channels;
- that a deterministic digest is a secret-key signature;
- that the Physics registry itself grants authority.

The registry exists to stop architectural drift and make every law traceable to an actual enforcing path, test and explicit remaining gap.