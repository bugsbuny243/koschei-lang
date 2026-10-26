"""A capability value is opaque: it renders as its type and is never compared.

Printing an authority token used to print the host's object representation,
memory address included: ``println(caps)`` leaked host internals and printed
something different on every run and in every executor. A token now renders
as ``<TypeName>`` everywhere, including inside a struct, in the interpreter,
the canonical MIR executor and MIR-Go binaries. The text names only the type,
which the source already shows; the scope a token was narrowed to stays out
of program output.

Comparing two tokens with ``==``/``!=`` asked the host whether they were the
same object: an identity question about authority that Koschei does not
define, and that a native binary answered differently. The checker refuses it
(KS2407) for every type that is, or contains at any struct depth, an authority
type or an HTTP ``Response``.
"""

from __future__ import annotations

import re

from . import interpreter as _runtime
from . import modules as _modules
from .ast_nodes import BinaryExpression
from .capability_effect_contract_v1 import CAPABILITY_TYPES
from .semantic import SemanticError
from .type_contracts import declaration_type
from .type_system import render_type

CODE = "KS2407"
# Response is a capability operation's result whose text and status are read
# through methods; the object itself has no identity to compare either.
_AUTHORITY = frozenset(CAPABILITY_TYPES) | {"Response"}
_NAME = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")

_INSTALLED = False
_ORIGINAL_CHECK_AFFINE = None


def opaque_text(type_name: str) -> str:
    return f"<{type_name}>"


def _structs(program, imports) -> dict:
    declarations = {item.name: item for item in program.structs}
    for module in (imports or {}).values():
        for name, declaration in getattr(module, "structs", {}).items():
            declarations.setdefault(name, declaration)
    return declarations


def _bears_authority(type_node, structs: dict, seen: set[str]) -> bool:
    for name in _NAME.findall(render_type(type_node)):
        if name in _AUTHORITY:
            return True
        declaration = structs.get(name)
        if declaration is None or name in seen:
            continue
        seen.add(name)
        for field in declaration.fields:
            if _bears_authority(declaration_type(declaration, field.type_ref), structs, seen):
                return True
    return False


def check_capability_comparisons(program, imports, typed_report) -> None:
    types = {id(item.expression): item.type for item in typed_report.expressions}
    structs = _structs(program, imports)
    for item in typed_report.expressions:
        expression = item.expression
        if not isinstance(expression, BinaryExpression) or expression.operator not in {"==", "!="}:
            continue
        for side in (expression.left, expression.right):
            type_node = types.get(id(side))
            if type_node is not None and _bears_authority(type_node, structs, set()):
                raise SemanticError(
                    CODE,
                    f"Yetki taşıyan değerler ({render_type(type_node)}) karşılaştırılamaz.",
                    expression.location,
                )


def _check_affine_resources(program, imports, typed_report):
    # Runs after the typestate and affine rules so their more specific
    # diagnostics keep priority over this one.
    result = _ORIGINAL_CHECK_AFFINE(program, imports, typed_report)
    check_capability_comparisons(program, imports, typed_report)
    return result


def _install_opaque_rendering() -> None:
    # ks_to_string renders any non-data value with str(); every canonical
    # authority class answers with its type name only.
    for type_name in sorted(CAPABILITY_TYPES):
        runtime_type = getattr(_runtime, type_name)
        text = opaque_text(type_name)
        runtime_type.__str__ = lambda self, _text=text: _text
        runtime_type.__repr__ = lambda self, _text=text: _text


def install_capability_opacity_v1() -> None:
    global _INSTALLED, _ORIGINAL_CHECK_AFFINE
    if _INSTALLED:
        return
    _install_opaque_rendering()
    _ORIGINAL_CHECK_AFFINE = _modules.check_affine_resources
    _modules.check_affine_resources = _check_affine_resources
    _INSTALLED = True


__all__ = [
    "CODE",
    "check_capability_comparisons",
    "install_capability_opacity_v1",
    "opaque_text",
]
