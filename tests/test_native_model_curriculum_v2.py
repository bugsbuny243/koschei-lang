from dataclasses import asdict
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


def test_first_slice_is_oracle_backed_and_deterministic():
    first = curriculum()
    second = curriculum()

    assert first == second
    assert first.case_count == 7
    assert first.stage_counts["N0"] == 3
    assert first.stage_counts["N2"] == 4
    assert first.accepted_count == 2
    assert first.rejected_count == 5
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
