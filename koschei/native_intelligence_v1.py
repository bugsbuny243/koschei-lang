"""Koschei-native intelligence identity and event binding v1.

Koschei Sentinel is no longer modeled as a separate authority-bearing product.
The model becomes an intelligence plane inside Koschei Lang.  In v1 the
canonical base model is Qwen/Qwen3.5-397B-A17B, but model inference can only
produce authority-free evidence/proposals.  Khar, Sathra, Matrix/Hara, Morth and
the normal execution gates remain the source of executable reality.

Model weights are intentionally not stored in this repository.  This module
binds the exact external model revision/weights, Koschei curriculum and trained
adapter identity into a sealed software identity that can be tied to one living
Galaxy event.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import string

from .khar_constitution_v1 import CANONICAL_KHAR_DIGEST_V1

CANONICAL_BASE_MODEL_V1 = "Qwen/Qwen3.5-397B-A17B"
_CTX = b"koschei.native-intelligence/v1\x00"
_HEX = frozenset(string.hexdigits.lower())


class NativeIntelligenceError(ValueError):
    pass


def _require_digest(value: str, label: str) -> str:
    if not isinstance(value, str) or len(value) != 64:
        raise NativeIntelligenceError(f"{label} must be a 64-character digest")
    lowered = value.lower()
    if any(ch not in _HEX for ch in lowered) or lowered == "0" * 64:
        raise NativeIntelligenceError(f"{label} must be a non-zero hexadecimal digest")
    return lowered


def _require_commit(value: str, label: str) -> str:
    if not isinstance(value, str) or len(value) != 40:
        raise NativeIntelligenceError(f"{label} must be a 40-character commit SHA")
    lowered = value.lower()
    if any(ch not in _HEX for ch in lowered) or lowered == "0" * 40:
        raise NativeIntelligenceError(f"{label} must be a non-zero hexadecimal SHA")
    return lowered


def _require_text(value: str, label: str, *, max_length: int = 160) -> str:
    if not isinstance(value, str) or not value or len(value) > max_length or "\x00" in value:
        raise NativeIntelligenceError(f"{label} must be non-empty bounded text")
    return value


def _hash(kind: bytes, rows: tuple[str, ...]) -> str:
    return hashlib.sha256(_CTX + kind + b"\x00" + "\n".join(rows).encode()).hexdigest()


@dataclass(frozen=True, slots=True)
class NativeIntelligenceIdentityV1:
    khar_digest: str
    base_model_id: str
    base_model_revision: str
    base_weights_digest: str
    curriculum_digest: str
    adapter_digest: str
    training_run_digest: str
    source_commit: str
    training_method: str
    multimodal: bool
    authority: bool
    digest: str
    version: int = 1

    def assert_sealed(self) -> None:
        if self.version != 1:
            raise NativeIntelligenceError("unsupported native intelligence identity version")
        if self.khar_digest != CANONICAL_KHAR_DIGEST_V1:
            raise NativeIntelligenceError("native intelligence is not bound to canonical Khar v1")
        if self.base_model_id != CANONICAL_BASE_MODEL_V1:
            raise NativeIntelligenceError("native intelligence base model is not canonical v1")
        revision = _require_commit(self.base_model_revision, "base_model_revision")
        weights = _require_digest(self.base_weights_digest, "base_weights_digest")
        curriculum = _require_digest(self.curriculum_digest, "curriculum_digest")
        adapter = _require_digest(self.adapter_digest, "adapter_digest")
        run = _require_digest(self.training_run_digest, "training_run_digest")
        source = _require_commit(self.source_commit, "source_commit")
        method = _require_text(self.training_method, "training_method", max_length=64)
        if self.multimodal is not True:
            raise NativeIntelligenceError("canonical Qwen native intelligence v1 is multimodal")
        if self.authority is not False:
            raise NativeIntelligenceError("native intelligence identity cannot carry authority")
        expected = _hash(
            b"identity",
            (
                f"khar={self.khar_digest}",
                f"base-model={self.base_model_id}",
                f"base-revision={revision}",
                f"base-weights={weights}",
                f"curriculum={curriculum}",
                f"adapter={adapter}",
                f"training-run={run}",
                f"source-commit={source}",
                f"training-method={method}",
                "multimodal=true",
                "authority=false",
            ),
        )
        if self.digest != expected:
            raise NativeIntelligenceError("native intelligence identity seal mismatch")


def build_native_intelligence_identity(
    *,
    base_model_revision: str,
    base_weights_digest: str,
    curriculum_digest: str,
    adapter_digest: str,
    training_run_digest: str,
    source_commit: str,
    training_method: str,
) -> NativeIntelligenceIdentityV1:
    """Seal one exact Koschei-trained Qwen intelligence identity.

    ``adapter_digest`` identifies the trained Koschei delta/checkpoint.  It may
    represent LoRA/QLoRA or another explicitly recorded training artifact; v1
    does not pretend that one training method is already final.
    """

    result = NativeIntelligenceIdentityV1(
        khar_digest=CANONICAL_KHAR_DIGEST_V1,
        base_model_id=CANONICAL_BASE_MODEL_V1,
        base_model_revision=_require_commit(base_model_revision, "base_model_revision"),
        base_weights_digest=_require_digest(base_weights_digest, "base_weights_digest"),
        curriculum_digest=_require_digest(curriculum_digest, "curriculum_digest"),
        adapter_digest=_require_digest(adapter_digest, "adapter_digest"),
        training_run_digest=_require_digest(training_run_digest, "training_run_digest"),
        source_commit=_require_commit(source_commit, "source_commit"),
        training_method=_require_text(training_method, "training_method", max_length=64),
        multimodal=True,
        authority=False,
        digest="",
    )
    object.__setattr__(
        result,
        "digest",
        _hash(
            b"identity",
            (
                f"khar={result.khar_digest}",
                f"base-model={result.base_model_id}",
                f"base-revision={result.base_model_revision}",
                f"base-weights={result.base_weights_digest}",
                f"curriculum={result.curriculum_digest}",
                f"adapter={result.adapter_digest}",
                f"training-run={result.training_run_digest}",
                f"source-commit={result.source_commit}",
                f"training-method={result.training_method}",
                "multimodal=true",
                "authority=false",
            ),
        ),
    )
    result.assert_sealed()
    return result


@dataclass(frozen=True, slots=True)
class NativeIntelligenceEventBindingV1:
    intelligence_digest: str
    veyra_digest: str
    native_mir_fingerprint: str
    epoch: int
    proposal_digest: str
    observation_digest: str
    output_digest: str
    authority: bool
    digest: str
    version: int = 1

    def assert_for(
        self,
        intelligence: NativeIntelligenceIdentityV1,
        *,
        veyra_digest: str,
        native_mir_fingerprint: str,
        epoch: int,
        proposal_digest: str,
    ) -> None:
        if self.version != 1:
            raise NativeIntelligenceError("unsupported native intelligence event binding version")
        intelligence.assert_sealed()
        if self.authority is not False:
            raise NativeIntelligenceError("native intelligence event binding cannot carry authority")
        if isinstance(epoch, bool) or not isinstance(epoch, int) or epoch < 0:
            raise NativeIntelligenceError("native intelligence epoch must be non-negative")
        expected_values = {
            "intelligence_digest": intelligence.digest,
            "veyra_digest": _require_digest(veyra_digest, "veyra_digest"),
            "native_mir_fingerprint": _require_digest(
                native_mir_fingerprint, "native_mir_fingerprint"
            ),
            "epoch": epoch,
            "proposal_digest": _require_digest(proposal_digest, "proposal_digest"),
        }
        for field, expected in expected_values.items():
            if getattr(self, field) != expected:
                raise NativeIntelligenceError(f"native intelligence binding {field} mismatch")
        observation = _require_digest(self.observation_digest, "observation_digest")
        output = _require_digest(self.output_digest, "output_digest")
        expected_digest = _hash(
            b"event",
            (
                f"intelligence={self.intelligence_digest}",
                f"veyra={self.veyra_digest}",
                f"mir={self.native_mir_fingerprint}",
                f"epoch={self.epoch}",
                f"proposal={self.proposal_digest}",
                f"observation={observation}",
                f"output={output}",
                "authority=false",
            ),
        )
        if self.digest != expected_digest:
            raise NativeIntelligenceError("native intelligence event binding seal mismatch")


def bind_native_intelligence_event(
    intelligence: NativeIntelligenceIdentityV1,
    *,
    veyra_digest: str,
    native_mir_fingerprint: str,
    epoch: int,
    proposal_digest: str,
    observation_digest: str,
    output_digest: str,
) -> NativeIntelligenceEventBindingV1:
    """Bind one model observation/output to one exact authority-free proposal event."""

    intelligence.assert_sealed()
    if isinstance(epoch, bool) or not isinstance(epoch, int) or epoch < 0:
        raise NativeIntelligenceError("native intelligence epoch must be non-negative")
    result = NativeIntelligenceEventBindingV1(
        intelligence_digest=intelligence.digest,
        veyra_digest=_require_digest(veyra_digest, "veyra_digest"),
        native_mir_fingerprint=_require_digest(
            native_mir_fingerprint, "native_mir_fingerprint"
        ),
        epoch=epoch,
        proposal_digest=_require_digest(proposal_digest, "proposal_digest"),
        observation_digest=_require_digest(observation_digest, "observation_digest"),
        output_digest=_require_digest(output_digest, "output_digest"),
        authority=False,
        digest="",
    )
    object.__setattr__(
        result,
        "digest",
        _hash(
            b"event",
            (
                f"intelligence={result.intelligence_digest}",
                f"veyra={result.veyra_digest}",
                f"mir={result.native_mir_fingerprint}",
                f"epoch={result.epoch}",
                f"proposal={result.proposal_digest}",
                f"observation={result.observation_digest}",
                f"output={result.output_digest}",
                "authority=false",
            ),
        ),
    )
    result.assert_for(
        intelligence,
        veyra_digest=result.veyra_digest,
        native_mir_fingerprint=result.native_mir_fingerprint,
        epoch=result.epoch,
        proposal_digest=result.proposal_digest,
    )
    return result
