"""Trainer-only remote dataset mirror receipt for Qwen397B v1.

A remote GPU job must not receive the constitutional test split. The canonical
trainer mirror therefore contains exactly train + validation from one sealed
export. The local export manifest still commits the test split SHA, but no test
locator is present in this receipt.

This is deterministic lineage evidence, not independent provider attestation.
The uploader must round-trip the exact remote bytes before sealing the receipt.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import string

from .native_intelligence_training_export_v1 import NativeTrainingExportManifestV1

_CTX = b"koschei.qwen397b-trainer-mirror/v1\x00"
_HEX = frozenset(string.hexdigits.lower())
CANONICAL_MIRROR_PROVIDER_V1 = "huggingface-hub"


class Qwen397BTrainerMirrorError(ValueError):
    pass


def _canonical_json(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _hash(payload: object) -> str:
    return hashlib.sha256(_CTX + _canonical_json(payload)).hexdigest()


def _digest(value: str, label: str, *, length: int = 64) -> str:
    if not isinstance(value, str) or len(value) != length:
        raise Qwen397BTrainerMirrorError(f"{label} must be {length} hexadecimal characters")
    lowered = value.lower()
    if any(char not in _HEX for char in lowered) or lowered == "0" * length:
        raise Qwen397BTrainerMirrorError(f"{label} must be a non-zero hexadecimal value")
    return lowered


def _repo_id(value: str) -> str:
    if (
        not isinstance(value, str)
        or not value
        or len(value) > 160
        or value.count("/") != 1
        or any(char.isspace() for char in value)
        or "\x00" in value
    ):
        raise Qwen397BTrainerMirrorError("invalid trainer mirror dataset repo id")
    return value


@dataclass(frozen=True, slots=True)
class Qwen397BTrainerMirrorReceiptV1:
    provider: str
    dataset_repo_id: str
    resolved_revision: str
    training_export_digest: str
    train_filename: str
    train_sha256: str
    train_byte_count: int
    validation_filename: str
    validation_sha256: str
    validation_byte_count: int
    sealed_test_sha256: str
    test_exposed_to_trainer: bool
    roundtrip_evidence_digest: str
    authority: bool
    digest: str
    version: int = 1

    def _payload(self) -> dict[str, object]:
        return {
            "provider": self.provider,
            "dataset_repo_id": self.dataset_repo_id,
            "resolved_revision": self.resolved_revision,
            "training_export_digest": self.training_export_digest,
            "train_filename": self.train_filename,
            "train_sha256": self.train_sha256,
            "train_byte_count": self.train_byte_count,
            "validation_filename": self.validation_filename,
            "validation_sha256": self.validation_sha256,
            "validation_byte_count": self.validation_byte_count,
            "sealed_test_sha256": self.sealed_test_sha256,
            "test_exposed_to_trainer": False,
            "roundtrip_evidence_digest": self.roundtrip_evidence_digest,
            "authority": False,
        }

    def assert_for(self, manifest: NativeTrainingExportManifestV1) -> None:
        if self.version != 1:
            raise Qwen397BTrainerMirrorError("unsupported trainer mirror receipt version")
        manifest.assert_sealed()
        if self.provider != CANONICAL_MIRROR_PROVIDER_V1:
            raise Qwen397BTrainerMirrorError("trainer mirror provider drift")
        _repo_id(self.dataset_repo_id)
        _digest(self.resolved_revision, "resolved_revision", length=40)
        if self.training_export_digest != manifest.digest:
            raise Qwen397BTrainerMirrorError("trainer mirror belongs to a different training export")
        _digest(self.training_export_digest, "training_export_digest")
        _digest(self.roundtrip_evidence_digest, "roundtrip_evidence_digest")
        rows = {row.split: row for row in manifest.files}
        train = rows["train"]
        validation = rows["validation"]
        test = rows["test"]
        expected = {
            "train_filename": train.filename,
            "train_sha256": train.sha256,
            "train_byte_count": train.byte_count,
            "validation_filename": validation.filename,
            "validation_sha256": validation.sha256,
            "validation_byte_count": validation.byte_count,
            "sealed_test_sha256": test.sha256,
        }
        for field, value in expected.items():
            if getattr(self, field) != value:
                raise Qwen397BTrainerMirrorError(f"trainer mirror {field} mismatch")
        if self.test_exposed_to_trainer is not False:
            raise Qwen397BTrainerMirrorError("trainer mirror must not expose the test split")
        if self.authority is not False:
            raise Qwen397BTrainerMirrorError("trainer mirror receipt cannot carry authority")
        if self.digest != _hash(self._payload()):
            raise Qwen397BTrainerMirrorError("trainer mirror receipt seal mismatch")


def seal_qwen397b_trainer_mirror_v1(
    manifest: NativeTrainingExportManifestV1,
    *,
    dataset_repo_id: str,
    resolved_revision: str,
    roundtrip_evidence_digest: str,
) -> Qwen397BTrainerMirrorReceiptV1:
    """Seal one train+validation mirror after an uploader verified remote bytes."""

    manifest.assert_sealed()
    rows = {row.split: row for row in manifest.files}
    result = Qwen397BTrainerMirrorReceiptV1(
        provider=CANONICAL_MIRROR_PROVIDER_V1,
        dataset_repo_id=_repo_id(dataset_repo_id),
        resolved_revision=_digest(resolved_revision, "resolved_revision", length=40),
        training_export_digest=manifest.digest,
        train_filename=rows["train"].filename,
        train_sha256=rows["train"].sha256,
        train_byte_count=rows["train"].byte_count,
        validation_filename=rows["validation"].filename,
        validation_sha256=rows["validation"].sha256,
        validation_byte_count=rows["validation"].byte_count,
        sealed_test_sha256=rows["test"].sha256,
        test_exposed_to_trainer=False,
        roundtrip_evidence_digest=_digest(
            roundtrip_evidence_digest,
            "roundtrip_evidence_digest",
        ),
        authority=False,
        digest="",
    )
    object.__setattr__(result, "digest", _hash(result._payload()))
    result.assert_for(manifest)
    return result
