"""Qwen3.5-397B-A17B-specific Koschei training plan boundary v1.

Generic native-intelligence plans remain useful for future model families, but
the first Koschei 397B run must not accept an arbitrary revision, configuration
or training method. This module binds the generic sealed plan to one canonical
Qwen repository revision and the canonical Koschei LoRA profile v1.
"""
from __future__ import annotations

from .native_intelligence_holdout_v1 import NativeIntelligenceHoldoutV1
from .native_intelligence_qwen397b_profile_v1 import (
    Qwen397BKoscheiTrainingProfileV1,
    canonical_qwen397b_koschei_profile_v1,
)
from .native_intelligence_training_corpus_v1 import NativeTrainingCorpusReleaseV1
from .native_intelligence_training_export_v1 import NativeTrainingExportManifestV1
from .native_intelligence_training_lineage_v1 import (
    NativeIntelligenceTrainingLineageError,
    NativeTrainingPlanV1,
    seal_native_training_plan_v1,
)

CANONICAL_QWEN397B_REVISION_V1 = "8472618112abcbd45acbcdc58436aff4233c23f7"
CANONICAL_QWEN397B_TRAINING_METHOD_V1 = "lora-sft-v1"


class Qwen397BTrainingPlanError(ValueError):
    pass


def require_canonical_qwen397b_training_plan_v1(
    plan: NativeTrainingPlanV1,
    profile: Qwen397BKoscheiTrainingProfileV1 | None = None,
) -> None:
    """Require one generic plan to be exactly the canonical first Qwen397B run."""

    profile = profile or canonical_qwen397b_koschei_profile_v1()
    profile.assert_sealed()
    try:
        plan.assert_sealed()
    except NativeIntelligenceTrainingLineageError as error:
        raise Qwen397BTrainingPlanError(str(error)) from error
    if plan.base_model_revision != CANONICAL_QWEN397B_REVISION_V1:
        raise Qwen397BTrainingPlanError("Qwen397B base revision drift")
    if plan.training_config_digest != profile.digest:
        raise Qwen397BTrainingPlanError("Qwen397B training profile digest mismatch")
    if plan.training_method != CANONICAL_QWEN397B_TRAINING_METHOD_V1:
        raise Qwen397BTrainingPlanError("Qwen397B training method drift")


def seal_canonical_qwen397b_training_plan_v1(
    holdout: NativeIntelligenceHoldoutV1,
    corpus: NativeTrainingCorpusReleaseV1,
    export_manifest: NativeTrainingExportManifestV1,
    *,
    base_weights_digest: str,
    profile: Qwen397BKoscheiTrainingProfileV1 | None = None,
) -> NativeTrainingPlanV1:
    """Seal the only canonical first-run 397B Koschei plan."""

    profile = profile or canonical_qwen397b_koschei_profile_v1()
    profile.assert_sealed()
    try:
        plan = seal_native_training_plan_v1(
            holdout,
            corpus,
            export_manifest,
            base_model_revision=CANONICAL_QWEN397B_REVISION_V1,
            base_weights_digest=base_weights_digest,
            training_config_digest=profile.digest,
            training_method=CANONICAL_QWEN397B_TRAINING_METHOD_V1,
        )
    except NativeIntelligenceTrainingLineageError as error:
        raise Qwen397BTrainingPlanError(str(error)) from error
    require_canonical_qwen397b_training_plan_v1(plan, profile)
    return plan
