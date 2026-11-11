"""Complete first-run configuration evidence for Koschei Qwen397B v1.

A static LoRA profile is not enough to identify a real training run. The first
397B configuration joins four already-sealed facts:

- the canonical Koschei Qwen adapter profile;
- the exact pinned external base-artifact preflight;
- the exact balanced training export;
- the pinned-tokenizer train/validation profile with zero truncation.

The resulting digest is the ``training_config_digest`` consumed by the generic
native training plan. This object is evidence only and carries no authority.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json

from .native_intelligence_qwen397b_base_spec_v1 import (
    CANONICAL_QWEN397B_MODEL_ID_V1,
    CANONICAL_QWEN397B_REVISION_V1,
    CANONICAL_QWEN397B_TRAINING_METHOD_V1,
)
from .native_intelligence_qwen397b_preflight_v1 import Qwen397BPreflightEvidenceV1
from .native_intelligence_qwen397b_profile_v1 import Qwen397BKoscheiTrainingProfileV1
from .native_intelligence_qwen397b_token_profile_v1 import Qwen397BTokenProfileV1
from .native_intelligence_training_export_v1 import NativeTrainingExportManifestV1

_CTX = b"koschei.native-intelligence-qwen397b-run-config/v1\x00"


class Qwen397BRunConfigError(ValueError):
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


@dataclass(frozen=True, slots=True)
class Qwen397BRunConfigV1:
    base_model_id: str
    base_model_revision: str
    training_method: str
    profile_digest: str
    base_preflight_digest: str
    base_weights_identity_digest: str
    training_export_digest: str
    token_profile_digest: str
    tokenizer_revision: str
    authority: bool
    digest: str
    version: int = 1

    def _payload(self) -> dict[str, object]:
        return {
            "base_model_id": self.base_model_id,
            "base_model_revision": self.base_model_revision,
            "training_method": self.training_method,
            "profile_digest": self.profile_digest,
            "base_preflight_digest": self.base_preflight_digest,
            "base_weights_identity_digest": self.base_weights_identity_digest,
            "training_export_digest": self.training_export_digest,
            "token_profile_digest": self.token_profile_digest,
            "tokenizer_revision": self.tokenizer_revision,
            "authority": False,
        }

    def assert_for(
        self,
        profile: Qwen397BKoscheiTrainingProfileV1,
        preflight: Qwen397BPreflightEvidenceV1,
        token_profile: Qwen397BTokenProfileV1,
        manifest: NativeTrainingExportManifestV1,
    ) -> None:
        if self.version != 1:
            raise Qwen397BRunConfigError("unsupported Qwen397B run-config version")
        try:
            profile.assert_sealed()
            preflight.assert_sealed()
            token_profile.assert_for(manifest, profile)
            manifest.assert_sealed()
        except ValueError as error:
            raise Qwen397BRunConfigError(str(error)) from error

        expected = {
            "base_model_id": CANONICAL_QWEN397B_MODEL_ID_V1,
            "base_model_revision": CANONICAL_QWEN397B_REVISION_V1,
            "training_method": CANONICAL_QWEN397B_TRAINING_METHOD_V1,
            "profile_digest": profile.digest,
            "base_preflight_digest": preflight.digest,
            "base_weights_identity_digest": preflight.weights_identity_digest,
            "training_export_digest": manifest.digest,
            "token_profile_digest": token_profile.digest,
            "tokenizer_revision": CANONICAL_QWEN397B_REVISION_V1,
        }
        for field, value in expected.items():
            if getattr(self, field) != value:
                raise Qwen397BRunConfigError(f"Qwen397B run-config mismatch: {field}")
        if preflight.resolved_revision != self.base_model_revision:
            raise Qwen397BRunConfigError("Qwen397B base preflight revision mismatch")
        if token_profile.tokenizer_revision != self.base_model_revision:
            raise Qwen397BRunConfigError("Qwen397B tokenizer/base revision mismatch")
        if token_profile.training_export_digest != self.training_export_digest:
            raise Qwen397BRunConfigError("Qwen397B token/export identity mismatch")
        if self.authority is not False:
            raise Qwen397BRunConfigError("Qwen397B run-config cannot carry authority")
        if self.digest != _hash(self._payload()):
            raise Qwen397BRunConfigError("Qwen397B run-config seal mismatch")


def seal_qwen397b_run_config_v1(
    profile: Qwen397BKoscheiTrainingProfileV1,
    preflight: Qwen397BPreflightEvidenceV1,
    token_profile: Qwen397BTokenProfileV1,
    manifest: NativeTrainingExportManifestV1,
) -> Qwen397BRunConfigV1:
    """Seal the complete non-authoritative identity of the first 397B run config."""

    try:
        profile.assert_sealed()
        preflight.assert_sealed()
        token_profile.assert_for(manifest, profile)
        manifest.assert_sealed()
    except ValueError as error:
        raise Qwen397BRunConfigError(str(error)) from error

    result = Qwen397BRunConfigV1(
        base_model_id=CANONICAL_QWEN397B_MODEL_ID_V1,
        base_model_revision=CANONICAL_QWEN397B_REVISION_V1,
        training_method=CANONICAL_QWEN397B_TRAINING_METHOD_V1,
        profile_digest=profile.digest,
        base_preflight_digest=preflight.digest,
        base_weights_identity_digest=preflight.weights_identity_digest,
        training_export_digest=manifest.digest,
        token_profile_digest=token_profile.digest,
        tokenizer_revision=token_profile.tokenizer_revision,
        authority=False,
        digest="",
    )
    object.__setattr__(result, "digest", _hash(result._payload()))
    result.assert_for(profile, preflight, token_profile, manifest)
    return result
