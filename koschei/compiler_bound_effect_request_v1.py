"""Compiler-bound privileged request issuance v1.

This is the sanctioned bootstrap bridge from checked compiler MIR to the native
exact-request execution world. The caller chooses the business request identity
and payload/identity/epoch/nonce evidence, but does not choose the privileged
operation label or capability type/method.

Those authority facts are derived from one exact direct capability call in
sealed compiler MIR and then bound into `CanonicalEffectRequest` plus the
deny-only request capability-domain constraint.
"""
from __future__ import annotations

from dataclasses import dataclass

from .compiler_capability_effect_basis_v1 import (
    CompilerCapabilityEffectBasisV1,
    derive_compiler_capability_effect_basis_v1,
)
from .mir import MirGraph
from .native_sigil_mir_v1 import NativeSigilMir
from .native_sigil_request_binding_v1 import CanonicalEffectRequest, seal_effect_request
from .request_capability_domain_constraint_v1 import (
    RequestCapabilityDomainConstraintV1,
    bind_request_capability_domain_v1,
)


class CompilerBoundEffectRequestV1Error(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class CompilerBoundEffectRequestV1:
    """One compiler-derived operation bound to one exact native request."""

    request: CanonicalEffectRequest
    compiler_basis: CompilerCapabilityEffectBasisV1
    domain_constraint: RequestCapabilityDomainConstraintV1
    authority: bool = False
    version: int = 1

    def assert_sealed(
        self,
        native_mir: NativeSigilMir,
        compiler_mir: MirGraph,
    ) -> None:
        if self.version != 1 or self.authority is not False:
            raise CompilerBoundEffectRequestV1Error(
                "compiler-bound request flags are invalid"
            )
        if not isinstance(native_mir, NativeSigilMir):
            raise CompilerBoundEffectRequestV1Error("NativeSigilMir required")
        if not isinstance(compiler_mir, MirGraph):
            raise CompilerBoundEffectRequestV1Error("sealed MirGraph required")
        self.request.assert_sealed(native_mir)
        self.compiler_basis.assert_matches_mir(compiler_mir)
        self.domain_constraint.assert_sealed(self.request)
        if self.domain_constraint.compiler_basis != self.compiler_basis:
            raise CompilerBoundEffectRequestV1Error(
                "request domain constraint differs from compiler basis"
            )
        if self.request.operation != self.compiler_basis.canonical_effect:
            raise CompilerBoundEffectRequestV1Error(
                "request operation differs from compiler-derived effect"
            )


def seal_compiler_bound_effect_request_v1(
    native_mir: NativeSigilMir,
    compiler_mir: MirGraph,
    *,
    module_name: str,
    function_name: str,
    effect_id: str,
    subject: str,
    request_digest: str,
    identity_digest: str,
    epoch: int,
    nonce_digest: str,
) -> CompilerBoundEffectRequestV1:
    """Issue an exact request whose privileged operation comes only from compiler MIR."""

    if not isinstance(native_mir, NativeSigilMir):
        raise CompilerBoundEffectRequestV1Error("NativeSigilMir required")
    if not isinstance(compiler_mir, MirGraph):
        raise CompilerBoundEffectRequestV1Error("sealed MirGraph required")
    native_mir.assert_sealed()
    compiler_mir.assert_sealed()

    basis = derive_compiler_capability_effect_basis_v1(
        compiler_mir,
        module_name=module_name,
        function_name=function_name,
    )
    request = seal_effect_request(
        native_mir,
        effect_id=effect_id,
        subject=subject,
        operation=basis.canonical_effect,
        request_digest=request_digest,
        identity_digest=identity_digest,
        epoch=epoch,
        nonce_digest=nonce_digest,
    )
    constraint = bind_request_capability_domain_v1(
        request,
        compiler_basis=basis,
    )
    result = CompilerBoundEffectRequestV1(
        request=request,
        compiler_basis=basis,
        domain_constraint=constraint,
    )
    result.assert_sealed(native_mir, compiler_mir)
    return result
