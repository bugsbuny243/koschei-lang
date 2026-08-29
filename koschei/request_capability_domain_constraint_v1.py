"""Exact-request capability power-domain constraint v1.

The constraint is a deny-only bridge between one exact `CanonicalEffectRequest`
and one capability use already derived from sealed compiler MIR. Runtime callers
do not choose a capability type/method pair here; those facts come from
`CompilerCapabilityEffectBasisV1`.

This module defines no grant, permit, delegation, or ALLOW decision. Existing
Koschei capability semantics remain authoritative in
`capability_effect_contract_v1`; existing Khar/Galaxy execution remains the only
critical-effect admission path.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib

from .compiler_capability_effect_basis_v1 import CompilerCapabilityEffectBasisV1
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
    compiler_basis_digest: str,
    compiler_mir_fingerprint: str,
    capability_type: str,
    capability_method: str,
    canonical_effect: str,
    power_domain: str,
) -> str:
    rows = (
        f"request={request_digest}",
        f"compiler-basis={compiler_basis_digest}",
        f"compiler-mir={compiler_mir_fingerprint}",
        f"capability-type={capability_type}",
        f"capability-method={capability_method}",
        f"canonical-effect={canonical_effect}",
        f"power-domain={power_domain}",
        "compiler-bound=1",
        "deny-only=1",
        "authority=0",
        "version=1",
    )
    return hashlib.sha256(_CTX + "\n".join(rows).encode("utf-8")).hexdigest()


@dataclass(frozen=True, slots=True)
class RequestCapabilityDomainConstraintV1:
    """Non-authoritative exact-request constraint sourced from compiler MIR."""

    request_digest: str
    compiler_basis: CompilerCapabilityEffectBasisV1
    capability_type: str
    capability_method: str
    canonical_effect: str
    power_domain: str
    digest: str
    compiler_bound: bool = True
    deny_only: bool = True
    authority: bool = False
    version: int = 1

    def assert_sealed(self, request: CanonicalEffectRequest) -> None:
        if not isinstance(request, CanonicalEffectRequest):
            raise RequestCapabilityDomainConstraintV1Error(
                "canonical effect request required"
            )
        if (
            self.version != 1
            or self.compiler_bound is not True
            or self.deny_only is not True
            or self.authority is not False
        ):
            raise RequestCapabilityDomainConstraintV1Error(
                "request capability-domain constraint flags are invalid"
            )
        if not isinstance(self.compiler_basis, CompilerCapabilityEffectBasisV1):
            raise RequestCapabilityDomainConstraintV1Error(
                "compiler capability-effect basis v1 required"
            )
        self.compiler_basis.assert_sealed()
        if self.request_digest != request.digest:
            raise RequestCapabilityDomainConstraintV1Error(
                "capability-domain constraint is bound to another canonical request"
            )

        basis = self.compiler_basis
        if self.capability_type != basis.capability_type:
            raise RequestCapabilityDomainConstraintV1Error(
                "capability-domain constraint type differs from compiler basis"
            )
        if self.capability_method != basis.capability_method:
            raise RequestCapabilityDomainConstraintV1Error(
                "capability-domain constraint method differs from compiler basis"
            )
        if self.canonical_effect != basis.canonical_effect:
            raise RequestCapabilityDomainConstraintV1Error(
                "capability-domain constraint effect differs from compiler basis"
            )
        if self.power_domain != basis.power_domain:
            raise RequestCapabilityDomainConstraintV1Error(
                "capability-domain constraint domain differs from compiler basis"
            )
        if request.operation != basis.canonical_effect:
            raise RequestCapabilityDomainConstraintV1Error(
                "canonical request operation differs from compiler capability effect identity"
            )

        expected_digest = _digest(
            request_digest=_text(self.request_digest, "request_digest"),
            compiler_basis_digest=_text(basis.digest, "compiler_basis_digest"),
            compiler_mir_fingerprint=_text(
                basis.mir_fingerprint,
                "compiler_mir_fingerprint",
            ),
            capability_type=_text(self.capability_type, "capability_type"),
            capability_method=_text(self.capability_method, "capability_method"),
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
    compiler_basis: CompilerCapabilityEffectBasisV1,
) -> RequestCapabilityDomainConstraintV1:
    """Bind an exact request to one compiler-derived same-domain capability use.

    Runtime callers cannot select capability type/method here. V1 accepts only a
    sealed compiler basis previously derived from sealed `MirGraph` evidence.
    The resulting object can deny admission but cannot create authority or ALLOW.
    """

    if not isinstance(request, CanonicalEffectRequest):
        raise RequestCapabilityDomainConstraintV1Error(
            "canonical effect request required"
        )
    if not isinstance(compiler_basis, CompilerCapabilityEffectBasisV1):
        raise RequestCapabilityDomainConstraintV1Error(
            "compiler capability-effect basis v1 required"
        )
    compiler_basis.assert_sealed()
    if request.operation != compiler_basis.canonical_effect:
        raise RequestCapabilityDomainConstraintV1Error(
            "canonical request operation differs from compiler capability effect identity"
        )

    result = RequestCapabilityDomainConstraintV1(
        request_digest=_text(request.digest, "request_digest"),
        compiler_basis=compiler_basis,
        capability_type=compiler_basis.capability_type,
        capability_method=compiler_basis.capability_method,
        canonical_effect=compiler_basis.canonical_effect,
        power_domain=compiler_basis.power_domain,
        digest="",
    )
    object.__setattr__(
        result,
        "digest",
        _digest(
            request_digest=result.request_digest,
            compiler_basis_digest=compiler_basis.digest,
            compiler_mir_fingerprint=compiler_basis.mir_fingerprint,
            capability_type=result.capability_type,
            capability_method=result.capability_method,
            canonical_effect=result.canonical_effect,
            power_domain=result.power_domain,
        ),
    )
    result.assert_sealed(request)
    return result
