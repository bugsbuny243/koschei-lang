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

Canonical requests now carry both semantic `universe_plan_digest` and executable `activation_plan_digest`, closing the previous identity gap between compiler proof binding and durable epoch/replay enforcement.

## 7. Axis independence

Compromise or observation of one Khar axis must not automatically reveal, synthesize, or satisfy another axis.

A valid `vaal` witness is not an `esh` witness. A valid `teyr` witness is not a `rha` witness. The Galaxy must not hide a single common trust object behind six different names.

Logical independence is currently enforced by requiring six distinct axis witnesses. Failure-independence tests must still prove that six logical axes are also separated by their real failure roots.

## 8. No permanent attack map

Koschei is designed under the assumption that an attacker may use models trained specifically against Koschei, collect long-running observations, reverse-engineer exposed artifacts, and continuously retrain.

The architecture target is therefore stronger than syntax novelty. The attacker should not receive a stable operational map merely by learning the language grammar, conventional file organization, or one customer's prior observations.

Current first enforcement slice combines the existing `library_adversary_learning_resistance_v0.py` and `library_adaptive_visibility_v0.py` with `nur_nyr_projection_v1.py`: observer/session pressure controls a rotating visibility envelope, and the Nyr surface changes across visibility epochs, observer sessions and customer Veyras while canonical MIR remains unchanged.

This is not yet a claim that every runtime artifact, timing channel, memory observation or external side channel is non-learnable. The projection layer is one part of No Golden Tray, not its sole defense. If a projection leaks, Khar concurrence and independence laws remain mandatory.

## 9. Vormir direction

Vormir represents irreversible cost for deeper or higher-power transitions. The intended physics is accumulation-resistant: a transition must not allow old and new critical reach to coexist for free.

Current first enforcement slice: `koschei/vormir_sacrifice_v1.py` retains the older commitment API for compatibility but adds a durable epoch-sacrifice path. A fully contained old epoch must be tombstoned through `DurableEpochFence` before the staged successor can be accepted. The successor exists before the irreversible step only as a fully `INACTIVE` state, so old active reach and new active reach are not allowed to coexist. The sacrifice also requires evidence from at least two distinct witness-domain digests and survives process restart.

This first slice proves durable epoch sacrifice. It does not yet prove that the witness domains have physically independent failure roots, nor does it yet express every possible Aevra-level sacrifice.

## 10. Morth, Event Horizon, and Black Hole

Morth denotes a path that no longer has a valid future in the living Galaxy.

Event Horizon denotes the irreversible boundary after which an old Aevra/authority/reality path cannot return through ordinary rollback.

Black Hole denotes the terminal sink for dead identity, dead authority, stale epoch state, consumed events, and compromised lineage. Historical evidence may remain inspectable; dead power must not escape into a new living path.

Current first enforcement slice: `koschei/morth_black_hole_v1.py` provides an append-only durable Black Hole for canonical Aevra identities. Crossing its Event Horizon writes a sealed Morth record with Veyra, Aevra, death epoch, cause and evidence. There is deliberately no delete, restore or unbury API. A Morth Aevra is rejected before atomic Sathra execution even when the request and six-axis concurrence are otherwise valid.

Rebirth is explicitly distinct from resurrection: the same visible Koschei subject may be born again only as a different Aevra identity after the Morth epoch. The old Aevra digest remains terminal and inspectable.

This first slice covers Aevra finality and composes with existing durable epoch tombstones and one-shot event finality. Full Matrix/lineage-wide Black Hole composition remains future work.

## 11. Matrix direction

Matrix denotes a controlled execution reality within the Galaxy. Sharing one Matrix must not imply sharing the same Hara, authority, knowledge surface, or critical reach.

Future canonical work must define Matrix identity, reality binding, entry/exit law, cross-Matrix transition, and how a Matrix becomes contained or Morth without exposing a global Galaxy map.

## 12. Autonomous systems

Automated or model-driven systems may operate inside Koschei, but they do not gain sovereignty over Khar. They must not be able to weaken concurrence, rewrite evidence finality, manufacture another axis, or declare their own policy changes constitutional.

## 13. Implementation order

The implementation sequence is:

1. **FIRST SLICE APPLIED** — keep the native `lexer -> parser -> AST -> typed semantics -> MIR -> Library -> Universe -> proof -> enforcement` chain working and fail-closed;
2. **FIRST SLICE APPLIED** — bind native sigil MIR into the canonical module/compiler spine rather than leaving a parallel path;
3. **FIRST SLICE APPLIED** — bind exact critical requests to six-axis Sathra concurrence and durable one-shot event finality;
4. **FIRST SLICE APPLIED** — define Veyra identity and customer-Galaxy identity separation without creating a new golden topology-map object;
5. **FIRST SLICE APPLIED** — define observer projection / time-bounded visible-surface rules under `nur`;
6. **FIRST SLICE APPLIED** — implement durable Vormir epoch-sacrifice physics;
7. **FIRST SLICE APPLIED** — unify the first Aevra-level Morth / Event Horizon / Black Hole enforcement path;
8. **NEXT** — prove real failure independence for the six axes;
9. expand adversarial tests for attacker-specific model learning and cross-customer generalization;
10. only then grow higher Galaxy mechanisms such as survival branching and advanced autonomous orchestration.

The phrase `FIRST SLICE APPLIED` means a concrete enforced path and tests now exist. It does not mean the complete constitutional area is finished.

## 14. Anti-drift rule

A new module is not progress merely because it has a security-themed name. New implementation work must close a stated constitutional gap, attach to the language/Library/Universe execution chain, or provide adversarial proof for an existing law.

Koschei must not become a pile of disconnected security utilities.
