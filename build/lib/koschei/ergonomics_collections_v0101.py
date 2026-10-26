"""Deterministic collection ergonomics for Koschei v0.10.1.

The surface is intentionally small and total:
- List<T>.take(Int) -> List<T>; non-positive counts return an empty list.
- Map<String, V>.keys_sorted_by_value(Bool) -> List<String> for homogeneous
  Int, Float, or String values. Ties are resolved by key ascending so the
  interpreter and native backend are deterministic.
"""
from __future__ import annotations

from functools import cmp_to_key
from typing import Any

from . import _typed_expr as typed_expr
from . import _typed_ops as typed_ops
from . import codegen_go as codegen
from . import ergonomics_semantics
from . import interpreter as runtime
from . import semantic
from .type_contracts import require_assignable
from .type_system import (
    BOOL,
    INT,
    STRING,
    GenericType,
    UnknownType,
    alternatives,
    generic,
    is_named,
    render_type,
)

_INSTALLED = False


def _require_arity(name: str, values: list[Any], expected: int, location) -> None:
    if len(values) != expected:
        raise semantic.SemanticError(
            "KS1301",
            f"{name}() {expected} argüman bekler, {len(values)} verildi.",
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
    values = argument_types or []
    if receiver_type == "List" and method_name == "take":
        _require_arity("List.take", values, 1, location)
        self._require_assignable(
            ("Int",), values[0], "List.take() öğe sayısı", location
        )
        return "List"
    if receiver_type == "Map" and method_name == "keys_sorted_by_value":
        _require_arity("Map.keys_sorted_by_value", values, 1, location)
        self._require_assignable(
            ("Bool",),
            values[0],
            "Map.keys_sorted_by_value() descending argümanı",
            location,
        )
        return "List"
    return _semantic_method.original(
        self,
        receiver_type,
        method_name,
        location,
        argument_types,
        arguments,
    )


def _iterable_item_type(checker, expression):
    from . import ast_nodes as ast

    if isinstance(expression, ast.CallExpression) and isinstance(
        expression.callee, ast.MemberExpression
    ):
        if expression.callee.member == "take":
            return _iterable_item_type(checker, expression.callee.object)
        if expression.callee.member == "keys_sorted_by_value":
            return "String"
    return _iterable_item_type.original(checker, expression)


def _validate_comparable_value(value, location) -> None:
    known: list[str] = []
    for item in alternatives(value):
        if isinstance(item, UnknownType):
            continue
        if not any(is_named(item, name) for name in ("Int", "Float", "String")):
            raise semantic.SemanticError(
                "KS1306",
                "Map.keys_sorted_by_value() yalnızca Int, Float veya String "
                f"değerleri sıralayabilir; {render_type(item)} bulundu.",
                location,
            )
        known.append(render_type(item))
    if len(set(known)) > 1:
        raise semantic.SemanticError(
            "KS1306",
            "Map.keys_sorted_by_value() tek ve homojen bir değer tipi ister; "
            + ", ".join(sorted(set(known)))
            + " bulundu.",
            location,
        )


def _typed_method(receiver, method, arguments, location):
    if isinstance(receiver, GenericType) and receiver.name == "List" and method == "take":
        if len(arguments) != 1:
            raise semantic.SemanticError(
                "KS1301",
                f"List.take() 1 argüman bekler, {len(arguments)} verildi.",
                location,
            )
        require_assignable(INT, arguments[0], "List.take() öğe sayısı", location)
        return receiver
    if is_named(receiver, "List") and method == "take":
        if len(arguments) != 1:
            raise semantic.SemanticError(
                "KS1301",
                f"List.take() 1 argüman bekler, {len(arguments)} verildi.",
                location,
            )
        require_assignable(INT, arguments[0], "List.take() öğe sayısı", location)
        return generic("List", UnknownType())

    if (
        isinstance(receiver, GenericType)
        and receiver.name == "Map"
        and method == "keys_sorted_by_value"
    ):
        if len(arguments) != 1:
            raise semantic.SemanticError(
                "KS1301",
                "Map.keys_sorted_by_value() 1 argüman bekler, "
                f"{len(arguments)} verildi.",
                location,
            )
        require_assignable(
            BOOL,
            arguments[0],
            "Map.keys_sorted_by_value() descending argümanı",
            location,
        )
        key = receiver.arguments[0] if receiver.arguments else STRING
        value = receiver.arguments[1] if len(receiver.arguments) > 1 else UnknownType()
        _validate_comparable_value(value, location)
        return generic("List", key)
    if is_named(receiver, "Map") and method == "keys_sorted_by_value":
        if len(arguments) != 1:
            raise semantic.SemanticError(
                "KS1301",
                "Map.keys_sorted_by_value() 1 argüman bekler, "
                f"{len(arguments)} verildi.",
                location,
            )
        require_assignable(
            BOOL,
            arguments[0],
            "Map.keys_sorted_by_value() descending argümanı",
            location,
        )
        return generic("List", STRING)
    return _typed_method.original(receiver, method, arguments, location)


def _rank_kind(values: list[Any]) -> str | None:
    if not values:
        return "empty"
    if all(type(value) is int for value in values):
        return "Int"
    if all(type(value) is float for value in values):
        return "Float"
    if all(isinstance(value, str) for value in values):
        return "String"
    return None


def _invoke_member(self, member, arguments):
    receiver = member.receiver
    name = member.name
    if isinstance(receiver, list) and name == "take":
        self._require_arity(name, arguments, 1, member.location)
        count = arguments[0]
        if type(count) is not int:
            return runtime.KsError("List.take() öğe sayısı Int olmalıdır")
        if count <= 0:
            return []
        return list(receiver[:count])

    if isinstance(receiver, dict) and name == "keys_sorted_by_value":
        self._require_arity(name, arguments, 1, member.location)
        descending = arguments[0]
        if type(descending) is not bool:
            return runtime.KsError(
                "Map.keys_sorted_by_value() descending argümanı Bool olmalıdır"
            )
        if runtime._contains_capability(receiver):
            raise runtime.KoscheiRuntimeError(
                "KS3401",
                "Capability taşıyan Map değerleri sıralanamaz.",
                member.location,
            )
        keys = list(receiver.keys())
        if _rank_kind([receiver[key] for key in keys]) is None:
            return runtime.KsError(
                "Map.keys_sorted_by_value() yalnızca homojen Int, Float veya "
                "String değerleri sıralar"
            )

        def compare(left_key: str, right_key: str) -> int:
            left = receiver[left_key]
            right = receiver[right_key]
            order = -1 if left < right else 1 if left > right else 0
            if order:
                return -order if descending else order
            return -1 if left_key < right_key else 1 if left_key > right_key else 0

        return sorted(keys, key=cmp_to_key(compare))

    return _invoke_member.original(self, member, arguments)


def _patch_native_runtime() -> None:
    helpers = r'''
func ksListTake(value any, countValue any) any {
	list, ok := value.([]any)
	if !ok {
		return ksErrorf("List.take() bir List bekler")
	}
	count, ok := countValue.(int64)
	if !ok {
		return ksErrorf("List.take() öğe sayısı Int olmalıdır")
	}
	if count <= 0 {
		return []any{}
	}
	if count > int64(len(list)) {
		count = int64(len(list))
	}
	result := make([]any, int(count))
	copy(result, list[:int(count)])
	return result
}

func ksMapKeysSortedByValue(value any, descendingValue any) any {
	mapping, ok := value.(*KsMap)
	if !ok {
		return ksErrorf("Map.keys_sorted_by_value() bir Map bekler")
	}
	descending, ok := descendingValue.(bool)
	if !ok {
		return ksErrorf("Map.keys_sorted_by_value() descending argümanı Bool olmalıdır")
	}
	if ksContainsCapability(mapping) {
		return ksErrorf("KS3401: Capability taşıyan Map değerleri sıralanamaz")
	}
	kind := ""
	for _, key := range mapping.Keys {
		current := ""
		switch mapping.Values[key].(type) {
		case int64:
			current = "Int"
		case float64:
			current = "Float"
		case string:
			current = "String"
		default:
			return ksErrorf("Map.keys_sorted_by_value() yalnızca homojen Int, Float veya String değerleri sıralar")
		}
		if kind == "" {
			kind = current
		} else if kind != current {
			return ksErrorf("Map.keys_sorted_by_value() yalnızca homojen Int, Float veya String değerleri sıralar")
		}
	}
	keys := append([]string(nil), mapping.Keys...)
	sort.SliceStable(keys, func(i, j int) bool {
		leftKey, rightKey := keys[i], keys[j]
		order, comparable := ksCompare(mapping.Values[leftKey], mapping.Values[rightKey])
		if !comparable {
			return leftKey < rightKey
		}
		if order == 0 {
			return leftKey < rightKey
		}
		if descending {
			return order > 0
		}
		return order < 0
	})
	result := make([]any, len(keys))
	for index, key := range keys {
		result[index] = key
	}
	return result
}

'''
    anchor = "func ksCallValueMethod(receiver any, method string, arguments ...any) any {"
    if "func ksListTake(" not in codegen.RUNTIME_PRELUDE:
        if anchor not in codegen.RUNTIME_PRELUDE:
            raise RuntimeError("native value-method dispatcher changed; v0.10.1 patch refused")
        codegen.RUNTIME_PRELUDE = codegen.RUNTIME_PRELUDE.replace(
            anchor, helpers + anchor, 1
        )

    list_anchor = '''\t\tcase "filter":
\t\t\tif len(arguments) != 1 { return ksErrorf("KS4003: filter bir argüman alır") }
\t\t\treturn ksListFilter(receiver, arguments[0])
'''
    list_replacement = list_anchor + '''\t\tcase "take":
\t\t\tif len(arguments) != 1 { return ksErrorf("KS4003: take bir argüman alır") }
\t\t\treturn ksListTake(receiver, arguments[0])
'''
    if 'case "take":' not in codegen.RUNTIME_PRELUDE:
        if list_anchor not in codegen.RUNTIME_PRELUDE:
            raise RuntimeError("native List dispatcher changed; v0.10.1 patch refused")
        codegen.RUNTIME_PRELUDE = codegen.RUNTIME_PRELUDE.replace(
            list_anchor, list_replacement, 1
        )

    map_anchor = '''\t\tcase "keys":
\t\t\tif len(arguments) != 0 { return ksErrorf("KS4003: keys argüman almaz") }
\t\t\treturn ksMapKeys(receiver)
'''
    map_replacement = map_anchor + '''\t\tcase "keys_sorted_by_value":
\t\t\tif len(arguments) != 1 { return ksErrorf("KS4003: keys_sorted_by_value bir argüman alır") }
\t\t\treturn ksMapKeysSortedByValue(receiver, arguments[0])
'''
    if 'case "keys_sorted_by_value":' not in codegen.RUNTIME_PRELUDE:
        if map_anchor not in codegen.RUNTIME_PRELUDE:
            raise RuntimeError("native Map dispatcher changed; v0.10.1 patch refused")
        codegen.RUNTIME_PRELUDE = codegen.RUNTIME_PRELUDE.replace(
            map_anchor, map_replacement, 1
        )


def install_collections_v0101() -> None:
    global _INSTALLED
    if _INSTALLED:
        return

    semantic.LIST_METHODS.add("take")
    semantic.MAP_METHODS.add("keys_sorted_by_value")
    runtime.LIST_METHODS.add("take")
    runtime.MAP_METHODS.add("keys_sorted_by_value")
    codegen.LIST_METHODS.add("take")
    codegen.MAP_METHODS.add("keys_sorted_by_value")
    codegen.VALUE_METHODS.update({"take", "keys_sorted_by_value"})

    _semantic_method.original = semantic.SemanticChecker._check_method_call
    semantic.SemanticChecker._check_method_call = _semantic_method

    _iterable_item_type.original = ergonomics_semantics._iterable_item_type
    ergonomics_semantics._iterable_item_type = _iterable_item_type

    _typed_method.original = typed_ops.method_type
    typed_ops.method_type = _typed_method
    typed_expr.method_type = _typed_method

    _invoke_member.original = runtime.Interpreter._invoke_member
    runtime.Interpreter._invoke_member = _invoke_member

    _patch_native_runtime()
    _INSTALLED = True
