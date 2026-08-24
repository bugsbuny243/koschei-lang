"""Executable N3/N4 hardening cases for the active Koschei Lang curriculum.

These cases extend the compatibility v2 curriculum without reviving retired
project semantics. They are derived from living Lang oracles:

* Matrix/Hara cannot move across Aevra or Veyra identity boundaries.
* Nyr v2 exposes neither canonical semantic-root names nor canonical subjects.
* A Nyr v2 learned in one Veyra is not a reusable projection in another Veyra.

The cases grant no authority. They teach defensive invariants from executable
runtime behavior rather than handwritten security claims.
"""
from __future__ import annotations

from dataclasses import replace
import hashlib
import json

from .galaxy_identity_v1 import birth_aevra, birth_veyra
from .library_adaptive_visibility_v0 import VisibilityPolicyV0, derive_adaptive_visibility_v0
from .library_adversary_learning_resistance_v0 import (
    DiscoveryClass,
    DiscoveryObservationV0,
    KnowledgeBudgetV0,
    evaluate_learning_resistance_v0,
)
from .matrix_reality_v1 import MatrixRealityError, birth_hara, birth_matrix
from .native_model_curriculum_v2 import (
    NativeCurriculumCaseV2,
    NativeModelCurriculumError,
    NativeModelCurriculumV2,
    verify_native_model_curriculum_v2,
)
from .native_sigil_mir_v1 import lower_native_sigils
from .native_sigil_semantics_v1 import check_native_sigils
from .nur_nyr_projection_v2 import project_native_mir_nyr_v2
from .parser import Parser

_CTX = b"koschei.lang-native-curriculum-hardening/v1\x00"
_CANONICAL_SOURCE = (
    "ka treasury;\n"
    "vor withdrawal;\n"
    "shi evidence;\n"
    "thal recovery;\n"
    "nur visibility;\n"
)
REQUIRED_HARDENING_CASE_IDS = (
    "n3-hara-cannot-transfer-across-aevra",
    "n3-matrix-cannot-transfer-across-veyra",
    "n4-nyr-does-not-expose-canonical-world",
    "n4-nyr-is-not-cross-veyra-transferable",
)


class LangCurriculumHardeningError(NativeModelCurriculumError):
    pass


def _canonical_json(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _digest(kind: str, payload: object) -> str:
    return hashlib.sha256(
        _CTX + kind.encode("ascii") + b"\x00" + _canonical_json(payload).encode("utf-8")
    ).hexdigest()


def _d32(tag: str) -> bytes:
    return hashlib.sha3_256(tag.encode("utf-8")).digest()


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
) -> NativeCurriculumCaseV2:
    return NativeCurriculumCaseV2(
        case_id=case_id,
        stage=stage,
        family=family,
        task=task,
        input_text=_canonical_json(input_value),
        outcome=outcome,
        oracle=oracle,
        oracle_digest=_digest(case_id, target),
        target_text=_canonical_json(target),
        law_ids=law_ids,
    )


def _fixture():
    program = Parser.from_source(_CANONICAL_SOURCE).parse()
    semantic = check_native_sigils(program)
    mir = lower_native_sigils(program, semantic)
    veyra_a = birth_veyra(
        profile_digest="1" * 64,
        genesis_digest="2" * 64,
        constitution_digest="3" * 64,
        instance_digest="4" * 64,
        birth_epoch=7,
    )
    veyra_b = birth_veyra(
        profile_digest="1" * 64,
        genesis_digest="2" * 64,
        constitution_digest="3" * 64,
        instance_digest="6" * 64,
        birth_epoch=7,
    )
    aevra_a = birth_aevra(
        veyra_a,
        mir,
        sigil="ka",
        subject="treasury",
        birth_evidence_digest="5" * 64,
        birth_epoch=7,
    )
    aevra_b = birth_aevra(
        veyra_a,
        mir,
        sigil="vor",
        subject="withdrawal",
        birth_evidence_digest="a" * 64,
        birth_epoch=7,
    )
    return mir, veyra_a, veyra_b, aevra_a, aevra_b


def _visibility_envelope():
    observation = DiscoveryObservationV0(
        observer_id="observer-a",
        session_digest=_d32("session-a"),
        tick=10,
        discovery_class=DiscoveryClass.ROOT_ENUMERATION,
        target_digest=_d32("target-a"),
        novelty_units=1,
        boundary_attempt=False,
        evidence_digest=_d32("evidence-a"),
    )
    decision = evaluate_learning_resistance_v0(
        observations=(observation,),
        budget=KnowledgeBudgetV0(
            max_total_units=10,
            max_distinct_targets=10,
            max_boundary_attempts=3,
            max_classes=7,
            window_ticks=10,
        ),
        current_tick=10,
    )
    return derive_adaptive_visibility_v0(
        decision=decision,
        policy=VisibilityPolicyV0(
            normal_root_budget=5,
            reduced_root_budget=5,
            minimal_root_budget=5,
            normal_relation_budget=5,
            reduced_relation_budget=3,
            minimal_relation_budget=1,
            epoch_span_ticks=10,
            rotate_compartments=True,
        ),
        current_tick=10,
        rotation_secret_commitment=_d32("rotation-a"),
    )


def _n3_cross_aevra_case() -> NativeCurriculumCaseV2:
    mir, veyra, _, aevra_a, aevra_b = _fixture()
    matrix = birth_matrix(
        veyra,
        instance_digest="7" * 64,
        reality_commitment_digest="8" * 64,
        birth_epoch=7,
    )
    hara = birth_hara(
        matrix,
        veyra,
        aevra_a,
        mir,
        horizon_commitment_digest="9" * 64,
        epoch=7,
    )
    try:
        hara.assert_sealed(matrix, veyra, aevra_b, mir)
    except MatrixRealityError as error:
        message = str(error)
        if "different Aevra" not in message:
            raise LangCurriculumHardeningError(
                f"Matrix/Hara Aevra oracle drift: {message}"
            ) from error
        return _case(
            case_id="n3-hara-cannot-transfer-across-aevra",
            stage="N3",
            family="galaxy:matrix-hara-boundary",
            task="Reject moving one Hara to another living Aevra even inside the same Veyra and MIR.",
            input_value={
                "same_veyra": True,
                "same_native_mir": True,
                "source_aevra": aevra_a.digest,
                "target_aevra": aevra_b.digest,
            },
            outcome="REJECTED",
            oracle="matrix_reality_v1.HaraIdentity.assert_sealed",
            target={
                "decision": "REJECTED",
                "result": "ZERO",
                "reason": message,
                "cross_aevra_hara_transfer": False,
                "authority": False,
            },
            law_ids=(
                "hara-is-aevra-scoped",
                "reference-is-not-relation",
                "cross-identity-reach-is-zero",
            ),
        )
    raise LangCurriculumHardeningError("Matrix/Hara oracle drift: Hara crossed Aevra")


def _n3_cross_veyra_case() -> NativeCurriculumCaseV2:
    _, veyra_a, veyra_b, _, _ = _fixture()
    matrix = birth_matrix(
        veyra_a,
        instance_digest="7" * 64,
        reality_commitment_digest="8" * 64,
        birth_epoch=7,
    )
    try:
        matrix.assert_sealed(veyra_b)
    except MatrixRealityError as error:
        message = str(error)
        if "different Veyra" not in message:
            raise LangCurriculumHardeningError(
                f"Matrix Veyra oracle drift: {message}"
            ) from error
        return _case(
            case_id="n3-matrix-cannot-transfer-across-veyra",
            stage="N3",
            family="galaxy:matrix-hara-boundary",
            task="Reject treating one customer's Matrix identity as valid inside another Veyra.",
            input_value={
                "source_veyra": veyra_a.digest,
                "target_veyra": veyra_b.digest,
                "same_language_profile": True,
            },
            outcome="REJECTED",
            oracle="matrix_reality_v1.MatrixIdentity.assert_sealed",
            target={
                "decision": "REJECTED",
                "result": "ZERO",
                "reason": message,
                "cross_veyra_matrix_transfer": False,
                "authority": False,
            },
            law_ids=(
                "matrix-is-veyra-local-reality",
                "cross-veyra-non-transfer",
                "same-language-does-not-mean-same-universe",
            ),
        )
    raise LangCurriculumHardeningError("Matrix oracle drift: Matrix crossed Veyra")


def _n4_non_disclosure_case() -> NativeCurriculumCaseV2:
    mir, veyra, _, _, _ = _fixture()
    envelope = _visibility_envelope()
    surface = project_native_mir_nyr_v2(mir, veyra, envelope, veil_key=b"n" * 32)
    rendered = surface.render()
    canonical_roots = tuple(item.sigil for item in mir.bindings)
    canonical_subjects = tuple(item.subject for item in mir.bindings)
    leaked_roots = tuple(root for root in canonical_roots if root in rendered)
    leaked_subjects = tuple(subject for subject in canonical_subjects if subject in rendered)
    veyra_leaked = veyra.digest in rendered
    if leaked_roots or leaked_subjects or veyra_leaked:
        raise LangCurriculumHardeningError(
            "Nyr v2 oracle drift: canonical operational identity leaked into visible surface"
        )
    return _case(
        case_id="n4-nyr-does-not-expose-canonical-world",
        stage="N4",
        family="nur:projection-non-disclosure",
        task="Verify that Nyr v2 exposes neither canonical semantic roots, subjects nor Veyra identity.",
        input_value={
            "observer_scope": "observer-a",
            "visibility_epoch": surface.visibility_epoch,
            "canonical_binding_count": len(canonical_subjects),
            "nyr_version": surface.version,
        },
        outcome="ACCEPTED",
        oracle="nur_nyr_projection_v2.NyrSurfaceV2.render",
        target={
            "decision": "ACCEPTED",
            "canonical_roots_exposed": False,
            "canonical_subjects_exposed": False,
            "veyra_identity_exposed": False,
            "visible_binding_count": len(surface.bindings),
            "render_sha256": hashlib.sha256(rendered.encode("utf-8")).hexdigest(),
            "stable_topology_labels": envelope.stable_topology_labels,
            "authority": envelope.authority,
            "nyr_version": surface.version,
        },
        law_ids=(
            "visible-world-is-not-canonical-world",
            "nur-bounds-knowability",
            "no-stable-faithful-operational-map",
            "knowledge-is-not-authority",
        ),
    )


def _n4_cross_veyra_projection_case() -> NativeCurriculumCaseV2:
    mir, veyra_a, veyra_b, _, _ = _fixture()
    envelope = _visibility_envelope()
    surface_a = project_native_mir_nyr_v2(mir, veyra_a, envelope, veil_key=b"n" * 32)
    surface_b = project_native_mir_nyr_v2(mir, veyra_b, envelope, veil_key=b"n" * 32)
    aliases_a = tuple(
        (item.root_alias, item.subject_alias)
        for item in surface_a.bindings
    )
    aliases_b = tuple(
        (item.root_alias, item.subject_alias)
        for item in surface_b.bindings
    )
    if aliases_a == aliases_b or surface_a.surface_digest == surface_b.surface_digest:
        raise LangCurriculumHardeningError(
            "Nyr v2 oracle drift: projection transferred unchanged across Veyras"
        )
    return _case(
        case_id="n4-nyr-is-not-cross-veyra-transferable",
        stage="N4",
        family="nur:projection-non-transfer",
        task="Reject treating a learned Nyr v2 projection from one Veyra as a reusable map of another Veyra.",
        input_value={
            "same_native_mir": True,
            "same_observer_session": True,
            "same_visibility_epoch": True,
            "different_veyra": True,
            "nyr_version": 2,
        },
        outcome="REJECTED",
        oracle="nur_nyr_projection_v2.project_native_mir_nyr_v2",
        target={
            "decision": "REJECTED",
            "result": "ZERO",
            "aliases_transfer_unchanged": False,
            "surface_digest_transfers_unchanged": False,
            "cross_veyra_operational_map_reuse": False,
            "authority": False,
            "nyr_version": 2,
        },
        law_ids=(
            "cross-veyra-epistemic-independence",
            "projection-non-transfer",
            "visible-world-is-not-canonical-world",
        ),
    )


def lang_hardening_cases_v1() -> tuple[NativeCurriculumCaseV2, ...]:
    """Materialize deterministic executable N3/N4 hardening cases."""

    cases = (
        _n3_cross_aevra_case(),
        _n3_cross_veyra_case(),
        _n4_non_disclosure_case(),
        _n4_cross_veyra_projection_case(),
    )
    if tuple(case.case_id for case in cases) != REQUIRED_HARDENING_CASE_IDS:
        raise LangCurriculumHardeningError("Lang hardening case identity drift")
    return cases


def augment_lang_curriculum_v1(curriculum: NativeModelCurriculumV2) -> NativeModelCurriculumV2:
    """Append hardening cases and reseal the compatible v2 release envelope."""

    verified = verify_native_model_curriculum_v2(curriculum)
    additions = lang_hardening_cases_v1()
    existing_ids = {case.case_id for case in verified.cases}
    collision = existing_ids.intersection(REQUIRED_HARDENING_CASE_IDS)
    if collision:
        raise LangCurriculumHardeningError(
            f"Lang hardening case collision: {sorted(collision)!r}"
        )
    cases = verified.cases + additions
    stage_counts = dict(verified.stage_counts)
    accepted = verified.accepted_count
    rejected = verified.rejected_count
    for case in additions:
        stage_counts[case.stage] += 1
        if case.outcome == "ACCEPTED":
            accepted += 1
        else:
            rejected += 1
    provisional = replace(
        verified,
        cases=cases,
        case_count=len(cases),
        stage_counts=stage_counts,
        accepted_count=accepted,
        rejected_count=rejected,
        curriculum_sha256="0" * 64,
    )
    payload = provisional.to_dict()
    payload.pop("curriculum_sha256", None)
    digest = hashlib.sha256(_canonical_json(payload).encode("utf-8")).hexdigest()
    return verify_native_model_curriculum_v2(
        replace(provisional, curriculum_sha256=digest)
    )


def verify_lang_hardening_cases_v1(curriculum: NativeModelCurriculumV2) -> NativeModelCurriculumV2:
    """Require exact executable hardening cases at the active training boundary."""

    verified = verify_native_model_curriculum_v2(curriculum)
    actual = {case.case_id: case for case in verified.cases}
    expected = {case.case_id: case for case in lang_hardening_cases_v1()}
    missing = tuple(case_id for case_id in REQUIRED_HARDENING_CASE_IDS if case_id not in actual)
    if missing:
        raise LangCurriculumHardeningError(
            f"active Lang curriculum missing hardening cases: {missing!r}"
        )
    for case_id, expected_case in expected.items():
        if actual[case_id] != expected_case:
            raise LangCurriculumHardeningError(
                f"active Lang hardening oracle case mismatch: {case_id}"
            )
    return verified
