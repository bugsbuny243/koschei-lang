"""Compiler-derived exact capability-effect basis v1.

A privileged runtime request must not invent its capability type, method, or
effect label after compilation. This module derives one exact capability use
from already sealed `MirGraph` + Typed-HIR evidence and the canonical capability
contract.

V1 is intentionally strict: the selected function must be a leaf with exactly
one direct canonical capability call and exactly one canonical capability effect
in MIR. Local/imported call indirection and multiple capability call-sites fail
closed until MIR has explicit call-site effect identities.

The basis is non-authoritative. It cannot ALLOW execution; it only binds runtime
admission to a capability fact already present in checked compiler output.
"""
from __future__ import annotations

from dataclasses import dataclass, fields, is_dataclass
import hashlib
from typing import Any

from .ast_nodes import CallExpression, Identifier, MemberExpression
from .capability_effect_contract_v1 import (
    effect_for,
    require_capability_method_same_power_domain,
)
from .mir import MirGraph
from .type_system import NamedType

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


def _walk(value: Any):
    if is_dataclass(value):
        yield value
        for field in fields(value):
            yield from _walk(getattr(value, field.name))
    elif isinstance(value, (tuple, list)):
        for item in value:
            yield from _walk(item)
    elif isinstance(value, dict):
        for item in value.values():
            yield from _walk(item)


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
        "direct-call=1",
        "authority=0",
        "version=1",
    )
    return hashlib.sha256(_CTX + "\n".join(rows).encode("utf-8")).hexdigest()


@dataclass(frozen=True, slots=True)
class CompilerCapabilityEffectBasisV1:
    """One exact direct capability call proven by sealed compiler output."""

    mir_fingerprint: str
    module_name: str
    function_name: str
    capability_type: str
    capability_method: str
    canonical_effect: str
    power_domain: str
    source_line: int
    source_column: int
    digest: str
    direct_call: bool = True
    authority: bool = False
    version: int = 1

    def assert_sealed(self) -> None:
        if self.version != 1 or self.direct_call is not True or self.authority is not False:
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
        )
        if self.digest != expected:
            raise CompilerCapabilityEffectBasisV1Error(
                "compiler capability-effect basis seal mismatch"
            )

    def assert_matches_mir(self, mir: MirGraph) -> None:
        """Re-derive this basis from sealed MIR and require exact equality."""

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
    """Derive one exact direct capability use from sealed compiler MIR.

    V1 rejects local/imported call indirection and multiple capability call-sites.
    That prevents the runtime bridge from guessing which authority operation a
    broad function-level effect summary was intended to authorize.
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

    imported_aliases = frozenset(module.imports)
    imported_calls: list[str] = []
    capability_uses: list[tuple[str, str, str, str, int, int]] = []
    for node in _walk(function.declaration.body):
        if not isinstance(node, CallExpression):
            continue
        callee = node.callee
        if isinstance(callee, MemberExpression):
            receiver = callee.object
            if isinstance(receiver, Identifier) and receiver.name in imported_aliases:
                imported_calls.append(f"{receiver.name}.{callee.member}")
                continue
            receiver_type = module.type_of(receiver)
            capability_type = (
                receiver_type.name if isinstance(receiver_type, NamedType) else ""
            )
            canonical_effect = effect_for(capability_type, callee.member)
            if canonical_effect is None:
                continue
            expected_effect, power_domain = require_capability_method_same_power_domain(
                capability_type,
                callee.member,
            )
            if expected_effect != canonical_effect:
                raise CompilerCapabilityEffectBasisV1Error(
                    "compiler capability use disagrees with canonical effect contract"
                )
            capability_uses.append(
                (
                    capability_type,
                    callee.member,
                    canonical_effect,
                    power_domain,
                    callee.location.line,
                    callee.location.column,
                )
            )

    if imported_calls:
        raise CompilerCapabilityEffectBasisV1Error(
            "compiler capability basis v1 requires a leaf function without imported calls"
        )
    if len(capability_uses) != 1:
        raise CompilerCapabilityEffectBasisV1Error(
            "compiler capability basis v1 requires exactly one direct capability call"
        )

    (
        capability_type,
        capability_method,
        canonical_effect,
        power_domain,
        source_line,
        source_column,
    ) = capability_uses[0]
    if function.effects != (canonical_effect,):
        raise CompilerCapabilityEffectBasisV1Error(
            "sealed MIR effect set is not the exact compiler capability basis effect"
        )

    result = CompilerCapabilityEffectBasisV1(
        mir_fingerprint=mir.fingerprint,
        module_name=module.name,
        function_name=function.name,
        capability_type=capability_type,
        capability_method=capability_method,
        canonical_effect=canonical_effect,
        power_domain=power_domain,
        source_line=source_line,
        source_column=source_column,
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
        ),
    )
    result.assert_sealed()
    return result
