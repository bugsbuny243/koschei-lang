"""NON-AUTHORITATIVE Go conformance projection for sealed Koschei MIR v4.

Koschei semantics are owned by canonical checking, Typed HIR and sealed MIR.
This module materializes an already-sealed graph into Go without consulting the
AST. Each MIR instruction becomes a call into ``mir_go_runtime_v2``, whose
helpers mirror ``mir_executor_v1`` rule by rule, so the native binary computes
the same values as the canonical executor: runtime Error values (Int overflow,
division by zero, failed String/List operations) flow as values, runtime type
evidence is checked at every call boundary, and output uses the canonical
renderer. Anything outside the admitted subset fails closed before Go is
generated.

The projection is not metered: the interpreter's step budget is a ``ks run``
policy, not program semantics. The call-depth limit is enforced.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
import math
import re
from typing import Any

from .mir import MirFunction, MirGraph, MirModule
from .mir_extension_instructions_v4 import (
    MirCapabilityCall,
    MirFallibleIsSuccess,
    MirFalliblePayload,
    MirInterpolate,
    MirIsRuntimeError,
    MirStructFieldSet,
    MirStructFinish,
    MirStructNew,
    MirStructSet,
    MirUnit,
    MirVariantConstruct,
    MirVariantIs,
    MirVariantPayload,
)
from .mir_go_runtime_v2 import (
    MIR_GO_BYTES_RUNTIME_V2,
    MIR_GO_CLOCK_IMPORTS_V2,
    MIR_GO_CLOCK_RUNTIME_V2,
    MIR_GO_INPUT_IMPORTS_V2,
    MIR_GO_INPUT_RUNTIME_V2,
    MIR_GO_RANDOM_IMPORTS_V2,
    MIR_GO_RANDOM_RUNTIME_V2,
    MIR_GO_RUNTIME_V2,
    MIR_GO_RUNTIME_V2_IMPORTS,
    MIR_GO_SHA3_BYTES_RUNTIME_V2,
    MIR_GO_SHA3_IMPORTS_V2,
    MIR_GO_SHA3_RUNTIME_V2,
    MIR_GO_VALUE_BUDGET_RUNTIME_V2,
)
from .mir_ir import (
    MirAstFallback,
    MirBinary,
    MirBind,
    MirBranch,
    MirCall,
    MirConst,
    MirIterHasNext,
    MirIterInit,
    MirIterNext,
    MirJump,
    MirList,
    MirLoad,
    MirMember,
    MirReturn,
    MirStore,
    MirUnary,
    MirUnreachable,
)
from .native_broker_v1 import BROKER_IMPORTS, broker_runtime
from .native_net_v1 import NET_IMPORTS, net_runtime
from .native_serve_v1 import SERVE_IMPORTS, request_runtime, serve_runtime
from .mir_variant_runtime_v1 import MirVariantRuntimeError, split_canonical_variant_v1
from .secure_hash_v1 import NAME as SECURE_HASH_NAME, SHA3_256_MAX_INPUT_BYTES
from .semantic import INT_MAX, INT_MIN
from .type_contracts import declaration_type
from .type_system import GenericType, NamedType, TypeNode, alternatives, render_type
from .value_budget_v1 import (
    BYTES_MESSAGE,
    LIST_MESSAGE,
    MAX_LIST_ITEMS,
    MAX_STRING_BYTES,
    STRING_MESSAGE,
)

_BINARY = frozenset(
    {"+", "-", "*", "/", "%", "==", "!=", "<", "<=", ">", ">=", "&&", "||"}
)
_UNARY = frozenset({"!", "-"})
_BUILTINS = {
    "print": "_ksPrint",
    "println": "_ksPrintln",
    "Error": "_ksErrorValue",
    SECURE_HASH_NAME: "_ksSha3_256",
    "bytes_from_hex": "_ksBytesFromHex",
    "sha3_256_bytes": "_ksSha3_256Bytes",
}
_STRING_METHODS = frozenset({"length", "contains", "trim", "split", "join", "to_int", "to_bytes"})
_LIST_METHODS = frozenset({"length", "get", "push", "contains", "take"})
_BYTES_METHODS = frozenset({"length", "hex", "to_text", "slice", "get"})
_RESPONSE_METHODS = frozenset({"text", "status"})
_REQUEST_METHODS = frozenset({"method", "path", "header", "body", "body_bytes"})
_VALUE_METHODS = (
    _STRING_METHODS | _LIST_METHODS | _BYTES_METHODS | _RESPONSE_METHODS | _REQUEST_METHODS
)
_BUILTIN_VARIANTS = {
    "Option": {"Some": True, "None": False},
    "Result": {"Ok": True, "Err": True},
}
_CAPABILITY_TYPES = frozenset(
    {
        "SystemCaps",
        "NetRoot",
        "DiskRoot",
        "EnvRoot",
        "ProcessRoot",
        "NetCaps",
        "DiskCaps",
        "DiskReadCaps",
        "EnvCaps",
        "ProcessCaps",
        "PersistRoot",
        "PersistCaps",
        "ServeRoot",
        "ServeCaps",
        "InputRoot",
        "InputCaps",
        "ClockRoot",
        "ClockCaps",
        "RandomRoot",
        "RandomCaps",
        "Response",
    }
)
# Program input (argv, stdin), the clock and the operating system's random
# source reach no resource, so a native binary may carry them. Every other
# authority domain needs the native capability broker and stays fail-closed
# (KS4004).
_NATIVE_CAPABILITY_DOMAINS = {
    "SystemCaps": None,
    "InputRoot": "input",
    "InputCaps": "input",
    "ClockRoot": "clock",
    "ClockCaps": "clock",
    "RandomRoot": "random",
    "RandomCaps": "random",
    # Disk, the environment and the network go through the native
    # capability broker (native_broker_v1, native_net_v1).
    "NetRoot": "net",
    "NetCaps": "net",
    "Response": "net",
    "ServeRoot": "serve",
    "ServeCaps": "serve",
    "DiskRoot": "broker",
    "DiskReadCaps": "broker",
    "DiskCaps": "broker",
    "EnvRoot": "broker",
    "EnvCaps": "broker",
}
_NATIVE_CAPABILITY_TYPES = frozenset(_NATIVE_CAPABILITY_DOMAINS)
_NATIVE_CAPABILITY_MEMBERS = {
    ("InputRoot", "input"): "_ksCapsInput",
    ("ClockRoot", "clock"): "_ksCapsClock",
    ("RandomRoot", "random"): "_ksCapsRandom",
    ("DiskRoot", "disk"): "_ksCapsDisk",
    ("EnvRoot", "env"): "_ksCapsEnv",
    ("NetRoot", "net"): "_ksCapsNet",
    ("ServeRoot", "serve"): "_ksCapsServe",
}
_NATIVE_CAPABILITY_CALLS = {
    ("InputRoot", "allow"): ("_ksInputAllow", 1),
    ("InputCaps", "args"): ("_ksInputArgs", 0),
    ("InputCaps", "read_text"): ("_ksInputReadText", 0),
    ("InputCaps", "read_bytes"): ("_ksInputReadBytes", 0),
    ("ClockRoot", "allow"): ("_ksClockAllow", 1),
    ("ClockCaps", "now_ms"): ("_ksClockNow", 0),
    ("ClockCaps", "monotonic_ms"): ("_ksClockMonotonic", 0),
    ("RandomRoot", "allow"): ("_ksRandomAllow", 1),
    ("RandomCaps", "hex"): ("_ksRandomHex", 1),
    ("RandomCaps", "below"): ("_ksRandomBelow", 1),
    ("RandomCaps", "bytes"): ("_ksRandomBytes", 1),
    ("DiskRoot", "allow_read_only"): ("_ksDiskAllowReadOnly", 1),
    ("DiskReadCaps", "read"): ("_ksDiskReadText", 1),
    ("DiskReadCaps", "read_file"): ("_ksDiskReadText", 1),
    ("DiskReadCaps", "read_bytes"): ("_ksDiskReadBytes", 1),
    ("DiskReadCaps", "list"): ("_ksDiskList", 1),
    ("DiskRoot", "allow"): ("_ksDiskAllow", 1),
    ("DiskCaps", "read"): ("_ksDiskReadText", 1),
    ("DiskCaps", "read_file"): ("_ksDiskReadText", 1),
    ("DiskCaps", "read_bytes"): ("_ksDiskReadBytes", 1),
    ("DiskCaps", "list"): ("_ksDiskList", 1),
    ("DiskCaps", "write"): ("_ksDiskWrite", 2),
    ("DiskCaps", "write_file"): ("_ksDiskWrite", 2),
    ("DiskCaps", "delete"): ("_ksDiskDelete", 1),
    ("EnvRoot", "allow"): ("_ksEnvAllow", 1),
    ("EnvCaps", "get"): ("_ksEnvGet", 0),
    ("NetRoot", "allow"): ("_ksNetAllow", 1),
    ("NetCaps", "get"): ("_ksNetGet", 1),
    ("ServeRoot", "allow"): ("_ksServeAllow", 5),
    ("ServeCaps", "accept"): ("_ksServeAccept", 0),
    ("ServeCaps", "reply"): ("_ksServeReply", 2),
}
_ADMITTED_INSTRUCTIONS = (
    MirConst,
    MirLoad,
    MirBind,
    MirStore,
    MirUnary,
    MirBinary,
    MirCall,
    MirMember,
    MirList,
    MirIterInit,
    MirIterHasNext,
    MirIterNext,
    MirInterpolate,
    MirIsRuntimeError,
    MirFallibleIsSuccess,
    MirFalliblePayload,
    MirUnit,
    MirVariantConstruct,
    MirVariantIs,
    MirVariantPayload,
    MirStructNew,
    MirStructSet,
    MirStructFinish,
    MirStructFieldSet,
    MirCapabilityCall,
)
_GO_IDENTIFIER = re.compile(r"[^A-Za-z0-9_]")
_ENUM_GO_TYPE = "_ksEnumValue"


class MirGoUnsupported(ValueError):
    """Raised when a checked graph is not representable by MIR-Go."""


@dataclass(frozen=True, slots=True)
class MirGoSupport:
    supported: bool
    reasons: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class _Ref:
    """A statically resolved non-value slot: a call target or module alias."""

    kind: str  # "function", "builtin", "module" or "member"
    module_key: str = ""
    name: str = ""


@dataclass(frozen=True, slots=True)
class _FunctionPlan:
    module: MirModule
    function: MirFunction
    symbol: str
    refs: dict[int, _Ref]
    mutable: dict[str, bool]
    structs: dict[str, Any]


def inspect_mir_go_support(mir: MirGraph) -> MirGoSupport:
    """Report whether the sealed graph is representable by this host adapter."""

    reasons, _ = _plan(mir)
    return MirGoSupport(not reasons, tuple(dict.fromkeys(reasons)))


def generate_go_mir_native(mir: MirGraph) -> str:
    """Project sealed MIR into Go without acquiring semantic authority."""

    reasons, plans = _plan(mir)
    if reasons:
        raise MirGoUnsupported("; ".join(dict.fromkeys(reasons)))
    symbols = {
        (plan.module.key, plan.function.name): plan.symbol for plan in plans
    }
    root_main = symbols[(mir.root, "main")]
    builtins_used = {
        ref.name for plan in plans for ref in plan.refs.values() if ref.kind == "builtin"
    }
    uses_bytes_digest = "sha3_256_bytes" in builtins_used
    uses_digest = SECURE_HASH_NAME in builtins_used or uses_bytes_digest
    domains = _used_domains(plans)
    imports = sorted(
        {
            *MIR_GO_RUNTIME_V2_IMPORTS,
            *(MIR_GO_SHA3_IMPORTS_V2 if uses_digest else ()),
            *(MIR_GO_INPUT_IMPORTS_V2 if "input" in domains else ()),
            *(MIR_GO_CLOCK_IMPORTS_V2 if "clock" in domains else ()),
            *(MIR_GO_RANDOM_IMPORTS_V2 if "random" in domains else ()),
            *(BROKER_IMPORTS if "broker" in domains else ()),
            *(NET_IMPORTS if "net" in domains else ()),
            *(SERVE_IMPORTS if "serve" in domains else ()),
        }
    )

    lines = [
        "// Code generated from sealed Koschei MIR v4. DO NOT EDIT.",
        "// NON-AUTHORITATIVE host projection; sealed MIR owns semantics.",
        "package main",
        "",
        "import (",
        *(f'\t"{name}"' for name in imports),
        ")",
        MIR_GO_RUNTIME_V2,
        MIR_GO_VALUE_BUDGET_RUNTIME_V2.format(
            max_string_bytes=MAX_STRING_BYTES,
            max_list_items=MAX_LIST_ITEMS,
            string_message=_go_string(STRING_MESSAGE),
            list_message=_go_string(LIST_MESSAGE),
            bytes_message=_go_string(BYTES_MESSAGE),
        ),
        _bytes_runtime(),
        request_runtime(),
    ]
    if uses_digest:
        lines.append(MIR_GO_SHA3_RUNTIME_V2.format(max_bytes=SHA3_256_MAX_INPUT_BYTES))
    if uses_bytes_digest:
        from .bytes_v1 import SHA3_SIZE_MESSAGE, SHA3_TYPE_MESSAGE

        lines.append(
            MIR_GO_SHA3_BYTES_RUNTIME_V2.format(
                type_message=_go_string(SHA3_TYPE_MESSAGE),
                size_message=_go_string(SHA3_SIZE_MESSAGE),
            )
        )
    if "input" in domains:
        lines.append(_input_runtime())
    if "clock" in domains:
        lines.append(_clock_runtime())
    if "random" in domains:
        lines.append(_random_runtime())
    if "broker" in domains:
        lines.append(broker_runtime())
    if "net" in domains:
        lines.append(net_runtime())
    if "serve" in domains:
        lines.append(serve_runtime())
    for plan in plans:
        lines.extend(_emit_function(plan, symbols))
        lines.append("")
    main = next(item for item in mir.root_module.functions if item.name == "main")
    entry_arguments = "_ksSystemCaps{}" if main.parameters else ""
    # Like the canonical executor, an Error returned by main fails the run.
    if "broker" in domains:
        entry = [f"\t_ksBrokerEntry(func() {{ _ksFinish({root_main}({entry_arguments})) }})"]
    else:
        entry = [f"\t_ksFinish({root_main}({entry_arguments}))"]
    lines.extend(["func main() {", *entry, "}", ""])
    return "\n".join(lines)


def _bytes_runtime() -> str:
    from .bytes_v1 import GET_MESSAGE, HEX_MESSAGE, NOT_TEXT_MESSAGE, SLICE_MESSAGE

    slice_prefix, rest = SLICE_MESSAGE.split("{start}..{end}")
    slice_middle, slice_suffix = rest.split("{length}")
    get_prefix, rest = GET_MESSAGE.split("{index}")
    get_middle, get_suffix = rest.split("{length}")
    return MIR_GO_BYTES_RUNTIME_V2.format(
        not_text_message=_go_string(NOT_TEXT_MESSAGE),
        hex_message=_go_string(HEX_MESSAGE),
        slice_prefix=_go_string(slice_prefix),
        slice_middle=_go_string(slice_middle),
        slice_suffix=_go_string(slice_suffix),
        get_prefix=_go_string(get_prefix),
        get_middle=_go_string(get_middle),
        get_suffix=_go_string(get_suffix),
    )


def _used_domains(plans: list["_FunctionPlan"]) -> set[str]:
    """Authority domains a program touches; each one's runtime is emitted alone."""

    domains: set[str] = set()
    for plan in plans:
        for block in plan.function.blocks:
            for instruction in block.instructions:
                if isinstance(instruction, MirCapabilityCall):
                    produced = instruction.capability_type
                elif isinstance(instruction, MirMember):
                    produced = _capability_member_type(instruction)
                else:
                    continue
                domain = _NATIVE_CAPABILITY_DOMAINS.get(produced or "")
                if domain is not None:
                    domains.add(domain)
    if "net" in domains or "serve" in domains:
        domains.add("broker")
    return domains


def _clock_runtime() -> str:
    from .clock_random_v1 import (
        CLOCK_ALLOW_RANGE_MESSAGE,
        CLOCK_ALLOW_TYPE_MESSAGE,
        MAX_RESOLUTION_MS,
        MIN_RESOLUTION_MS,
    )

    return MIR_GO_CLOCK_RUNTIME_V2.format(
        min_resolution=MIN_RESOLUTION_MS,
        max_resolution=MAX_RESOLUTION_MS,
        type_message=_go_string(CLOCK_ALLOW_TYPE_MESSAGE),
        range_message=_go_string(CLOCK_ALLOW_RANGE_MESSAGE),
    )


def _random_runtime() -> str:
    from .clock_random_v1 import (
        BELOW_BOUND_MESSAGE,
        BELOW_COST_BYTES,
        BYTES_COUNT_MESSAGE,
        HEX_COUNT_MESSAGE,
        MAX_HEX_BYTES,
        MAX_RANDOM_BYTES,
        MIN_RANDOM_BYTES,
        RANDOM_ALLOW_RANGE_MESSAGE,
        RANDOM_ALLOW_TYPE_MESSAGE,
        RANDOM_BUDGET_MESSAGE,
    )

    budget_prefix, budget_suffix = RANDOM_BUDGET_MESSAGE.split("{max_bytes}")
    return MIR_GO_RANDOM_RUNTIME_V2.format(
        min_bytes=MIN_RANDOM_BYTES,
        max_bytes=MAX_RANDOM_BYTES,
        max_hex=MAX_HEX_BYTES,
        below_cost=BELOW_COST_BYTES,
        type_message=_go_string(RANDOM_ALLOW_TYPE_MESSAGE),
        range_message=_go_string(RANDOM_ALLOW_RANGE_MESSAGE),
        hex_message=_go_string(HEX_COUNT_MESSAGE),
        bytes_message=_go_string(BYTES_COUNT_MESSAGE),
        below_message=_go_string(BELOW_BOUND_MESSAGE),
        budget_prefix=_go_string(budget_prefix),
        budget_suffix=_go_string(budget_suffix),
    )


def _input_runtime() -> str:
    from .program_input_v1 import (
        ALLOW_RANGE_MESSAGE,
        ALLOW_TYPE_MESSAGE,
        ARGUMENT_MESSAGE,
        BUDGET_MESSAGE,
        MAX_INPUT_BYTES,
        MIN_INPUT_BYTES,
        NOT_TEXT_MESSAGE,
        UNAVAILABLE_MESSAGE,
    )

    argument_prefix, argument_suffix = ARGUMENT_MESSAGE.split("{index}")
    budget_prefix, budget_suffix = BUDGET_MESSAGE.split("{max_bytes}")
    return MIR_GO_INPUT_RUNTIME_V2.format(
        min_bytes=MIN_INPUT_BYTES,
        max_bytes=MAX_INPUT_BYTES,
        type_message=_go_string(ALLOW_TYPE_MESSAGE),
        range_message=_go_string(ALLOW_RANGE_MESSAGE),
        argument_prefix=_go_string(argument_prefix),
        argument_suffix=_go_string(argument_suffix),
        budget_prefix=_go_string(budget_prefix),
        budget_suffix=_go_string(budget_suffix),
        unavailable_message=_go_string(UNAVAILABLE_MESSAGE),
        not_text_message=_go_string(NOT_TEXT_MESSAGE),
    )


def emit_go_from_mir(mir: MirGraph) -> str:
    """Compatibility name for the same non-authoritative sealed projection."""

    return generate_go_mir_native(mir)


# ---- admission and static resolution ---------------------------------------


def _plan(mir: MirGraph) -> tuple[list[str], list[_FunctionPlan]]:
    mir.assert_sealed()
    reasons: list[str] = []
    modules = mir.in_dependency_order()
    enums = {
        declaration.name: declaration
        for module in modules
        for declaration in module.program.enums
    }
    constructors = {"Some", "None", "Ok", "Err"} | {
        variant.name for declaration in enums.values() for variant in declaration.variants
    }

    # Struct names are unique across a graph (KS1604), so one table serves
    # every module.
    structs = {
        declaration.name: declaration
        for module in modules
        for declaration in module.program.structs
    }
    for module in modules:
        for declaration in module.program.structs:
            reasons.extend(_struct_declaration_reasons(module, declaration))

    root = mir.root_module
    main = next((item for item in root.functions if item.name == "main"), None)
    if main is None:
        reasons.append("MIR-Go requires main")
    elif main.parameters and not _main_takes_system_caps(main):
        reasons.append("MIR-Go requires main() or main(caps: SystemCaps)")

    plans: list[_FunctionPlan] = []
    for module_index, module in enumerate(modules):
        for function_index, function in enumerate(module.functions):
            label = f"{module.name}.{function.name}"
            refs, mutable, function_reasons = _resolve_function(
                mir, module, function, enums, structs, constructors, label
            )
            reasons.extend(function_reasons)
            plans.append(
                _FunctionPlan(
                    module=module,
                    function=function,
                    symbol=(
                        f"_ks_fn_{module_index}_{function_index}_"
                        f"{_safe_identifier(function.name)}"
                    ),
                    refs=refs,
                    mutable=mutable,
                    structs=structs,
                )
            )
    return reasons, plans


def _main_takes_system_caps(main: MirFunction) -> bool:
    return len(main.parameters) == 1 and _runtime_names(main.parameters[0].type) == (
        "SystemCaps",
    )


def _capability_member_type(instruction: MirMember) -> str | None:
    """The authority type a member read produces, if it produces one.

    Struct fields are never capability-typed in admitted programs (see
    ``_struct_declaration_reasons``), so such a read is a ``SystemCaps`` root.
    """

    names = _runtime_names(instruction.type)
    if len(names) == 1 and names[0] in _CAPABILITY_TYPES:
        return names[0]
    return None


def _struct_declaration_reasons(module: MirModule, declaration: Any) -> list[str]:
    label = f"{module.name}.{declaration.name}"
    if tuple(getattr(declaration, "type_parameters", ()) or ()):
        return [f"{label}: MIR-Go does not compile generic structs yet"]
    reasons: list[str] = []
    for field in declaration.fields:
        rendered = render_type(declaration_type(declaration, field.type_ref))
        names = set(re.findall(r"[A-Za-z_][A-Za-z0-9_]*", rendered))
        blocked = sorted(names & _CAPABILITY_TYPES)
        if blocked:
            reasons.append(
                f"{label}.{field.name}: capability-typed struct fields are not "
                f"MIR-Go ({', '.join(blocked)})"
            )
    return reasons


def _struct_field_names(declaration: Any, field_name: str) -> tuple[str, ...]:
    """Runtime type names a struct field value is checked against.

    Struct literals (``StructBuilderV1.set_field``) and field assignments
    (``struct_field_set_v1``) both check the declared field type; generic
    structs are not admitted, so no type argument is substituted.
    """

    field = next(item for item in declaration.fields if item.name == field_name)
    return _runtime_names(declaration_type(declaration, field.type_ref))


def _struct_instance(declaration: Any, type_node: TypeNode) -> bool:
    """Whether a MIR type identifies exactly one instance of ``declaration``."""

    candidates = [
        option
        for option in alternatives(type_node)
        if isinstance(option, (NamedType, GenericType)) and option.name == declaration.name
    ]
    return len(candidates) == 1 and isinstance(candidates[0], NamedType)


def _signature_reasons(function: MirFunction, label: str) -> list[str]:
    reasons: list[str] = []
    types = [function.return_type, *(parameter.type for parameter in function.parameters)]
    for type_node in types:
        rendered = render_type(type_node)
        names = set(re.findall(r"[A-Za-z_][A-Za-z0-9_]*", rendered))
        blocked = sorted(names & (_CAPABILITY_TYPES - _NATIVE_CAPABILITY_TYPES))
        if blocked:
            reasons.append(
                f"{label}: capability-typed signatures are not MIR-Go "
                f"({', '.join(blocked)})"
            )
    return reasons


def _resolve_function(
    mir: MirGraph,
    module: MirModule,
    function: MirFunction,
    enums: dict[str, Any],
    structs: dict[str, Any],
    constructors: set[str],
    label: str,
) -> tuple[dict[int, _Ref], dict[str, bool], list[str]]:
    reasons = _signature_reasons(function, label)
    parameters = {parameter.name for parameter in function.parameters}
    mutable: dict[str, bool] = {}
    for block in function.blocks:
        for instruction in block.instructions:
            if isinstance(instruction, MirBind):
                previous = mutable.get(instruction.name)
                if previous is not None and previous != instruction.is_mutable:
                    reasons.append(
                        f"{label}: binding {instruction.name!r} changes mutability"
                    )
                mutable[instruction.name] = instruction.is_mutable
    bindings = parameters | set(mutable)
    functions = {item.name for item in module.functions}
    # A member that is called is a String/List method; one that is only read
    # is a struct field (Koschei has no function-typed fields).
    callees = {
        instruction.callee
        for block in function.blocks
        for instruction in block.instructions
        if isinstance(instruction, MirCall)
    }
    struct_fields = {
        field.name for declaration in structs.values() for field in declaration.fields
    }

    refs: dict[int, _Ref] = {}
    for block in function.blocks:
        for instruction in block.instructions:
            if isinstance(instruction, MirAstFallback):
                reasons.append(
                    f"{label}: AST fallback remains for {instruction.node_kind}"
                )
                continue
            if not isinstance(instruction, _ADMITTED_INSTRUCTIONS):
                reasons.append(
                    f"{label}: unsupported instruction {type(instruction).__name__}"
                )
                continue
            if isinstance(instruction, MirCapabilityCall):
                key = (instruction.capability_type, instruction.method)
                if key not in _NATIVE_CAPABILITY_CALLS:
                    reasons.append(
                        f"{label}: native binaries cannot use "
                        f"{instruction.capability_type}.{instruction.method} until the "
                        "native capability broker exists (G2)"
                    )
                elif len(instruction.arguments) != _NATIVE_CAPABILITY_CALLS[key][1]:
                    reasons.append(
                        f"{label}: {instruction.capability_type}.{instruction.method} "
                        "arity drifted"
                    )
                continue
            if isinstance(instruction, MirMember) and _capability_member_type(instruction):
                produced = _capability_member_type(instruction)
                if (produced, instruction.member) not in _NATIVE_CAPABILITY_MEMBERS:
                    reasons.append(
                        f"{label}: native binaries carry only program input; {produced} "
                        f"through .{instruction.member} needs the native capability "
                        "broker (G2)"
                    )
                continue
            if isinstance(instruction, MirLoad):
                name = instruction.name
                if name in bindings:
                    continue
                if name in functions:
                    refs[instruction.target] = _Ref("function", module.key, name)
                elif name in constructors:
                    reasons.append(
                        f"{label}: constructor values are not MIR-Go yet ({name})"
                    )
                elif name in _BUILTINS:
                    refs[instruction.target] = _Ref("builtin", name=name)
                elif name in module.imports:
                    refs[instruction.target] = _Ref("module", module.imports[name])
                else:
                    reasons.append(f"{label}: unknown static MIR load {name!r}")
            elif isinstance(instruction, MirMember):
                target = refs.get(instruction.object)
                if target is None and instruction.target not in callees:
                    if instruction.member not in struct_fields:
                        reasons.append(
                            f"{label}: member {instruction.member!r} is not a struct field"
                        )
                elif target is None:
                    if instruction.member not in _VALUE_METHODS:
                        reasons.append(
                            f"{label}: method {instruction.member!r} is not MIR-Go yet"
                        )
                    refs[instruction.target] = _Ref("member", name=instruction.member)
                elif target.kind == "module":
                    imported = mir.module_of(target.module_key)
                    if not any(item.name == instruction.member for item in imported.functions):
                        reasons.append(
                            f"{label}: {imported.name}.{instruction.member} is not a function"
                        )
                    refs[instruction.target] = _Ref(
                        "function", target.module_key, instruction.member
                    )
                else:
                    reasons.append(f"{label}: member access on a {target.kind} reference")
            elif isinstance(instruction, MirConst):
                if instruction.value is None or not isinstance(
                    instruction.value, (bool, int, float, str)
                ):
                    reasons.append(f"{label}: unsupported MIR constant {instruction.value!r}")
            elif isinstance(instruction, MirUnary) and instruction.operator not in _UNARY:
                reasons.append(f"{label}: unary operator {instruction.operator!r} unsupported")
            elif isinstance(instruction, MirBinary) and instruction.operator not in _BINARY:
                reasons.append(f"{label}: binary operator {instruction.operator!r} unsupported")
            elif isinstance(
                instruction, (MirVariantConstruct, MirVariantIs, MirVariantPayload)
            ):
                reasons.extend(_variant_reasons(instruction, enums, label))
            elif isinstance(
                instruction, (MirStructNew, MirStructSet, MirStructFinish, MirStructFieldSet)
            ):
                reasons.extend(_struct_reasons(instruction, structs, label))

    for block in function.blocks:
        for instruction in block.instructions:
            reasons.extend(_use_reasons(instruction, refs, mir, label))
        for slot in _terminator_operands(block.terminator):
            if slot in refs:
                reasons.append(f"{label}: function values are not MIR-Go yet")
        if not isinstance(block.terminator, (MirReturn, MirJump, MirBranch, MirUnreachable)):
            reasons.append(
                f"{label}: unsupported terminator {type(block.terminator).__name__}"
            )
    return refs, mutable, reasons


def _use_reasons(instruction: Any, refs: dict[int, _Ref], mir: MirGraph, label: str) -> list[str]:
    reasons: list[str] = []
    if isinstance(instruction, MirCall):
        callee = refs.get(instruction.callee)
        if callee is None or callee.kind == "module":
            reasons.append(f"{label}: dynamic call targets are not MIR-Go yet")
        elif callee.kind == "function":
            target = next(
                item
                for item in mir.module_of(callee.module_key).functions
                if item.name == callee.name
            )
            if len(target.parameters) != len(instruction.arguments):
                reasons.append(f"{label}: call arity mismatch for {callee.name}")
        elif callee.kind == "builtin" and len(instruction.arguments) != 1:
            reasons.append(f"{label}: {callee.name} requires one argument")
        operands = instruction.arguments
    elif isinstance(instruction, MirMember):
        target = refs.get(instruction.object)
        operands = () if target is not None and target.kind == "module" else (instruction.object,)
    else:
        operands = _operands(instruction)
    for slot in operands:
        if slot in refs:
            reasons.append(f"{label}: function values are not MIR-Go yet")
    return reasons


def _struct_reasons(instruction: Any, structs: dict[str, Any], label: str) -> list[str]:
    if isinstance(instruction, MirStructNew):
        declaration = structs.get(instruction.type_name)
        if declaration is None:
            return [f"{label}: unknown struct {instruction.type_name!r}"]
        declared = tuple(field.name for field in declaration.fields)
        required = tuple(instruction.required_fields)
        if len(required) != len(set(required)) or set(required) != set(declared):
            return [f"{label}: struct {declaration.name} required fields drifted"]
        if not _struct_instance(declaration, instruction.type):
            return [f"{label}: struct type does not identify one {declaration.name}"]
        return []
    owners = [
        option.name
        for option in alternatives(instruction.type)
        if isinstance(option, NamedType) and option.name in structs
    ]
    if len(owners) != 1:
        return [f"{label}: struct instruction type does not identify one struct"]
    declaration = structs[owners[0]]
    if isinstance(instruction, (MirStructSet, MirStructFieldSet)) and not any(
        field.name == instruction.field for field in declaration.fields
    ):
        return [f"{label}: {declaration.name} has no field {instruction.field!r}"]
    return []


def _struct_owner(instruction: Any, structs: dict[str, Any]) -> Any:
    (owner,) = [
        option.name
        for option in alternatives(instruction.type)
        if isinstance(option, NamedType) and option.name in structs
    ]
    return structs[owner]


def _operands(instruction: Any) -> tuple[int, ...]:
    if isinstance(instruction, (MirBind, MirStore)):
        return (instruction.source,)
    if isinstance(instruction, (MirStructSet, MirStructFieldSet)):
        return (instruction.object, instruction.source)
    if isinstance(instruction, MirStructFinish):
        return (instruction.source,)
    if isinstance(instruction, MirUnary):
        return (instruction.operand,)
    if isinstance(instruction, MirBinary):
        return (instruction.left, instruction.right)
    if isinstance(instruction, (MirList, MirInterpolate)):
        return tuple(instruction.items)
    if isinstance(instruction, MirIterInit):
        return (instruction.iterable,)
    if isinstance(instruction, (MirIterHasNext, MirIterNext)):
        return (instruction.iterator,)
    if isinstance(
        instruction,
        (
            MirIsRuntimeError,
            MirFallibleIsSuccess,
            MirFalliblePayload,
            MirVariantIs,
            MirVariantPayload,
        ),
    ):
        return (instruction.source,)
    if isinstance(instruction, MirVariantConstruct):
        return () if instruction.source is None else (instruction.source,)
    if isinstance(instruction, MirCapabilityCall):
        return (instruction.object, *instruction.arguments)
    return ()


def _terminator_operands(terminator: Any) -> tuple[int, ...]:
    if isinstance(terminator, MirReturn) and terminator.value is not None:
        return (terminator.value,)
    if isinstance(terminator, MirBranch):
        return (terminator.condition,)
    return ()


def _variant_reasons(instruction: Any, enums: dict[str, Any], label: str) -> list[str]:
    try:
        owner, variant = split_canonical_variant_v1(instruction.variant)
    except MirVariantRuntimeError as exc:
        return [f"{label}: invalid canonical variant identity: {exc}"]
    builtin = _BUILTIN_VARIANTS.get(owner)
    if builtin is not None:
        expects_payload = builtin.get(variant)
        if expects_payload is None:
            return [f"{label}: unknown builtin canonical variant {instruction.variant}"]
    else:
        declaration = enums.get(owner)
        if declaration is None:
            return [f"{label}: unknown canonical enum owner {owner!r}"]
        target = next(
            (item for item in declaration.variants if item.name == variant), None
        )
        if target is None:
            return [f"{label}: unknown canonical enum variant {instruction.variant!r}"]
        expects_payload = target.payload_type is not None
    if isinstance(instruction, MirVariantConstruct):
        if expects_payload != (instruction.source is not None):
            return [f"{label}: constructor payload shape drifted for {instruction.variant}"]
        if _variant_type_arguments(instruction) is None:
            return [f"{label}: variant type does not identify one owner instance"]
    if isinstance(instruction, MirVariantPayload) and not expects_payload:
        return [f"{label}: payload requested from payload-free {instruction.variant}"]
    return []


def _variant_type_arguments(instruction: MirVariantConstruct) -> tuple[str, ...] | None:
    owner, _ = split_canonical_variant_v1(instruction.variant)
    concrete = [
        option
        for option in alternatives(instruction.type)
        if isinstance(option, (NamedType, GenericType)) and option.name == owner
    ]
    if len(concrete) != 1:
        return None
    selected = concrete[0]
    if isinstance(selected, GenericType):
        return tuple(render_type(item) for item in selected.arguments)
    return ()


# ---- emission --------------------------------------------------------------


def _emit_function(plan: _FunctionPlan, symbols: dict[tuple[str, str], str]) -> list[str]:
    function = plan.function
    parameter_symbols = {
        parameter.name: f"_ks_p_{index}_{_safe_identifier(parameter.name)}"
        for index, parameter in enumerate(function.parameters)
    }
    # Locals live in two arrays instead of one Go variable per MIR slot: the Go
    # compiler does not SSA-allocate arrays, so build time stays linear in the
    # size of very large functions.
    binding_symbols = {name: f"_ks_b[{index}]" for index, name in enumerate(plan.mutable)}
    names = {**parameter_symbols, **binding_symbols}
    slot_index = {
        slot: index for index, slot in enumerate(sorted(_value_slots(function, plan.refs)))
    }

    def value(slot: int) -> str:
        return f"_ks_v[{slot_index[slot]}]"

    type_parameters = tuple(getattr(function.declaration, "type_parameters", ()) or ())
    label = f"{plan.module.name}.{function.name}"

    signature = ", ".join(f"{symbol} any" for symbol in parameter_symbols.values())
    lines = [f"func {plan.symbol}({signature}) any {{"]
    if type_parameters:
        parameter_set = ", ".join(f"{_go_string(name)}: true" for name in type_parameters)
        lines.append(f"\t_ks_tp := map[string]bool{{{parameter_set}}}")
        lines.append("\t_ks_tb := map[string]string{}")
        lines.append("\t_, _ = _ks_tp, _ks_tb")
        evidence = "_ks_tp, _ks_tb"
    else:
        evidence = "nil, nil"
    for parameter in function.parameters:
        expected = _go_string_slice(_runtime_names(parameter.type))
        lines.extend(
            [
                f"\tif !_ksMatchesType({parameter_symbols[parameter.name]}, {expected}, {evidence}) {{",
                f"\t\t_ksAbort({_call_contract_code(type_parameters)}, "
                f"{_go_string(f'{label}: argument {parameter.name!r} violates its type contract')})",
                "\t}",
            ]
        )
    lines.extend(["\t_ksEnter()", "\tdefer _ksLeave()"])
    for symbol in parameter_symbols.values():
        lines.append(f"\t_ = {symbol}")
    lines.extend(
        [
            f"\tvar _ks_b [{len(binding_symbols)}]any",
            f"\tvar _ks_v [{len(slot_index)}]any",
            "\t_, _ = _ks_b, _ks_v",
        ]
    )

    return_contract = _go_string_slice(_runtime_names(function.return_type))
    lines.extend(["\t_ks_pc := 0", "\tfor {", "\t\tswitch _ks_pc {"])
    for block in function.blocks:
        lines.append(f"\t\tcase {block.id}:")
        for instruction in block.instructions:
            lines.extend(
                _emit_instruction(instruction, plan, names, symbols, label, value)
            )
        lines.extend(
            _emit_terminator(
                block.terminator,
                value=value,
                return_contract=return_contract,
                evidence=evidence,
                contract_code=_call_contract_code(type_parameters),
                label=label,
            )
        )
    lines.extend(
        [
            "\t\tdefault:",
            '\t\t\t_ksAbort("KS5002", "invalid sealed Koschei MIR block")',
            "\t\t}",
            "\t}",
            "}",
        ]
    )
    return lines


def _value_slots(function: MirFunction, refs: dict[int, _Ref]) -> set[int]:
    """Slots that hold runtime values; a bound String/List member is one."""

    slots: set[int] = set()
    for block in function.blocks:
        for instruction in block.instructions:
            target = getattr(instruction, "target", None)
            if target is None:
                continue
            ref = refs.get(target)
            if ref is None or ref.kind == "member":
                slots.add(target)
    return slots


def _emit_instruction(
    instruction: Any,
    plan: _FunctionPlan,
    names: dict[str, str],
    symbols: dict[tuple[str, str], str],
    label: str,
    value: Callable[[int], str],
) -> list[str]:
    prefix = "\t\t\t"
    refs = plan.refs

    if isinstance(instruction, MirLoad):
        if instruction.target in refs:
            return []
        return [f"{prefix}{value(instruction.target)} = {names[instruction.name]}"]
    if isinstance(instruction, MirMember) and _capability_member_type(instruction):
        helper = _NATIVE_CAPABILITY_MEMBERS[
            (_capability_member_type(instruction), instruction.member)
        ]
        return [f"{prefix}{value(instruction.target)} = {helper}({value(instruction.object)})"]
    if isinstance(instruction, MirCapabilityCall):
        helper, _ = _NATIVE_CAPABILITY_CALLS[(instruction.capability_type, instruction.method)]
        arguments = ", ".join(
            value(item) for item in (instruction.object, *instruction.arguments)
        )
        return [f"{prefix}{value(instruction.target)} = {helper}({arguments})"]
    if isinstance(instruction, MirMember):
        ref = refs.get(instruction.target)
        if ref is None:
            return [
                f"{prefix}{value(instruction.target)} = "
                f"_ksField({value(instruction.object)}, {_go_string(instruction.member)})"
            ]
        if ref.kind != "member":
            return []
        return [
            f"{prefix}{value(instruction.target)} = "
            f"_ksMemberOf({value(instruction.object)}, {_go_string(instruction.member)})"
        ]
    if isinstance(instruction, MirConst):
        return [f"{prefix}{value(instruction.target)} = {_go_constant(instruction.value)}"]
    if isinstance(instruction, MirUnit):
        return [f"{prefix}{value(instruction.target)} = _ksUnit{{}}"]
    if isinstance(instruction, MirBind):
        return [f"{prefix}{names[instruction.name]} = {value(instruction.source)}"]
    if isinstance(instruction, MirStore):
        if not plan.mutable.get(instruction.name, False):
            message = _go_string(f"{label}: {instruction.name!r} is an immutable binding")
            return [f'{prefix}_ksAbort("KS3201", {message})']
        return [f"{prefix}{names[instruction.name]} = {value(instruction.source)}"]
    if isinstance(instruction, MirUnary):
        helper = "_ksNot" if instruction.operator == "!" else "_ksNegate"
        return [f"{prefix}{value(instruction.target)} = {helper}({value(instruction.operand)})"]
    if isinstance(instruction, MirBinary):
        return [
            f"{prefix}{value(instruction.target)} = _ksBinary("
            f"{_go_string(instruction.operator)}, {value(instruction.left)}, "
            f"{value(instruction.right)})"
        ]
    if isinstance(instruction, MirList):
        items = ", ".join(value(item) for item in instruction.items)
        return [f"{prefix}{value(instruction.target)} = []any{{{items}}}"]
    if isinstance(instruction, MirInterpolate):
        parts = " + ".join(f"_ksToString({value(item)})" for item in instruction.items)
        return [f"{prefix}{value(instruction.target)} = _ksBudgetText({parts or chr(34) * 2})"]
    if isinstance(instruction, MirIsRuntimeError):
        return [f"{prefix}{value(instruction.target)} = _ksIsError({value(instruction.source)})"]
    if isinstance(instruction, MirFallibleIsSuccess):
        return [
            f"{prefix}{value(instruction.target)} = "
            f"_ksFallibleSuccess({value(instruction.source)})"
        ]
    if isinstance(instruction, MirFalliblePayload):
        return [
            f"{prefix}{value(instruction.target)} = "
            f"_ksFalliblePayload({value(instruction.source)})"
        ]
    if isinstance(instruction, MirIterInit):
        return [f"{prefix}{value(instruction.target)} = _ksIterInit({value(instruction.iterable)})"]
    if isinstance(instruction, MirIterHasNext):
        return [
            f"{prefix}{value(instruction.target)} = _ksIterHasNext({value(instruction.iterator)})"
        ]
    if isinstance(instruction, MirIterNext):
        return [f"{prefix}{value(instruction.target)} = _ksIterNext({value(instruction.iterator)})"]
    if isinstance(instruction, MirCall):
        arguments = ", ".join(value(item) for item in instruction.arguments)
        callee = refs[instruction.callee]
        if callee.kind == "function":
            call = f"{symbols[(callee.module_key, callee.name)]}({arguments})"
        elif callee.kind == "builtin":
            call = f"{_BUILTINS[callee.name]}({arguments})"
        else:
            separator = ", " if arguments else ""
            call = f"_ksInvokeMember({value(instruction.callee)}{separator}{arguments})"
        return [f"{prefix}{value(instruction.target)} = {call}"]
    if isinstance(instruction, MirStructNew):
        fields = _go_string_slice(tuple(instruction.required_fields))
        return [
            f"{prefix}{value(instruction.target)} = "
            f"_ksStructNew({_go_string(instruction.type_name)}, {fields})"
        ]
    if isinstance(instruction, MirStructSet):
        declaration = _struct_owner(instruction, plan.structs)
        expected = _go_string_slice(
            _struct_field_names(declaration, instruction.field)
        )
        return [
            f"{prefix}_ksStructSet({value(instruction.object)}, "
            f"{_go_string(instruction.field)}, {value(instruction.source)}, {expected})"
        ]
    if isinstance(instruction, MirStructFinish):
        return [f"{prefix}{value(instruction.target)} = _ksStructFinish({value(instruction.source)})"]
    if isinstance(instruction, MirStructFieldSet):
        declaration = _struct_owner(instruction, plan.structs)
        expected = _go_string_slice(
            _struct_field_names(declaration, instruction.field)
        )
        return [
            f"{prefix}{value(instruction.target)} = _ksStructWith("
            f"{value(instruction.object)}, {_go_string(declaration.name)}, "
            f"{_go_string(instruction.field)}, {value(instruction.source)}, {expected})"
        ]
    if isinstance(instruction, MirVariantConstruct):
        owner, variant = split_canonical_variant_v1(instruction.variant)
        type_arguments = _variant_type_arguments(instruction)
        assert type_arguments is not None
        payload = "nil" if instruction.source is None else value(instruction.source)
        has_payload = "false" if instruction.source is None else "true"
        evidence = _go_string_slice(type_arguments) if type_arguments else "nil"
        type_parameters = tuple(getattr(plan.function.declaration, "type_parameters", ()) or ())
        if type_arguments and any(
            re.search(rf"\b{re.escape(name)}\b", argument)
            for name in type_parameters
            for argument in type_arguments
        ):
            # Inside a generic function the evidence names the runtime
            # binding (T = Int), as the canonical executor records it.
            evidence = f"_ksBindTypeArgs({evidence}, _ks_tp, _ks_tb)"
        return [
            f"{prefix}{value(instruction.target)} = {_ENUM_GO_TYPE}{{"
            f"owner: {_go_string(owner)}, variant: {_go_string(variant)}, "
            f"hasPayload: {has_payload}, payload: {payload}, typeArgs: {evidence}}}"
        ]
    if isinstance(instruction, MirVariantIs):
        owner, variant = split_canonical_variant_v1(instruction.variant)
        temp = f"_ks_variant_{instruction.target}"
        return [
            f"{prefix}{temp} := _ksAsEnum({value(instruction.source)})",
            f"{prefix}{value(instruction.target)} = "
            f"{temp}.owner == {_go_string(owner)} && "
            f"{temp}.variant == {_go_string(variant)}",
        ]
    if isinstance(instruction, MirVariantPayload):
        owner, variant = split_canonical_variant_v1(instruction.variant)
        temp = f"_ks_variant_{instruction.target}"
        return [
            f"{prefix}{temp} := _ksAsEnum({value(instruction.source)})",
            f"{prefix}if {temp}.owner != {_go_string(owner)} || "
            f"{temp}.variant != {_go_string(variant)} || !{temp}.hasPayload {{",
            f'{prefix}\t_ksAbort("KS5002", "canonical variant payload proof mismatch")',
            f"{prefix}}}",
            f"{prefix}{value(instruction.target)} = {temp}.payload",
        ]
    raise MirGoUnsupported(
        f"unsupported instruction reached MIR-Go emitter: {type(instruction).__name__}"
    )


def _emit_terminator(
    terminator: Any,
    *,
    value: Callable[[int], str],
    return_contract: str,
    evidence: str,
    contract_code: str,
    label: str,
) -> list[str]:
    prefix = "\t\t\t"
    if isinstance(terminator, MirReturn):
        result = "_ksUnit{}" if terminator.value is None else value(terminator.value)
        message = _go_string(f"{label}: return value violates its type contract")
        return [
            f"{prefix}_ks_result := {result}",
            f"{prefix}if !_ksMatchesType(_ks_result, {return_contract}, {evidence}) {{",
            f"{prefix}\t_ksAbort({contract_code}, {message})",
            f"{prefix}}}",
            f"{prefix}return _ks_result",
        ]
    if isinstance(terminator, MirJump):
        return [f"{prefix}_ks_pc = {terminator.target}", f"{prefix}continue"]
    if isinstance(terminator, MirBranch):
        return [
            f"{prefix}if _ksCondition({value(terminator.condition)}) {{",
            f"{prefix}\t_ks_pc = {terminator.then_block}",
            f"{prefix}}} else {{",
            f"{prefix}\t_ks_pc = {terminator.else_block}",
            f"{prefix}}}",
            f"{prefix}continue",
        ]
    if isinstance(terminator, MirUnreachable):
        return [f'{prefix}_ksAbort("KS5002", "unreachable sealed Koschei MIR block")']
    raise MirGoUnsupported(f"unsupported terminator {type(terminator).__name__}")


# ---- Go literals -------------------------------------------------------------


def _runtime_names(type_node: TypeNode) -> tuple[str, ...]:
    return tuple(render_type(item) for item in alternatives(type_node))


def _call_contract_code(type_parameters: tuple[str, ...]) -> str:
    return '"KS3106"' if type_parameters else '"KS3401"'


def _go_constant(value: object) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, int):
        if not INT_MIN <= value <= INT_MAX:
            message = f"KS3501: Int literal 64-bit aralığı aştı: {value}"
            return f"_ksError{{message: {_go_string(message)}}}"
        return f"int64({value})"
    if isinstance(value, float):
        if math.isnan(value):
            return "math.NaN()"
        if math.isinf(value):
            return "math.Inf(1)" if value > 0 else "math.Inf(-1)"
        if value == 0 and math.copysign(1.0, value) < 0:
            return "math.Copysign(0, -1)"
        return f"float64({value!r})"
    if isinstance(value, str):
        return _go_string(value)
    raise MirGoUnsupported(f"unsupported MIR literal {value!r}")


def _go_string(value: str) -> str:
    out = ['"']
    for char in value:
        code = ord(char)
        if char == '"':
            out.append('\\"')
        elif char == "\\":
            out.append("\\\\")
        elif char == "\n":
            out.append("\\n")
        elif char == "\r":
            out.append("\\r")
        elif char == "\t":
            out.append("\\t")
        elif 0x20 <= code < 0x7F:
            out.append(char)
        elif code < 0x80:
            out.append(f"\\x{code:02x}")
        elif 0xD800 <= code <= 0xDFFF:
            raise MirGoUnsupported("string constant contains a surrogate code point")
        elif code <= 0xFFFF:
            out.append(f"\\u{code:04x}")
        else:
            out.append(f"\\U{code:08x}")
    out.append('"')
    return "".join(out)


def _go_string_slice(values: tuple[str, ...]) -> str:
    return "[]string{" + ", ".join(_go_string(item) for item in values) + "}"


def _safe_identifier(value: str) -> str:
    cleaned = _GO_IDENTIFIER.sub("_", value)
    if not cleaned or cleaned[0].isdigit():
        cleaned = "_" + cleaned
    return cleaned


__all__ = [
    "MirGoSupport",
    "MirGoUnsupported",
    "emit_go_from_mir",
    "generate_go_mir_native",
    "inspect_mir_go_support",
]
