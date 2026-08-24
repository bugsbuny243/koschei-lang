# Koschei Native Intelligence Contract v1

Status: architectural invariant, first enforcement slice applied

## 1. Decision

Koschei Sentinel is not a separate sovereign runtime in the target architecture. Its intelligence function is folded into Koschei Lang as a native, Khar-bounded intelligence plane.

The canonical v1 base model is:

`Qwen/Qwen3.5-397B-A17B`

Koschei does not vendor the base weights into Git. The language repository owns the identity, training lineage, curriculum, adapter/checkpoint lineage, benchmark evidence and execution laws. Base weights remain in an external model store pinned by immutable revision and content identity.

The model may observe, classify, reason, explain, rank bounded survival futures and propose actions. Model output alone is never executable authority.

## 2. Sentinel merge law

The old conceptual split:

`Koschei Lang -> separate Sentinel -> recommendation`

is replaced by:

`Koschei Lang -> native intelligence plane -> Khar-bounded proposal -> constitutional execution`

Historical Sentinel datasets, adapters, receipts and benchmarks remain evidence sources. They are not silently relabelled as native-intelligence v1 artifacts.

A historical artifact may enter the new curriculum only after it is revalidated against the current Koschei language/Universe/Galaxy laws and its source lineage is preserved.

## 3. Canonical model identity

`koschei/native_intelligence_v1.py` binds one trained intelligence identity to all of:

- canonical Khar v1 digest;
- exact base model registry ID;
- immutable base-model revision;
- base-weight content digest;
- Koschei curriculum digest;
- trained adapter/checkpoint digest;
- training-run digest;
- exact Koschei source commit;
- recorded training method;
- multimodal identity;
- `authority = false`.

Changing any one of these identities invalidates the model identity seal.

The base model name by itself is not sufficient identity. Mutable `main` is never sufficient training provenance.

## 4. Model output is event evidence, not power

`NativeIntelligenceEventBindingV1` binds one model observation/output to:

- one native-intelligence identity;
- one customer Veyra;
- one native-MIR executable reality;
- one request epoch;
- one exact bounded-autonomy proposal;
- one observation digest;
- one output digest.

The binding is explicitly authority-free. A copied model answer, transcript or hidden-state export is not a reusable execution credential.

The same output cannot be moved to another customer Galaxy, another compiler product, another epoch or another proposal without invalidating the binding.

## 5. Execution law

There is deliberately no `model_execute()` side door.

`koschei/native_intelligence_execution_v1.py` accepts model-originated activity only when the native-intelligence identity and exact event binding verify, then delegates to the strongest witnessed bounded-autonomy path.

The composed path is:

`Qwen observation/output`
`-> authority-free exact proposal binding`
`-> bounded autonomy`
`-> exact survival branch`
`-> witnessed implementation root`
`-> canonical Khar`
`-> living Aevra/Veyra`
`-> current Matrix/Hara`
`-> exact request`
`-> 6/6 Sathra`
`-> six independent failure roots`
`-> atomic one-shot finality`

The model may influence which already-eligible future is proposed. It cannot manufacture an eligible future, weaken Khar, synthesize a missing axis, resurrect Morth, replace current Hara, mint authority or declare its own output final.

## 6. Training target

The old compiler-oracle curriculum is useful but insufficient for the merged architecture. Native-intelligence training must expand beyond capability/token examples into Koschei-native physics.

The intended curriculum order is:

### N0 — Native language birth

- native syntax and semantics;
- `ka / vor / shi / thal / nur`;
- parser -> typed semantics -> sealed MIR;
- compiler-oracle truth over model confidence.

### N1 — Galaxy identity

- Aevra/Veyra identity;
- copy is not birth;
- cross-customer non-transfer;
- Nyr is not Aevra;
- observer/time-bound projection.

### N2 — Khar and six-axis reality

- canonical Khar cannot be caller-substituted;
- `1/6..5/6 = 0`;
- same-event/same-Aevra/same-Veyra/same-reality/same-epoch concurrence;
- six independent failure roots;
- Sathra is one-shot event reality, not stored power.

### N3 — Matrix, Morth and Vormir

- current Matrix/Hara admission;
- old Hara becomes Morth after Event Horizon;
- Black Hole has no resurrection API;
- rebirth is new identity, not restoration;
- irreversible Vormir sacrifice before deeper successor reach.

### N4 — Adversarial learning resistance

- No Golden Tray;
- rotating Nyr surfaces;
- cross-session and cross-Veyra non-transfer;
- canonical subjects/topology must not be exposed as labels;
- attacker-specific AI is assumed to retrain continuously.

### N5 — Survival intelligence

- Khar-violating futures are impossible, not merely low-scored;
- authority escape/cross-domain spread hard ceilings;
- deterministic branch objective;
- model proposal is evidence only;
- selected future still requires exact Galaxy event admission.

### N6 — Security intelligence specialization

Historical Sentinel security material may enter here after native-language hard gates pass. Evidence-grounded threat classification, attack-chain reasoning, anomaly explanation and defensive recommendations belong here. Web3 or other sector specialization is a later Veyra/sector curriculum, not the definition of the model.

## 7. Training method

The target is specialization, not full retraining of hundreds of billions of parameters from scratch.

Initial production research should use LoRA/PEFT-style supervised fine-tuning with an exact pinned base revision, followed by hard-gate evaluation. DPO/GRPO or other post-training methods may be added only after the supervised native-physics baseline is stable and every reward/verifier rule is Khar-bounded.

A training run must emit a sealed lineage containing at minimum:

- base model ID and immutable revision;
- base-weight identity;
- exact Koschei source commit;
- curriculum release digest;
- train/validation/test digests;
- training configuration digest;
- adapter/checkpoint digest;
- benchmark release digest;
- promotion/finalization evidence.

A completed adapter is not automatically deployed.

## 8. Storage layout

The approximately 100 GB connected Google Drive capacity is useful for private Koschei-owned training artifacts but cannot hold the canonical full base-model repository.

Intended Drive use:

- private raw/reviewed corpus;
- pseudonymized training releases;
- curriculum exports;
- adapter checkpoints;
- evaluation corpora and benchmark outputs;
- run receipts and finalization evidence;
- selected resumable checkpoints where size permits.

Do not duplicate the full Qwen base weights in Drive merely to make Koschei identity depend on a copied file set. Base weights stay in a pinned external model store; Koschei records and verifies their identity.

Git continues to exclude model weights, private corpora, secrets, salts and large checkpoints.

## 9. Historical Sentinel migration

Existing Sentinel training work supplies useful patterns already proven in the earlier workflow:

- pinned base revision;
- dataset readiness boundary;
- deterministic adapter manifest;
- offline-job receipt;
- benchmark-before-promotion;
- append-only candidate finalization;
- no automatic production authority.

These controls should be migrated into native Koschei naming and current Galaxy bindings instead of rebuilding weaker copies.

Historical Qwen2.5-1.5B adapters remain historical candidates. They do not become Qwen3.5-397B native-intelligence candidates by inheritance.

## 10. Anti-drift rules

1. The model is inside Koschei Lang but is not above Koschei Lang.
2. Model confidence never substitutes for compiler, Khar, Sathra or evidence.
3. No model output is a seventh stone or a master key.
4. Training data must not teach hidden customer Veyra topology as transferable truth.
5. A model trained for one customer must not automatically inherit another customer's Galaxy relations.
6. Native intelligence must remain replaceable without changing Khar.
7. A better model may improve reasoning quality; it cannot weaken the laws required for execution.
8. The full base weights must not become a new Golden Object.
9. A single adapter, checkpoint, Drive folder, model account or inference process must not represent the whole Galaxy.
10. Claims of physical isolation, hardware attestation, quantum resistance or universal AI-inference resistance require separate evidence; names alone do not count.
