import json

import pytest

from koschei.native_model_curriculum_v2 import (
    NativeModelCurriculumError,
    build_native_model_curriculum_v2,
    load_native_model_curriculum_v2,
    verify_native_model_curriculum_v2,
    write_native_model_curriculum_v2,
)


def curriculum():
    return build_native_model_curriculum_v2(
        source_commit="a" * 40,
        parent_curriculum_digest="b" * 64,
    )


def test_native_curriculum_through_n5_is_oracle_backed_and_deterministic():
    first = curriculum()
    second = curriculum()

    assert first == second
    assert first.case_count == 17
    assert first.stage_counts["N0"] == 3
    assert first.stage_counts["N1"] == 0
    assert first.stage_counts["N2"] == 4
    assert first.stage_counts["N3"] == 4
    assert first.stage_counts["N4"] == 2
    assert first.stage_counts["N5"] == 4
    assert first.stage_counts["N6"] == 0
    assert first.accepted_count == 7
    assert first.rejected_count == 10
    assert len(first.curriculum_sha256) == 64


def test_five_of_six_is_encoded_as_zero_not_partial_authority():
    item = next(case for case in curriculum().cases if case.case_id == "n2-five-of-six-is-zero")
    target = json.loads(item.target_text)

    assert item.outcome == "REJECTED"
    assert target["result"] == "ZERO"
    assert target["partial_authority"] == 0
    assert "partial concurrence is zero" in target["reason"]


def test_cross_veyra_six_fragments_are_rejected():
    item = next(
        case
        for case in curriculum().cases
        if case.case_id == "n2-cross-veyra-fragments-are-zero"
    )
    target = json.loads(item.target_text)

    assert item.outcome == "REJECTED"
    assert target["result"] == "ZERO"
    assert "same Veyra binding" in target["reason"]


def test_native_sigils_are_compiler_oracle_output():
    item = next(case for case in curriculum().cases if case.case_id == "n0-five-native-sigils")
    target = json.loads(item.target_text)

    assert target["decision"] == "ACCEPTED"
    assert target["sigils"] == ["ka", "vor", "shi", "thal", "nur"]
    assert len(target["native_mir_fingerprint"]) == 64
    assert len(target["typed_semantic_digest"]) == 64


def test_vormir_curriculum_kills_old_epoch_before_successor_head():
    item = next(
        case for case in curriculum().cases if case.case_id == "n3-vormir-durable-epoch-sacrifice"
    )
    target = json.loads(item.target_text)

    assert item.outcome == "ACCEPTED"
    assert target["sacrificed_epoch"] == 7
    assert target["successor_epoch"] == 8
    assert target["old_epoch_tombstoned"] is True
    assert target["successor_is_durable_head"] is True
    assert target["successor_born_inactive"] is True
    assert target["witness_domain_count"] == 2


def test_morth_curriculum_forbids_dead_aevra_future():
    item = next(
        case for case in curriculum().cases if case.case_id == "n3-morth-has-no-living-future"
    )
    target = json.loads(item.target_text)

    assert item.outcome == "REJECTED"
    assert target["result"] == "MORTH"
    assert target["resurrection_allowed"] is False
    assert "no living future" in target["reason"]


def test_nur_curriculum_rotates_nyr_without_creating_authority():
    item = next(
        case for case in curriculum().cases if case.case_id == "n4-nur-rotates-nyr-without-authority"
    )
    target = json.loads(item.target_text)

    assert item.outcome == "ACCEPTED"
    assert target["aliases_rotate"] is True
    assert target["canonical_sigils_stable"] is True
    assert target["stable_topology_labels"] is False
    assert target["authority"] is False
    assert target["surface_digest_a"] != target["surface_digest_b"]


def test_learning_pressure_can_contain_visibility_to_zero():
    item = next(
        case
        for case in curriculum().cases
        if case.case_id == "n4-contained-learning-pressure-exposes-no-nyr"
    )
    target = json.loads(item.target_text)

    assert item.outcome == "REJECTED"
    assert target["learning_posture"] == "contained"
    assert target["visibility_allowed"] is False
    assert target["root_budget"] == 0
    assert target["relation_budget"] == 0
    assert target["authority"] is False


def test_survival_curriculum_rejects_khar_violating_branch():
    item = next(
        case
        for case in curriculum().cases
        if case.case_id == "n5-survival-selects-least-loss-khar-future"
    )
    target = json.loads(item.target_text)

    assert item.outcome == "ACCEPTED"
    assert target["unsafe_branch_rejected"] is True
    assert target["chosen_branch_digest"] == "a" * 64
    assert target["authority"] is False


def test_bounded_autonomy_curriculum_is_proposal_only():
    item = next(
        case
        for case in curriculum().cases
        if case.case_id == "n5-autonomy-proposes-but-cannot-authorize"
    )
    target = json.loads(item.target_text)

    assert item.outcome == "ACCEPTED"
    assert target["authority"] is False
    assert target["proposal_round"] == 3
    assert target["chosen_branch_digest"] == "a" * 64


def test_summary_or_case_tampering_breaks_release_digest():
    value = curriculum().to_dict()
    value["accepted_count"] = 99
    with pytest.raises(NativeModelCurriculumError, match="outcome counts mismatch"):
        verify_native_model_curriculum_v2(value)

    value = curriculum().to_dict()
    value["cases"][0]["task"] = "attacker relabelled task"
    with pytest.raises(NativeModelCurriculumError, match="digest mismatch"):
        verify_native_model_curriculum_v2(value)


def test_write_load_round_trip_and_no_overwrite(tmp_path):
    path = tmp_path / "native-curriculum-v2.json"
    expected = curriculum()

    write_native_model_curriculum_v2(expected, path)
    assert load_native_model_curriculum_v2(path) == expected

    with pytest.raises(FileExistsError):
        write_native_model_curriculum_v2(expected, path)
