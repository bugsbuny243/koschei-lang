"""Sealed training-plan and training-receipt lineage for native intelligence v1.

Before compute starts, Koschei seals the exact base revision/weights, source
commit, constitutional holdout, balanced verified oracle corpus, exact exported
JSONL byte manifest, training configuration and method. Caller-supplied
corpus/split hashes are not accepted by the public plan API.

After training, adapter/checkpoint/log evidence is sealed into a receipt bound to
that exact plan. The receipt digest is the ``training_run_digest`` consumed by
``NativeIntelligenceIdentityV1``. Neither plan nor receipt carries execution
authority or deployment approval.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import string

from .khar_constitution_v1 import CANONICAL_KHAR_DIGEST_V1
from .native_intelligence_holdout_v1 import NativeIntelligenceHoldoutV1
from .native_intelligence_training_balance_v1 import require_native_training_balance_v1
from .native_intelligence_training_corpus_v1 import NativeTrainingCorpusReleaseV1
from .native_intelligence_training_export_v1 import NativeTrainingExportManifestV1
from .native_intelligence_v1 import (
    CANONICAL_BASE_MODEL_V1,
    NativeIntelligenceIdentityV1,
    build_native_intelligence_identity,
)

_CTX = b"koschei.native-intelligence-training-lineage/v1\x00"
_HEX = frozenset(string.hexdigits.lower())


class NativeIntelligenceTrainingLineageError(ValueError):
    pass


def _canonical_json(value: object) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _hash(kind: bytes, payload: object) -> str:
    return hashlib.sha256(_CTX + kind + b"\x00" + _canonical_json(payload)).hexdigest()


def _digest(value: str, label: str, *, length: int = 64) -> str:
    if not isinstance(value, str) or len(value) != length:
        raise NativeIntelligenceTrainingLineageError(f"{label} must be {length} hexadecimal characters")
    lowered = value.lower()
    if any(char not in _HEX for char in lowered) or lowered == "0" * length:
        raise NativeIntelligenceTrainingLineageError(f"{label} must be a non-zero hexadecimal value")
    return lowered


def _text(value: str, label: str, *, max_length: int = 96) -> str:
    if not isinstance(value, str) or not value or len(value) > max_length or "\x00" in value:
        raise NativeIntelligenceTrainingLineageError(f"{label} must be non-empty bounded text")
    return value


@dataclass(frozen=True, slots=True)
class NativeTrainingPlanV1:
    khar_digest: str
    base_model_id: str
    base_model_revision: str
    base_weights_digest: str
    source_commit: str
    curriculum_digest: str
    constitutional_holdout_digest: str
    training_corpus_digest: str
    training_export_digest: str
    train_split_digest: str
    validation_split_digest: str
    test_split_digest: str
    training_config_digest: str
    training_method: str
    authority: bool
    digest: str
    version: int = 1

    def assert_sealed(self) -> None:
        if self.version != 1:
            raise NativeIntelligenceTrainingLineageError("unsupported native training plan version")
        if self.khar_digest != CANONICAL_KHAR_DIGEST_V1:
            raise NativeIntelligenceTrainingLineageError("native training plan is not bound to canonical Khar v1")
        if self.base_model_id != CANONICAL_BASE_MODEL_V1:
            raise NativeIntelligenceTrainingLineageError("native training plan base model is not canonical v1")
        if self.authority is not False:
            raise NativeIntelligenceTrainingLineageError("native training plan cannot carry authority")

        revision = _digest(self.base_model_revision, "base_model_revision", length=40)
        weights = _digest(self.base_weights_digest, "base_weights_digest")
        source = _digest(self.source_commit, "source_commit", length=40)
        curriculum = _digest(self.curriculum_digest, "curriculum_digest")
        holdout = _digest(self.constitutional_holdout_digest, "constitutional_holdout_digest")
        corpus = _digest(self.training_corpus_digest, "training_corpus_digest")
        export = _digest(self.training_export_digest, "training_export_digest")
        train = _digest(self.train_split_digest, "train_split_digest")
        validation = _digest(self.validation_split_digest, "validation_split_digest")
        test = _digest(self.test_split_digest, "test_split_digest")
        config = _digest(self.training_config_digest, "training_config_digest")
        method = _text(self.training_method, "training_method", max_length=64)

        if len({train, validation, test}) != 3:
            raise NativeIntelligenceTrainingLineageError("train/validation/test split digests must be distinct")
        if holdout in {corpus, export, train, validation, test}:
            raise NativeIntelligenceTrainingLineageError("constitutional holdout cannot be reused as training material")

        expected = _hash(
            b"plan",
            {
                "khar_digest": self.khar_digest,
                "base_model_id": self.base_model_id,
                "base_model_revision": revision,
                "base_weights_digest": weights,
                "source_commit": source,
                "curriculum_digest": curriculum,
                "constitutional_holdout_digest": holdout,
                "training_corpus_digest": corpus,
                "training_export_digest": export,
                "train_split_digest": train,
                "validation_split_digest": validation,
                "test_split_digest": test,
                "training_config_digest": config,
                "training_method": method,
                "authority": False,
            },
        )
        if self.digest != expected:
            raise NativeIntelligenceTrainingLineageError("native training plan seal mismatch")


@dataclass(frozen=True, slots=True)
class NativeTrainingReceiptV1:
    plan_digest: str
    adapter_digest: str
    final_checkpoint_digest: str
    trainer_log_digest: str
    completed_steps: int
    completion_evidence_digest: str
    authority: bool
    deployment_approved: bool
    digest: str
    version: int = 1

    def assert_for(self, plan: NativeTrainingPlanV1) -> None:
        if self.version != 1:
            raise NativeIntelligenceTrainingLineageError("unsupported native training receipt version")
        plan.assert_sealed()
        if self.plan_digest != plan.digest:
            raise NativeIntelligenceTrainingLineageError("training receipt belongs to a different plan")
        if self.authority is not False:
            raise NativeIntelligenceTrainingLineageError("training receipt cannot carry authority")
        if self.deployment_approved is not False:
            raise NativeIntelligenceTrainingLineageError("training completion is not deployment approval")
        adapter = _digest(self.adapter_digest, "adapter_digest")
        checkpoint = _digest(self.final_checkpoint_digest, "final_checkpoint_digest")
        log = _digest(self.trainer_log_digest, "trainer_log_digest")
        evidence = _digest(self.completion_evidence_digest, "completion_evidence_digest")
        if isinstance(self.completed_steps, bool) or not isinstance(self.completed_steps, int) or self.completed_steps < 1:
            raise NativeIntelligenceTrainingLineageError("completed_steps must be a positive integer")
        expected = _hash(
            b"receipt",
            {
                "plan_digest": self.plan_digest,
                "adapter_digest": adapter,
                "final_checkpoint_digest": checkpoint,
                "trainer_log_digest": log,
                "completed_steps": self.completed_steps,
                "completion_evidence_digest": evidence,
                "authority": False,
                "deployment_approved": False,
            },
        )
        if self.digest != expected:
            raise NativeIntelligenceTrainingLineageError("native training receipt seal mismatch")


def seal_native_training_plan_v1(
    holdout: NativeIntelligenceHoldoutV1,
    corpus: NativeTrainingCorpusReleaseV1,
    export_manifest: NativeTrainingExportManifestV1,
    *,
    base_model_revision: str,
    base_weights_digest: str,
    training_config_digest: str,
    training_method: str,
) -> NativeTrainingPlanV1:
    """Seal exact logical and byte-materialized balanced training identity before compute."""

    holdout.assert_sealed()
    try:
        corpus.assert_sealed(holdout)
        require_native_training_balance_v1(corpus)
        export_manifest.assert_for(holdout, corpus)
    except ValueError as error:
        raise NativeIntelligenceTrainingLineageError(str(error)) from error

    result = NativeTrainingPlanV1(
        khar_digest=CANONICAL_KHAR_DIGEST_V1,
        base_model_id=CANONICAL_BASE_MODEL_V1,
        base_model_revision=_digest(base_model_revision, "base_model_revision", length=40),
        base_weights_digest=_digest(base_weights_digest, "base_weights_digest"),
        source_commit=holdout.source_commit,
        curriculum_digest=holdout.curriculum_digest,
        constitutional_holdout_digest=holdout.digest,
        training_corpus_digest=corpus.digest,
        training_export_digest=export_manifest.digest,
        train_split_digest=corpus.split_digest("train"),
        validation_split_digest=corpus.split_digest("validation"),
        test_split_digest=corpus.split_digest("test"),
        training_config_digest=_digest(training_config_digest, "training_config_digest"),
        training_method=_text(training_method, "training_method", max_length=64),
        authority=False,
        digest="",
    )
    object.__setattr__(
        result,
        "digest",
        _hash(
            b"plan",
            {
                "khar_digest": result.khar_digest,
                "base_model_id": result.base_model_id,
                "base_model_revision": result.base_model_revision,
                "base_weights_digest": result.base_weights_digest,
                "source_commit": result.source_commit,
                "curriculum_digest": result.curriculum_digest,
                "constitutional_holdout_digest": result.constitutional_holdout_digest,
                "training_corpus_digest": result.training_corpus_digest,
                "training_export_digest": result.training_export_digest,
                "train_split_digest": result.train_split_digest,
                "validation_split_digest": result.validation_split_digest,
                "test_split_digest": result.test_split_digest,
                "training_config_digest": result.training_config_digest,
                "training_method": result.training_method,
                "authority": False,
            },
        ),
    )
    result.assert_sealed()
    return result


def seal_native_training_receipt_v1(
    plan: NativeTrainingPlanV1,
    *,
    adapter_digest: str,
    final_checkpoint_digest: str,
    trainer_log_digest: str,
    completed_steps: int,
    completion_evidence_digest: str,
) -> NativeTrainingReceiptV1:
    """Seal completed training evidence without granting deployment authority."""

    plan.assert_sealed()
    result = NativeTrainingReceiptV1(
        plan_digest=plan.digest,
        adapter_digest=_digest(adapter_digest, "adapter_digest"),
        final_checkpoint_digest=_digest(final_checkpoint_digest, "final_checkpoint_digest"),
        trainer_log_digest=_digest(trainer_log_digest, "trainer_log_digest"),
        completed_steps=completed_steps,
        completion_evidence_digest=_digest(completion_evidence_digest, "completion_evidence_digest"),
        authority=False,
        deployment_approved=False,
        digest="",
    )
    object.__setattr__(
        result,
        "digest",
        _hash(
            b"receipt",
            {
                "plan_digest": result.plan_digest,
                "adapter_digest": result.adapter_digest,
                "final_checkpoint_digest": result.final_checkpoint_digest,
                "trainer_log_digest": result.trainer_log_digest,
                "completed_steps": result.completed_steps,
                "completion_evidence_digest": result.completion_evidence_digest,
                "authority": False,
                "deployment_approved": False,
            },
        ),
    )
    result.assert_for(plan)
    return result


def build_native_intelligence_from_training_receipt_v1(
    plan: NativeTrainingPlanV1,
    receipt: NativeTrainingReceiptV1,
) -> NativeIntelligenceIdentityV1:
    """Bridge one sealed training receipt into the existing model identity."""

    plan.assert_sealed()
    receipt.assert_for(plan)
    return build_native_intelligence_identity(
        base_model_revision=plan.base_model_revision,
        base_weights_digest=plan.base_weights_digest,
        curriculum_digest=plan.curriculum_digest,
        adapter_digest=receipt.adapter_digest,
        training_run_digest=receipt.digest,
        source_commit=plan.source_commit,
        training_method=plan.training_method,
    )
