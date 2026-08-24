"""Sealed constitutional holdout for Koschei native intelligence v1.

The oracle-backed N0..N6 curriculum is not ordinary supervised-training data.
Those cases define a constitutional evaluation boundary. Training on the exact
inputs would let a model memorize the gate that is supposed to test it.

This module therefore fingerprints a verified native curriculum as a holdout
release with ``training_inclusion_allowed = False`` and provides a fail-closed
check that rejects training examples reusing a holdout case identity or exact
holdout input.

The holdout is evidence, not authority. It contains no model weights, secrets or
customer Galaxy topology.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import string
from typing import Iterable

from .native_model_curriculum_v2 import (
    STAGES,
    NativeModelCurriculumV2,
    verify_native_model_curriculum_v2,
)

_CTX = b"koschei.native-intelligence-holdout/v1\x00"
_HEX = frozenset(string.hexdigits.lower())


class NativeIntelligenceHoldoutError(ValueError):
    pass


def _canonical_json(value: object) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def _hash(kind: bytes, value: object) -> str:
    return hashlib.sha256(_CTX + kind + b"\x00" + _canonical_json(value)).hexdigest()


def _digest(value: str, label: str, *, length: int = 64) -> str:
    if not isinstance(value, str) or len(value) != length:
        raise NativeIntelligenceHoldoutError(
            f"{label} must be {length} hexadecimal characters"
        )
    lowered = value.lower()
    if any(char not in _HEX for char in lowered) or lowered == "0" * length:
        raise NativeIntelligenceHoldoutError(
            f"{label} must be a non-zero hexadecimal value"
        )
    return lowered


def _text(value: str, label: str, *, max_length: int = 256) -> str:
    if (
        not isinstance(value, str)
        or not value
        or len(value) > max_length
        or "\x00" in value
    ):
        raise NativeIntelligenceHoldoutError(f"{label} must be non-empty bounded text")
    return value


@dataclass(frozen=True, slots=True)
class HoldoutCaseFingerprintV1:
    case_id: str
    stage: str
    outcome: str
    oracle_digest: str
    input_digest: str
    target_digest: str
    pair_digest: str
    digest: str
    version: int = 1

    def assert_sealed(self) -> None:
        if self.version != 1:
            raise NativeIntelligenceHoldoutError("unsupported holdout case version")
        case_id = _text(self.case_id, "holdout case_id")
        if self.stage not in STAGES:
            raise NativeIntelligenceHoldoutError("unsupported holdout stage")
        if self.outcome not in {"ACCEPTED", "REJECTED"}:
            raise NativeIntelligenceHoldoutError("unsupported holdout outcome")
        oracle = _digest(self.oracle_digest, "holdout oracle_digest")
        input_digest = _digest(self.input_digest, "holdout input_digest")
        target_digest = _digest(self.target_digest, "holdout target_digest")
        pair = _digest(self.pair_digest, "holdout pair_digest")
        expected_pair = _hash(
            b"pair",
            {
                "input_digest": input_digest,
                "target_digest": target_digest,
            },
        )
        if pair != expected_pair:
            raise NativeIntelligenceHoldoutError("holdout input/target pair mismatch")
        expected = _hash(
            b"case",
            {
                "case_id": case_id,
                "stage": self.stage,
                "outcome": self.outcome,
                "oracle_digest": oracle,
                "input_digest": input_digest,
                "target_digest": target_digest,
                "pair_digest": pair,
            },
        )
        if self.digest != expected:
            raise NativeIntelligenceHoldoutError("holdout case seal mismatch")


@dataclass(frozen=True, slots=True)
class NativeIntelligenceHoldoutV1:
    source_commit: str
    curriculum_digest: str
    case_count: int
    stage_counts: tuple[tuple[str, int], ...]
    cases: tuple[HoldoutCaseFingerprintV1, ...]
    training_inclusion_allowed: bool
    digest: str
    version: int = 1

    def assert_sealed(self) -> None:
        if self.version != 1:
            raise NativeIntelligenceHoldoutError("unsupported native holdout version")
        source = _digest(self.source_commit, "holdout source_commit", length=40)
        curriculum = _digest(self.curriculum_digest, "holdout curriculum_digest")
        if self.training_inclusion_allowed is not False:
            raise NativeIntelligenceHoldoutError(
                "constitutional holdout cannot be admitted as training data"
            )
        if not isinstance(self.case_count, int) or self.case_count < 1:
            raise NativeIntelligenceHoldoutError("holdout case_count must be positive")
        if self.case_count != len(self.cases):
            raise NativeIntelligenceHoldoutError("holdout case_count mismatch")

        expected_stage_counts = tuple(
            (stage, sum(case.stage == stage for case in self.cases))
            for stage in STAGES
        )
        if self.stage_counts != expected_stage_counts:
            raise NativeIntelligenceHoldoutError("holdout stage_counts mismatch")

        case_ids: set[str] = set()
        input_digests: set[str] = set()
        pair_digests: set[str] = set()
        case_digests: list[str] = []
        for case in self.cases:
            case.assert_sealed()
            if case.case_id in case_ids:
                raise NativeIntelligenceHoldoutError("duplicate holdout case identity")
            if case.input_digest in input_digests:
                raise NativeIntelligenceHoldoutError("duplicate holdout input")
            if case.pair_digest in pair_digests:
                raise NativeIntelligenceHoldoutError("duplicate holdout input/target pair")
            case_ids.add(case.case_id)
            input_digests.add(case.input_digest)
            pair_digests.add(case.pair_digest)
            case_digests.append(case.digest)

        expected = _hash(
            b"release",
            {
                "source_commit": source,
                "curriculum_digest": curriculum,
                "case_count": self.case_count,
                "stage_counts": list(self.stage_counts),
                "case_digests": case_digests,
                "training_inclusion_allowed": False,
            },
        )
        if self.digest != expected:
            raise NativeIntelligenceHoldoutError("native holdout release seal mismatch")


@dataclass(frozen=True, slots=True)
class TrainingExampleFingerprintV1:
    example_id: str
    input_digest: str
    target_digest: str
    pair_digest: str
    digest: str
    version: int = 1

    def assert_sealed(self) -> None:
        if self.version != 1:
            raise NativeIntelligenceHoldoutError("unsupported training fingerprint version")
        example_id = _text(self.example_id, "training example_id")
        input_digest = _digest(self.input_digest, "training input_digest")
        target_digest = _digest(self.target_digest, "training target_digest")
        pair = _digest(self.pair_digest, "training pair_digest")
        expected_pair = _hash(
            b"pair",
            {
                "input_digest": input_digest,
                "target_digest": target_digest,
            },
        )
        if pair != expected_pair:
            raise NativeIntelligenceHoldoutError("training input/target pair mismatch")
        expected = _hash(
            b"training-example",
            {
                "example_id": example_id,
                "input_digest": input_digest,
                "target_digest": target_digest,
                "pair_digest": pair,
            },
        )
        if self.digest != expected:
            raise NativeIntelligenceHoldoutError("training example fingerprint mismatch")


def _fingerprint_case(
    *,
    case_id: str,
    stage: str,
    outcome: str,
    oracle_digest: str,
    input_text: str,
    target_text: str,
) -> HoldoutCaseFingerprintV1:
    input_digest = hashlib.sha256(input_text.encode("utf-8")).hexdigest()
    target_digest = hashlib.sha256(target_text.encode("utf-8")).hexdigest()
    pair = _hash(
        b"pair",
        {
            "input_digest": input_digest,
            "target_digest": target_digest,
        },
    )
    result = HoldoutCaseFingerprintV1(
        case_id=case_id,
        stage=stage,
        outcome=outcome,
        oracle_digest=oracle_digest,
        input_digest=input_digest,
        target_digest=target_digest,
        pair_digest=pair,
        digest="",
    )
    object.__setattr__(
        result,
        "digest",
        _hash(
            b"case",
            {
                "case_id": result.case_id,
                "stage": result.stage,
                "outcome": result.outcome,
                "oracle_digest": result.oracle_digest,
                "input_digest": result.input_digest,
                "target_digest": result.target_digest,
                "pair_digest": result.pair_digest,
            },
        ),
    )
    result.assert_sealed()
    return result


def build_native_intelligence_holdout_v1(
    curriculum: NativeModelCurriculumV2,
) -> NativeIntelligenceHoldoutV1:
    """Seal a verified N0..N6 curriculum as evaluation-only evidence."""

    verified = verify_native_model_curriculum_v2(curriculum)
    cases = tuple(
        _fingerprint_case(
            case_id=case.case_id,
            stage=case.stage,
            outcome=case.outcome,
            oracle_digest=case.oracle_digest,
            input_text=case.input_text,
            target_text=case.target_text,
        )
        for case in verified.cases
    )
    stage_counts = tuple(
        (stage, sum(case.stage == stage for case in cases))
        for stage in STAGES
    )
    result = NativeIntelligenceHoldoutV1(
        source_commit=verified.source_commit,
        curriculum_digest=verified.curriculum_sha256,
        case_count=len(cases),
        stage_counts=stage_counts,
        cases=cases,
        training_inclusion_allowed=False,
        digest="",
    )
    object.__setattr__(
        result,
        "digest",
        _hash(
            b"release",
            {
                "source_commit": result.source_commit,
                "curriculum_digest": result.curriculum_digest,
                "case_count": result.case_count,
                "stage_counts": list(result.stage_counts),
                "case_digests": [case.digest for case in result.cases],
                "training_inclusion_allowed": False,
            },
        ),
    )
    result.assert_sealed()
    return result


def fingerprint_training_example_v1(
    *,
    example_id: str,
    input_text: str,
    target_text: str,
) -> TrainingExampleFingerprintV1:
    """Fingerprint one candidate training example without granting admission."""

    _text(example_id, "training example_id")
    if not isinstance(input_text, str) or not input_text or "\x00" in input_text:
        raise NativeIntelligenceHoldoutError("training input_text must be non-empty text")
    if not isinstance(target_text, str) or not target_text or "\x00" in target_text:
        raise NativeIntelligenceHoldoutError("training target_text must be non-empty text")
    input_digest = hashlib.sha256(input_text.encode("utf-8")).hexdigest()
    target_digest = hashlib.sha256(target_text.encode("utf-8")).hexdigest()
    pair = _hash(
        b"pair",
        {
            "input_digest": input_digest,
            "target_digest": target_digest,
        },
    )
    result = TrainingExampleFingerprintV1(
        example_id=example_id,
        input_digest=input_digest,
        target_digest=target_digest,
        pair_digest=pair,
        digest="",
    )
    object.__setattr__(
        result,
        "digest",
        _hash(
            b"training-example",
            {
                "example_id": result.example_id,
                "input_digest": result.input_digest,
                "target_digest": result.target_digest,
                "pair_digest": result.pair_digest,
            },
        ),
    )
    result.assert_sealed()
    return result


def require_training_disjoint_from_holdout_v1(
    holdout: NativeIntelligenceHoldoutV1,
    examples: Iterable[TrainingExampleFingerprintV1],
) -> tuple[TrainingExampleFingerprintV1, ...]:
    """Reject exact holdout leakage before a training release can be sealed."""

    holdout.assert_sealed()
    supplied = tuple(examples)
    if not supplied:
        raise NativeIntelligenceHoldoutError("training candidate set cannot be empty")

    holdout_ids = {case.case_id for case in holdout.cases}
    holdout_inputs = {case.input_digest for case in holdout.cases}
    holdout_pairs = {case.pair_digest for case in holdout.cases}
    seen_ids: set[str] = set()
    seen_pairs: set[str] = set()

    for example in supplied:
        example.assert_sealed()
        if example.example_id in holdout_ids:
            raise NativeIntelligenceHoldoutError(
                "training example reuses constitutional holdout case identity"
            )
        if example.input_digest in holdout_inputs:
            raise NativeIntelligenceHoldoutError(
                "training example reuses constitutional holdout input"
            )
        if example.pair_digest in holdout_pairs:
            raise NativeIntelligenceHoldoutError(
                "training example reuses constitutional holdout input/target pair"
            )
        if example.example_id in seen_ids:
            raise NativeIntelligenceHoldoutError("duplicate training example identity")
        if example.pair_digest in seen_pairs:
            raise NativeIntelligenceHoldoutError("duplicate training input/target pair")
        seen_ids.add(example.example_id)
        seen_pairs.add(example.pair_digest)

    return supplied
