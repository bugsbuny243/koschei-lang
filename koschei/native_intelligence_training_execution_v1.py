"""Exact launch-to-execution lineage for Koschei native intelligence v1.

A training plan and an artifact receipt are insufficient to prove that the
artifact was produced by the sealed launch boundary. This module closes that gap
with two authority-free evidence objects:

1. a run-start receipt bound to the exact launch, environment, launcher and
   external job/evidence identity;
2. an execution receipt that binds the run-start receipt to the final adapter
   artifact receipt.

Only the execution receipt may be bridged into NativeIntelligenceIdentityV1.
External job evidence is recorded here but not magically attested: hardware or
provider attestation remains a stronger future layer.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import string

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

_CTX = b"koschei.native-intelligence-training-execution/v1\x00"
_HEX = frozenset(string.hexdigits.lower())


class NativeTrainingExecutionError(ValueError):
    pass


def _canonical_json(value: object) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def _hash(kind: bytes, payload: object) -> str:
    return hashlib.sha256(_CTX + kind + b"\x00" + _canonical_json(payload)).hexdigest()


def _digest(value: str, label: str) -> str:
    if not isinstance(value, str) or len(value) != 64:
        raise NativeTrainingExecutionError(f"{label} must be a 64-character digest")
    lowered = value.lower()
    if any(char not in _HEX for char in lowered) or lowered == "0" * 64:
        raise NativeTrainingExecutionError(f"{label} must be a non-zero hexadecimal digest")
    return lowered


def _text(value: str, label: str, *, max_length: int = 96) -> str:
    if (
        not isinstance(value, str)
        or not value
        or len(value) > max_length
        or "\x00" in value
    ):
        raise NativeTrainingExecutionError(f"{label} must be non-empty bounded text")
    return value


@dataclass(frozen=True, slots=True)
class NativeTrainingRunStartV1:
    plan_digest: str
    launch_digest: str
    training_export_digest: str
    trainer_environment_digest: str
    launcher_digest: str
    provider: str
    job_reference_digest: str
    start_evidence_digest: str
    authority: bool
    digest: str
    version: int = 1

    def assert_for(
        self,
        plan: NativeTrainingPlanV1,
        launch: NativeTrainingLaunchSpecV1,
        manifest: NativeTrainingExportManifestV1,
    ) -> None:
        if self.version != 1:
            raise NativeTrainingExecutionError("unsupported native training run-start version")
        plan.assert_sealed()
        launch.assert_for(plan, manifest)
        if self.plan_digest != plan.digest:
            raise NativeTrainingExecutionError("training run start belongs to a different plan")
        if self.launch_digest != launch.digest:
            raise NativeTrainingExecutionError("training run start belongs to a different launch")
        if self.training_export_digest != manifest.digest:
            raise NativeTrainingExecutionError("training run start belongs to a different export")
        if self.trainer_environment_digest != launch.trainer_environment_digest:
            raise NativeTrainingExecutionError("training run start environment mismatch")
        if self.launcher_digest != launch.launcher_digest:
            raise NativeTrainingExecutionError("training run start launcher mismatch")
        provider = _text(self.provider, "provider", max_length=64)
        job = _digest(self.job_reference_digest, "job_reference_digest")
        evidence = _digest(self.start_evidence_digest, "start_evidence_digest")
        if self.authority is not False:
            raise NativeTrainingExecutionError("training run start cannot carry authority")
        expected = _hash(
            b"run-start",
            {
                "plan_digest": self.plan_digest,
                "launch_digest": self.launch_digest,
                "training_export_digest": self.training_export_digest,
                "trainer_environment_digest": self.trainer_environment_digest,
                "launcher_digest": self.launcher_digest,
                "provider": provider,
                "job_reference_digest": job,
                "start_evidence_digest": evidence,
                "authority": False,
            },
        )
        if self.digest != expected:
            raise NativeTrainingExecutionError("native training run-start seal mismatch")


@dataclass(frozen=True, slots=True)
class NativeTrainingExecutionReceiptV1:
    plan_digest: str
    launch_digest: str
    run_start_digest: str
    artifact_receipt_digest: str
    adapter_digest: str
    final_checkpoint_digest: str
    completed_steps: int
    completion_evidence_digest: str
    authority: bool
    deployment_approved: bool
    digest: str
    version: int = 1

    def assert_for(
        self,
        plan: NativeTrainingPlanV1,
        launch: NativeTrainingLaunchSpecV1,
        manifest: NativeTrainingExportManifestV1,
        run_start: NativeTrainingRunStartV1,
        artifact_receipt: NativeTrainingReceiptV1,
    ) -> None:
        if self.version != 1:
            raise NativeTrainingExecutionError("unsupported native training execution receipt version")
        plan.assert_sealed()
        launch.assert_for(plan, manifest)
        run_start.assert_for(plan, launch, manifest)
        artifact_receipt.assert_for(plan)
        if self.plan_digest != plan.digest:
            raise NativeTrainingExecutionError("training execution belongs to a different plan")
        if self.launch_digest != launch.digest:
            raise NativeTrainingExecutionError("training execution belongs to a different launch")
        if self.run_start_digest != run_start.digest:
            raise NativeTrainingExecutionError("training execution belongs to a different run start")
        if self.artifact_receipt_digest != artifact_receipt.digest:
            raise NativeTrainingExecutionError("training execution belongs to a different artifact receipt")
        if self.adapter_digest != artifact_receipt.adapter_digest:
            raise NativeTrainingExecutionError("training execution adapter mismatch")
        if self.final_checkpoint_digest != artifact_receipt.final_checkpoint_digest:
            raise NativeTrainingExecutionError("training execution checkpoint mismatch")
        if self.completed_steps != artifact_receipt.completed_steps:
            raise NativeTrainingExecutionError("training execution completed-step mismatch")
        if self.completion_evidence_digest != artifact_receipt.completion_evidence_digest:
            raise NativeTrainingExecutionError("training execution completion evidence mismatch")
        if self.authority is not False:
            raise NativeTrainingExecutionError("training execution receipt cannot carry authority")
        if self.deployment_approved is not False:
            raise NativeTrainingExecutionError("training execution is not deployment approval")
        expected = _hash(
            b"execution-receipt",
            {
                "plan_digest": self.plan_digest,
                "launch_digest": self.launch_digest,
                "run_start_digest": self.run_start_digest,
                "artifact_receipt_digest": self.artifact_receipt_digest,
                "adapter_digest": self.adapter_digest,
                "final_checkpoint_digest": self.final_checkpoint_digest,
                "completed_steps": self.completed_steps,
                "completion_evidence_digest": self.completion_evidence_digest,
                "authority": False,
                "deployment_approved": False,
            },
        )
        if self.digest != expected:
            raise NativeTrainingExecutionError("native training execution receipt seal mismatch")


def seal_native_training_run_start_v1(
    plan: NativeTrainingPlanV1,
    launch: NativeTrainingLaunchSpecV1,
    manifest: NativeTrainingExportManifestV1,
    *,
    provider: str,
    job_reference_digest: str,
    start_evidence_digest: str,
) -> NativeTrainingRunStartV1:
    """Seal one external compute start against the exact launch boundary."""

    launch.assert_for(plan, manifest)
    result = NativeTrainingRunStartV1(
        plan_digest=plan.digest,
        launch_digest=launch.digest,
        training_export_digest=manifest.digest,
        trainer_environment_digest=launch.trainer_environment_digest,
        launcher_digest=launch.launcher_digest,
        provider=_text(provider, "provider", max_length=64),
        job_reference_digest=_digest(job_reference_digest, "job_reference_digest"),
        start_evidence_digest=_digest(start_evidence_digest, "start_evidence_digest"),
        authority=False,
        digest="",
    )
    object.__setattr__(
        result,
        "digest",
        _hash(
            b"run-start",
            {
                "plan_digest": result.plan_digest,
                "launch_digest": result.launch_digest,
                "training_export_digest": result.training_export_digest,
                "trainer_environment_digest": result.trainer_environment_digest,
                "launcher_digest": result.launcher_digest,
                "provider": result.provider,
                "job_reference_digest": result.job_reference_digest,
                "start_evidence_digest": result.start_evidence_digest,
                "authority": False,
            },
        ),
    )
    result.assert_for(plan, launch, manifest)
    return result


def seal_native_training_execution_receipt_v1(
    plan: NativeTrainingPlanV1,
    launch: NativeTrainingLaunchSpecV1,
    manifest: NativeTrainingExportManifestV1,
    run_start: NativeTrainingRunStartV1,
    artifact_receipt: NativeTrainingReceiptV1,
) -> NativeTrainingExecutionReceiptV1:
    """Bind final training artifacts to the exact launched run."""

    run_start.assert_for(plan, launch, manifest)
    artifact_receipt.assert_for(plan)
    result = NativeTrainingExecutionReceiptV1(
        plan_digest=plan.digest,
        launch_digest=launch.digest,
        run_start_digest=run_start.digest,
        artifact_receipt_digest=artifact_receipt.digest,
        adapter_digest=artifact_receipt.adapter_digest,
        final_checkpoint_digest=artifact_receipt.final_checkpoint_digest,
        completed_steps=artifact_receipt.completed_steps,
        completion_evidence_digest=artifact_receipt.completion_evidence_digest,
        authority=False,
        deployment_approved=False,
        digest="",
    )
    object.__setattr__(
        result,
        "digest",
        _hash(
            b"execution-receipt",
            {
                "plan_digest": result.plan_digest,
                "launch_digest": result.launch_digest,
                "run_start_digest": result.run_start_digest,
                "artifact_receipt_digest": result.artifact_receipt_digest,
                "adapter_digest": result.adapter_digest,
                "final_checkpoint_digest": result.final_checkpoint_digest,
                "completed_steps": result.completed_steps,
                "completion_evidence_digest": result.completion_evidence_digest,
                "authority": False,
                "deployment_approved": False,
            },
        ),
    )
    result.assert_for(plan, launch, manifest, run_start, artifact_receipt)
    return result


def build_native_intelligence_from_execution_receipt_v1(
    plan: NativeTrainingPlanV1,
    launch: NativeTrainingLaunchSpecV1,
    manifest: NativeTrainingExportManifestV1,
    run_start: NativeTrainingRunStartV1,
    artifact_receipt: NativeTrainingReceiptV1,
    execution_receipt: NativeTrainingExecutionReceiptV1,
) -> NativeIntelligenceIdentityV1:
    """Create the model identity only from fully bound execution evidence."""

    execution_receipt.assert_for(
        plan,
        launch,
        manifest,
        run_start,
        artifact_receipt,
    )
    return build_native_intelligence_identity(
        base_model_revision=plan.base_model_revision,
        base_weights_digest=plan.base_weights_digest,
        curriculum_digest=plan.curriculum_digest,
        adapter_digest=execution_receipt.adapter_digest,
        training_run_digest=execution_receipt.digest,
        source_commit=plan.source_commit,
        training_method=plan.training_method,
    )
