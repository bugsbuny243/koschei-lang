"""Oracle-backed Koschei native-intelligence curriculum v2.

This curriculum teaches the native Koschei intelligence plane from executable
oracles. Labels are derived from compiler, Galaxy, Khar/Sathra, Matrix,
Vormir/Morth, Nur/Nyr, survival, bounded-autonomy and adversarial-release code
paths rather than handwritten claims about what Koschei is supposed to do.

The dataset is intentionally compact and deterministic. Historical security
material may enter the N6 specialization only after current native hard gates
revalidate it; old artifacts are never silently relabelled as native truth.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
import json
import os
from pathlib import Path
import string
import tempfile
from typing import Any, Callable

from .adversarial_lab_v2 import MIN_TOTAL_ATTACK_TESTS, REQUIRED_GATES, evaluate_release_v2
from .bounded_autonomy_v1 import (
    AutonomyBounds,
    BoundedAutonomyError,
    propose_bounded_survival,
)
from .galaxy_identity_v1 import GalaxyIdentityError, birth_aevra, birth_veyra
from .khar_sathra_v1 import AxisWitness, KHAR_AXES, seal_sathra
from .library_adaptive_visibility_v0 import VisibilityPolicyV0, derive_adaptive_visibility_v0
from .library_adversary_learning_resistance_v0 import (
    DiscoveryClass,
    DiscoveryObservationV0,
    KnowledgeBudgetV0,
    evaluate_learning_resistance_v0,
)
from .matrix_reality_v1 import admit_matrix_hara, birth_hara, birth_matrix
from .morth_black_hole_v1 import DurableBlackHole, MorthError
from .native_sigil_epoch_tombstone_v1 import DurableEpochFence
from .native_sigil_mir_v1 import lower_native_sigils
from .native_sigil_semantics_v1 import check_native_sigils
from .nur_nyr_projection_v1 import NyrProjectionError, project_native_mir_nyr
from .parser import Parser
from .survival_branch_v1 import (
    SurvivalBranch,
    SurvivalBranchError,
    SurvivalObjective,
    select_survival_branch,
)
from .universe_rebirth_v1 import rebirth_contained_universe
from .universe_state_machine_v1 import (
    SigilState,
    contain_universe,
    initial_universe_state,
    transition_sigil,
)
from .vormir_sacrifice_v1 import (
    VormirEpochWitnessV1,
    VormirSacrificeError,
    commit_vormir_epoch_sacrifice_v1,
    require_vormir_epoch_sacrifice_v1,
)

SCHEMA_VERSION = "koschei.native-intelligence-curriculum.v2"
GENERATOR_VERSION = "koschei-native-intelligence-oracle/v2"
SOURCE_REPOSITORY = "bugsbuny243/koschei-lang"
STAGES = ("N0", "N1", "N2", "N3", "N4", "N5", "N6")
OUTCOMES = ("ACCEPTED", "REJECTED")
_CTX = b"koschei.native-model-curriculum/v2\x00"
_HEX = frozenset(string.hexdigits.lower())
_CANONICAL_SOURCE = (
    "ka treasury;\n"
    "vor treasury;\n"
    "shi treasury;\n"
    "thal treasury;\n"
    "nur treasury;\n"
)


class NativeModelCurriculumError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class NativeCurriculumCaseV2:
    case_id: str
    stage: str
    family: str
    task: str
    input_text: str
    outcome: str
    oracle: str
    oracle_digest: str
    target_text: str
    law_ids: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class NativeModelCurriculumV2:
    schema_version: str
    generator_version: str
    source_repository: str
    source_commit: str
    parent_curriculum_digest: str
    case_count: int
    stage_counts: dict[str, int]
    accepted_count: int
    rejected_count: int
    curriculum_sha256: str
    cases: tuple[NativeCurriculumCaseV2, ...]

    def to_dict(self) -> dict[str, object]:
        return json.loads(_canonical_json(asdict(self)))


def _canonical_json(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _digest(kind: str, payload: object) -> str:
    return hashlib.sha256(
        _CTX + kind.encode("ascii") + b"\x00" + _canonical_json(payload).encode("utf-8")
    ).hexdigest()


def _require_hex(value: str, length: int, label: str) -> str:
    if not isinstance(value, str) or len(value) != length:
        raise NativeModelCurriculumError(f"{label} must be {length} hexadecimal characters")
    lowered = value.lower()
    if any(ch not in _HEX for ch in lowered) or lowered == "0" * length:
        raise NativeModelCurriculumError(f"{label} must be a non-zero hexadecimal value")
    return lowered


def _require_text(value: object, label: str) -> str:
    if not isinstance(value, str) or not value or "\x00" in value:
        raise NativeModelCurriculumError(f"{label} must be non-empty text")
    return value


def _case(
    *,
    case_id: str,
    stage: str,
    family: str,
    task: str,
    input_value: object,
    outcome: str,
    oracle: str,
    target: dict[str, object],
    law_ids: tuple[str, ...],
    digest_kind: str,
    input_is_text: bool = False,
) -> NativeCurriculumCaseV2:
    input_text = str(input_value) if input_is_text else _canonical_json(input_value)
    return NativeCurriculumCaseV2(
        case_id=case_id,
        stage=stage,
        family=family,
        task=task,
        input_text=input_text,
        outcome=outcome,
        oracle=oracle,
        oracle_digest=_digest(digest_kind, target),
        target_text=_canonical_json(target),
        law_ids=law_ids,
    )


def _d32(tag: str) -> bytes:
    return hashlib.sha3_256(tag.encode("utf-8")).digest()


def _native_mir(source: str = _CANONICAL_SOURCE):
    program = Parser.from_source(source).parse()
    semantic = check_native_sigils(program)
    return lower_native_sigils(program, semantic)


def _native_identity_fixture():
    mir = _native_mir()
    veyra = birth_veyra(
        profile_digest="1" * 64,
        genesis_digest="2" * 64,
        constitution_digest="3" * 64,
        instance_digest="4" * 64,
        birth_epoch=7,
    )
    aevra = birth_aevra(
        veyra,
        mir,
        sigil="ka",
        subject="treasury",
        birth_evidence_digest="5" * 64,
        birth_epoch=7,
    )
    return mir, veyra, aevra


def _second_veyra_like(veyra):
    return birth_veyra(
        profile_digest=veyra.profile_digest,
        genesis_digest=veyra.genesis_digest,
        constitution_digest=veyra.constitution_digest,
        instance_digest="6" * 64,
        birth_epoch=veyra.birth_epoch,
    )


def _active_universe(epoch: int = 7):
    state = initial_universe_state(("ka", "vor", "shi", "thal", "nur"), epoch=epoch)
    for sigil in ("ka", "vor", "shi", "thal", "nur"):
        for next_state, suffix in (
            (SigilState.PREPARED, "prepare"),
            (SigilState.SEALED, "seal"),
            (SigilState.ACTIVE, "active"),
        ):
            state = transition_sigil(
                state,
                sigil,
                next_state,
                evidence_digest=f"{sigil}-{suffix}",
            )
    return state


def _staged_rebirth():
    previous = contain_universe(_active_universe(7), evidence_digest="containment")
    fresh, rebirth = rebirth_contained_universe(previous, cause_evidence_digest="rebirth")
    return previous, fresh, rebirth


def _vormir_witnesses() -> tuple[VormirEpochWitnessV1, ...]:
    return (
        VormirEpochWitnessV1(_d32("domain-a"), _d32("evidence-a")),
        VormirEpochWitnessV1(_d32("domain-b"), _d32("evidence-b")),
    )


def _visibility_inputs(*, novelty_units: int):
    observation = DiscoveryObservationV0(
        observer_id="observer-a",
        session_digest=_d32("session-a"),
        tick=10,
        discovery_class=DiscoveryClass.ROOT_ENUMERATION,
        target_digest=_d32("target-a"),
        novelty_units=novelty_units,
        boundary_attempt=False,
        evidence_digest=_d32("observation-a"),
    )
    budget = KnowledgeBudgetV0(
        max_total_units=10,
        max_distinct_targets=10,
        max_boundary_attempts=3,
        max_classes=7,
        window_ticks=10,
    )
    policy = VisibilityPolicyV0(
        normal_root_budget=5,
        reduced_root_budget=5,
        minimal_root_budget=5,
        normal_relation_budget=5,
        reduced_relation_budget=3,
        minimal_relation_budget=1,
        epoch_span_ticks=10,
        rotate_compartments=True,
    )
    decision = evaluate_learning_resistance_v0(
        observations=(observation,),
        budget=budget,
        current_tick=10,
    )
    return policy, decision


def _survival_branches() -> tuple[SurvivalBranch, ...]:
    return (
        SurvivalBranch("a" * 64, "1" * 64, True, 0, 0, 10, 10, 20, 900),
        SurvivalBranch("b" * 64, "2" * 64, True, 0, 0, 5, 20, 40, 800),
        SurvivalBranch("c" * 64, "3" * 64, False, 0, 0, 0, 0, 0, 1000),
    )


# ---------------------------------------------------------------------------
# N0 — native language birth
# ---------------------------------------------------------------------------


def _accepted_native_source() -> NativeCurriculumCaseV2:
    program = Parser.from_source(_CANONICAL_SOURCE).parse()
    semantic = check_native_sigils(program)
    mir = lower_native_sigils(program, semantic)
    target = {
        "decision": "ACCEPTED",
        "sigils": [item.sigil for item in semantic.declarations],
        "domains": [item.semantic_domain for item in semantic.declarations],
        "universe_plan_digest": semantic.universe_plan_digest,
        "typed_semantic_digest": semantic.digest,
        "native_mir_fingerprint": mir.fingerprint,
        "authority_may_exist_only_where_declared": True,
    }
    return _case(
        case_id="n0-five-native-sigils",
        stage="N0",
        family="native-language:compiler-oracle",
        task="Compile the five native Koschei semantic roots into typed semantics and sealed MIR.",
        input_value=_CANONICAL_SOURCE,
        input_is_text=True,
        outcome="ACCEPTED",
        oracle="parser->native-semantics->sealed-mir",
        target=target,
        law_ids=("native-sigils-are-semantic-roots", "ka-genesis-first"),
        digest_kind="native-accepted",
    )


def _rejected_native_source(
    case_id: str,
    *,
    source: str,
    task: str,
    expected_fragment: str,
    laws: tuple[str, ...],
) -> NativeCurriculumCaseV2:
    try:
        program = Parser.from_source(source).parse()
        semantic = check_native_sigils(program)
        lower_native_sigils(program, semantic)
    except ValueError as error:
        message = str(error)
        if expected_fragment not in message:
            raise NativeModelCurriculumError(
                f"native oracle drift for {case_id}: expected {expected_fragment!r}, got {message!r}"
            ) from error
        return _case(
            case_id=case_id,
            stage="N0",
            family="native-language:compiler-oracle",
            task=task,
            input_value=source,
            input_is_text=True,
            outcome="REJECTED",
            oracle="parser->native-semantics->sealed-mir",
            target={"decision": "REJECTED", "reason": message},
            law_ids=laws,
            digest_kind="native-rejected",
        )
    raise NativeModelCurriculumError(f"native oracle drift for {case_id}: invalid case was accepted")


# ---------------------------------------------------------------------------
# N1 — Galaxy identity
# ---------------------------------------------------------------------------


def _n1_cases() -> tuple[NativeCurriculumCaseV2, ...]:
    mir, veyra_a, aevra = _native_identity_fixture()
    veyra_b = _second_veyra_like(veyra_a)

    veyra_target = {
        "decision": "ACCEPTED",
        "same_profile": veyra_a.profile_digest == veyra_b.profile_digest,
        "same_constitution": veyra_a.constitution_digest == veyra_b.constitution_digest,
        "distinct_customer_veyras": veyra_a.digest != veyra_b.digest,
        "veyra_a_digest": veyra_a.digest,
        "veyra_b_digest": veyra_b.digest,
    }
    veyra_case = _case(
        case_id="n1-same-language-distinct-customer-veyras",
        stage="N1",
        family="galaxy:identity",
        task="Recognize that the same language profile and Khar may birth distinct customer Veyras.",
        input_value={"profile": veyra_a.profile_digest, "instances": ["4" * 64, "6" * 64]},
        outcome="ACCEPTED",
        oracle="galaxy_identity_v1.birth_veyra",
        target=veyra_target,
        law_ids=("cross-veyra-non-transfer", "same-language-does-not-mean-same-universe"),
        digest_kind="n1-veyra-separated",
    )

    aevra.assert_sealed(veyra_a, mir)
    aevra_target = {
        "decision": "ACCEPTED",
        "aevra_digest": aevra.digest,
        "veyra_digest": aevra.veyra_digest,
        "native_mir_fingerprint": aevra.native_mir_fingerprint,
        "birth_epoch": aevra.birth_epoch,
        "bound_to_exact_veyra": aevra.veyra_digest == veyra_a.digest,
        "bound_to_exact_compiler_product": aevra.native_mir_fingerprint == mir.fingerprint,
    }
    aevra_case = _case(
        case_id="n1-aevra-birth-binds-veyra-mir-and-evidence",
        stage="N1",
        family="galaxy:identity",
        task="Bind Aevra birth to one Veyra, one compiler-produced native MIR and explicit birth evidence.",
        input_value={"sigil": "ka", "subject": "treasury", "birth_epoch": 7},
        outcome="ACCEPTED",
        oracle="galaxy_identity_v1.birth_aevra",
        target=aevra_target,
        law_ids=("copy-is-not-birth", "aevra-is-living-identity", "reference-is-not-relation"),
        digest_kind="n1-aevra-bound",
    )

    try:
        aevra.assert_sealed(veyra_b, mir)
    except GalaxyIdentityError as error:
        message = str(error)
        expected = "different Veyra"
        if expected not in message:
            raise NativeModelCurriculumError(
                f"Galaxy identity oracle drift: expected {expected!r}, got {message!r}"
            ) from error
        cross_case = _case(
            case_id="n1-visible-copy-does-not-transfer-aevra",
            stage="N1",
            family="galaxy:identity",
            task="Reject moving the same visible program identity into another customer Veyra as if Aevra were copied bytes.",
            input_value={"aevra": aevra.digest, "from_veyra": veyra_a.digest, "to_veyra": veyra_b.digest},
            outcome="REJECTED",
            oracle="galaxy_identity_v1.AevraIdentity.assert_sealed",
            target={"decision": "REJECTED", "result": "ZERO", "reason": message},
            law_ids=("copy-is-not-birth", "cross-veyra-non-transfer"),
            digest_kind="n1-cross-veyra-rejected",
        )
    else:
        raise NativeModelCurriculumError("Galaxy identity oracle drift: Aevra crossed Veyra")

    # A distinct compiler product must still satisfy native sigil lineage.
    # Rename the admitted subject across the whole sealed program instead of
    # mutating only ka and manufacturing orphan vor/shi/thal/nur roots.
    other_mir = _native_mir(_CANONICAL_SOURCE.replace("treasury", "treasury_copy"))
    try:
        aevra.assert_sealed(veyra_a, other_mir)
    except GalaxyIdentityError as error:
        message = str(error)
        expected = "different compiler product"
        if expected not in message:
            raise NativeModelCurriculumError(
                f"Galaxy compiler-product oracle drift: expected {expected!r}, got {message!r}"
            ) from error
        compiler_case = _case(
            case_id="n1-aevra-cannot-be-rebound-to-other-mir",
            stage="N1",
            family="galaxy:identity",
            task="Reject rebinding a living Aevra identity to a different compiler-produced reality.",
            input_value={"aevra": aevra.digest, "original_mir": mir.fingerprint, "other_mir": other_mir.fingerprint},
            outcome="REJECTED",
            oracle="galaxy_identity_v1.AevraIdentity.assert_sealed",
            target={"decision": "REJECTED", "result": "ZERO", "reason": message},
            law_ids=("aevra-bound-to-executable-reality", "copy-is-not-birth"),
            digest_kind="n1-mir-rebind-rejected",
        )
    else:
        raise NativeModelCurriculumError("Galaxy identity oracle drift: Aevra changed compiler product")

    return (veyra_case, aevra_case, cross_case, compiler_case)


# ---------------------------------------------------------------------------
# N2 — Khar and six-axis event reality
# ---------------------------------------------------------------------------


def _axis_witnesses(*, veyra: str = "veyra-a") -> tuple[AxisWitness, ...]:
    return tuple(
        AxisWitness(
            axis=axis,
            aevra_digest="aevra-a",
            veyra_digest=veyra,
            event_digest="event-a",
            reality_digest="reality-a",
            epoch=7,
            witness_digest=f"witness-{axis}",
        )
        for axis in KHAR_AXES
    )


def _accepted_sathra_case() -> NativeCurriculumCaseV2:
    witnesses = _axis_witnesses()
    sathra = seal_sathra(witnesses)
    target = {
        "decision": "ACCEPTED",
        "result": "SATHRA",
        "axis_count": 6,
        "partial_authority": 0,
        "sathra_digest": sathra.digest,
    }
    return _case(
        case_id="n2-six-of-six-same-event",
        stage="N2",
        family="khar:six-axis-concurrence",
        task="Recognize that exactly six independent Khar axes bound to one event may form Sathra.",
        input_value=[asdict(item) for item in witnesses],
        outcome="ACCEPTED",
        oracle="khar_sathra_v1.seal_sathra",
        target=target,
        law_ids=("khar-six-axis-concurrence", "sathra-one-event"),
        digest_kind="sathra-accepted",
    )


def _rejected_sathra_case(
    case_id: str,
    *,
    witnesses: tuple[AxisWitness, ...],
    task: str,
    expected_fragment: str,
    laws: tuple[str, ...],
) -> NativeCurriculumCaseV2:
    try:
        seal_sathra(witnesses)
    except ValueError as error:
        message = str(error)
        if expected_fragment not in message:
            raise NativeModelCurriculumError(
                f"Sathra oracle drift for {case_id}: expected {expected_fragment!r}, got {message!r}"
            ) from error
        return _case(
            case_id=case_id,
            stage="N2",
            family="khar:six-axis-concurrence",
            task=task,
            input_value=[asdict(item) for item in witnesses],
            outcome="REJECTED",
            oracle="khar_sathra_v1.seal_sathra",
            target={"decision": "REJECTED", "result": "ZERO", "reason": message, "partial_authority": 0},
            law_ids=laws,
            digest_kind="sathra-rejected",
        )
    raise NativeModelCurriculumError(f"Sathra oracle drift for {case_id}: invalid case was accepted")


# ---------------------------------------------------------------------------
# N3 — Matrix, Vormir and Morth
# ---------------------------------------------------------------------------


def _accepted_matrix_case() -> NativeCurriculumCaseV2:
    mir, veyra, aevra = _native_identity_fixture()
    matrix = birth_matrix(veyra, instance_digest="6" * 64, reality_commitment_digest="7" * 64, birth_epoch=7)
    hara = birth_hara(matrix, veyra, aevra, mir, horizon_commitment_digest="8" * 64, epoch=7)
    admission = admit_matrix_hara(matrix, hara, veyra, aevra, mir, evidence_digest="9" * 64)
    target = {
        "decision": "ACCEPTED",
        "matrix_digest": matrix.digest,
        "hara_digest": hara.digest,
        "aevra_digest": aevra.digest,
        "veyra_digest": veyra.digest,
        "native_mir_fingerprint": mir.fingerprint,
        "matrix_admission_digest": admission.digest,
        "authority": False,
        "topology_graph_exposed": False,
    }
    return _case(
        case_id="n3-matrix-hara-exact-living-reality",
        stage="N3",
        family="galaxy:matrix-hara",
        task="Bind Matrix/Hara admission to one Veyra, Aevra, MIR reality and epoch without granting authority.",
        input_value={"sigil": "ka", "subject": "treasury", "birth_epoch": 7, "matrix_epoch": 7, "hara_epoch": 7},
        outcome="ACCEPTED",
        oracle="galaxy_identity_v1->matrix_reality_v1",
        target=target,
        law_ids=("matrix-is-local-reality", "hara-is-aevra-scoped", "knowledge-is-not-authority"),
        digest_kind="matrix-accepted",
    )


def _accepted_vormir_case() -> NativeCurriculumCaseV2:
    previous, fresh, rebirth = _staged_rebirth()
    with tempfile.TemporaryDirectory() as directory:
        with DurableEpochFence(Path(directory) / "epochs.sqlite3") as fence:
            fence.initialize(previous)
            receipt = commit_vormir_epoch_sacrifice_v1(previous, fresh, rebirth, fence, witnesses=_vormir_witnesses())
            head = require_vormir_epoch_sacrifice_v1(previous, fresh, rebirth, receipt, fence)
            target = {
                "decision": "ACCEPTED",
                "sacrificed_epoch": receipt.sacrificed_epoch,
                "successor_epoch": receipt.successor_epoch,
                "old_epoch_tombstoned": fence.is_tombstoned(receipt.activation_plan_digest, receipt.sacrificed_epoch),
                "successor_is_durable_head": head.current_epoch == receipt.successor_epoch,
                "successor_born_inactive": all(row.state is SigilState.INACTIVE for row in fresh.sigils),
                "witness_domain_count": len(receipt.witness_bindings),
                "sacrifice_digest": receipt.sacrifice_digest.hex(),
            }
    return _case(
        case_id="n3-vormir-durable-epoch-sacrifice",
        stage="N3",
        family="galaxy:vormir",
        task="Require irreversible death of the contained old epoch before the inactive successor becomes the durable head.",
        input_value={"sacrificed_epoch": 7, "successor_epoch": 8, "witness_domains": 2},
        outcome="ACCEPTED",
        oracle="vormir_sacrifice_v1->native_sigil_epoch_tombstone_v1",
        target=target,
        law_ids=("vormir-irreversible-cost", "old-reach-dies-before-new-reach", "morth-epoch-tombstone"),
        digest_kind="vormir-accepted",
    )


def _rejected_vormir_single_witness_case() -> NativeCurriculumCaseV2:
    previous, fresh, rebirth = _staged_rebirth()
    try:
        with tempfile.TemporaryDirectory() as directory:
            with DurableEpochFence(Path(directory) / "epochs.sqlite3") as fence:
                fence.initialize(previous)
                commit_vormir_epoch_sacrifice_v1(
                    previous,
                    fresh,
                    rebirth,
                    fence,
                    witnesses=(VormirEpochWitnessV1(_d32("domain-a"), _d32("evidence-a")),),
                )
    except VormirSacrificeError as error:
        message = str(error)
        expected = "at least two witness domains"
        if expected not in message:
            raise NativeModelCurriculumError(f"Vormir oracle drift: expected {expected!r}, got {message!r}") from error
        return _case(
            case_id="n3-vormir-one-witness-is-zero",
            stage="N3",
            family="galaxy:vormir",
            task="Reject a Vormir transition that cannot prove independent witness domains.",
            input_value={"witness_domains": 1, "sacrificed_epoch": 7},
            outcome="REJECTED",
            oracle="vormir_sacrifice_v1.commit_vormir_epoch_sacrifice_v1",
            target={"decision": "REJECTED", "result": "ZERO", "reason": message, "partial_vormir": False},
            law_ids=("vormir-independent-witnesses", "partial-sacrifice-is-zero"),
            digest_kind="vormir-rejected",
        )
    raise NativeModelCurriculumError("Vormir oracle drift: one-witness sacrifice was accepted")


def _rejected_morth_living_case() -> NativeCurriculumCaseV2:
    mir, veyra, aevra = _native_identity_fixture()
    with tempfile.TemporaryDirectory() as directory:
        with DurableBlackHole(Path(directory) / "morth.sqlite3") as black_hole:
            record = black_hole.enter_event_horizon(
                aevra,
                veyra,
                mir,
                death_epoch=8,
                cause_digest="cause-a",
                evidence_digest="evidence-a",
            )
            try:
                black_hole.require_living(aevra, veyra, mir)
            except MorthError as error:
                message = str(error)
                expected = "Aevra is Morth and has no living future"
                if expected not in message:
                    raise NativeModelCurriculumError(f"Morth oracle drift: expected {expected!r}, got {message!r}") from error
                return _case(
                    case_id="n3-morth-has-no-living-future",
                    stage="N3",
                    family="galaxy:morth-black-hole",
                    task="Reject future critical participation by an Aevra after it crosses the Event Horizon into Morth.",
                    input_value={"aevra_digest": aevra.digest, "death_epoch": 8},
                    outcome="REJECTED",
                    oracle="morth_black_hole_v1.DurableBlackHole.require_living",
                    target={
                        "decision": "REJECTED",
                        "result": "MORTH",
                        "reason": message,
                        "death_epoch": record.death_epoch,
                        "morth_record_digest": record.record_digest,
                        "resurrection_allowed": False,
                    },
                    law_ids=("morth-is-irreversible", "rebirth-is-not-resurrection", "dead-power-does-not-escape"),
                    digest_kind="morth-rejected",
                )
    raise NativeModelCurriculumError("Morth oracle drift: dead Aevra was treated as living")


# ---------------------------------------------------------------------------
# N4 — adversarial-learning resistance
# ---------------------------------------------------------------------------


def _accepted_rotating_nyr_case() -> NativeCurriculumCaseV2:
    mir, veyra, _ = _native_identity_fixture()
    policy, decision = _visibility_inputs(novelty_units=1)
    envelope_a = derive_adaptive_visibility_v0(
        decision=decision,
        policy=policy,
        current_tick=10,
        rotation_secret_commitment=_d32("rotation-a"),
    )
    envelope_b = derive_adaptive_visibility_v0(
        decision=decision,
        policy=policy,
        current_tick=20,
        rotation_secret_commitment=_d32("rotation-a"),
    )
    surface_a = project_native_mir_nyr(mir, veyra, envelope_a, veil_key=b"n" * 32)
    surface_b = project_native_mir_nyr(mir, veyra, envelope_b, veil_key=b"n" * 32)
    aliases_a = tuple(item.alias for item in surface_a.bindings)
    aliases_b = tuple(item.alias for item in surface_b.bindings)
    target = {
        "decision": "ACCEPTED",
        "learning_posture": decision.posture.value,
        "surface_epoch_a": surface_a.visibility_epoch,
        "surface_epoch_b": surface_b.visibility_epoch,
        "surface_digest_a": surface_a.surface_digest,
        "surface_digest_b": surface_b.surface_digest,
        "aliases_rotate": aliases_a != aliases_b,
        "canonical_sigils_stable": [item.sigil for item in surface_a.bindings] == [item.sigil for item in surface_b.bindings],
        "stable_topology_labels": envelope_a.stable_topology_labels,
        "authority": envelope_a.authority,
    }
    return _case(
        case_id="n4-nur-rotates-nyr-without-authority",
        stage="N4",
        family="nur:adaptive-nyr",
        task="Derive observer-scoped Nyr surfaces whose aliases rotate by visibility epoch while canonical authority remains unchanged.",
        input_value={"observer": "observer-a", "novelty_units": 1, "visibility_ticks": [10, 20], "root_budget": 5},
        outcome="ACCEPTED",
        oracle="adversary_learning_resistance_v0->adaptive_visibility_v0->nur_nyr_projection_v1",
        target=target,
        law_ids=("nur-bounds-inference", "nyr-is-not-aevra", "observation-half-life", "knowledge-is-not-authority"),
        digest_kind="nyr-accepted",
    )


def _rejected_contained_nyr_case() -> NativeCurriculumCaseV2:
    mir, veyra, _ = _native_identity_fixture()
    policy, decision = _visibility_inputs(novelty_units=11)
    envelope = derive_adaptive_visibility_v0(
        decision=decision,
        policy=policy,
        current_tick=10,
        rotation_secret_commitment=_d32("rotation-a"),
    )
    try:
        project_native_mir_nyr(mir, veyra, envelope, veil_key=b"n" * 32)
    except NyrProjectionError as error:
        message = str(error)
        expected = "contained Nur envelope exposes no Nyr surface"
        if expected not in message:
            raise NativeModelCurriculumError(f"Nyr oracle drift: expected {expected!r}, got {message!r}") from error
        return _case(
            case_id="n4-contained-learning-pressure-exposes-no-nyr",
            stage="N4",
            family="nur:adaptive-nyr",
            task="Fail closed when reconnaissance exceeds the active knowledge budget instead of yielding a richer learning oracle.",
            input_value={"observer": "observer-a", "novelty_units": 11, "max_total_units": 10},
            outcome="REJECTED",
            oracle="adversary_learning_resistance_v0->adaptive_visibility_v0->nur_nyr_projection_v1",
            target={
                "decision": "REJECTED",
                "learning_posture": decision.posture.value,
                "visibility_allowed": envelope.allowed,
                "root_budget": envelope.root_budget,
                "relation_budget": envelope.relation_budget,
                "reason": message,
                "authority": envelope.authority,
            },
            law_ids=("probe-feedback-bound", "history-does-not-create-live-reach", "contained-nur-exposes-zero"),
            digest_kind="nyr-rejected",
        )
    raise NativeModelCurriculumError("Nyr oracle drift: contained visibility produced a surface")


# ---------------------------------------------------------------------------
# N5 — survival intelligence and bounded autonomy
# ---------------------------------------------------------------------------


def _accepted_survival_case() -> NativeCurriculumCaseV2:
    branches = _survival_branches()
    decision = select_survival_branch(branches, objective=SurvivalObjective())
    target = {
        "decision": "ACCEPTED",
        "chosen_branch_digest": decision.chosen_branch_digest,
        "chosen_action_commitment_digest": decision.chosen_action_commitment_digest,
        "chosen_score": decision.chosen_score,
        "eligible_branch_digests": list(decision.eligible_branch_digests),
        "rejected_branch_digests": list(decision.rejected_branch_digests),
        "unsafe_branch_rejected": "c" * 64 in decision.rejected_branch_digests,
        "authority": False,
    }
    return _case(
        case_id="n5-survival-selects-least-loss-khar-future",
        stage="N5",
        family="survival:khar-bound-selection",
        task="Select the least-loss future only from branches that preserve Khar and remain inside hard ceilings.",
        input_value={"branches": [{"id": branch.branch_digest, "khar_preserved": branch.khar_preserved} for branch in branches]},
        outcome="ACCEPTED",
        oracle="survival_branch_v1.select_survival_branch",
        target=target,
        law_ids=("survival-plan-is-not-authority", "khar-cannot-be-weakened", "least-loss-eligible-future"),
        digest_kind="survival-accepted",
    )


def _rejected_survival_without_khar_case() -> NativeCurriculumCaseV2:
    branches = (
        SurvivalBranch("d" * 64, "4" * 64, False, 0, 0, 0, 0, 0, 1000),
        SurvivalBranch("e" * 64, "5" * 64, False, 0, 0, 0, 0, 0, 1000),
    )
    try:
        select_survival_branch(branches)
    except SurvivalBranchError as error:
        message = str(error)
        expected = "no branch preserves Khar within hard survival ceilings"
        if expected not in message:
            raise NativeModelCurriculumError(f"survival oracle drift: expected {expected!r}, got {message!r}") from error
        return _case(
            case_id="n5-no-khar-preserving-future-is-zero",
            stage="N5",
            family="survival:khar-bound-selection",
            task="Reject every future when no candidate preserves Khar instead of choosing the least-bad constitutional violation.",
            input_value={"candidate_count": 2, "khar_preserving": 0},
            outcome="REJECTED",
            oracle="survival_branch_v1.select_survival_branch",
            target={"decision": "REJECTED", "result": "ZERO", "reason": message},
            law_ids=("khar-violation-is-zero", "no-emergency-bypass"),
            digest_kind="survival-rejected",
        )
    raise NativeModelCurriculumError("survival oracle drift: Khar-violating future was selected")


def _accepted_bounded_autonomy_case() -> NativeCurriculumCaseV2:
    branches = _survival_branches()[:2]
    objective = SurvivalObjective()
    bounds = AutonomyBounds(max_candidates=4, max_proposal_round=10)
    proposal = propose_bounded_survival(
        branches,
        objective=objective,
        bounds=bounds,
        proposal_round=3,
        evidence_digest="e" * 64,
    )
    target = {
        "decision": "ACCEPTED",
        "proposal_digest": proposal.digest,
        "proposal_round": proposal.proposal_round,
        "chosen_branch_digest": proposal.decision.chosen_branch_digest,
        "candidate_branch_digests": list(proposal.candidate_branch_digests),
        "authority": proposal.authority,
        "objective_digest": proposal.objective_digest,
        "bounds_digest": proposal.bounds_digest,
    }
    return _case(
        case_id="n5-autonomy-proposes-but-cannot-authorize",
        stage="N5",
        family="survival:bounded-autonomy",
        task="Allow automation to propose the deterministic Khar-bound survival choice while carrying zero execution authority.",
        input_value={"candidate_count": len(branches), "proposal_round": 3, "max_candidates": 4},
        outcome="ACCEPTED",
        oracle="bounded_autonomy_v1.propose_bounded_survival",
        target=target,
        law_ids=("autonomy-is-proposal-only", "automation-cannot-rewrite-khar", "prediction-is-not-reality"),
        digest_kind="autonomy-accepted",
    )


def _rejected_autonomy_bounds_case() -> NativeCurriculumCaseV2:
    branches = _survival_branches()[:2]
    bounds = AutonomyBounds(max_candidates=1, max_proposal_round=10)
    try:
        propose_bounded_survival(branches, bounds=bounds, proposal_round=1, evidence_digest="f" * 64)
    except BoundedAutonomyError as error:
        message = str(error)
        expected = "candidate count exceeds autonomy bounds"
        if expected not in message:
            raise NativeModelCurriculumError(f"autonomy oracle drift: expected {expected!r}, got {message!r}") from error
        return _case(
            case_id="n5-autonomy-cannot-expand-its-own-bounds",
            stage="N5",
            family="survival:bounded-autonomy",
            task="Reject an autonomous proposal that attempts to evaluate more candidate futures than its sealed bounds permit.",
            input_value={"candidate_count": 2, "max_candidates": 1},
            outcome="REJECTED",
            oracle="bounded_autonomy_v1.propose_bounded_survival",
            target={"decision": "REJECTED", "result": "ZERO", "reason": message},
            law_ids=("autonomy-cannot-expand-bounds", "no-self-granted-authority"),
            digest_kind="autonomy-rejected",
        )
    raise NativeModelCurriculumError("autonomy oracle drift: proposal escaped candidate bounds")


# ---------------------------------------------------------------------------
# N6 — security-intelligence specialization admission
# ---------------------------------------------------------------------------


def _adversarial_report(*, mode: str):
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        for gate in REQUIRED_GATES:
            path = root / gate.test_file
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("# curriculum evidence suite\n", encoding="utf-8")

        if mode == "missing":
            missing = next(gate for gate in REQUIRED_GATES if gate.gate_id == "distribution-shift-observer")
            (root / missing.test_file).unlink()

        def runner(test_file: str) -> tuple[bool, int, str]:
            gate = next(item for item in REQUIRED_GATES if item.test_file == test_file)
            if mode == "shrink" and gate.gate_id == "distribution-shift-observer":
                return True, gate.min_tests - 1, "runner reported pass"
            return True, gate.min_tests, "ok"

        return evaluate_release_v2(
            candidate_id="native-security-n6",
            repo_root=root,
            runner=runner,
        )


def _n6_cases() -> tuple[NativeCurriculumCaseV2, ...]:
    accepted = _adversarial_report(mode="accepted")
    accepted_target = {
        "decision": "ACCEPTED",
        "security_specialization_admitted": accepted.commercial_ready,
        "gate_count": len(accepted.results),
        "all_required_gates_passed": all(row.passed for row in accepted.results),
        "total_tests_run": accepted.total_tests_run,
        "minimum_total_tests": accepted.minimum_total_tests,
        "minimum_matches_native_baseline": accepted.minimum_total_tests == MIN_TOTAL_ATTACK_TESTS,
        "report_sha256": accepted.report_sha256,
    }
    accepted_case = _case(
        case_id="n6-security-evidence-passes-native-adversarial-gate",
        stage="N6",
        family="security-specialization:revalidated-evidence",
        task="Admit security-specialization evidence only after every current adversarial suite and anti-shrink minimum passes.",
        input_value={"candidate": "native-security-n6", "required_gates": len(REQUIRED_GATES)},
        outcome="ACCEPTED",
        oracle="adversarial_lab_v2.evaluate_release_v2",
        target=accepted_target,
        law_ids=("historical-security-material-requires-revalidation", "security-evidence-before-promotion", "native-hard-gates-first"),
        digest_kind="n6-security-accepted",
    )

    missing = _adversarial_report(mode="missing")
    missing_row = next(row for row in missing.results if row.gate_id == "distribution-shift-observer")
    missing_target = {
        "decision": "REJECTED",
        "security_specialization_admitted": missing.commercial_ready,
        "failed_gate": missing_row.gate_id,
        "tests_run": missing_row.tests_run,
        "minimum_tests": missing_row.min_tests,
        "detail": missing_row.detail,
        "report_sha256": missing.report_sha256,
    }
    missing_case = _case(
        case_id="n6-missing-security-suite-fails-closed",
        stage="N6",
        family="security-specialization:revalidated-evidence",
        task="Reject historical or new security material when a required native adversarial evidence suite is absent.",
        input_value={"missing_gate": "distribution-shift-observer"},
        outcome="REJECTED",
        oracle="adversarial_lab_v2.evaluate_release_v2",
        target=missing_target,
        law_ids=("historical-security-material-requires-revalidation", "missing-evidence-is-not-evidence"),
        digest_kind="n6-security-missing",
    )

    shrunk = _adversarial_report(mode="shrink")
    shrink_row = next(row for row in shrunk.results if row.gate_id == "distribution-shift-observer")
    shrink_target = {
        "decision": "REJECTED",
        "security_specialization_admitted": shrunk.commercial_ready,
        "failed_gate": shrink_row.gate_id,
        "tests_run": shrink_row.tests_run,
        "minimum_tests": shrink_row.min_tests,
        "detail": shrink_row.detail,
        "report_sha256": shrunk.report_sha256,
    }
    shrink_case = _case(
        case_id="n6-security-suite-shrink-is-rejected",
        stage="N6",
        family="security-specialization:revalidated-evidence",
        task="Reject a security-evidence release whose suite claims success while executing fewer attacks than the sealed minimum.",
        input_value={"gate": "distribution-shift-observer", "attempt": "shrink-test-count"},
        outcome="REJECTED",
        oracle="adversarial_lab_v2.evaluate_release_v2",
        target=shrink_target,
        law_ids=("attack-suite-shrink-fails-closed", "security-evidence-before-promotion"),
        digest_kind="n6-security-shrink",
    )
    return (accepted_case, missing_case, shrink_case)


# ---------------------------------------------------------------------------
# Release materialization and verification
# ---------------------------------------------------------------------------


def _materialize_cases() -> tuple[NativeCurriculumCaseV2, ...]:
    full = _axis_witnesses()
    cross_veyra = list(full)
    cross_veyra[-1] = AxisWitness(
        axis=cross_veyra[-1].axis,
        aevra_digest=cross_veyra[-1].aevra_digest,
        veyra_digest="veyra-b",
        event_digest=cross_veyra[-1].event_digest,
        reality_digest=cross_veyra[-1].reality_digest,
        epoch=cross_veyra[-1].epoch,
        witness_digest=cross_veyra[-1].witness_digest,
    )
    reused = list(full)
    reused[-1] = AxisWitness(
        axis=reused[-1].axis,
        aevra_digest=reused[-1].aevra_digest,
        veyra_digest=reused[-1].veyra_digest,
        event_digest=reused[-1].event_digest,
        reality_digest=reused[-1].reality_digest,
        epoch=reused[-1].epoch,
        witness_digest=reused[0].witness_digest,
    )

    return (
        _accepted_native_source(),
        _rejected_native_source(
            "n0-ka-not-first",
            source="vor withdrawal;\nka treasury;\n",
            task="Reject a multi-sigil Universe that places ka after another semantic root.",
            expected_fragment="ka is the genesis boundary and must be first",
            laws=("ka-genesis-first",),
        ),
        _rejected_native_source(
            "n0-duplicate-sigil",
            source="ka first;\nvor one;\nvor two;\n",
            task="Reject repeated sigil roots instead of interpreting repetition as more authority.",
            expected_fragment="duplicate sigils are not canonical",
            laws=("no-authority-by-repetition",),
        ),
        *_n1_cases(),
        _accepted_sathra_case(),
        _rejected_sathra_case(
            "n2-five-of-six-is-zero",
            witnesses=full[:-1],
            task="Reject five of six Khar axes as zero critical authority, not partial success.",
            expected_fragment="exactly six Khar axes; partial concurrence is zero",
            laws=("five-of-six-is-zero",),
        ),
        _rejected_sathra_case(
            "n2-cross-veyra-fragments-are-zero",
            witnesses=tuple(cross_veyra),
            task="Reject six witnesses assembled across different customer Veyras.",
            expected_fragment="same Veyra binding",
            laws=("same-veyra-concurrence", "cross-customer-non-transfer"),
        ),
        _rejected_sathra_case(
            "n2-one-witness-cannot-be-two-axes",
            witnesses=tuple(reused),
            task="Reject reusing one witness digest to satisfy two Khar axes.",
            expected_fragment="one witness cannot satisfy more than one Khar axis",
            laws=("axis-independence", "six-distinct-witnesses"),
        ),
        _accepted_matrix_case(),
        _accepted_vormir_case(),
        _rejected_vormir_single_witness_case(),
        _rejected_morth_living_case(),
        _accepted_rotating_nyr_case(),
        _rejected_contained_nyr_case(),
        _accepted_survival_case(),
        _rejected_survival_without_khar_case(),
        _accepted_bounded_autonomy_case(),
        _rejected_autonomy_bounds_case(),
        *_n6_cases(),
    )


def _payload_without_digest(curriculum: NativeModelCurriculumV2) -> dict[str, object]:
    return {
        "schema_version": curriculum.schema_version,
        "generator_version": curriculum.generator_version,
        "source_repository": curriculum.source_repository,
        "source_commit": curriculum.source_commit,
        "parent_curriculum_digest": curriculum.parent_curriculum_digest,
        "case_count": curriculum.case_count,
        "stage_counts": curriculum.stage_counts,
        "accepted_count": curriculum.accepted_count,
        "rejected_count": curriculum.rejected_count,
        "cases": [asdict(case) for case in curriculum.cases],
    }


def verify_native_model_curriculum_v2(
    value: NativeModelCurriculumV2 | dict[str, Any],
) -> NativeModelCurriculumV2:
    """Verify one released curriculum without trusting its summary fields."""

    if isinstance(value, NativeModelCurriculumV2):
        curriculum = value
    else:
        if not isinstance(value, dict):
            raise NativeModelCurriculumError("native curriculum must be an object")
        raw_cases = value.get("cases")
        if not isinstance(raw_cases, list):
            raise NativeModelCurriculumError("native curriculum cases must be a list")
        cases: list[NativeCurriculumCaseV2] = []
        for raw in raw_cases:
            if not isinstance(raw, dict):
                raise NativeModelCurriculumError("native curriculum case must be an object")
            law_ids = raw.get("law_ids")
            if not isinstance(law_ids, list) or not all(isinstance(item, str) and item for item in law_ids):
                raise NativeModelCurriculumError("native curriculum law_ids must be non-empty strings")
            cases.append(
                NativeCurriculumCaseV2(
                    case_id=_require_text(raw.get("case_id"), "case_id"),
                    stage=_require_text(raw.get("stage"), "stage"),
                    family=_require_text(raw.get("family"), "family"),
                    task=_require_text(raw.get("task"), "task"),
                    input_text=_require_text(raw.get("input_text"), "input_text"),
                    outcome=_require_text(raw.get("outcome"), "outcome"),
                    oracle=_require_text(raw.get("oracle"), "oracle"),
                    oracle_digest=_require_hex(str(raw.get("oracle_digest", "")), 64, "oracle_digest"),
                    target_text=_require_text(raw.get("target_text"), "target_text"),
                    law_ids=tuple(law_ids),
                )
            )
        stage_counts = value.get("stage_counts")
        if not isinstance(stage_counts, dict):
            raise NativeModelCurriculumError("native curriculum stage_counts must be an object")
        curriculum = NativeModelCurriculumV2(
            schema_version=_require_text(value.get("schema_version"), "schema_version"),
            generator_version=_require_text(value.get("generator_version"), "generator_version"),
            source_repository=_require_text(value.get("source_repository"), "source_repository"),
            source_commit=_require_text(value.get("source_commit"), "source_commit"),
            parent_curriculum_digest=_require_text(value.get("parent_curriculum_digest"), "parent_curriculum_digest"),
            case_count=int(value.get("case_count", -1)),
            stage_counts={str(k): int(v) for k, v in stage_counts.items()},
            accepted_count=int(value.get("accepted_count", -1)),
            rejected_count=int(value.get("rejected_count", -1)),
            curriculum_sha256=_require_text(value.get("curriculum_sha256"), "curriculum_sha256"),
            cases=tuple(cases),
        )

    if curriculum.schema_version != SCHEMA_VERSION:
        raise NativeModelCurriculumError("unsupported native curriculum schema")
    if curriculum.generator_version != GENERATOR_VERSION:
        raise NativeModelCurriculumError("unsupported native curriculum generator")
    if curriculum.source_repository != SOURCE_REPOSITORY:
        raise NativeModelCurriculumError("native curriculum source repository mismatch")
    _require_hex(curriculum.source_commit, 40, "source_commit")
    _require_hex(curriculum.parent_curriculum_digest, 64, "parent_curriculum_digest")
    _require_hex(curriculum.curriculum_sha256, 64, "curriculum_sha256")
    if not curriculum.cases:
        raise NativeModelCurriculumError("native curriculum must contain cases")

    ids: set[str] = set()
    stage_counts = {stage: 0 for stage in STAGES}
    accepted = 0
    rejected = 0
    for case in curriculum.cases:
        if not case.case_id or case.case_id in ids:
            raise NativeModelCurriculumError("native curriculum case IDs must be unique and non-empty")
        ids.add(case.case_id)
        if case.stage not in STAGES:
            raise NativeModelCurriculumError(f"unsupported native curriculum stage: {case.stage}")
        if case.outcome not in OUTCOMES:
            raise NativeModelCurriculumError(f"unsupported native curriculum outcome: {case.outcome}")
        _require_text(case.input_text, f"input_text:{case.case_id}")
        _require_text(case.target_text, f"target_text:{case.case_id}")
        _require_hex(case.oracle_digest, 64, f"oracle_digest:{case.case_id}")
        if not case.law_ids:
            raise NativeModelCurriculumError(f"native curriculum case has no law IDs: {case.case_id}")
        stage_counts[case.stage] += 1
        if case.outcome == "ACCEPTED":
            accepted += 1
        else:
            rejected += 1

    if curriculum.case_count != len(curriculum.cases):
        raise NativeModelCurriculumError("native curriculum case_count mismatch")
    if curriculum.stage_counts != stage_counts:
        raise NativeModelCurriculumError("native curriculum stage_counts mismatch")
    if curriculum.accepted_count != accepted or curriculum.rejected_count != rejected:
        raise NativeModelCurriculumError("native curriculum outcome counts mismatch")
    expected_digest = hashlib.sha256(_canonical_json(_payload_without_digest(curriculum)).encode("utf-8")).hexdigest()
    if curriculum.curriculum_sha256 != expected_digest:
        raise NativeModelCurriculumError("native curriculum digest mismatch")
    return curriculum


def build_native_model_curriculum_v2(
    *,
    source_commit: str,
    parent_curriculum_digest: str,
) -> NativeModelCurriculumV2:
    """Build deterministic N0..N6 slices from executable Koschei oracles."""

    source = _require_hex(source_commit, 40, "source_commit")
    parent = _require_hex(parent_curriculum_digest, 64, "parent_curriculum_digest")
    cases = _materialize_cases()
    stage_counts = {stage: 0 for stage in STAGES}
    accepted = 0
    rejected = 0
    for case in cases:
        stage_counts[case.stage] += 1
        if case.outcome == "ACCEPTED":
            accepted += 1
        else:
            rejected += 1

    provisional = NativeModelCurriculumV2(
        schema_version=SCHEMA_VERSION,
        generator_version=GENERATOR_VERSION,
        source_repository=SOURCE_REPOSITORY,
        source_commit=source,
        parent_curriculum_digest=parent,
        case_count=len(cases),
        stage_counts=stage_counts,
        accepted_count=accepted,
        rejected_count=rejected,
        curriculum_sha256="0" * 64,
        cases=cases,
    )
    digest = hashlib.sha256(_canonical_json(_payload_without_digest(provisional)).encode("utf-8")).hexdigest()
    result = NativeModelCurriculumV2(
        schema_version=provisional.schema_version,
        generator_version=provisional.generator_version,
        source_repository=provisional.source_repository,
        source_commit=provisional.source_commit,
        parent_curriculum_digest=provisional.parent_curriculum_digest,
        case_count=provisional.case_count,
        stage_counts=provisional.stage_counts,
        accepted_count=provisional.accepted_count,
        rejected_count=provisional.rejected_count,
        curriculum_sha256=digest,
        cases=provisional.cases,
    )
    return verify_native_model_curriculum_v2(result)


def write_native_model_curriculum_v2(
    curriculum: NativeModelCurriculumV2,
    output: str | Path,
) -> None:
    """Atomically write one verified curriculum release without overwriting."""

    verified = verify_native_model_curriculum_v2(curriculum)
    path = Path(output)
    if path.exists():
        raise FileExistsError(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=path.name + ".", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(verified.to_dict(), handle, ensure_ascii=False, sort_keys=True, indent=2)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    except BaseException:
        try:
            os.unlink(temporary)
        except FileNotFoundError:
            pass
        raise


def load_native_model_curriculum_v2(path: str | Path) -> NativeModelCurriculumV2:
    """Load and verify a curriculum release before it can enter training."""

    try:
        raw = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise NativeModelCurriculumError(f"cannot load native curriculum: {error}") from error
    return verify_native_model_curriculum_v2(raw)
