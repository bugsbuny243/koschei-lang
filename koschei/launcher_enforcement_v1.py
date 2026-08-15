"""Koschei launcher enforcement contract v1.

This module does not spawn a process and therefore does not claim OS sandboxing.
It binds a trusted launch permit to exact compiler capability evidence and checks
whether a concrete future platform adapter can enforce that plan fail-closed.

Every dataclass crossing this boundary is independently revalidated from its
contents. Object construction is never treated as authority.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from typing import Iterable

from .trust_plane_v1 import StaticCapabilityRequest
from .trusted_launcher_v1 import TrustedLaunchPermit

_PLAN_SCHEMA = "koschei.sandbox-enforcement-plan.v1"
_ADAPTER_SCHEMA = "koschei.sandbox-adapter-descriptor.v1"
_READINESS_SCHEMA = "koschei.sandbox-readiness.v1"
_PERMIT_SCHEMA = "koschei.trusted-launch-permit.v1"
_CAPABILITY_SCHEMA = "koschei.static-capability-request.v1"
_DOMAINS = frozenset({"disk", "net", "env", "process"})


class LauncherEnforcementError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class SandboxEnforcementPlan:
    artifact_sha256: str
    trust_manifest_digest: str
    policy_hash: str
    capability_request_digest: str
    launch_permit_digest: str
    authorization_redemption_digest: str
    effective_capabilities: tuple[str, ...]
    grants: tuple[tuple[str, str, bool], ...]
    denied_domains: tuple[str, ...]
    environment_inheritance: str
    inherited_file_descriptors: str
    shell_execution: str
    executable_identity: str
    plan_digest: str

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": _PLAN_SCHEMA,
            "artifact_sha256": self.artifact_sha256,
            "trust_manifest_digest": self.trust_manifest_digest,
            "policy_hash": self.policy_hash,
            "capability_request_digest": self.capability_request_digest,
            "launch_permit_digest": self.launch_permit_digest,
            "authorization_redemption_digest": self.authorization_redemption_digest,
            "effective_capabilities": list(self.effective_capabilities),
            "grants": _grant_rows(self.grants),
            "denied_domains": list(self.denied_domains),
            "environment_inheritance": self.environment_inheritance,
            "inherited_file_descriptors": self.inherited_file_descriptors,
            "shell_execution": self.shell_execution,
            "executable_identity": self.executable_identity,
            "plan_digest": self.plan_digest,
        }


@dataclass(frozen=True, slots=True)
class SandboxAdapterDescriptor:
    adapter_id: str
    adapter_version: str
    platform: str
    config_digest: str
    supported_domains: tuple[str, ...]
    exact_scope_enforcement: bool
    default_deny_unrequested_domains: bool
    empty_environment_by_default: bool
    close_inherited_file_descriptors: bool
    shell_disabled: bool
    executable_digest_verified_at_spawn: bool
    descriptor_digest: str

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": _ADAPTER_SCHEMA,
            "adapter_id": self.adapter_id,
            "adapter_version": self.adapter_version,
            "platform": self.platform,
            "config_digest": self.config_digest,
            "supported_domains": list(self.supported_domains),
            "exact_scope_enforcement": self.exact_scope_enforcement,
            "default_deny_unrequested_domains": self.default_deny_unrequested_domains,
            "empty_environment_by_default": self.empty_environment_by_default,
            "close_inherited_file_descriptors": self.close_inherited_file_descriptors,
            "shell_disabled": self.shell_disabled,
            "executable_digest_verified_at_spawn": self.executable_digest_verified_at_spawn,
            "descriptor_digest": self.descriptor_digest,
        }


@dataclass(frozen=True, slots=True)
class SandboxReadiness:
    ready: bool
    code: str
    reason: str
    plan_digest: str
    adapter_descriptor_digest: str
    readiness_digest: str

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": _READINESS_SCHEMA,
            "ready": self.ready,
            "code": self.code,
            "reason": self.reason,
            "plan_digest": self.plan_digest,
            "adapter_descriptor_digest": self.adapter_descriptor_digest,
            "readiness_digest": self.readiness_digest,
        }


def build_sandbox_enforcement_plan(
    permit: TrustedLaunchPermit,
    capability_request: StaticCapabilityRequest,
) -> SandboxEnforcementPlan:
    _validate_launch_permit_identity(permit)
    grants, derived_capabilities = _validate_static_capability_request(capability_request)
    if permit.capability_request_digest != capability_request.request_digest:
        raise LauncherEnforcementError(
            "launch permit is bound to different static capability evidence"
        )
    if permit.effective_capabilities != derived_capabilities:
        raise LauncherEnforcementError(
            "launch permit capabilities differ from static capability evidence"
        )

    requested_domains = {domain for domain, _scope, _read_only in grants}
    denied_domains = tuple(sorted(_DOMAINS - requested_domains))
    payload = {
        "schema_version": _PLAN_SCHEMA,
        "artifact_sha256": permit.artifact_sha256,
        "trust_manifest_digest": permit.trust_manifest_digest,
        "policy_hash": permit.policy_hash,
        "capability_request_digest": capability_request.request_digest,
        "launch_permit_digest": permit.permit_digest,
        "authorization_redemption_digest": permit.authorization_redemption_digest,
        "effective_capabilities": list(derived_capabilities),
        "grants": _grant_rows(grants),
        "denied_domains": list(denied_domains),
        "environment_inheritance": "deny_ambient_inheritance",
        "inherited_file_descriptors": "close_all_except_launcher_contract",
        "shell_execution": "disabled",
        "executable_identity": "verify_sha256_immediately_before_spawn",
    }
    return SandboxEnforcementPlan(
        artifact_sha256=permit.artifact_sha256,
        trust_manifest_digest=permit.trust_manifest_digest,
        policy_hash=permit.policy_hash,
        capability_request_digest=capability_request.request_digest,
        launch_permit_digest=permit.permit_digest,
        authorization_redemption_digest=permit.authorization_redemption_digest,
        effective_capabilities=derived_capabilities,
        grants=grants,
        denied_domains=denied_domains,
        environment_inheritance="deny_ambient_inheritance",
        inherited_file_descriptors="close_all_except_launcher_contract",
        shell_execution="disabled",
        executable_identity="verify_sha256_immediately_before_spawn",
        plan_digest=_digest(payload),
    )


def build_sandbox_adapter_descriptor(
    *,
    adapter_id: str,
    adapter_version: str,
    platform: str,
    config_digest: str,
    supported_domains: Iterable[str],
    exact_scope_enforcement: bool,
    default_deny_unrequested_domains: bool,
    empty_environment_by_default: bool,
    close_inherited_file_descriptors: bool,
    shell_disabled: bool,
    executable_digest_verified_at_spawn: bool,
) -> SandboxAdapterDescriptor:
    adapter_id = _text(adapter_id, "adapter_id")
    adapter_version = _text(adapter_version, "adapter_version")
    platform = _text(platform, "platform")
    config_digest = _require_digest(config_digest, "config_digest")
    domains = _canonical_domains(supported_domains)
    controls = {
        "exact_scope_enforcement": exact_scope_enforcement,
        "default_deny_unrequested_domains": default_deny_unrequested_domains,
        "empty_environment_by_default": empty_environment_by_default,
        "close_inherited_file_descriptors": close_inherited_file_descriptors,
        "shell_disabled": shell_disabled,
        "executable_digest_verified_at_spawn": executable_digest_verified_at_spawn,
    }
    if not all(isinstance(value, bool) for value in controls.values()):
        raise LauncherEnforcementError("sandbox security controls must be booleans")
    payload = {
        "schema_version": _ADAPTER_SCHEMA,
        "adapter_id": adapter_id,
        "adapter_version": adapter_version,
        "platform": platform,
        "config_digest": config_digest,
        "supported_domains": list(domains),
        **controls,
    }
    return SandboxAdapterDescriptor(
        adapter_id=adapter_id,
        adapter_version=adapter_version,
        platform=platform,
        config_digest=config_digest,
        supported_domains=domains,
        descriptor_digest=_digest(payload),
        **controls,
    )


def evaluate_sandbox_readiness(
    plan: SandboxEnforcementPlan,
    descriptor: SandboxAdapterDescriptor,
) -> SandboxReadiness:
    try:
        _validate_plan(plan)
        _validate_descriptor(descriptor)
    except LauncherEnforcementError as error:
        return _readiness(False, "KS1961", str(error), plan, descriptor)

    required_domains = {domain for domain, _scope, _read_only in plan.grants}
    missing = tuple(sorted(required_domains - set(descriptor.supported_domains)))
    if missing:
        return _readiness(
            False,
            "KS1962",
            "sandbox adapter cannot enforce requested domains: " + ", ".join(missing),
            plan,
            descriptor,
        )
    if not all(
        (
            descriptor.exact_scope_enforcement,
            descriptor.default_deny_unrequested_domains,
            descriptor.empty_environment_by_default,
            descriptor.close_inherited_file_descriptors,
            descriptor.shell_disabled,
            descriptor.executable_digest_verified_at_spawn,
        )
    ):
        return _readiness(
            False,
            "KS1963",
            "sandbox adapter does not enforce every mandatory launcher boundary",
            plan,
            descriptor,
        )
    return _readiness(
        True,
        "KS1960",
        "adapter descriptor satisfies exact-scope and mandatory default-deny boundaries",
        plan,
        descriptor,
    )


def _validate_launch_permit_identity(permit: TrustedLaunchPermit) -> None:
    if not isinstance(permit, TrustedLaunchPermit):
        raise LauncherEnforcementError("invalid trusted launch permit")
    capabilities = _canonical_launcher_capabilities(permit.effective_capabilities)
    payload = {
        "schema_version": _PERMIT_SCHEMA,
        "environment": _text(permit.environment, "environment"),
        "artifact_sha256": _require_digest(permit.artifact_sha256, "artifact_sha256"),
        "trust_manifest_digest": _require_digest(permit.trust_manifest_digest, "trust_manifest_digest"),
        "policy_hash": _require_digest(permit.policy_hash, "policy_hash"),
        "capability_request_digest": _require_digest(
            permit.capability_request_digest, "capability_request_digest"
        ),
        "effective_capabilities": list(capabilities),
        "launch_decision_digest": _require_digest(
            permit.launch_decision_digest, "launch_decision_digest"
        ),
        "deployment_authorization_digest": _require_digest(
            permit.deployment_authorization_digest, "deployment_authorization_digest"
        ),
        "authorization_redemption_digest": _require_digest(
            permit.authorization_redemption_digest, "authorization_redemption_digest"
        ),
        "authorization_id": _text(permit.authorization_id, "authorization_id"),
    }
    if permit.permit_digest != _digest(payload):
        raise LauncherEnforcementError("trusted launch permit digest does not match contents")


def _validate_static_capability_request(
    request: StaticCapabilityRequest,
) -> tuple[tuple[tuple[str, str, bool], ...], tuple[str, ...]]:
    if not isinstance(request, StaticCapabilityRequest):
        raise LauncherEnforcementError("invalid static capability request")
    grants = _canonical_grants(request.grants)
    if grants != request.grants:
        raise LauncherEnforcementError("static capability grants are not canonical")
    capabilities = _capabilities_from_grants(grants)
    if request.capabilities != capabilities:
        raise LauncherEnforcementError(
            "static capability list does not match exact narrowed grants"
        )
    payload = {
        "schema_version": _CAPABILITY_SCHEMA,
        "capabilities": list(capabilities),
        "grants": _grant_rows(grants),
    }
    if request.request_digest != _digest(payload):
        raise LauncherEnforcementError(
            "static capability request digest does not match contents"
        )
    return grants, capabilities


def _validate_plan(plan: SandboxEnforcementPlan) -> None:
    if not isinstance(plan, SandboxEnforcementPlan):
        raise LauncherEnforcementError("invalid sandbox enforcement plan")
    grants = _canonical_grants(plan.grants)
    capabilities = _capabilities_from_grants(grants)
    if plan.effective_capabilities != capabilities:
        raise LauncherEnforcementError("sandbox plan capabilities do not match grants")
    denied = tuple(sorted(_DOMAINS - {domain for domain, _scope, _ro in grants}))
    if denied != plan.denied_domains:
        raise LauncherEnforcementError("sandbox denied-domain set is not canonical")
    payload = {
        "schema_version": _PLAN_SCHEMA,
        "artifact_sha256": _require_digest(plan.artifact_sha256, "artifact_sha256"),
        "trust_manifest_digest": _require_digest(
            plan.trust_manifest_digest, "trust_manifest_digest"
        ),
        "policy_hash": _require_digest(plan.policy_hash, "policy_hash"),
        "capability_request_digest": _require_digest(
            plan.capability_request_digest, "capability_request_digest"
        ),
        "launch_permit_digest": _require_digest(
            plan.launch_permit_digest, "launch_permit_digest"
        ),
        "authorization_redemption_digest": _require_digest(
            plan.authorization_redemption_digest, "authorization_redemption_digest"
        ),
        "effective_capabilities": list(capabilities),
        "grants": _grant_rows(grants),
        "denied_domains": list(denied),
        "environment_inheritance": "deny_ambient_inheritance",
        "inherited_file_descriptors": "close_all_except_launcher_contract",
        "shell_execution": "disabled",
        "executable_identity": "verify_sha256_immediately_before_spawn",
    }
    if plan.environment_inheritance != payload["environment_inheritance"]:
        raise LauncherEnforcementError("ambient environment inheritance is not denied")
    if plan.inherited_file_descriptors != payload["inherited_file_descriptors"]:
        raise LauncherEnforcementError("inherited file descriptors are not closed")
    if plan.shell_execution != "disabled":
        raise LauncherEnforcementError("shell execution is not disabled")
    if plan.executable_identity != payload["executable_identity"]:
        raise LauncherEnforcementError(
            "executable identity is not verified at spawn boundary"
        )
    if plan.plan_digest != _digest(payload):
        raise LauncherEnforcementError("sandbox plan digest does not match contents")


def _validate_descriptor(descriptor: SandboxAdapterDescriptor) -> None:
    if not isinstance(descriptor, SandboxAdapterDescriptor):
        raise LauncherEnforcementError("invalid sandbox adapter descriptor")
    domains = _canonical_domains(descriptor.supported_domains)
    controls = (
        descriptor.exact_scope_enforcement,
        descriptor.default_deny_unrequested_domains,
        descriptor.empty_environment_by_default,
        descriptor.close_inherited_file_descriptors,
        descriptor.shell_disabled,
        descriptor.executable_digest_verified_at_spawn,
    )
    if not all(isinstance(value, bool) for value in controls):
        raise LauncherEnforcementError("sandbox security controls must be booleans")
    payload = {
        "schema_version": _ADAPTER_SCHEMA,
        "adapter_id": _text(descriptor.adapter_id, "adapter_id"),
        "adapter_version": _text(descriptor.adapter_version, "adapter_version"),
        "platform": _text(descriptor.platform, "platform"),
        "config_digest": _require_digest(descriptor.config_digest, "config_digest"),
        "supported_domains": list(domains),
        "exact_scope_enforcement": descriptor.exact_scope_enforcement,
        "default_deny_unrequested_domains": descriptor.default_deny_unrequested_domains,
        "empty_environment_by_default": descriptor.empty_environment_by_default,
        "close_inherited_file_descriptors": descriptor.close_inherited_file_descriptors,
        "shell_disabled": descriptor.shell_disabled,
        "executable_digest_verified_at_spawn": descriptor.executable_digest_verified_at_spawn,
    }
    if descriptor.descriptor_digest != _digest(payload):
        raise LauncherEnforcementError(
            "sandbox adapter descriptor digest does not match contents"
        )


def _readiness(
    ready: bool,
    code: str,
    reason: str,
    plan: SandboxEnforcementPlan,
    descriptor: SandboxAdapterDescriptor,
) -> SandboxReadiness:
    plan_digest = (
        plan.plan_digest if _is_digest(getattr(plan, "plan_digest", "")) else "0" * 64
    )
    descriptor_digest = (
        descriptor.descriptor_digest
        if _is_digest(getattr(descriptor, "descriptor_digest", ""))
        else "0" * 64
    )
    payload = {
        "schema_version": _READINESS_SCHEMA,
        "ready": ready,
        "code": code,
        "reason": reason,
        "plan_digest": plan_digest,
        "adapter_descriptor_digest": descriptor_digest,
    }
    return SandboxReadiness(
        ready=ready,
        code=code,
        reason=reason,
        plan_digest=plan_digest,
        adapter_descriptor_digest=descriptor_digest,
        readiness_digest=_digest(payload),
    )


def _capabilities_from_grants(
    grants: tuple[tuple[str, str, bool], ...],
) -> tuple[str, ...]:
    capabilities: set[str] = set()
    for domain, _scope, read_only in grants:
        if domain == "disk":
            capabilities.add("disk.read")
            if not read_only:
                capabilities.add("disk.write")
        elif domain == "net":
            capabilities.add("net.io")
        elif domain == "env":
            capabilities.add("env.read")
        elif domain == "process":
            capabilities.add("process.exec")
        else:
            raise LauncherEnforcementError(f"unsupported sandbox domain: {domain}")
    return tuple(sorted(capabilities))


def _canonical_launcher_capabilities(values: Iterable[str]) -> tuple[str, ...]:
    allowed = {"disk.read", "disk.write", "net.io", "env.read", "process.exec"}
    raw = tuple(values)
    if any(not isinstance(value, str) or value not in allowed for value in raw):
        raise LauncherEnforcementError("invalid launch permit capability")
    capabilities = tuple(sorted(set(raw)))
    if capabilities != raw:
        raise LauncherEnforcementError("launch permit capabilities are not canonical")
    return capabilities


def _canonical_grants(
    grants: Iterable[tuple[str, str, bool]],
) -> tuple[tuple[str, str, bool], ...]:
    normalized: set[tuple[str, str, bool]] = set()
    raw = tuple(grants)
    for grant in raw:
        if not isinstance(grant, tuple) or len(grant) != 3:
            raise LauncherEnforcementError("invalid static capability grant")
        domain, scope, read_only = grant
        domain = _text(domain, "domain")
        if domain not in _DOMAINS:
            raise LauncherEnforcementError(f"unsupported sandbox domain: {domain}")
        scope = _text(scope, "scope")
        if not isinstance(read_only, bool):
            raise LauncherEnforcementError("grant read_only must be boolean")
        normalized.add((domain, scope, read_only))
    canonical = tuple(sorted(normalized))
    if canonical != raw:
        raise LauncherEnforcementError("static capability grants are not canonical")
    return canonical


def _grant_rows(grants: tuple[tuple[str, str, bool], ...]) -> list[dict[str, object]]:
    return [
        {"domain": domain, "scope": scope, "read_only": read_only}
        for domain, scope, read_only in grants
    ]


def _canonical_domains(values: Iterable[str]) -> tuple[str, ...]:
    raw = tuple(values)
    if any(not isinstance(value, str) or not value.strip() for value in raw):
        raise LauncherEnforcementError("sandbox domain must be non-empty text")
    domains = tuple(sorted(set(value.strip() for value in raw)))
    if domains != raw:
        raise LauncherEnforcementError("sandbox domains are not canonical")
    unknown = set(domains) - _DOMAINS
    if unknown:
        raise LauncherEnforcementError(
            "unknown sandbox domains: " + ", ".join(sorted(unknown))
        )
    return domains


def _text(value: object, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise LauncherEnforcementError(f"{field} must be non-empty text")
    return value.strip()


def _require_digest(value: object, field: str) -> str:
    if not _is_digest(value):
        raise LauncherEnforcementError(f"{field} must be a SHA-256 digest")
    return str(value)


def _is_digest(value: object) -> bool:
    return (
        isinstance(value, str)
        and len(value) == 64
        and all(ch in "0123456789abcdef" for ch in value)
    )


def _digest(value: object) -> str:
    encoded = json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()
