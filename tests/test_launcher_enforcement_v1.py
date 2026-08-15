from __future__ import annotations

from dataclasses import replace
import hashlib
import json

import pytest

from koschei.launcher_enforcement_v1 import (
    LauncherEnforcementError,
    build_sandbox_adapter_descriptor,
    build_sandbox_enforcement_plan,
    evaluate_sandbox_readiness,
)
from koschei.trust_plane_v1 import StaticCapabilityRequest
from koschei.trusted_launcher_v1 import TrustedLaunchPermit


def digest(value: object) -> str:
    encoded = json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def capability_request() -> StaticCapabilityRequest:
    grants = (
        ("disk", "/srv/koschei/data", True),
        ("net", "https://api.example", False),
    )
    capabilities = ("disk.read", "net.io")
    payload = {
        "schema_version": "koschei.static-capability-request.v1",
        "capabilities": list(capabilities),
        "grants": [
            {"domain": domain, "scope": scope, "read_only": read_only}
            for domain, scope, read_only in grants
        ],
    }
    return StaticCapabilityRequest(
        capabilities=capabilities,
        grants=grants,
        request_digest=digest(payload),
    )


def trusted_permit(request: StaticCapabilityRequest) -> TrustedLaunchPermit:
    payload = {
        "schema_version": "koschei.trusted-launch-permit.v1",
        "environment": "production",
        "artifact_sha256": digest("artifact"),
        "trust_manifest_digest": digest("trust-manifest"),
        "policy_hash": digest("policy"),
        "capability_request_digest": request.request_digest,
        "effective_capabilities": list(request.capabilities),
        "launch_decision_digest": digest("launch-decision"),
        "deployment_authorization_digest": digest("deployment-authorization"),
        "authorization_id": "launch-auth-test-0001",
    }
    return TrustedLaunchPermit(
        environment="production",
        artifact_sha256=payload["artifact_sha256"],
        trust_manifest_digest=payload["trust_manifest_digest"],
        policy_hash=payload["policy_hash"],
        capability_request_digest=request.request_digest,
        effective_capabilities=request.capabilities,
        launch_decision_digest=payload["launch_decision_digest"],
        deployment_authorization_digest=payload["deployment_authorization_digest"],
        authorization_id=payload["authorization_id"],
        permit_digest=digest(payload),
    )


def strong_adapter(*, domains=("disk", "net")):
    return build_sandbox_adapter_descriptor(
        adapter_id="linux-sandbox-test",
        adapter_version="1",
        platform="linux-amd64",
        config_digest=digest("sandbox-config"),
        supported_domains=domains,
        exact_scope_enforcement=True,
        default_deny_unrequested_domains=True,
        empty_environment_by_default=True,
        close_inherited_file_descriptors=True,
        shell_disabled=True,
        executable_digest_verified_at_spawn=True,
    )


def test_exact_permit_and_request_build_scope_preserving_plan():
    request = capability_request()
    permit = trusted_permit(request)

    plan = build_sandbox_enforcement_plan(permit, request)

    assert plan.effective_capabilities == ("disk.read", "net.io")
    assert plan.grants == request.grants
    assert plan.denied_domains == ("env", "process")
    assert plan.environment_inheritance == "deny_ambient_inheritance"
    assert plan.inherited_file_descriptors == "close_all_except_launcher_contract"
    assert plan.shell_execution == "disabled"
    assert plan.executable_identity == "verify_sha256_immediately_before_spawn"


def test_forged_permit_with_valid_looking_digest_is_rejected():
    request = capability_request()
    permit = trusted_permit(request)
    forged = replace(permit, artifact_sha256=digest("attacker-artifact"))

    with pytest.raises(LauncherEnforcementError):
        build_sandbox_enforcement_plan(forged, request)


def test_permit_capability_request_substitution_is_rejected():
    request = capability_request()
    permit = trusted_permit(request)
    forged = replace(permit, capability_request_digest=digest("other-request"))

    with pytest.raises(LauncherEnforcementError):
        build_sandbox_enforcement_plan(forged, request)


def test_forged_static_request_digest_is_rejected():
    request = capability_request()
    permit = trusted_permit(request)
    forged = replace(request, request_digest=digest("attacker-request"))

    with pytest.raises(LauncherEnforcementError):
        build_sandbox_enforcement_plan(permit, forged)


def test_static_capabilities_must_match_exact_grants():
    request = capability_request()
    permit = trusted_permit(request)
    forged = replace(request, capabilities=("disk.read", "net.io", "process.exec"))

    with pytest.raises(LauncherEnforcementError):
        build_sandbox_enforcement_plan(permit, forged)


def test_missing_requested_domain_is_not_ready():
    request = capability_request()
    plan = build_sandbox_enforcement_plan(trusted_permit(request), request)
    readiness = evaluate_sandbox_readiness(plan, strong_adapter(domains=("disk",)))

    assert readiness.ready is False
    assert readiness.code == "KS1962"


def test_any_missing_mandatory_boundary_is_not_ready():
    request = capability_request()
    plan = build_sandbox_enforcement_plan(trusted_permit(request), request)
    descriptor = strong_adapter()
    descriptor = replace(descriptor, shell_disabled=False)
    payload = descriptor.to_dict()
    payload.pop("descriptor_digest")
    descriptor = replace(descriptor, descriptor_digest=digest(payload))

    readiness = evaluate_sandbox_readiness(plan, descriptor)

    assert readiness.ready is False
    assert readiness.code == "KS1963"


def test_strong_descriptor_is_readiness_only_and_succeeds_deterministically():
    request = capability_request()
    plan = build_sandbox_enforcement_plan(trusted_permit(request), request)
    descriptor = strong_adapter()

    first = evaluate_sandbox_readiness(plan, descriptor)
    second = evaluate_sandbox_readiness(plan, descriptor)

    assert first.ready is True
    assert first.code == "KS1960"
    assert first.to_dict() == second.to_dict()
    assert not hasattr(first, "execute")
    assert not hasattr(first, "spawn")


def test_tampered_descriptor_digest_is_rejected():
    request = capability_request()
    plan = build_sandbox_enforcement_plan(trusted_permit(request), request)
    descriptor = replace(strong_adapter(), descriptor_digest=digest("tampered"))

    readiness = evaluate_sandbox_readiness(plan, descriptor)

    assert readiness.ready is False
    assert readiness.code == "KS1961"


def test_tampered_plan_is_rejected():
    request = capability_request()
    plan = build_sandbox_enforcement_plan(trusted_permit(request), request)
    plan = replace(plan, denied_domains=("env",))

    readiness = evaluate_sandbox_readiness(plan, strong_adapter())

    assert readiness.ready is False
    assert readiness.code == "KS1961"
