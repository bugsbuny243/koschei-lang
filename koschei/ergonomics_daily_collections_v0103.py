"""Small deterministic daily-collection helpers for Koschei v0.10.3."""
from __future__ import annotations

from typing import Any

from . import _typed_expr as typed_expr
from . import _typed_ops as typed_ops
from . import codegen_go as codegen
from . import interpreter as runtime
from . import semantic
from .type_contracts import require_assignable
from .type_system import INT, STRING, GenericType, UnknownType, generic, is_named, union_type

_INSTALLED = False


def _semantic_method(
    self,
    receiver_type,
    method_name,
    location,
    argument_types=None,
    arguments=None,
):
    values = argument_types or []
    if receiver_type == "List" and method_name == "first_difference":
        if len(values) != 1:
            raise semantic.SemanticError(
                "KS1301",
                f"List.first_difference() 1 argüman bekler, {len(values)} verildi.",
                location,
            )
        self._require_assignable(
            ("List",),
            values[0],
            "List.first_difference() karşılaştırılan liste",
            location,
        )
        return "Option<Int>"
    if receiver_type == "Map" and method_name == "merge":
        if len(values) != 1:
            raise semantic.SemanticError(
                "KS1301",
                f"Map.merge() 1 argüman bekler, {len(values)} verildi.",
                location,
            )
        self._require_assignable(
            ("Map",), values[0], "Map.merge() üst katmanı", location
        )
        return "Map"
    return _semantic_method.original(
        self,
        receiver_type,
        method_name,
        location,
        argument_types,
        arguments,
    )


def _typed_method(receiver, method, arguments, location):
    if isinstance(receiver, GenericType) and receiver.name == "List" and method == "first_difference":
        if len(arguments) != 1:
            raise semantic.SemanticError(
                "KS1301",
                f"List.first_difference() 1 argüman bekler, {len(arguments)} verildi.",
                location,
            )
        require_assignable(
            receiver,
            arguments[0],
            "List.first_difference() karşılaştırılan liste",
            location,
        )
        return generic("Option", INT)
    if is_named(receiver, "List") and method == "first_difference":
        if len(arguments) != 1:
            raise semantic.SemanticError(
                "KS1301",
                f"List.first_difference() 1 argüman bekler, {len(arguments)} verildi.",
                location,
            )
        require_assignable(
            generic("List", UnknownType()),
            arguments[0],
            "List.first_difference() karşılaştırılan liste",
            location,
        )
        return generic("Option", INT)

    if isinstance(receiver, GenericType) and receiver.name == "Map" and method == "merge":
        if len(arguments) != 1:
            raise semantic.SemanticError(
                "KS1301",
                f"Map.merge() 1 argüman bekler, {len(arguments)} verildi.",
                location,
            )
        other = arguments[0]
        if not isinstance(other, GenericType) or other.name != "Map":
            require_assignable(receiver, other, "Map.merge() üst katmanı", location)
            return receiver
        left_key = receiver.arguments[0] if receiver.arguments else STRING
        left_value = receiver.arguments[1] if len(receiver.arguments) > 1 else UnknownType()
        right_key = other.arguments[0] if other.arguments else STRING
        right_value = other.arguments[1] if len(other.arguments) > 1 else UnknownType()
        require_assignable(left_key, right_key, "Map.merge() anahtar tipi", location)
        require_assignable(right_key, left_key, "Map.merge() anahtar tipi", location)
        return generic("Map", left_key, union_type(left_value, right_value))
    if is_named(receiver, "Map") and method == "merge":
        if len(arguments) != 1:
            raise semantic.SemanticError(
                "KS1301",
                f"Map.merge() 1 argüman bekler, {len(arguments)} verildi.",
                location,
            )
        require_assignable(
            generic("Map", STRING, UnknownType()),
            arguments[0],
            "Map.merge() üst katmanı",
            location,
        )
        return generic("Map", STRING, UnknownType())
    return _typed_method.original(receiver, method, arguments, location)


def _invoke_member(self, member, arguments):
    receiver = member.receiver
    name = member.name
    if isinstance(receiver, list) and name == "first_difference":
        self._require_arity(name, arguments, 1, member.location)
        other = arguments[0]
        if not isinstance(other, list):
            return runtime.KsError("List.first_difference() bir List bekler")
        limit = min(len(receiver), len(other))
        for index in range(limit):
            if receiver[index] != other[index]:
                return runtime.EnumValue("Option", "Some", index)
        if len(receiver) != len(other):
            return runtime.EnumValue("Option", "Some", limit)
        return runtime.EnumValue("Option", "None")

    if isinstance(receiver, dict) and name == "merge":
        self._require_arity(name, arguments, 1, member.location)
        other = arguments[0]
        if not isinstance(other, dict):
            return runtime.KsError("Map.merge() bir Map bekler")
        if runtime._contains_capability(receiver) or runtime._contains_capability(other):
            raise runtime.KoscheiRuntimeError(
                "KS3401",
                "Capability taşıyan Map değerleri birleştirilemez.",
                member.location,
            )
        result = dict(receiver)
        result.update(other)
        return result

    return _invoke_member.original(self, member, arguments)


def _patch_native_runtime() -> None:
    helpers = r'''
func ksListFirstDifference(value any, otherValue any) any {
	left, ok := value.([]any)
	if !ok {
		return ksErrorf("List.first_difference() bir List bekler")
	}
	right, ok := otherValue.([]any)
	if !ok {
		return ksErrorf("List.first_difference() bir List bekler")
	}
	limit := len(left)
	if len(right) < limit {
		limit = len(right)
	}
	for index := 0; index < limit; index++ {
		if !ksTruthy(ksEq(left[index], right[index])) {
			return ksEnum("Option", "Some", int64(index), true)
		}
	}
	if len(left) != len(right) {
		return ksEnum("Option", "Some", int64(limit), true)
	}
	return ksEnum("Option", "None", ksUnit, false)
}

func ksMapMerge(value any, otherValue any) any {
	base, ok := value.(*KsMap)
	if !ok {
		return ksErrorf("Map.merge() bir Map bekler")
	}
	overlay, ok := otherValue.(*KsMap)
	if !ok {
		return ksErrorf("Map.merge() bir Map bekler")
	}
	if ksContainsCapability(base) || ksContainsCapability(overlay) {
		return ksErrorf("KS3401: Capability taşıyan Map değerleri birleştirilemez")
	}
	result := &KsMap{
		Keys: append([]string(nil), base.Keys...),
		Values: make(map[string]any, len(base.Values)+len(overlay.Values)),
	}
	for key, item := range base.Values {
		result.Values[key] = item
	}
	for _, key := range overlay.Keys {
		if _, exists := result.Values[key]; !exists {
			result.Keys = append(result.Keys, key)
		}
		result.Values[key] = overlay.Values[key]
	}
	return result
}

'''
    anchor = "func ksCallValueMethod(receiver any, method string, arguments ...any) any {"
    if "func ksListFirstDifference(" not in codegen.RUNTIME_PRELUDE:
        if anchor not in codegen.RUNTIME_PRELUDE:
            raise RuntimeError("native value-method dispatcher changed; v0.10.3 patch refused")
        codegen.RUNTIME_PRELUDE = codegen.RUNTIME_PRELUDE.replace(anchor, helpers + anchor, 1)

    list_anchor = '''\t\tcase "find":
\t\t\tif len(arguments) != 1 { return ksErrorf("KS4003: find bir argüman alır") }
\t\t\treturn ksListFind(receiver, arguments[0])
'''
    list_replacement = list_anchor + '''\t\tcase "first_difference":
\t\t\tif len(arguments) != 1 { return ksErrorf("KS4003: first_difference bir argüman alır") }
\t\t\treturn ksListFirstDifference(receiver, arguments[0])
'''
    if 'case "first_difference":' not in codegen.RUNTIME_PRELUDE:
        if list_anchor not in codegen.RUNTIME_PRELUDE:
            raise RuntimeError("native List dispatcher changed; v0.10.3 patch refused")
        codegen.RUNTIME_PRELUDE = codegen.RUNTIME_PRELUDE.replace(
            list_anchor, list_replacement, 1
        )

    map_anchor = '''\t\tcase "keys_sorted_by_value":
\t\t\tif len(arguments) != 1 { return ksErrorf("KS4003: keys_sorted_by_value bir argüman alır") }
\t\t\treturn ksMapKeysSortedByValue(receiver, arguments[0])
'''
    map_replacement = map_anchor + '''\t\tcase "merge":
\t\t\tif len(arguments) != 1 { return ksErrorf("KS4003: merge bir argüman alır") }
\t\t\treturn ksMapMerge(receiver, arguments[0])
'''
    if 'case "merge":' not in codegen.RUNTIME_PRELUDE:
        if map_anchor not in codegen.RUNTIME_PRELUDE:
            raise RuntimeError("native Map dispatcher changed; v0.10.3 patch refused")
        codegen.RUNTIME_PRELUDE = codegen.RUNTIME_PRELUDE.replace(
            map_anchor, map_replacement, 1
        )


def install_daily_collections_v0103() -> None:
    global _INSTALLED
    if _INSTALLED:
        return

    semantic.LIST_METHODS.add("first_difference")
    semantic.MAP_METHODS.add("merge")
    runtime.LIST_METHODS.add("first_difference")
    runtime.MAP_METHODS.add("merge")
    codegen.LIST_METHODS.add("first_difference")
    codegen.MAP_METHODS.add("merge")
    codegen.VALUE_METHODS.update({"first_difference", "merge"})

    _semantic_method.original = semantic.SemanticChecker._check_method_call
    semantic.SemanticChecker._check_method_call = _semantic_method

    _typed_method.original = typed_ops.method_type
    typed_ops.method_type = _typed_method
    typed_expr.method_type = _typed_method

    _invoke_member.original = runtime.Interpreter._invoke_member
    runtime.Interpreter._invoke_member = _invoke_member

    _patch_native_runtime()
    _INSTALLED = True
