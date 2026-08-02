"""Fail-closed numeric List reductions for Koschei v0.10.5.

The methods are deliberately fallible:
- List<Int>.sum/min/max() -> Result<Int, Error>
- List<Float>.sum/min/max() -> Result<Float, Error>

An empty list has no runtime element evidence, Int summation can overflow, and
Float values can be non-finite.  Returning Result keeps those cases explicit
without inventing a value or weakening the structural type contract.
"""
from __future__ import annotations

import math
from typing import Any

from . import _typed_expr as typed_expr
from . import _typed_ops as typed_ops
from . import codegen_go as codegen
from . import interpreter as runtime
from . import semantic
from .type_system import (
    ERROR,
    GenericType,
    NamedType,
    UnknownType,
    generic,
    is_named,
    render_type,
)

_INSTALLED = False
_METHODS = frozenset({"sum", "min", "max"})


def _require_zero_arity(name: str, values: list[Any], location) -> None:
    if values:
        raise semantic.SemanticError(
            "KS1301",
            f"List.{name}() argüman almaz, {len(values)} verildi.",
            location,
        )


def _semantic_method(
    self,
    receiver_type,
    method_name,
    location,
    argument_types=None,
    arguments=None,
):
    if (
        isinstance(receiver_type, str)
        and (receiver_type == "List" or receiver_type.startswith("List<"))
        and method_name in _METHODS
    ):
        _require_zero_arity(method_name, argument_types or [], location)
        # Typed HIR has already proved the exact Int/Float item type.  The
        # legacy pass intentionally sees an erased collection and therefore
        # carries a wildcard only; it must not guess Int or Float.
        return "Result<_, Error>"
    return _semantic_method.original(
        self,
        receiver_type,
        method_name,
        location,
        argument_types,
        arguments,
    )


def _numeric_item(receiver, method: str, location) -> NamedType | None:
    if isinstance(receiver, GenericType) and receiver.name == "List":
        item = receiver.arguments[0] if receiver.arguments else UnknownType()
        if isinstance(item, NamedType) and item.name in {"Int", "Float"}:
            return item
        raise semantic.SemanticError(
            "KS1306",
            f"List.{method}() yalnızca kanıtlanmış List<Int> veya List<Float> "
            f"üzerinde kullanılabilir; {render_type(receiver)} bulundu.",
            location,
        )
    if is_named(receiver, "List"):
        raise semantic.SemanticError(
            "KS1306",
            f"List.{method}() için öğe tipinin Int veya Float olduğu "
            "kanıtlanmalıdır.",
            location,
        )
    return None


def _typed_method(receiver, method, arguments, location):
    if method in _METHODS:
        item = _numeric_item(receiver, method, location)
        if item is not None:
            _require_zero_arity(method, list(arguments), location)
            return generic("Result", item, ERROR)
    return _typed_method.original(receiver, method, arguments, location)


def _result_ok(value: Any):
    return runtime.EnumValue("Result", "Ok", value)


def _result_error(message: str):
    return runtime.EnumValue("Result", "Err", runtime.KsError(message))


def _runtime_kind(values: list[Any]) -> str | None:
    if all(type(value) is int for value in values):
        return "Int"
    if all(type(value) is float for value in values):
        return "Float"
    return None


def _reduce_int(values: list[int], operation: str):
    if operation == "sum":
        total = 0
        for value in values:
            total += value
            if total < runtime.INT_MIN or total > runtime.INT_MAX:
                return _result_error(
                    "KS3501: List.sum() işaretli 64-bit Int aralığını aştı"
                )
        return _result_ok(total)
    if operation == "min":
        result = values[0]
        for value in values[1:]:
            if value < result:
                result = value
        return _result_ok(result)
    result = values[0]
    for value in values[1:]:
        if value > result:
            result = value
    return _result_ok(result)


def _reduce_float(values: list[float], operation: str):
    if not all(math.isfinite(value) for value in values):
        return _result_error(
            f"List.{operation}() NaN veya Infinity kabul etmez"
        )
    if operation == "sum":
        total = 0.0
        for value in values:
            total += value
            if not math.isfinite(total):
                return _result_error(
                    "List.sum() sonlu Float aralığının dışına çıktı"
                )
        return _result_ok(total)
    if operation == "min":
        result = values[0]
        for value in values[1:]:
            if value < result:
                result = value
        return _result_ok(result)
    result = values[0]
    for value in values[1:]:
        if value > result:
            result = value
    return _result_ok(result)


def _invoke_member(self, member, arguments):
    receiver = member.receiver
    name = member.name
    if isinstance(receiver, list) and name in _METHODS:
        self._require_arity(name, arguments, 0, member.location)
        if runtime._contains_capability(receiver):
            raise runtime.KoscheiRuntimeError(
                "KS3401",
                f"Capability taşıyan List üzerinde {name}() çalıştırılamaz.",
                member.location,
            )
        if not receiver:
            return _result_error(f"List.{name}() boş List üzerinde tanımlı değildir")
        kind = _runtime_kind(receiver)
        if kind == "Int":
            return _reduce_int(receiver, name)
        if kind == "Float":
            return _reduce_float(receiver, name)
        return _result_error(
            f"List.{name}() homojen Int veya Float öğeler bekler"
        )
    return _invoke_member.original(self, member, arguments)


def _patch_native_runtime() -> None:
    helpers = r'''
func ksFiniteFloat(value float64) bool {
	const maximum = 1.7976931348623157e308
	return value == value && value <= maximum && value >= -maximum
}

func ksReductionError(message string) any {
	return ksEnum("Result", "Err", ksErrorf(message), true)
}

func ksListNumericReduction(value any, operation string) any {
	list, ok := value.([]any)
	if !ok {
		return ksReductionError("List." + operation + "() bir List bekler")
	}
	if ksContainsCapability(list) {
		return ksErrorf("KS3401: Capability taşıyan List üzerinde " + operation + "() çalıştırılamaz")
	}
	if len(list) == 0 {
		return ksReductionError("List." + operation + "() boş List üzerinde tanımlı değildir")
	}

	switch list[0].(type) {
	case int64:
		total := int64(0)
		minimum, ok := list[0].(int64)
		if !ok { return ksReductionError("List." + operation + "() homojen Int veya Float öğeler bekler") }
		maximum := minimum
		for _, raw := range list {
			item, ok := raw.(int64)
			if !ok {
				return ksReductionError("List." + operation + "() homojen Int veya Float öğeler bekler")
			}
			if operation == "sum" {
				next := ksAdd(total, item)
				if problem, failed := next.(*KsError); failed {
					return ksEnum("Result", "Err", problem, true)
				}
				total = next.(int64)
			}
			if item < minimum { minimum = item }
			if item > maximum { maximum = item }
		}
		switch operation {
		case "sum":
			return ksEnum("Result", "Ok", total, true)
		case "min":
			return ksEnum("Result", "Ok", minimum, true)
		case "max":
			return ksEnum("Result", "Ok", maximum, true)
		}

	case float64:
		total := float64(0)
		minimum, ok := list[0].(float64)
		if !ok || !ksFiniteFloat(minimum) {
			return ksReductionError("List." + operation + "() NaN veya Infinity kabul etmez")
		}
		maximum := minimum
		for _, raw := range list {
			item, ok := raw.(float64)
			if !ok {
				return ksReductionError("List." + operation + "() homojen Int veya Float öğeler bekler")
			}
			if !ksFiniteFloat(item) {
				return ksReductionError("List." + operation + "() NaN veya Infinity kabul etmez")
			}
			if operation == "sum" {
				total += item
				if !ksFiniteFloat(total) {
					return ksReductionError("List.sum() sonlu Float aralığının dışına çıktı")
				}
			}
			if item < minimum { minimum = item }
			if item > maximum { maximum = item }
		}
		switch operation {
		case "sum":
			return ksEnum("Result", "Ok", total, true)
		case "min":
			return ksEnum("Result", "Ok", minimum, true)
		case "max":
			return ksEnum("Result", "Ok", maximum, true)
		}
	}
	return ksReductionError("List." + operation + "() homojen Int veya Float öğeler bekler")
}

'''
    anchor = "func ksCallValueMethod(receiver any, method string, arguments ...any) any {"
    if "func ksListNumericReduction(" not in codegen.RUNTIME_PRELUDE:
        if anchor not in codegen.RUNTIME_PRELUDE:
            raise RuntimeError("native value-method dispatcher changed; v0.10.5 patch refused")
        codegen.RUNTIME_PRELUDE = codegen.RUNTIME_PRELUDE.replace(
            anchor, helpers + anchor, 1
        )

    list_anchor = '''\t\tcase "first_difference":
\t\t\tif len(arguments) != 1 { return ksErrorf("KS4003: first_difference bir argüman alır") }
\t\t\treturn ksListFirstDifference(receiver, arguments[0])
'''
    list_replacement = list_anchor + '''\t\tcase "sum", "min", "max":
\t\t\tif len(arguments) != 0 { return ksErrorf("KS4003: " + method + " argüman almaz") }
\t\t\treturn ksListNumericReduction(receiver, method)
'''
    if 'case "sum", "min", "max":' not in codegen.RUNTIME_PRELUDE:
        if list_anchor not in codegen.RUNTIME_PRELUDE:
            raise RuntimeError("native List dispatcher changed; v0.10.5 patch refused")
        codegen.RUNTIME_PRELUDE = codegen.RUNTIME_PRELUDE.replace(
            list_anchor, list_replacement, 1
        )


def install_numeric_reductions_v0105() -> None:
    global _INSTALLED
    if _INSTALLED:
        return

    semantic.LIST_METHODS.update(_METHODS)
    runtime.LIST_METHODS.update(_METHODS)
    codegen.LIST_METHODS.update(_METHODS)
    codegen.VALUE_METHODS.update(_METHODS)

    _semantic_method.original = semantic.SemanticChecker._check_method_call
    semantic.SemanticChecker._check_method_call = _semantic_method

    _typed_method.original = typed_ops.method_type
    typed_ops.method_type = _typed_method
    typed_expr.method_type = _typed_method

    _invoke_member.original = runtime.Interpreter._invoke_member
    runtime.Interpreter._invoke_member = _invoke_member

    _patch_native_runtime()
    _INSTALLED = True
