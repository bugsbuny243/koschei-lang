"""Koschei Trusted Launcher v1 — permit construction only.

This module intentionally does not spawn a process. It combines two independent
authority gates and emits a tamper-evident launch permit only when both succeed:

1. deterministic Trust Plane artifact/policy/static-capability verification;
2. externally signed, time-bounded, atomically single-use launch authorization.

The permit binds the actual atomic redemption evidence, not merely the signed
authorization payload. OS sandbox enforcement and process creation are later
layers.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
from typing import Callable

from .build_manifest import NativeBuildManifest
from .deployment_authorization_v1 import (
    DeploymentAuthorization,
    redeem_deployment_authorization,
)
from .release_proof import ReleaseProof
from .trust_plane_v1 import (
    LaunchDecision,
    LocalPolicy,
    StaticCapabilityRequest,
    TrustArtifactManifest,
    evaluate_launch,
)

_SCHEMA = "koschei.trusted-launch-permit.v1"


@dataclass(frozen=True, slots=True)
class TrustedLaunchPermit:
    environment: str
    artifact_sha256: str
    trust_manifest_digest: str
    policy_hash: str
    capability_request_digest: str
    effective_capabilities: tuple[str, ...]
    launch_decision_digest: str
    deployment_authorization_digest: str
    authorization_redemption_digest: str
    authorization_id: str
    permit_digest: str

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": _SCHEMA,
            "environment": self.environment,
            "artifact_sha256": self.artifact_sha256,
            "trust_manifest_digest": self.trust_manifest_digest,
            "policy_hash": self.policy_hash,
            "capability_request_digest": self.capability_request_digest,
            "effective_capabilities": list(self.effective_capabilities),
            "launch_decision_digest": self.launch_decision_digest,
            "deployment_authorization_digest": self.deployment_authorization_digest,
            "authorization_redemption_digest": self.authorization_redemption_digest,
            "authorization_id": self.authorization_id,
            "permit_digest": self.permit_digest,
        }


def authorize_trusted_launch(
    *,
    artifact_manifest: TrustArtifactManifest,
    local_policy: LocalPolicy,
    capability_request: StaticCapabilityRequest,
    build: NativeBuildManifest,
    release_proof: ReleaseProof,
    artifact: str | Path,
    deployment_authorization: DeploymentAuthorization,
    authorization_signature: bytes,
    signature_verifier: Callable[[bytes, bytes], bool],
    atomic_redeemer: Callable[[str, str], bool],
    current_epoch: int,
) -> TrustedLaunchPermit | None:
    """Return a one-operation launch permit or fail closed with ``None``.

    The deployment authorization is redeemed only after deterministic artifact
    eligibility succeeds. A failed artifact/provenance/policy check therefore
    never burns a valid authorization.
    """

    launch_decision = evaluate_launch(
        artifact_manifest,
        local_policy=local_policy,
        capability_request=capability_request,
        build=build,
        release_proof=release_proof,
        artifact=artifact,
    )
    if not launch_decision.allowed:
        return None

    if not _launch_decision_matches(
        launch_decision,
        artifact_manifest=artifact_manifest,
        local_policy=local_policy,
        capability_request=capability_request,
    ):
        return None

    redeemed = redeem_deployment_authorization(
        deployment_authorization,
        signature=authorization_signature,
        signature_verifier=signature_verifier,
        atomic_redeemer=atomic_redeemer,
        current_epoch=current_epoch,
        expected_operation="launch",
        expected_environment=local_policy.environment,
        artifact_manifest=artifact_manifest,
        local_policy=local_policy,
        capability_request=capability_request,
    )
    if redeemed is None:
        return None

    if not _redemption_matches(
        redeemed,
        artifact_manifest=artifact_manifest,
        local_policy=local_policy,
        capability_request=capability_request,
        authorization_id=deployment_authorization.authorization_id,
    ):
        return None

    payload = {
        "schema_version": _SCHEMA,
        "environment": local_policy.environment,
        "artifact_sha256": artifact_manifest.artifact_sha256,
        "trust_manifest_digest": artifact_manifest.manifest_digest,
        "policy_hash": local_policy.policy_hash,
        "capability_request_digest": capability_request.request_digest,
        "effective_capabilities": list(launch_decision.effective_capabilities),
        "launch_decision_digest": launch_decision.decision_digest,
        "deployment_authorization_digest": redeemed.authorization_digest,
        "authorization_redemption_digest": redeemed.redemption_digest,
        "authorization_id": redeemed.authorization_id,
    }
    return TrustedLaunchPermit(
        environment=local_policy.environment,
        artifact_sha256=artifact_manifest.artifact_sha256,
        trust_manifest_digest=artifact_manifest.manifest_digest,
        policy_hash=local_policy.policy_hash,
        capability_request_digest=capability_request.request_digest,
        effective_capabilities=launch_decision.effective_capabilities,
        launch_decision_digest=launch_decision.decision_digest,
        deployment_authorization_digest=redeemed.authorization_digest,
        authorization_redemption_digest=redeemed.redemption_digest,
        authorization_id=redeemed.authorization_id,
        permit_digest=_digest(payload),
    )


def _launch_decision_matches(
    decision: LaunchDecision,
    *,
    artifact_manifest: TrustArtifactManifest,
    local_policy: LocalPolicy,
    capability_request: StaticCapabilityRequest,
) -> bool:
    return (
        decision.allowed is True
        and decision.artifact_sha256 == artifact_manifest.artifact_sha256
        and decision.policy_hash == local_policy.policy_hash
        and decision.capability_request_digest == capability_request.request_digest
        and decision.effective_capabilities == capability_request.capabilities
    )


def _redemption_matches(
    redemption: object,
    *,
    artifact_manifest: TrustArtifactManifest,
    local_policy: LocalPolicy,
    capability_request: StaticCapabilityRequest,
    authorization_id: str,
) -> bool:
    return (
        getattr(redemption, "authorization_id", None) == authorization_id
        and getattr(redemption, "operation", None) == "launch"
        and getattr(redemption, "environment", None) == local_policy.environment
        and getattr(redemption, "artifact_sha256", None) == artifact_manifest.artifact_sha256
        and getattr(redemption, "trust_manifest_digest", None) == artifact_manifest.manifest_digest
        and getattr(redemption, "policy_hash", None) == local_policy.policy_hash
        and getattr(redemption, "capability_request_digest", None) == capability_request.request_digest
        and isinstance(getattr(redemption, "authorization_digest", None), str)
        and isinstance(getattr(redemption, "redemption_digest", None), str)
    )


def _digest(value: object) -> str:
    encoded = json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()
