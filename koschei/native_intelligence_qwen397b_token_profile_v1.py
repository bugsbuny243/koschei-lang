"""Tokenizer preflight evidence for the first Koschei Qwen397B run v1.

The first-run profile caps SFT sequences at 4096 tokens. Before expensive compute
may begin, the exact train and validation export bytes must be formatted with the
pinned Qwen tokenizer and measured. V1 permits zero silent truncation: if one
example exceeds the cap, the corpus/profile must be changed and resealed.

The token profile binds not only a formatting-version label but the exact stdlib
formatter contract digest, so prompt/role drift cannot silently reuse an old
preflight. The sealed test split is intentionally absent from this evidence
because it is not a trainer input.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import string

from .native_intelligence_qwen397b_base_spec_v1 import CANONICAL_QWEN397B_REVISION_V1
from .native_intelligence_qwen397b_profile_v1 import Qwen397BKoscheiTrainingProfileV1
from .native_intelligence_qwen397b_sft_format_v1 import (
    FORMATTING_VERSION_V1,
    qwen397b_format_contract_digest_v1,
)
from .native_intelligence_training_export_v1 import NativeTrainingExportManifestV1

_CTX = b"koschei.native-intelligence-qwen397b-token-profile/v1\x00"
_HEX = frozenset(string.hexdigits.lower())


class Qwen397BTokenProfileError(ValueError):
    pass


def _canonical_json(value: object) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def _hash(payload: object) -> str:
    return hashlib.sha256(_CTX + _canonical_json(payload)).hexdigest()


def _digest(value: str, label: str) -> str:
    if not isinstance(value, str) or len(value) != 64:
        raise Qwen397BTokenProfileError(f"{label} must be a 64-character digest")
    lowered = value.lower()
    if any(char not in _HEX for char in lowered) or lowered == "0" * 64:
        raise Qwen397BTokenProfileError(f"{label} must be a non-zero hexadecimal digest")
    return lowered


@dataclass(frozen=True, slots=True)
class Qwen397BTokenProfileV1:
    training_export_digest: str
    tokenizer_revision: str
    formatting_version: str
    format_contract_digest: str
    max_length: int
    train_examples: int
    validation_examples: int
    train_tokens: int
    validation_tokens: int
    max_train_tokens: int
    max_validation_tokens: int
    train_truncated_examples: int
    validation_truncated_examples: int
    authority: bool
    digest: str
    version: int = 1

    def _payload(self) -> dict[str, object]:
        return {
            "training_export_digest": self.training_export_digest,
            "tokenizer_revision": self.tokenizer_revision,
            "formatting_version": self.formatting_version,
            "format_contract_digest": self.format_contract_digest,
            "max_length": self.max_length,
            "train_examples": self.train_examples,
            "validation_examples": self.validation_examples,
            "train_tokens": self.train_tokens,
            "validation_tokens": self.validation_tokens,
            "max_train_tokens": self.max_train_tokens,
            "max_validation_tokens": self.max_validation_tokens,
            "train_truncated_examples": self.train_truncated_examples,
            "validation_truncated_examples": self.validation_truncated_examples,
            "authority": False,
        }

    def assert_for(
        self,
        manifest: NativeTrainingExportManifestV1,
        profile: Qwen397BKoscheiTrainingProfileV1,
    ) -> None:
        if self.version != 1:
            raise Qwen397BTokenProfileError("unsupported Qwen397B token profile version")
        manifest.assert_sealed()
        profile.assert_sealed()
        if self.training_export_digest != manifest.digest:
            raise Qwen397BTokenProfileError("token profile belongs to a different training export")
        if self.tokenizer_revision != CANONICAL_QWEN397B_REVISION_V1:
            raise Qwen397BTokenProfileError("tokenizer revision drift")
        if self.formatting_version != FORMATTING_VERSION_V1:
            raise Qwen397BTokenProfileError("SFT formatting version drift")
        expected_format = qwen397b_format_contract_digest_v1()
        if self.format_contract_digest != expected_format:
            raise Qwen397BTokenProfileError("SFT format contract digest mismatch")
        _digest(self.format_contract_digest, "format_contract_digest")
        if self.max_length != profile.max_sequence_length:
            raise Qwen397BTokenProfileError("token profile max length differs from training profile")
        expected_counts = {row.split: row.example_count for row in manifest.files}
        if self.train_examples != expected_counts["train"]:
            raise Qwen397BTokenProfileError("token profile train example count mismatch")
        if self.validation_examples != expected_counts["validation"]:
            raise Qwen397BTokenProfileError("token profile validation example count mismatch")
        for field in (
            "train_examples",
            "validation_examples",
            "train_tokens",
            "validation_tokens",
            "max_train_tokens",
            "max_validation_tokens",
            "train_truncated_examples",
            "validation_truncated_examples",
        ):
            value = getattr(self, field)
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                raise Qwen397BTokenProfileError(f"invalid token-profile field: {field}")
        if self.train_examples < 1 or self.validation_examples < 1:
            raise Qwen397BTokenProfileError("token-profile splits cannot be empty")
        if self.train_tokens < self.train_examples or self.validation_tokens < self.validation_examples:
            raise Qwen397BTokenProfileError("token-profile token totals are impossible")
        if self.max_train_tokens > self.max_length or self.max_validation_tokens > self.max_length:
            raise Qwen397BTokenProfileError("token-profile recorded unbounded sequence length")
        if self.train_truncated_examples != 0 or self.validation_truncated_examples != 0:
            raise Qwen397BTokenProfileError(
                "first Qwen397B run forbids silent train/validation truncation"
            )
        if self.authority is not False:
            raise Qwen397BTokenProfileError("token profile cannot carry authority")
        _digest(self.training_export_digest, "training_export_digest")
        expected = _hash(self._payload())
        if self.digest != expected:
            raise Qwen397BTokenProfileError("Qwen397B token profile seal mismatch")


def seal_qwen397b_token_profile_v1(
    manifest: NativeTrainingExportManifestV1,
    profile: Qwen397BKoscheiTrainingProfileV1,
    *,
    tokenizer_revision: str,
    formatting_version: str,
    train_examples: int,
    validation_examples: int,
    train_tokens: int,
    validation_tokens: int,
    max_train_tokens: int,
    max_validation_tokens: int,
    train_truncated_examples: int,
    validation_truncated_examples: int,
) -> Qwen397BTokenProfileV1:
    result = Qwen397BTokenProfileV1(
        training_export_digest=manifest.digest,
        tokenizer_revision=tokenizer_revision,
        formatting_version=formatting_version,
        format_contract_digest=qwen397b_format_contract_digest_v1(),
        max_length=profile.max_sequence_length,
        train_examples=train_examples,
        validation_examples=validation_examples,
        train_tokens=train_tokens,
        validation_tokens=validation_tokens,
        max_train_tokens=max_train_tokens,
        max_validation_tokens=max_validation_tokens,
        train_truncated_examples=train_truncated_examples,
        validation_truncated_examples=validation_truncated_examples,
        authority=False,
        digest="",
    )
    object.__setattr__(result, "digest", _hash(result._payload()))
    result.assert_for(manifest, profile)
    return result
