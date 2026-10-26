"""Fail-closed operator gate for Decimal P1.

P1 exposes explicit fallible functions because scale mismatch and future rounding
cannot be represented safely as an infallible Bool/arithmetic operator yet.
"""

from __future__ import annotations

from . import _typed_expr as _typed_expr
from . import _typed_ops as _typed_ops
from . import semantic as _semantic
from .ast_nodes import CallExpression, Identifier, MemberExpression
from .type_system import TypeNode, alternatives, render_type

_INSTALLED = False
_ORIGINAL_SEMANTIC_BINARY = None
_ORIGINAL_TYPED_BINARY = None


def _contains_decimal_type(type_node: TypeNode) -> bool:
    return any(render_type(item) == "Decimal" for item in alternatives(type_node))


def _semantic_value_type(checker, expression):
    if isinstance(expression, Identifier):
        symbol = checker._resolve(expression.name)
        if symbol is not None:
            return symbol.type_name
        return None
    if isinstance(expression, CallExpression) and isinstance(expression.callee, Identifier):
        return {
            "decimal": "Decimal or Error",
            "decimal_add": "Decimal or Error",
            "decimal_sub": "Decimal or Error",
            "decimal_cmp": "Int or Error",
            "decimal_text": "String",
        }.get(expression.callee.name)
    if isinstance(expression, MemberExpression):
        owner = _semantic_value_type(checker, expression.object)
        declaration = checker.structs.get(owner or "")
        if declaration is not None:
            for field in declaration.fields:
                if field.name == expression.member:
                    return str(field.type_ref)
    return None


def _semantic_binary(self, expression):
    left = _semantic_value_type(self, expression.left)
    right = _semantic_value_type(self, expression.right)
    if any(
        "Decimal" in self._type_names(item)
        for item in (left, right)
        if item is not None
    ):
        raise _semantic.SemanticError(
            "KS3804",
            "Decimal P1 doğrudan işleç kullanmaz; exact/fallible sözleşme için "
            "decimal_add(), decimal_sub() veya decimal_cmp() kullanın.",
            expression.location,
        )
    return _ORIGINAL_SEMANTIC_BINARY(self, expression)


def _typed_binary(left, operator, right, location):
    if _contains_decimal_type(left) or _contains_decimal_type(right):
        raise _semantic.SemanticError(
            "KS3804",
            "Decimal P1 direct operators are disabled; use decimal_add(), "
            "decimal_sub() or decimal_cmp().",
            location,
        )
    return _ORIGINAL_TYPED_BINARY(left, operator, right, location)


def install_financial_decimal_operator_gate() -> None:
    global _INSTALLED, _ORIGINAL_SEMANTIC_BINARY, _ORIGINAL_TYPED_BINARY
    if _INSTALLED:
        return
    _ORIGINAL_SEMANTIC_BINARY = _semantic.SemanticChecker._check_binary
    _semantic.SemanticChecker._check_binary = _semantic_binary
    _ORIGINAL_TYPED_BINARY = _typed_ops.binary_type
    _typed_ops.binary_type = _typed_binary
    _typed_expr.binary_type = _typed_binary
    _INSTALLED = True
