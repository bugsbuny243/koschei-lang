"""Preserve structural List<T> evidence through legacy ``for`` checking.

Typed HIR already knows the exact iterable and item types.  The compatibility
semantic pass intentionally erases collection generics, so nested loops used to
lose the inner List element type.  This bridge carries the already-validated
Typed HIR evidence into that pass without weakening any type or capability
check.
"""
from __future__ import annotations

from . import modules, semantic
from . import ast_nodes as ast
from .type_system import (
    GenericType,
    TypeNode,
    UnionType,
    UnknownType,
    alternatives,
    render_type,
    union_type,
)

_INSTALLED = False
_PENDING_REPORTS: dict[int, object] = {}


def _location_key(value) -> tuple[str, int, int]:
    location = value.location
    return (type(value).__name__, location.line, location.column)


def _prepare_legacy_analysis(program, imports, report):
    legacy_program, legacy_imports = _prepare_legacy_analysis.original(
        program, imports, report
    )
    _PENDING_REPORTS[id(legacy_program)] = report
    return legacy_program, legacy_imports


def _checker_init(self, program, imports=None):
    _checker_init.original(self, program, imports)
    report = _PENDING_REPORTS.pop(id(program), None)
    self._v0104_expression_types = {}
    if report is not None:
        self._v0104_expression_types = {
            _location_key(item.expression): item.type for item in report.expressions
        }


def _evidence_type(checker, expression) -> TypeNode | None:
    return getattr(checker, "_v0104_expression_types", {}).get(
        _location_key(expression)
    )


def _list_item(type_node: TypeNode | None) -> TypeNode | None:
    if isinstance(type_node, GenericType) and type_node.name == "List":
        return type_node.arguments[0] if type_node.arguments else None
    if isinstance(type_node, UnionType):
        items: list[TypeNode] = []
        for option in alternatives(type_node):
            item = _list_item(option)
            if item is None:
                return None
            items.append(item)
        return union_type(*items)
    return None


def _legacy_item_name(type_node: TypeNode | None) -> str | None:
    if type_node is None or isinstance(type_node, UnknownType):
        return None
    if isinstance(type_node, GenericType) and type_node.name in {"List", "Map"}:
        return type_node.name
    return render_type(type_node)


def _fallback_item_type(checker, expression) -> str | None:
    if isinstance(expression, ast.Identifier):
        known = getattr(checker, "_v010_element_types", {}).get(expression.name)
        if known is not None:
            return known
        symbol = checker._resolve(expression.name)
        if symbol is not None:
            spelling = symbol.type_name or ""
            if spelling.startswith("List<") and spelling.endswith(">"):
                return spelling[5:-1].strip() or None
    return None


def _statement(self, statement):
    if not isinstance(statement, ast.ForStatement):
        return _statement.original(self, statement)

    iterable_type = self._check_expression(statement.iterable)
    if (
        iterable_type is not None
        and iterable_type != "List"
        and not iterable_type.startswith("List<")
    ):
        raise semantic.SemanticError(
            "KS1301",
            f"'for ... in' yalnızca List üzerinde çalışır, {iterable_type} bulundu.",
            statement.location,
        )

    item_node = _list_item(_evidence_type(self, statement.iterable))
    item_type = _legacy_item_name(item_node)
    if item_type is None:
        item_type = _fallback_item_type(self, statement.iterable)

    self._v010_loop_depth = getattr(self, "_v010_loop_depth", 0) + 1
    self.scopes.append({})
    try:
        self._declare(
            semantic.Symbol(
                statement.variable,
                item_type,
                False,
                statement.location,
            )
        )
        self.variable_count += 1
        self._check_statements(statement.body)
    finally:
        self.scopes.pop()
        self._v010_loop_depth -= 1
    return None


def install_nested_generics_v0104() -> None:
    global _INSTALLED
    if _INSTALLED:
        return

    _prepare_legacy_analysis.original = modules.prepare_legacy_analysis
    modules.prepare_legacy_analysis = _prepare_legacy_analysis

    _checker_init.original = semantic.SemanticChecker.__init__
    semantic.SemanticChecker.__init__ = _checker_init

    _statement.original = semantic.SemanticChecker._check_statement
    semantic.SemanticChecker._check_statement = _statement

    _INSTALLED = True
