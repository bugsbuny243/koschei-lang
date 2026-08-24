"""Fail-closed launch boundary for Koschei native-intelligence training v1.

A sealed training plan is still not permission to hand arbitrary files to a
trainer. Immediately before compute begins this module re-verifies the exact
materialized export bytes and derives a launch spec with strict data roles:

- train is the only gradient source;
- validation may be read for evaluation but never as a gradient source;
- test is sealed evidence and is not exposed through the trainer-input object.

This layer does not start remote compute and grants no deployment or execution
authority. It defines the only canonical data handoff for a later launcher.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
import string

from .native_intelligence_training_export_v1 import (
    NativeTrainingExportManifestV1,
    verify_native_training_export_v1,
)
from .native_intelligence_training_lineage_v1 import NativeTrainingPlanV1

_CTX = b"koschei.native-intelligence-training-launch/v1\x00"
_HEX = frozenset(string.hexdigits.lower())


class NativeTrainingLaunchError(ValueError):
    pass


def _canonical_json(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _hash(kind: bytes, payload: object) -> str:
    return hashlib.sha256(_CTX + kind + b"\x00" + _canonical_json(payload)).hexdigest()


def _digest(value: str, label: str) -> str:
    if not isinstance(value, str) or len(value) != 64:
        raise NativeTrainingLaunchError(f"{label} must be a 64-character digest")
    lowered = value.lower()
    if any(char not in _HEX for char in lowered) or lowered == "0" * 64:
        raise NativeTrainingLaunchError(f"{label} must be a non-zero hexadecimal digest")
    return lowered


def _manifest_rows(manifest: NativeTrainingExportManifestV1):
    manifest.assert_sealed()
    rows = {row.split: row for row in manifest.files}
    if set(rows) != {"train", "validation", "test"}:
        raise NativeTrainingLaunchError("training export split roles are incomplete")
    return rows


@dataclass(frozen=True, slots=True)
class NativeTrainingLaunchSpecV1:
    plan_digest: str
    training_export_digest: str
    trainer_environment_digest: str
    launcher_digest: str
    train_filename: str
    train_sha256: str
    validation_filename: str
    validation_sha256: str
    test_filename: str
    test_sha256: str
    gradient_source_split: str
    validation_only_split: str
    sealed_test_split: str
    test_exposed_to_trainer: bool
    authority: bool
    digest: str
    version: int = 1

    def assert_for(
        self,
        plan: NativeTrainingPlanV1,
        manifest: NativeTrainingExportManifestV1,
    ) -> None:
        if self.version != 1:
            raise NativeTrainingLaunchError("unsupported native training launch version")
        plan.assert_sealed()
        rows = _manifest_rows(manifest)
        if self.plan_digest != plan.digest:
            raise NativeTrainingLaunchError("training launch belongs to a different plan")
        if self.training_export_digest != manifest.digest:
            raise NativeTrainingLaunchError("training launch belongs to a different export")
        if plan.training_export_digest != manifest.digest:
            raise NativeTrainingLaunchError("training plan/export identity mismatch")
        if self.gradient_source_split != "train":
            raise NativeTrainingLaunchError("only train may be a gradient source")
        if self.validation_only_split != "validation":
            raise NativeTrainingLaunchError("validation role is non-canonical")
        if self.sealed_test_split != "test":
            raise NativeTrainingLaunchError("test role is non-canonical")
        if self.test_exposed_to_trainer is not False:
            raise NativeTrainingLaunchError("test split cannot be exposed to the trainer")
        if self.authority is not False:
            raise NativeTrainingLaunchError("training launch cannot carry authority")
        environment = _digest(self.trainer_environment_digest, "trainer_environment_digest")
        launcher = _digest(self.launcher_digest, "launcher_digest")
        expected_files = {
            "train_filename": rows["train"].filename,
            "train_sha256": rows["train"].sha256,
            "validation_filename": rows["validation"].filename,
            "validation_sha256": rows["validation"].sha256,
            "test_filename": rows["test"].filename,
            "test_sha256": rows["test"].sha256,
        }
        for field, expected in expected_files.items():
            if getattr(self, field) != expected:
                raise NativeTrainingLaunchError(f"training launch {field} mismatch")
        expected = _hash(
            b"launch",
            {
                "plan_digest": self.plan_digest,
                "training_export_digest": self.training_export_digest,
                "trainer_environment_digest": environment,
                "launcher_digest": launcher,
                **expected_files,
                "gradient_source_split": "train",
                "validation_only_split": "validation",
                "sealed_test_split": "test",
                "test_exposed_to_trainer": False,
                "authority": False,
            },
        )
        if self.digest != expected:
            raise NativeTrainingLaunchError("native training launch seal mismatch")


@dataclass(frozen=True, slots=True)
class NativeTrainerDataInputsV1:
    launch_digest: str
    train_path: str
    validation_path: str
    test_path: None
    gradient_source_splits: tuple[str, ...]
    evaluation_only_splits: tuple[str, ...]
    authority: bool

    def assert_for(self, launch: NativeTrainingLaunchSpecV1) -> None:
        if self.launch_digest != launch.digest:
            raise NativeTrainingLaunchError("trainer inputs belong to a different launch")
        if self.test_path is not None:
            raise NativeTrainingLaunchError("trainer inputs must not expose test path")
        if self.gradient_source_splits != ("train",):
            raise NativeTrainingLaunchError("trainer gradient source must be train only")
        if self.evaluation_only_splits != ("validation",):
            raise NativeTrainingLaunchError("trainer evaluation-only split must be validation")
        if self.authority is not False:
            raise NativeTrainingLaunchError("trainer data inputs cannot carry authority")
        if Path(self.train_path).name != launch.train_filename:
            raise NativeTrainingLaunchError("trainer train path mismatch")
        if Path(self.validation_path).name != launch.validation_filename:
            raise NativeTrainingLaunchError("trainer validation path mismatch")


def seal_native_training_launch_v1(
    plan: NativeTrainingPlanV1,
    manifest: NativeTrainingExportManifestV1,
    export_directory: str | Path,
    *,
    trainer_environment_digest: str,
    launcher_digest: str,
) -> NativeTrainingLaunchSpecV1:
    """Re-verify export bytes and seal canonical data roles before compute."""

    plan.assert_sealed()
    manifest.assert_sealed()
    if plan.training_export_digest != manifest.digest:
        raise NativeTrainingLaunchError("training plan/export identity mismatch")
    try:
        verify_native_training_export_v1(manifest, export_directory)
    except ValueError as error:
        raise NativeTrainingLaunchError(str(error)) from error
    rows = _manifest_rows(manifest)
    environment = _digest(trainer_environment_digest, "trainer_environment_digest")
    launcher = _digest(launcher_digest, "launcher_digest")
    values = {
        "plan_digest": plan.digest,
        "training_export_digest": manifest.digest,
        "trainer_environment_digest": environment,
        "launcher_digest": launcher,
        "train_filename": rows["train"].filename,
        "train_sha256": rows["train"].sha256,
        "validation_filename": rows["validation"].filename,
        "validation_sha256": rows["validation"].sha256,
        "test_filename": rows["test"].filename,
        "test_sha256": rows["test"].sha256,
        "gradient_source_split": "train",
        "validation_only_split": "validation",
        "sealed_test_split": "test",
        "test_exposed_to_trainer": False,
        "authority": False,
    }
    result = NativeTrainingLaunchSpecV1(**values, digest="")
    object.__setattr__(result, "digest", _hash(b"launch", values))
    result.assert_for(plan, manifest)
    return result


def materialize_native_trainer_inputs_v1(
    launch: NativeTrainingLaunchSpecV1,
    plan: NativeTrainingPlanV1,
    manifest: NativeTrainingExportManifestV1,
    export_directory: str | Path,
) -> NativeTrainerDataInputsV1:
    """Expose train+validation only after another exact-byte verification."""

    launch.assert_for(plan, manifest)
    try:
        verify_native_training_export_v1(manifest, export_directory)
    except ValueError as error:
        raise NativeTrainingLaunchError(str(error)) from error
    root = Path(export_directory).resolve()
    result = NativeTrainerDataInputsV1(
        launch_digest=launch.digest,
        train_path=str(root / launch.train_filename),
        validation_path=str(root / launch.validation_filename),
        test_path=None,
        gradient_source_splits=("train",),
        evaluation_only_splits=("validation",),
        authority=False,
    )
    result.assert_for(launch)
    return result
