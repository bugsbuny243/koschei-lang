"""Normalized MIR capability call-site facts v1.

Privileged capability provenance must not be reconstructed by walking source AST
once the compiler has already produced sealed MIR. This module derives exact
canonical capability call-sites only from normalized MIR value/instruction
relations (`MirLoad`/producer -> `MirMember` -> `MirCall`).

The derived fact is non-authoritative. It is deterministically bound to the
sealed MirGraph fingerprint and can only be used as evidence for later
request/domain binding. Unknown, imported, local-function and non-capability
calls simply do not become capability call-site facts.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib

from .capability_effect_contract_v1 import (
    effect_for,
    require_capability_method_same_power_domain,
)
from .mir import MirGraph, MirIntegrityError
from .mir_ir import MirCall, MirMember
from .type_system import NamedType

_CTX = b"koschei.mir-capability-callsite/v1\x00"


class MirCapabilityCallSiteV1Error(ValueError):
    pass


def _text(value: str, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise MirCapabilityCallSiteV1Error(f"{label} cannot be empty")
    return value.strip()


def _digest(
    *,
    mir_fingerprint: str,
    module_name: str,
    function_name: str,
    block_id: int,
    call_target: int,
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
        f"block={block_id}",
        f"call-target={call_target}",
        f"capability-type={capability_type}",
        f"capability-method={capability_method}",
        f"canonical-effect={canonical_effect}",
        f"power-domain={power_domain}",
        f"location={source_line}:{source_column}",
        "normalized-mir=1",
        "authority=0",
        "version=1",
    )
    return hashlib.sha256(_CTX + "\n".join(rows).encode("utf-8")).hexdigest()


@dataclass(frozen=True, slots=True)
class MirCapabilityCallSiteV1:
    """One exact canonical capability call proven from normalized sealed MIR."""

    mir_fingerprint: str
    module_name: str
    function_name: str
    block_id: int
    call_target: int
    capability_type: str
    capability_method: str
    canonical_effect: str
    power_domain: str
    source_line: int
    source_column: int
    digest: str
    normalized_mir: bool = True
    authority: bool = False
    version: int = 1

    def assert_sealed(self) -> None:
        if (
            self.version != 1
            or self.normalized_mir is not True
            or self.authority is not False
        ):
            raise MirCapabilityCallSiteV1Error(
                "MIR capability call-site flags are invalid"
            )
        if not isinstance(self.block_id, int) or isinstance(self.block_id, bool) or self.block_id < 0:
            raise MirCapabilityCallSiteV1Error("MIR capability block id is invalid")
        if not isinstance(self.call_target, int) or isinstance(self.call_target, bool) or self.call_target < 0:
            raise MirCapabilityCallSiteV1Error("MIR capability call target is invalid")
        if (
            not isinstance(self.source_line, int)
            or isinstance(self.source_line, bool)
            or self.source_line < 1
            or not isinstance(self.source_column, int)
            or isinstance(self.source_column, bool)
            or self.source_column < 1
        ):
            raise MirCapabilityCallSiteV1Error(
                "MIR capability call-site source location is invalid"
            )

        capability_type = _text(self.capability_type, "capability_type")
        capability_method = _text(self.capability_method, "capability_method")
        canonical_effect = _text(self.canonical_effect, "canonical_effect")
        power_domain = _text(self.power_domain, "power_domain")
        expected_effect, expected_domain = require_capability_method_same_power_domain(
            capability_type,
            capability_method,
        )
        if canonical_effect != expected_effect:
            raise MirCapabilityCallSiteV1Error(
                "MIR capability call-site effect differs from canonical contract"
            )
        if power_domain != expected_domain:
            raise MirCapabilityCallSiteV1Error(
                "MIR capability call-site domain differs from canonical contract"
            )

        expected = _digest(
            mir_fingerprint=_text(self.mir_fingerprint, "mir_fingerprint"),
            module_name=_text(self.module_name, "module_name"),
            function_name=_text(self.function_name, "function_name"),
            block_id=self.block_id,
            call_target=self.call_target,
            capability_type=capability_type,
            capability_method=capability_method,
            canonical_effect=canonical_effect,
            power_domain=power_domain,
            source_line=self.source_line,
            source_column=self.source_column,
        )
        if self.digest != expected:
            raise MirCapabilityCallSiteV1Error(
                "MIR capability call-site seal mismatch"
            )

    def assert_matches_mir(self, mir: MirGraph) -> None:
        sites = derive_mir_capability_callsites_v1(
            mir,
            module_name=self.module_name,
            function_name=self.function_name,
        )
        if self not in sites:
            raise MirCapabilityCallSiteV1Error(
                "MIR capability call-site does not exist in sealed normalized MIR"
            )


def _select_function(
    mir: MirGraph,
    *,
    module_name: str,
    function_name: str,
):
    if not isinstance(mir, MirGraph):
        raise MirCapabilityCallSiteV1Error("sealed MirGraph required")
    try:
        mir.assert_sealed()
    except MirIntegrityError as error:
        raise MirCapabilityCallSiteV1Error("sealed MirGraph required") from error

    selected_module_name = _text(module_name, "module_name")
    selected_function_name = _text(function_name, "function_name")
    modules = [
        module for module in mir.modules.values() if module.name == selected_module_name
    ]
    if len(modules) != 1:
        raise MirCapabilityCallSiteV1Error(
            "MIR capability call-sites require one unambiguous module name"
        )
    module = modules[0]
    functions = [
        function for function in module.functions if function.name == selected_function_name
    ]
    if len(functions) != 1:
        raise MirCapabilityCallSiteV1Error(
            "MIR capability call-sites require one unambiguous function"
        )
    return module, functions[0]


def derive_mir_capability_callsites_v1(
    mir: MirGraph,
    *,
    module_name: str,
    function_name: str,
) -> tuple[MirCapabilityCallSiteV1, ...]:
    """Derive direct canonical capability calls only from normalized MIR values."""

    module, function = _select_function(
        mir,
        module_name=module_name,
        function_name=function_name,
    )

    definitions: dict[int, object] = {}
    instruction_blocks: dict[int, int] = {}
    calls: list[MirCall] = []
    for block in function.blocks:
        for instruction in block.instructions:
            target = getattr(instruction, "target", None)
            if isinstance(target, int):
                definitions[target] = instruction
                instruction_blocks[target] = block.id
            if isinstance(instruction, MirCall):
                calls.append(instruction)

    result: list[MirCapabilityCallSiteV1] = []
    for call in calls:
        callee = definitions.get(call.callee)
        if not isinstance(callee, MirMember):
            continue
        receiver = definitions.get(callee.object)
        receiver_type = getattr(receiver, "type", None)
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
        if canonical_effect != expected_effect:
            raise MirCapabilityCallSiteV1Error(
                "normalized MIR capability call disagrees with canonical effect contract"
            )
        site = MirCapabilityCallSiteV1(
            mir_fingerprint=mir.fingerprint,
            module_name=module.name,
            function_name=function.name,
            block_id=instruction_blocks[call.target],
            call_target=call.target,
            capability_type=capability_type,
            capability_method=callee.member,
            canonical_effect=canonical_effect,
            power_domain=power_domain,
            source_line=call.location.line,
            source_column=call.location.column,
            digest="",
        )
        object.__setattr__(
            site,
            "digest",
            _digest(
                mir_fingerprint=site.mir_fingerprint,
                module_name=site.module_name,
                function_name=site.function_name,
                block_id=site.block_id,
                call_target=site.call_target,
                capability_type=site.capability_type,
                capability_method=site.capability_method,
                canonical_effect=site.canonical_effect,
                power_domain=site.power_domain,
                source_line=site.source_line,
                source_column=site.source_column,
            ),
        )
        site.assert_sealed()
        result.append(site)

    return tuple(result)
