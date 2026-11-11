"""Qwen397B-specific training launch boundary v1.

GitHub-hosted CI is not part of this boundary. Before trainer inputs may be
exposed, the exact source commit must have a sealed full/clean local validation
receipt, and the Qwen base/token/run-config evidence must still re-derive.
"""
from __future__ import annotations

from pathlib import Path

from .local_validation_v1 import (
    LocalValidationError,
    LocalValidationReceiptV1,
)
from .native_intelligence_qwen397b_preflight_v1 import Qwen397BPreflightEvidenceV1
from .native_intelligence_qwen397b_profile_v1 import (
    Qwen397BKoscheiTrainingProfileV1,
    canonical_qwen397b_koschei_profile_v1,
)
from .native_intelligence_qwen397b_token_profile_v1 import Qwen397BTokenProfileV1
from .native_intelligence_qwen397b_training_plan_v1 import (
    require_canonical_qwen397b_training_plan_v1,
)
from .native_intelligence_training_export_v1 import NativeTrainingExportManifestV1
from .native_intelligence_training_launch_v1 import (
    NativeTrainerDataInputsV1,
    NativeTrainingLaunchSpecV1,
    materialize_native_trainer_inputs_v1,
    seal_native_training_launch_v1,
)
from .native_intelligence_training_lineage_v1 import NativeTrainingPlanV1


class Qwen397BLaunchError(ValueError):
    pass


def _require_source_validation(
    plan: NativeTrainingPlanV1,
    validation_receipt: LocalValidationReceiptV1,
) -> None:
    try:
        plan.assert_sealed()
        validation_receipt.require_for_release(plan.source_commit)
    except (ValueError, LocalValidationError) as error:
        raise Qwen397BLaunchError(str(error)) from error


def _require_plan(
    plan: NativeTrainingPlanV1,
    manifest: NativeTrainingExportManifestV1,
    preflight: Qwen397BPreflightEvidenceV1,
    token_profile: Qwen397BTokenProfileV1,
    profile: Qwen397BKoscheiTrainingProfileV1,
) -> None:
    try:
        require_canonical_qwen397b_training_plan_v1(
            plan,
            manifest,
            preflight,
            token_profile,
            profile,
        )
    except ValueError as error:
        raise Qwen397BLaunchError(str(error)) from error


def seal_qwen397b_training_launch_v1(
    plan: NativeTrainingPlanV1,
    manifest: NativeTrainingExportManifestV1,
    preflight: Qwen397BPreflightEvidenceV1,
    token_profile: Qwen397BTokenProfileV1,
    validation_receipt: LocalValidationReceiptV1,
    export_directory: str | Path,
    *,
    trainer_environment_digest: str,
    launcher_digest: str,
    profile: Qwen397BKoscheiTrainingProfileV1 | None = None,
) -> NativeTrainingLaunchSpecV1:
    """Seal a Qwen launch only after full source and model evidence revalidation."""

    profile = profile or canonical_qwen397b_koschei_profile_v1()
    _require_source_validation(plan, validation_receipt)
    _require_plan(plan, manifest, preflight, token_profile, profile)
    try:
        return seal_native_training_launch_v1(
            plan,
            manifest,
            export_directory,
            trainer_environment_digest=trainer_environment_digest,
            launcher_digest=launcher_digest,
        )
    except ValueError as error:
        raise Qwen397BLaunchError(str(error)) from error


def materialize_qwen397b_trainer_inputs_v1(
    launch: NativeTrainingLaunchSpecV1,
    plan: NativeTrainingPlanV1,
    manifest: NativeTrainingExportManifestV1,
    preflight: Qwen397BPreflightEvidenceV1,
    token_profile: Qwen397BTokenProfileV1,
    validation_receipt: LocalValidationReceiptV1,
    export_directory: str | Path,
    *,
    profile: Qwen397BKoscheiTrainingProfileV1 | None = None,
) -> NativeTrainerDataInputsV1:
    """Expose train+validation only after another full source/Qwen recheck."""

    profile = profile or canonical_qwen397b_koschei_profile_v1()
    _require_source_validation(plan, validation_receipt)
    _require_plan(plan, manifest, preflight, token_profile, profile)
    try:
        return materialize_native_trainer_inputs_v1(
            launch,
            plan,
            manifest,
            export_directory,
        )
    except ValueError as error:
        raise Qwen397BLaunchError(str(error)) from error
