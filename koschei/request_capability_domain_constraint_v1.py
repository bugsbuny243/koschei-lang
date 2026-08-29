"""Exact-request capability power-domain constraint v1.

This module extracts only the useful default-deny invariant from the experimental
six-domain prototype: authority present in one power domain does not silently
become authority in another.

It does NOT define grants, permits, delegation, or an ALLOW decision. Existing
Koschei capability semantics remain authoritative in
`capability_effect_contract_v1`; existing Khar/Galaxy execution remains the only
critical-effect admission path. This object can only prove that one exact
request is paired with one already-canonical capability method whose effect
stays inside that capability's own power domain. The request operation itself
must be the same canonical effect identity, preventing a parallel caller-chosen
operation taxonomy from relabeling privileged work after admission.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib

from .capability_effect_contract_v1 import (
    CapabilityPowerDomainError,
    require_capability_method_same_power_domain,
)
from .native_sigil_request_binding_v1 import CanonicalEffectRequest

_CTX = b"koschei.request-capability-domain-constraint/v1\x00"


class RequestCapabilityDomainConstraintV1Error(ValueError):
    pass


def _text(value: str, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise RequestCapabilityDomainConstraintV1Error(f"{label} cannot be empty")
    return value.strip()


def _digest(
    *,
    request_digest: str,
    capability_type: str,
    capability_method: str,
    canonical_effect: str,
    power_domain: str,
) -> str:
    rows = (
        f"request={request_digest}",
        f"capability-type={capability_type}",
        f"capability-method={capability_method}",
        f"canonical-effect={canonical_effect}",
        f"power-domain={power_domain}",
        "deny-only=1",
        "authority=0",
        "version=1",
    )
    return hashlib.sha256(_CTX + "\n".join(rows).encode("utf-8")).hexdigest()


@dataclass(frozen=True, slots=True)
class RequestCapabilityDomainConstraintV1:
    """Non-authoritative exact-request proof of same-domain capability use."""

    request_digest: str
    capability_type: str
    capability_method: str
    canonical_effect: str
    power_domain: str
    digest: str
    deny_only: bool = True
    authority: bool = False
    version: int = 1

    def assert_sealed(self, request: CanonicalEffectRequest) -> None:
        if not isinstance(request, CanonicalEffectRequest):
            raise RequestCapabilityDomainConstraintV1Error(
                "canonical effect request required"
            )
        if self.version != 1 or self.deny_only is not True or self.authority is not False:
            raise RequestCapabilityDomainConstraintV1Error(
                "request capability-domain constraint flags are invalid"
            )
        if self.request_digest != request.digest:
            raise RequestCapabilityDomainConstraintV1Error(
                "capability-domain constraint is bound to another canonical request"
            )

        capability_type = _text(self.capability_type, "capability_type")
        capability_method = _text(self.capability_method, "capability_method")
        try:
            expected_effect, expected_domain = require_capability_method_same_power_domain(
                capability_type,
                capability_method,
            )
        except CapabilityPowerDomainError as error:
            raise RequestCapabilityDomainConstraintV1Error(str(error)) from error

        if self.canonical_effect != expected_effect:
            raise RequestCapabilityDomainConstraintV1Error(
                "capability-domain constraint canonical effect mismatch"
            )
        if request.operation != expected_effect:
            raise RequestCapabilityDomainConstraintV1Error(
                "canonical request operation differs from capability effect identity"
            )
        if self.power_domain != expected_domain:
            raise RequestCapabilityDomainConstraintV1Error(
                "capability-domain constraint power domain mismatch"
            )

        expected_digest = _digest(
            request_digest=_text(self.request_digest, "request_digest"),
            capability_type=capability_type,
            capability_method=capability_method,
            canonical_effect=_text(self.canonical_effect, "canonical_effect"),
            power_domain=_text(self.power_domain, "power_domain"),
        )
        if self.digest != expected_digest:
            raise RequestCapabilityDomainConstraintV1Error(
                "request capability-domain constraint seal mismatch"
            )


def bind_request_capability_domain_v1(
    request: CanonicalEffectRequest,
    *,
    capability_type: str,
    capability_method: str,
) -> RequestCapabilityDomainConstraintV1:
    """Bind an exact request to one canonical same-domain capability operation.

    This function never grants permission. Unknown or cross-domain capability
    relationships are rejected before a constraint object exists, and the exact
    request must already name the canonical effect as its operation.
    """

    if not isinstance(request, CanonicalEffectRequest):
        raise RequestCapabilityDomainConstraintV1Error(
            "canonical effect request required"
        )
    capability_type_value = _text(capability_type, "capability_type")
    capability_method_value = _text(capability_method, "capability_method")
    try:
        canonical_effect, power_domain = require_capability_method_same_power_domain(
            capability_type_value,
            capability_method_value,
        )
    except CapabilityPowerDomainError as error:
        raise RequestCapabilityDomainConstraintV1Error(str(error)) from error
    if request.operation != canonical_effect:
        raise RequestCapabilityDomainConstraintV1Error(
            "canonical request operation differs from capability effect identity"
        )

    result = RequestCapabilityDomainConstraintV1(
        request_digest=_text(request.digest, "request_digest"),
        capability_type=capability_type_value,
        capability_method=capability_method_value,
        canonical_effect=canonical_effect,
        power_domain=power_domain,
        digest="",
    )
    object.__setattr__(
        result,
        "digest",
        _digest(
            request_digest=result.request_digest,
            capability_type=result.capability_type,
            capability_method=result.capability_method,
            canonical_effect=result.canonical_effect,
            power_domain=result.power_domain,
        ),
    )
    result.assert_sealed(request)
    return result
