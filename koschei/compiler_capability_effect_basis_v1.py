"""Compiler-derived exact capability-effect basis v1.

A privileged runtime request must not invent its capability type, method, or
effect label after compilation. The exact authority fact is now derived only
from normalized sealed MIR capability call-site evidence.

V1 is intentionally strict: the selected function must be a leaf with exactly
one direct canonical capability call-site and exactly one canonical capability
effect in MIR. Local/imported call indirection and multiple capability call-sites
fail closed rather than being guessed.

The basis is non-authoritative. It cannot ALLOW execution; it only binds runtime
admission to a capability fact already present in checked compiler output.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib

from .capability_effect_contract_v1 import require_capability_method_same_power_domain
from .mir import MirGraph
from .mir_capability_callsite_v1 import derive_mir_capability_callsites_v1

_CTX = b"koschei.compiler-capability-effect-basis/v1\x00"


class CompilerCapabilityEffectBasisV1Error(ValueError):
    pass


def _text(value: str, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise CompilerCapabilityEffectBasisV1Error(f"{label} cannot be empty")
    return value.strip()


def _hex_digest(value: str, label: str) -> str:
    text = _text(value, label)
    if len(text) != 64:
        raise CompilerCapabilityEffectBasisV1Error(f"{label} must be sha256 hex")
    try:
        bytes.fromhex(text)
    except ValueError as error:
        raise CompilerCapabilityEffectBasisV1Error(
            f"{label} must be hexadecimal"
        ) from error
    return text


def _digest(
    *,
    mir_fingerprint: str,
    module_name: str,
    function_name: str,
    capability_type: str,
    capability_method: str,
    canonical_effect: str,
    power_domain: str,
    source_line: int,
    source_column: int,
    mir_callsite_digest: str,
) -> str:
    rows = (
        f"mir={mir_fingerprint}",
        f"module={module_name}",
        f"function={function_name}",
        f"capability-type={capability_type}",
        f"capability-method={capability_method}",
        f"canonical-effect={canonical_effect}",
        f"power-domain={power_domain}",
        f"location={source_line}:{source_column}",
        f"mir-callsite={mir_callsite_digest}",
        "direct-call=1",
        "normalized-mir=1",
        "authority=0",
        "version=1",
    )
    return hashlib.sha256(_CTX + "\n".join(rows).encode("utf-8")).hexdigest()


@dataclass(frozen=True, slots=True)
class CompilerCapabilityEffectBasisV1:
    """One exact capability call proven by normalized sealed compiler MIR."""

    mir_fingerprint: str
    module_name: str
    function_name: str
    capability_type: str
    capability_method: str
    canonical_effect: str
    power_domain: str
    source_line: int
    source_column: int
    mir_callsite_digest: str
    digest: str
    direct_call: bool = True
    normalized_mir: bool = True
    authority: bool = False
    version: int = 1

    def assert_sealed(self) -> None:
        if (
            self.version != 1
            or self.direct_call is not True
            or self.normalized_mir is not True
            or self.authority is not False
        ):
            raise CompilerCapabilityEffectBasisV1Error(
                "compiler capability-effect basis flags are invalid"
            )
        mir_fingerprint = _hex_digest(self.mir_fingerprint, "mir_fingerprint")
        module_name = _text(self.module_name, "module_name")
        function_name = _text(self.function_name, "function_name")
        capability_type = _text(self.capability_type, "capability_type")
        capability_method = _text(self.capability_method, "capability_method")
        canonical_effect = _text(self.canonical_effect, "canonical_effect")
        power_domain = _text(self.power_domain, "power_domain")
        mir_callsite_digest = _hex_digest(
            self.mir_callsite_digest,
            "mir_callsite_digest",
        )
        if (
            not isinstance(self.source_line, int)
            or isinstance(self.source_line, bool)
            or self.source_line < 1
            or not isinstance(self.source_column, int)
            or isinstance(self.source_column, bool)
            or self.source_column < 1
        ):
            raise CompilerCapabilityEffectBasisV1Error(
                "compiler capability use source location is invalid"
            )
        expected_effect, expected_domain = require_capability_method_same_power_domain(
            capability_type,
            capability_method,
        )
        if canonical_effect != expected_effect:
            raise CompilerCapabilityEffectBasisV1Error(
                "compiler basis canonical effect differs from capability contract"
            )
        if power_domain != expected_domain:
            raise CompilerCapabilityEffectBasisV1Error(
                "compiler basis power domain differs from capability contract"
            )
        expected = _digest(
            mir_fingerprint=mir_fingerprint,
            module_name=module_name,
            function_name=function_name,
            capability_type=capability_type,
            capability_method=capability_method,
            canonical_effect=canonical_effect,
            power_domain=power_domain,
            source_line=self.source_line,
            source_column=self.source_column,
            mir_callsite_digest=mir_callsite_digest,
        )
        if self.digest != expected:
            raise CompilerCapabilityEffectBasisV1Error(
                "compiler capability-effect basis seal mismatch"
            )

    def assert_matches_mir(self, mir: MirGraph) -> None:
        """Re-derive this basis from normalized sealed MIR and require exact equality."""

        if not isinstance(mir, MirGraph):
            raise CompilerCapabilityEffectBasisV1Error("sealed MirGraph required")
        derived = derive_compiler_capability_effect_basis_v1(
            mir,
            module_name=self.module_name,
            function_name=self.function_name,
        )
        if derived != self:
            raise CompilerCapabilityEffectBasisV1Error(
                "compiler capability-effect basis differs from sealed MIR"
            )


def derive_compiler_capability_effect_basis_v1(
    mir: MirGraph,
    *,
    module_name: str,
    function_name: str,
) -> CompilerCapabilityEffectBasisV1:
    """Derive one exact direct capability use from normalized sealed MIR.

    This function does not inspect `FunctionDeclaration.body`, source AST, or the
    Typed-HIR expression list. Call-site identity comes from the normalized MIR
    value graph and the canonical capability/effect contract.
    """

    if not isinstance(mir, MirGraph):
        raise CompilerCapabilityEffectBasisV1Error("sealed MirGraph required")
    mir.assert_sealed()
    selected_module_name = _text(module_name, "module_name")
    selected_function_name = _text(function_name, "function_name")

    modules = [
        module for module in mir.modules.values() if module.name == selected_module_name
    ]
    if len(modules) != 1:
        raise CompilerCapabilityEffectBasisV1Error(
            "compiler capability basis requires one unambiguous module name"
        )
    module = modules[0]
    functions = [
        function
        for function in module.functions
        if function.name == selected_function_name
    ]
    if len(functions) != 1:
        raise CompilerCapabilityEffectBasisV1Error(
            "compiler capability basis requires one unambiguous function"
        )
    function = functions[0]

    if function.calls:
        raise CompilerCapabilityEffectBasisV1Error(
            "compiler capability basis v1 requires a leaf function without local calls"
        )

    sites = derive_mir_capability_callsites_v1(
        mir,
        module_name=module.name,
        function_name=function.name,
    )
    if len(sites) != 1:
        raise CompilerCapabilityEffectBasisV1Error(
            "compiler capability basis v1 requires exactly one normalized MIR capability call"
        )
    site = sites[0]
    site.assert_sealed()
    if function.effects != (site.canonical_effect,):
        raise CompilerCapabilityEffectBasisV1Error(
            "sealed MIR effect set is not the exact normalized capability call effect"
        )

    result = CompilerCapabilityEffectBasisV1(
        mir_fingerprint=mir.fingerprint,
        module_name=module.name,
        function_name=function.name,
        capability_type=site.capability_type,
        capability_method=site.capability_method,
        canonical_effect=site.canonical_effect,
        power_domain=site.power_domain,
        source_line=site.source_line,
        source_column=site.source_column,
        mir_callsite_digest=site.digest,
        digest="",
    )
    object.__setattr__(
        result,
        "digest",
        _digest(
            mir_fingerprint=result.mir_fingerprint,
            module_name=result.module_name,
            function_name=result.function_name,
            capability_type=result.capability_type,
            capability_method=result.capability_method,
            canonical_effect=result.canonical_effect,
            power_domain=result.power_domain,
            source_line=result.source_line,
            source_column=result.source_column,
            mir_callsite_digest=result.mir_callsite_digest,
        ),
    )
    result.assert_sealed()
    return result
