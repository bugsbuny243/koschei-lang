from dataclasses import replace
import hashlib

import pytest

from koschei.native_intelligence_v1 import (
    CANONICAL_BASE_MODEL_V1,
    NativeIntelligenceError,
    bind_native_intelligence_event,
    build_native_intelligence_identity,
)


def d(tag: str) -> str:
    return hashlib.sha256(tag.encode()).hexdigest()


def identity():
    return build_native_intelligence_identity(
        base_model_revision="a" * 40,
        base_weights_digest=d("qwen397b-weights"),
        curriculum_digest=d("koschei-native-curriculum-v2"),
        adapter_digest=d("koschei-adapter"),
        training_run_digest=d("training-run"),
        source_commit="b" * 40,
        training_method="lora-sft",
    )


def test_canonical_qwen_identity_is_authority_free():
    model = identity()
    model.assert_sealed()
    assert model.base_model_id == CANONICAL_BASE_MODEL_V1
    assert model.authority is False
    assert model.multimodal is True


def test_model_identity_cannot_be_relabelled_to_another_base_model():
    model = identity()
    forged = replace(model, base_model_id="attacker/model")
    with pytest.raises(NativeIntelligenceError, match="base model is not canonical"):
        forged.assert_sealed()


def test_adapter_or_curriculum_tampering_breaks_model_identity():
    model = identity()
    with pytest.raises(NativeIntelligenceError, match="identity seal mismatch"):
        replace(model, adapter_digest=d("other-adapter")).assert_sealed()
    with pytest.raises(NativeIntelligenceError, match="identity seal mismatch"):
        replace(model, curriculum_digest=d("other-curriculum")).assert_sealed()


def test_model_identity_can_never_carry_authority():
    model = identity()
    with pytest.raises(NativeIntelligenceError, match="cannot carry authority"):
        replace(model, authority=True).assert_sealed()


def test_model_output_is_bound_to_one_exact_galaxy_proposal_event():
    model = identity()
    binding = bind_native_intelligence_event(
        model,
        veyra_digest=d("veyra-a"),
        native_mir_fingerprint=d("native-mir"),
        epoch=17,
        proposal_digest=d("proposal"),
        observation_digest=d("observation"),
        output_digest=d("model-output"),
    )
    binding.assert_for(
        model,
        veyra_digest=d("veyra-a"),
        native_mir_fingerprint=d("native-mir"),
        epoch=17,
        proposal_digest=d("proposal"),
    )
    assert binding.authority is False


def test_model_output_cannot_move_to_another_veyra_mir_epoch_or_proposal():
    model = identity()
    binding = bind_native_intelligence_event(
        model,
        veyra_digest=d("veyra-a"),
        native_mir_fingerprint=d("native-mir"),
        epoch=17,
        proposal_digest=d("proposal"),
        observation_digest=d("observation"),
        output_digest=d("model-output"),
    )
    cases = (
        dict(veyra_digest=d("veyra-b"), native_mir_fingerprint=d("native-mir"), epoch=17, proposal_digest=d("proposal")),
        dict(veyra_digest=d("veyra-a"), native_mir_fingerprint=d("other-mir"), epoch=17, proposal_digest=d("proposal")),
        dict(veyra_digest=d("veyra-a"), native_mir_fingerprint=d("native-mir"), epoch=18, proposal_digest=d("proposal")),
        dict(veyra_digest=d("veyra-a"), native_mir_fingerprint=d("native-mir"), epoch=17, proposal_digest=d("other-proposal")),
    )
    for kwargs in cases:
        with pytest.raises(NativeIntelligenceError, match="mismatch"):
            binding.assert_for(model, **kwargs)


def test_output_bytes_tampering_breaks_event_binding():
    model = identity()
    binding = bind_native_intelligence_event(
        model,
        veyra_digest=d("veyra-a"),
        native_mir_fingerprint=d("native-mir"),
        epoch=17,
        proposal_digest=d("proposal"),
        observation_digest=d("observation"),
        output_digest=d("model-output"),
    )
    forged = replace(binding, output_digest=d("forged-output"))
    with pytest.raises(NativeIntelligenceError, match="event binding seal mismatch"):
        forged.assert_for(
            model,
            veyra_digest=d("veyra-a"),
            native_mir_fingerprint=d("native-mir"),
            epoch=17,
            proposal_digest=d("proposal"),
        )
