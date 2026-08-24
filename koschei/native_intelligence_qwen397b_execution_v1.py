"""Qwen397B-specific launch-to-model-identity execution lineage v1.

The generic execution objects bind plan/launch/artifacts, but Qwen397B model
identity additionally requires that the plan still re-derives from the canonical
base preflight, exact export and zero-truncation tokenizer evidence. This module
is the only v1 bridge from completed Qwen training execution into
NativeIntelligenceIdentityV1.
"""
from __future__ import annotations

from .native_intelligence_qwen397b_preflight_v1 import Qwen397BPreflightEvidenceV1
from .native_intelligence_qwen397b_profile_v1 import (
    Qwen397BKoscheiTrainingProfileV1,
    canonical_qwen397b_koschei_profile_v1,
)
from .native_intelligence_qwen397b_token_profile_v1 import Qwen397BTokenProfileV1
from .native_intelligence_qwen397b_training_plan_v1 import (
    require_canonical_qwen397b_training_plan_v1,
)
from .native_intelligence_training_execution_v1 import (
    NativeTrainingExecutionReceiptV1,
    NativeTrainingRunStartV1,
    seal_native_training_execution_receipt_v1,
    seal_native_training_run_start_v1,
)
from .native_intelligence_training_export_v1 import NativeTrainingExportManifestV1
from .native_intelligence_training_launch_v1 import NativeTrainingLaunchSpecV1
from .native_intelligence_training_lineage_v1 import (
    NativeTrainingPlanV1,
    NativeTrainingReceiptV1,
)
from .native_intelligence_v1 import (
    NativeIntelligenceIdentityV1,
    build_native_intelligence_identity,
)


class Qwen397BExecutionError(ValueError):
    pass


def _require_qwen_plan(
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
        raise Qwen397BExecutionError(str(error)) from error


def seal_qwen397b_training_run_start_v1(
    plan: NativeTrainingPlanV1,
    launch: NativeTrainingLaunchSpecV1,
    manifest: NativeTrainingExportManifestV1,
    preflight: Qwen397BPreflightEvidenceV1,
    token_profile: Qwen397BTokenProfileV1,
    *,
    provider: str,
    job_reference_digest: str,
    start_evidence_digest: str,
    profile: Qwen397BKoscheiTrainingProfileV1 | None = None,
) -> NativeTrainingRunStartV1:
    profile = profile or canonical_qwen397b_koschei_profile_v1()
    _require_qwen_plan(plan, manifest, preflight, token_profile, profile)
    try:
        return seal_native_training_run_start_v1(
            plan,
            launch,
            manifest,
            provider=provider,
            job_reference_digest=job_reference_digest,
            start_evidence_digest=start_evidence_digest,
        )
    except ValueError as error:
        raise Qwen397BExecutionError(str(error)) from error


def seal_qwen397b_training_execution_receipt_v1(
    plan: NativeTrainingPlanV1,
    launch: NativeTrainingLaunchSpecV1,
    manifest: NativeTrainingExportManifestV1,
    preflight: Qwen397BPreflightEvidenceV1,
    token_profile: Qwen397BTokenProfileV1,
    run_start: NativeTrainingRunStartV1,
    artifact_receipt: NativeTrainingReceiptV1,
    *,
    profile: Qwen397BKoscheiTrainingProfileV1 | None = None,
) -> NativeTrainingExecutionReceiptV1:
    profile = profile or canonical_qwen397b_koschei_profile_v1()
    _require_qwen_plan(plan, manifest, preflight, token_profile, profile)
    try:
        return seal_native_training_execution_receipt_v1(
            plan,
            launch,
            manifest,
            run_start,
            artifact_receipt,
        )
    except ValueError as error:
        raise Qwen397BExecutionError(str(error)) from error


def build_qwen397b_native_intelligence_from_execution_receipt_v1(
    plan: NativeTrainingPlanV1,
    launch: NativeTrainingLaunchSpecV1,
    manifest: NativeTrainingExportManifestV1,
    preflight: Qwen397BPreflightEvidenceV1,
    token_profile: Qwen397BTokenProfileV1,
    run_start: NativeTrainingRunStartV1,
    artifact_receipt: NativeTrainingReceiptV1,
    execution_receipt: NativeTrainingExecutionReceiptV1,
    *,
    profile: Qwen397BKoscheiTrainingProfileV1 | None = None,
) -> NativeIntelligenceIdentityV1:
    """Create Qwen native intelligence only from complete Qwen execution evidence."""

    profile = profile or canonical_qwen397b_koschei_profile_v1()
    _require_qwen_plan(plan, manifest, preflight, token_profile, profile)
    try:
        execution_receipt.assert_for(
            plan,
            launch,
            manifest,
            run_start,
            artifact_receipt,
        )
    except ValueError as error:
        raise Qwen397BExecutionError(str(error)) from error

    return build_native_intelligence_identity(
        base_model_revision=plan.base_model_revision,
        base_weights_digest=plan.base_weights_digest,
        curriculum_digest=plan.curriculum_digest,
        adapter_digest=execution_receipt.adapter_digest,
        training_run_digest=execution_receipt.digest,
        source_commit=plan.source_commit,
        training_method=plan.training_method,
    )
