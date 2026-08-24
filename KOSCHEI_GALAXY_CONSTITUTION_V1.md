# Koschei Galaxy Constitution v1

Status: architectural invariant, implementation in progress

This contract extends `KOSCHEI_LIBRARY_UNIVERSE_CONTRACT_V1.md` and the main Koschei Lang vision without replacing them. Koschei remains a general-purpose native language with a small visible surface, a deep Library, and executable Universe physics. The Galaxy layer defines how a customer-specific living Universe may exist without exposing a stable security map as ordinary project structure.

## 1. Khar: non-weakening constitutional physics

Khar is the name for the laws a Koschei implementation must satisfy in order to remain Koschei. Khar is not a file, process, super-user, recovery credential, or privileged object.

A new compiler, Library implementation, Universe profile, recovery path, or customer Galaxy may extend behavior only when the extension does not weaken an already-active Khar law.

No emergency, recovery, debug, migration, operator, autonomous subsystem, or internal Library path may silently reinterpret a Khar law into a weaker rule.

## 2. No Golden Tray

Koschei must not deliberately expose a stable one-to-one map from ordinary project structure to critical Universe structure.

The following must not be treated as canonical Galaxy topology:

- source-file names or directory placement;
- a single configuration object;
- one master map of critical relationships;
- one privileged object whose possession represents the whole Galaxy;
- one runtime process whose memory represents the whole Galaxy;
- one visible sigil occurrence whose location directly identifies a critical power axis.

This law does not claim that source bytes can never leak. It requires that visible structure not itself be the complete operational power map.

## 3. Visible Koschei is not the living Galaxy

`ka / vor / shi / thal / nur` remain native developer-facing semantic roots. Their visible source representation is not itself the complete living Universe state.

The compiler and Library may produce authorized proofs and diagnostics, but a source tree must not be accepted as a substitute for Veyra, epoch, evidence, or living-event identity.

Time-bounded observer projections may vary without changing canonical Aevra meaning. Such projections must never be allowed to change Khar semantics.

Current first enforcement slice: `koschei/nur_nyr_projection_v1.py` derives observer/epoch-specific Nyr surfaces from sealed native MIR and a sealed Veyra. Canonical sigil roots remain visible while canonical subject names and Veyra identity are absent from the visible Nyr surface. This is not yet a claim that the entire customer Galaxy topology is hidden.

## 4. Aevra and Veyra

Aevra denotes a canonical Koschei program entity whose identity is greater than a copy of its visible bytes.

Veyra denotes the customer-specific living Galaxy geometry in which Aevra relationships become valid.

Two customer systems may speak the same Koschei language without sharing the same Veyra. Learning one customer's operational geometry must not be a language-level guarantee of another customer's geometry.

`copy(bytes) != birth(Aevra)` is a design law. A copied visible representation does not independently create canonical living identity.

Current first enforcement slice: `koschei/galaxy_identity_v1.py` seals Veyra identity without storing a topology map and binds Aevra birth to one Veyra, one native-MIR compiler product, one canonical sigil subject, one birth epoch and explicit birth evidence. This is identity separation; full distributed Galaxy geometry remains future work.

## 5. Six Khar axes

Critical reality requires six independent Koschei-native axes:

- `khor` — locus and isolation;
- `sei` — intent and control direction;
- `rha` — executable reality;
- `vaal` — effect force;
- `teyr` — temporal epoch;
- `esh` — continuity and living identity.

These names are native Koschei terms. Third-party fictional names may be useful design metaphors, but they are not runtime dependencies or language authority.

### Concurrence law

There is no partial critical success:

`1/6 = 0`

`2/6 = 0`

`3/6 = 0`

`4/6 = 0`

`5/6 = 0`

A Sathra may exist only when all six axes belong to the same Aevra, Veyra, event, reality, and epoch.

Six witnesses collected from different events, Galaxies, realities, or epochs are not a 6/6 concurrence.

One witness cannot substitute for two axes.

Current enforcement: `koschei/khar_sathra_v1.py` implements and seals this rule.

## 6. Sathra is an event, not stored super-power

Sathra is the moment in which six valid axes concur on one critical event. It is not a reusable master authority and must not become an Infinity-Gauntlet-style object that grants unrelated future outcomes.

Current enforcement: `koschei/sathra_request_binding_v1.py` binds one Sathra to the exact canonical privileged request, Aevra, Veyra, epoch and native-MIR executable reality. Its durable path then claims that exact event through `native_sigil_atomic_execution_coordinator_v1.py` before any critical effect can run. The event is finalized as `COMMITTED`, `REJECTED`, `CONTAINED`, or `UNCERTAIN`; the same exact request/Sathra cannot be claimed a second time.

Canonical requests carry both semantic `universe_plan_digest` and executable `activation_plan_digest`, binding compiler proof identity to durable epoch/replay identity.

## 7. Axis failure independence

Compromise or observation of one Khar axis must not automatically reveal, synthesize, or satisfy another axis.

A valid `vaal` witness is not an `esh` witness. A valid `teyr` witness is not a `rha` witness. The Galaxy must not hide a single common trust object behind six different names.

Current first enforcement slice: `koschei/khar_failure_independence_v1.py` binds each Sathra axis witness to an explicit failure-root digest, an independent attestation-domain digest and independence evidence. All six roots must differ, all six attestation domains must differ, one root cannot self-attest, and one axis root cannot act as another axis's attestation domain.

`koschei/galaxy_execution_gate_v1.py` makes that proof part of the strongest current critical-execution path. A logically complete 6/6 Sathra without its failure-independence proof cannot pass that gate.

This is an enforceable identity-separation law. It does not claim that physical independence is proven merely because six digests are different. Hardware, operator, infrastructure and organizational independence still require externally produced evidence that Koschei can verify and bind to these roots.

## 8. No permanent attack map

Koschei is designed under the assumption that an attacker may use models trained specifically against Koschei, collect long-running observations, reverse-engineer exposed artifacts, and continuously retrain.

The architecture target is therefore stronger than syntax novelty. The attacker should not receive a stable operational map merely by learning the language grammar, conventional file organization, or one customer's prior observations.

Current first enforcement slice combines the existing `library_adversary_learning_resistance_v0.py` and `library_adaptive_visibility_v0.py` with `nur_nyr_projection_v1.py`: observer/session pressure controls a rotating visibility envelope, and the Nyr surface changes across visibility epochs, observer sessions and customer Veyras while canonical MIR remains unchanged.

`tests/test_galaxy_adversarial_learning_v1.py` adds a long-running observer corpus across multiple epochs, sessions and customer Galaxies. It asserts that canonical subject names, Veyra identity and MIR locators are absent from Nyr output; aliases rotate over time/session and do not transfer between customer Veyras.

These tests prove stated projection invariants, not a universal theorem that every possible AI model can never infer anything. Timing channels, memory artifacts, deployment metadata and future runtime surfaces remain separate adversarial targets. If a projection leaks, Khar concurrence and failure-independence laws remain mandatory.

## 9. Vormir

Vormir represents irreversible cost for deeper or higher-power transitions. The intended physics is accumulation-resistant: a transition must not allow old and new critical reach to coexist for free.

Current first enforcement slice: `koschei/vormir_sacrifice_v1.py` retains the older commitment API for compatibility but adds a durable epoch-sacrifice path. A fully contained old epoch must be tombstoned through `DurableEpochFence` before the staged successor can be accepted. The successor exists before the irreversible step only as a fully `INACTIVE` state, so old active reach and new active reach are not allowed to coexist. The sacrifice also requires evidence from at least two distinct witness-domain digests and survives process restart.

This first slice proves durable epoch sacrifice. It does not yet express every possible Aevra-level sacrifice or independently certify the physical roots behind its witness domains.

## 10. Morth, Event Horizon, and Black Hole

Morth denotes a path that no longer has a valid future in the living Galaxy.

Event Horizon denotes the irreversible boundary after which an old Aevra/authority/reality path cannot return through ordinary rollback.

Black Hole denotes the terminal sink for dead identity, dead authority, stale epoch state, consumed events, and compromised lineage. Historical evidence may remain inspectable; dead power must not escape into a new living path.

Current first enforcement slice: `koschei/morth_black_hole_v1.py` provides an append-only durable Black Hole for canonical Aevra identities. Crossing its Event Horizon writes a sealed Morth record with Veyra, Aevra, death epoch, cause and evidence. There is deliberately no delete, restore or unbury API. A Morth Aevra is rejected before critical Galaxy execution even when the request and six-axis concurrence are otherwise valid.

Rebirth is explicitly distinct from resurrection: the same visible Koschei subject may be born again only as a different Aevra identity after the Morth epoch. The old Aevra digest remains terminal and inspectable.

This first slice covers Aevra finality and composes with durable epoch tombstones and one-shot event finality. Full lineage-wide Black Hole composition remains future work.

## 11. Matrix and Hara

Matrix denotes a controlled local execution reality within one Veyra. Sharing one Matrix does not imply sharing the same Hara, authority, knowledge surface, or critical reach.

Hara denotes one Aevra's scoped horizon inside a Matrix.

Current first enforcement slice: `koschei/matrix_reality_v1.py` seals Matrix identity to one Veyra and epoch, seals Hara identity to one Matrix and one Aevra, and creates explicit Matrix/Hara admission bound to native MIR reality and evidence. A Hara cannot move to another Aevra or Matrix; a Matrix cannot move to another customer Veyra.

`koschei/galaxy_execution_gate_v1.py` requires a valid Matrix/Hara admission in the same request epoch before the strongest current critical execution can proceed.

Cross-Matrix transition physics, Matrix-level containment/Morth and a canonical relationship to the `rha` axis are still future work.

## 12. Autonomous systems

Automated or model-driven systems may operate inside Koschei, but they do not gain sovereignty over Khar. They must not be able to weaken concurrence, rewrite evidence finality, manufacture another axis, or declare their own policy changes constitutional.

## 13. Strongest current critical path

The strongest current composed critical path is:

`native MIR -> Aevra/Veyra -> Matrix/Hara admission -> living/Morth check -> exact request proof -> 6/6 Sathra -> six failure-root proof -> atomic one-shot claim -> decision/effect finality`

This path is implemented by `koschei/galaxy_execution_gate_v1.py` together with the modules it verifies. Lower-level modules remain useful reference/composition boundaries, but new privileged Galaxy work should not intentionally bypass the strongest available constitutional gate.

## 14. Implementation order

1. **FIRST SLICE APPLIED** — native compiler/Library/Universe/proof/enforcement chain fail-closed;
2. **FIRST SLICE APPLIED** — native MIR in canonical module/compiler spine;
3. **FIRST SLICE APPLIED** — exact requests + 6/6 Sathra + durable one-shot finality;
4. **FIRST SLICE APPLIED** — Veyra/Aevra customer-Galaxy identity separation;
5. **FIRST SLICE APPLIED** — observer/time-bound Nyr surface under `nur`;
6. **FIRST SLICE APPLIED** — durable Vormir epoch sacrifice;
7. **FIRST SLICE APPLIED** — Aevra-level Morth / Event Horizon / Black Hole;
8. **FIRST SLICE APPLIED** — explicit six-axis failure-root independence and composed Galaxy gate;
9. **FIRST SLICE APPLIED** — adversarial rotating-surface/cross-customer regression corpus;
10. **FIRST SLICE APPLIED** — Matrix/Hara execution-reality identity and admission;
11. **NEXT** — explicit cross-Matrix transition and Matrix containment/finality;
12. then survival-branch selection and bounded autonomous orchestration.

`FIRST SLICE APPLIED` means a concrete enforced path and tests exist. It does not mean the entire constitutional area is complete.

## 15. Anti-drift rule

A new module is not progress merely because it has a security-themed name. New implementation work must close a stated constitutional gap, attach to the language/Library/Universe execution chain, or provide adversarial proof for an existing law.

Koschei must not become a pile of disconnected security utilities.
