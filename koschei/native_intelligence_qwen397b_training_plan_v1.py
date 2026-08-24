"""Qwen3.5-397B-A17B-specific Koschei training plan boundary v1.

The canonical first 397B plan is not identified by a static LoRA profile alone.
It must bind the pinned base-artifact preflight, the exact balanced export and a
zero-truncation tokenizer profile into one Qwen397BRunConfigV1. The generic
NativeTrainingPlanV1 then consumes that complete run-config digest.
"""
from __future__ import annotations

from .native_intelligence_holdout_v1 import NativeIntelligenceHoldoutV1
from .native_intelligence_qwen397b_base_spec_v1 import (
    CANONICAL_QWEN397B_REVISION_V1,
    CANONICAL_QWEN397B_TRAINING_METHOD_V1,
)
from .native_intelligence_qwen397b_preflight_v1 import Qwen397BPreflightEvidenceV1
from .native_intelligence_qwen397b_profile_v1 import (
    Qwen397BKoscheiTrainingProfileV1,
    canonical_qwen397b_koschei_profile_v1,
)
from .native_intelligence_qwen397b_run_config_v1 import (
    Qwen397BRunConfigError,
    seal_qwen397b_run_config_v1,
)
from .native_intelligence_qwen397b_token_profile_v1 import Qwen397BTokenProfileV1
from .native_intelligence_training_corpus_v1 import NativeTrainingCorpusReleaseV1
from .native_intelligence_training_export_v1 import NativeTrainingExportManifestV1
from .native_intelligence_training_lineage_v1 import (
    NativeIntelligenceTrainingLineageError,
    NativeTrainingPlanV1,
    seal_native_training_plan_v1,
)


class Qwen397BTrainingPlanError(ValueError):
    pass


def _run_config(
    profile: Qwen397BKoscheiTrainingProfileV1,
    preflight: Qwen397BPreflightEvidenceV1,
    token_profile: Qwen397BTokenProfileV1,
    manifest: NativeTrainingExportManifestV1,
):
    try:
        return seal_qwen397b_run_config_v1(
            profile,
            preflight,
            token_profile,
            manifest,
        )
    except ValueError as error:
        raise Qwen397BTrainingPlanError(str(error)) from error


def require_canonical_qwen397b_training_plan_v1(
    plan: NativeTrainingPlanV1,
    manifest: NativeTrainingExportManifestV1,
    preflight: Qwen397BPreflightEvidenceV1,
    token_profile: Qwen397BTokenProfileV1,
    profile: Qwen397BKoscheiTrainingProfileV1 | None = None,
) -> None:
    """Re-derive the full run-config and require exact plan identity."""

    profile = profile or canonical_qwen397b_koschei_profile_v1()
    config = _run_config(profile, preflight, token_profile, manifest)
    try:
        plan.assert_sealed()
    except NativeIntelligenceTrainingLineageError as error:
        raise Qwen397BTrainingPlanError(str(error)) from error

    if plan.base_model_revision != CANONICAL_QWEN397B_REVISION_V1:
        raise Qwen397BTrainingPlanError("Qwen397B base revision drift")
    if plan.base_weights_digest != preflight.weights_identity_digest:
        raise Qwen397BTrainingPlanError("Qwen397B base artifact identity mismatch")
    if plan.training_export_digest != manifest.digest:
        raise Qwen397BTrainingPlanError("Qwen397B training export mismatch")
    if plan.training_config_digest != config.digest:
        raise Qwen397BTrainingPlanError("Qwen397B complete run-config digest mismatch")
    if plan.training_method != CANONICAL_QWEN397B_TRAINING_METHOD_V1:
        raise Qwen397BTrainingPlanError("Qwen397B training method drift")


def seal_canonical_qwen397b_training_plan_v1(
    holdout: NativeIntelligenceHoldoutV1,
    corpus: NativeTrainingCorpusReleaseV1,
    export_manifest: NativeTrainingExportManifestV1,
    *,
    preflight: Qwen397BPreflightEvidenceV1,
    token_profile: Qwen397BTokenProfileV1,
    profile: Qwen397BKoscheiTrainingProfileV1 | None = None,
) -> NativeTrainingPlanV1:
    """Seal the canonical first-run 397B plan from complete preflight evidence."""

    profile = profile or canonical_qwen397b_koschei_profile_v1()
    config = _run_config(profile, preflight, token_profile, export_manifest)
    try:
        plan = seal_native_training_plan_v1(
            holdout,
            corpus,
            export_manifest,
            base_model_revision=CANONICAL_QWEN397B_REVISION_V1,
            base_weights_digest=preflight.weights_identity_digest,
            training_config_digest=config.digest,
            training_method=CANONICAL_QWEN397B_TRAINING_METHOD_V1,
        )
    except NativeIntelligenceTrainingLineageError as error:
        raise Qwen397BTrainingPlanError(str(error)) from error

    require_canonical_qwen397b_training_plan_v1(
        plan,
        export_manifest,
        preflight,
        token_profile,
        profile,
    )
    return plan
