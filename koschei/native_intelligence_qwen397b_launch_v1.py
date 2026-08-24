"""Qwen397B-specific training launch boundary v1.

The generic training launch enforces data roles and exact bytes. This wrapper
adds the model-family law: the plan must still re-derive from the canonical Qwen
base preflight, zero-truncation token profile and complete run-config immediately
before trainer inputs are exposed.
"""
from __future__ import annotations

from pathlib import Path

from .native_intelligence_qwen397b_preflight_v1 import Qwen397BPreflightEvidenceV1
from .native_intelligence_qwen397b_profile_v1 import (
    Qwen397BKoscheiTrainingProfileV1,
    canonical_qwen397b_koschei_profile_v1,
)
from .native_intelligence_qwen397b_token_profile_v1 import Qwen397BTokenProfileV1
from .native_intelligence_qwen397b_training_plan_v1 import (
    Qwen397BTrainingPlanError,
    require_canonical_qwen397b_training_plan_v1,
)
from .native_intelligence_training_export_v1 import NativeTrainingExportManifestV1
from .native_intelligence_training_launch_v1 import (
    NativeTrainerDataInputsV1,
    NativeTrainingLaunchError,
    NativeTrainingLaunchSpecV1,
    materialize_native_trainer_inputs_v1,
    seal_native_training_launch_v1,
)
from .native_intelligence_training_lineage_v1 import NativeTrainingPlanV1


class Qwen397BLaunchError(ValueError):
    pass


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
    export_directory: str | Path,
    *,
    trainer_environment_digest: str,
    launcher_digest: str,
    profile: Qwen397BKoscheiTrainingProfileV1 | None = None,
) -> NativeTrainingLaunchSpecV1:
    """Seal a launch only after complete Qwen first-run evidence is rechecked."""

    profile = profile or canonical_qwen397b_koschei_profile_v1()
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
    export_directory: str | Path,
    *,
    profile: Qwen397BKoscheiTrainingProfileV1 | None = None,
) -> NativeTrainerDataInputsV1:
    """Expose train+validation only after another full Qwen-plan recheck."""

    profile = profile or canonical_qwen397b_koschei_profile_v1()
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
