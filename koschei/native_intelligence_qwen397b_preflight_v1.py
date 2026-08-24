"""Sealed base-artifact preflight evidence for the first Koschei 397B run.

The 807-GB base model is external to this repository. Before a training plan may
claim a Qwen3.5-397B base identity, a preflight must resolve the pinned Hub commit,
verify the canonical architecture, observe all 94 safetensors shards and hash the
safetensors index bytes.

``weights_identity_digest`` is an artifact-identity commitment derived from this
resolved metadata. It is intentionally not described as a byte-for-byte hash of
all ~807 GB of weight shards.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import string

from .native_intelligence_qwen397b_profile_v1 import (
    OFFICIAL_ARCHITECTURE,
    OFFICIAL_EXPERTS,
    OFFICIAL_EXPERTS_PER_TOKEN,
    OFFICIAL_MAX_POSITION_EMBEDDINGS,
    OFFICIAL_TEXT_HIDDEN_SIZE,
    OFFICIAL_TEXT_LAYERS,
)
from .native_intelligence_qwen397b_training_plan_v1 import CANONICAL_QWEN397B_REVISION_V1
from .native_intelligence_v1 import CANONICAL_BASE_MODEL_V1

_CTX = b"koschei.native-intelligence-qwen397b-preflight/v1\x00"
_HEX = frozenset(string.hexdigits.lower())
EXPECTED_WEIGHT_SHARDS_V1 = 94
MIN_EXPECTED_WEIGHT_BYTES_V1 = 700_000_000_000


class Qwen397BPreflightError(ValueError):
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
        raise Qwen397BPreflightError(f"{label} must be a 64-character digest")
    lowered = value.lower()
    if any(char not in _HEX for char in lowered) or lowered == "0" * 64:
        raise Qwen397BPreflightError(f"{label} must be a non-zero hexadecimal digest")
    return lowered


@dataclass(frozen=True, slots=True)
class Qwen397BPreflightEvidenceV1:
    repo_id: str
    requested_revision: str
    resolved_revision: str
    shard_count: int
    weight_bytes: int
    safetensors_index_sha256: str
    architecture: str
    text_hidden_size: int
    text_layers: int
    experts: int
    experts_per_token: int
    native_context: int
    authority: bool
    weights_identity_digest: str
    digest: str
    version: int = 1

    def _identity_payload(self) -> dict[str, object]:
        return {
            "repo_id": self.repo_id,
            "requested_revision": self.requested_revision,
            "resolved_revision": self.resolved_revision,
            "shard_count": self.shard_count,
            "weight_bytes": self.weight_bytes,
            "safetensors_index_sha256": self.safetensors_index_sha256,
        }

    def _payload(self) -> dict[str, object]:
        return {
            **self._identity_payload(),
            "architecture": self.architecture,
            "text_hidden_size": self.text_hidden_size,
            "text_layers": self.text_layers,
            "experts": self.experts,
            "experts_per_token": self.experts_per_token,
            "native_context": self.native_context,
            "authority": False,
        }

    def assert_sealed(self) -> None:
        if self.version != 1:
            raise Qwen397BPreflightError("unsupported Qwen397B preflight version")
        if self.repo_id != CANONICAL_BASE_MODEL_V1:
            raise Qwen397BPreflightError("Qwen397B preflight repo mismatch")
        if self.requested_revision != CANONICAL_QWEN397B_REVISION_V1:
            raise Qwen397BPreflightError("Qwen397B requested revision drift")
        if self.resolved_revision != self.requested_revision:
            raise Qwen397BPreflightError("Qwen397B Hub revision did not resolve exactly")
        if self.shard_count != EXPECTED_WEIGHT_SHARDS_V1:
            raise Qwen397BPreflightError("Qwen397B safetensors shard count mismatch")
        if (
            isinstance(self.weight_bytes, bool)
            or not isinstance(self.weight_bytes, int)
            or self.weight_bytes < MIN_EXPECTED_WEIGHT_BYTES_V1
        ):
            raise Qwen397BPreflightError("Qwen397B weight-byte observation is incomplete")
        _digest(self.safetensors_index_sha256, "safetensors_index_sha256")
        expected_facts = {
            "architecture": OFFICIAL_ARCHITECTURE,
            "text_hidden_size": OFFICIAL_TEXT_HIDDEN_SIZE,
            "text_layers": OFFICIAL_TEXT_LAYERS,
            "experts": OFFICIAL_EXPERTS,
            "experts_per_token": OFFICIAL_EXPERTS_PER_TOKEN,
            "native_context": OFFICIAL_MAX_POSITION_EMBEDDINGS,
        }
        for field, expected in expected_facts.items():
            if getattr(self, field) != expected:
                raise Qwen397BPreflightError(f"Qwen397B preflight architecture drift: {field}")
        if self.authority is not False:
            raise Qwen397BPreflightError("Qwen397B preflight cannot carry authority")
        expected_identity = _hash(b"weights-identity", self._identity_payload())
        if self.weights_identity_digest != expected_identity:
            raise Qwen397BPreflightError("Qwen397B weights identity seal mismatch")
        expected = _hash(b"preflight", self._payload())
        if self.digest != expected:
            raise Qwen397BPreflightError("Qwen397B preflight seal mismatch")


def seal_qwen397b_preflight_v1(
    *,
    repo_id: str,
    requested_revision: str,
    resolved_revision: str,
    shard_count: int,
    weight_bytes: int,
    safetensors_index_sha256: str,
    architecture: str,
    text_hidden_size: int,
    text_layers: int,
    experts: int,
    experts_per_token: int,
    native_context: int,
) -> Qwen397BPreflightEvidenceV1:
    result = Qwen397BPreflightEvidenceV1(
        repo_id=repo_id,
        requested_revision=requested_revision,
        resolved_revision=resolved_revision,
        shard_count=shard_count,
        weight_bytes=weight_bytes,
        safetensors_index_sha256=_digest(
            safetensors_index_sha256,
            "safetensors_index_sha256",
        ),
        architecture=architecture,
        text_hidden_size=text_hidden_size,
        text_layers=text_layers,
        experts=experts,
        experts_per_token=experts_per_token,
        native_context=native_context,
        authority=False,
        weights_identity_digest="",
        digest="",
    )
    object.__setattr__(
        result,
        "weights_identity_digest",
        _hash(b"weights-identity", result._identity_payload()),
    )
    object.__setattr__(result, "digest", _hash(b"preflight", result._payload()))
    result.assert_sealed()
    return result
