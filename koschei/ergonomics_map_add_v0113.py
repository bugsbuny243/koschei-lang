"""Immutable numeric map accumulation for Koschei v0.10.13.

``Map<String, N>.add(String, N) -> Map<String, N>`` supports ``Int`` and
``Float`` values. Missing keys start from numeric zero, existing keys use the
same checked addition semantics as the language ``+`` operator, and the source
map is never mutated.
"""
from __future__ import annotations

from . import _typed_expr as typed_expr
from . import _typed_ops as typed_ops
from . import codegen_go as codegen
from . import interpreter as runtime
from . import semantic
from .type_contracts import require_assignable
from .type_system import (
    FLOAT,
    INT,
    STRING,
    GenericType,
    TypeNode,
    UnionType,
    UnknownType,
    alternatives,
    contains_named,
    generic,
    is_named,
    render_type,
    union_type,
)

_INSTALLED = False
_METHOD = "add"


def _require_two_arguments(values, location) -> None:
    if len(values) != 2:
        raise semantic.SemanticError(
            "KS1301",
            f"Map.add() anahtar ve delta olmak üzere 2 argüman bekler, "
            f"{len(values)} verildi.",
            location,
        )


def _numeric_value(type_node: TypeNode, location) -> TypeNode:
    if is_named(type_node, "Int") or is_named(type_node, "Float"):
        return type_node
    raise semantic.SemanticError(
        "KS1306",
        "Map.add() yalnızca Map<String, Int> veya Map<String, Float> "
        f"üzerinde güvenlidir; {render_type(type_node)} değer tipi bulundu.",
        location,
    )


def _typed_add(
    receiver: TypeNode,
    key: TypeNode,
    delta: TypeNode,
    location,
) -> TypeNode:
    if isinstance(receiver, UnionType):
        return union_type(
            *(
                _typed_add(option, key, delta, location)
                for option in alternatives(receiver)
            )
        )

    if isinstance(receiver, GenericType) and receiver.name == "Map":
        key_type = receiver.arguments[0] if receiver.arguments else STRING
        value_type = (
            receiver.arguments[1]
            if len(receiver.arguments) > 1
            else UnknownType()
        )
    elif is_named(receiver, "Map"):
        key_type = STRING
        value_type = UnknownType()
    else:
        raise semantic.SemanticError(
            "KS1306",
            f"Map.add() yalnızca Map üzerinde güvenlidir; "
            f"{render_type(receiver)} bulundu.",
            location,
        )

    for type_node in (key_type, value_type, key, delta):
        if contains_named(type_node, set(semantic.CAPABILITY_TYPES)):
            raise semantic.SemanticError(
                "KS2402",
                "Map.add() capability taşıyan anahtar veya değer kabul etmez.",
                location,
            )

    require_assignable(STRING, key_type, "Map.add() Map anahtar tipi", location)
    require_assignable(STRING, key, "Map.add() anahtar tipi", location)

    if isinstance(value_type, UnknownType):
        value_type = _numeric_value(delta, location)
    else:
        value_type = _numeric_value(value_type, location)
        require_assignable(
            value_type,
            delta,
            "Map.add() delta tipi",
            location,
        )
    return generic("Map", STRING, value_type)


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
        and (receiver_type == "Map" or receiver_type.startswith("Map<"))
        and method_name == _METHOD
    ):
        values = argument_types or []
        _require_two_arguments(values, location)
        self._require_assignable(
            ("String",), values[0], "Map.add() anahtar tipi", location
        )
        self._require_assignable(
            ("Int", "Float"), values[1], "Map.add() delta tipi", location
        )
        # Exact Map<String, N> preservation belongs to Typed HIR.
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
    if method == _METHOD:
        _require_two_arguments(arguments, location)
        return _typed_add(receiver, arguments[0], arguments[1], location)
    return _typed_method.original(receiver, method, arguments, location)


def _invoke_member(self, member, arguments):
    receiver = member.receiver
    if isinstance(receiver, dict) and member.name == _METHOD:
        self._require_arity(_METHOD, arguments, 2, member.location)
        key, delta = arguments
        if runtime._contains_capability(receiver) or runtime._contains_capability(delta):
            raise runtime.KoscheiRuntimeError(
                "KS3401",
                "Capability taşıyan Map veya delta üzerinde add() çalıştırılamaz.",
                member.location,
            )
        if not isinstance(key, str):
            return runtime.KsError("Map.add() anahtarı String olmalıdır")
        if type(delta) not in {int, float}:
            return runtime.KsError("Map.add() delta değeri Int veya Float olmalıdır")

        result = dict(receiver)
        if key not in result:
            result[key] = delta
            return result

        current = result[key]
        if type(current) is not type(delta):
            return runtime.KsError(
                "Map.add() mevcut değer ile delta aynı sayısal tipte olmalıdır"
            )
        if type(delta) is int:
            total = current + delta
            if not runtime.INT_MIN <= total <= runtime.INT_MAX:
                return runtime.Interpreter._int_overflow("+")
            result[key] = total
            return result

        result[key] = current + delta
        return result
    return _invoke_member.original(self, member, arguments)


def _patch_native_runtime() -> None:
    helper = r'''
func ksMapAdd(value any, keyValue any, delta any) any {
	base, ok := value.(*KsMap)
	if !ok {
		return ksErrorf("Map.add() bir Map bekler")
	}
	key, ok := keyValue.(string)
	if !ok {
		return ksErrorf("Map.add() anahtarı String olmalıdır")
	}
	switch delta.(type) {
	case int64, float64:
	default:
		return ksErrorf("Map.add() delta değeri Int veya Float olmalıdır")
	}
	if ksContainsCapability(base) || ksContainsCapability(delta) {
		return ksErrorf("KS3401: Capability taşıyan Map veya delta üzerinde add() çalıştırılamaz")
	}

	result := &KsMap{
		Keys: append([]string(nil), base.Keys...),
		Values: make(map[string]any, len(base.Values)+1),
	}
	for name, item := range base.Values {
		result.Values[name] = item
	}

	current, exists := result.Values[key]
	if !exists {
		result.Keys = append(result.Keys, key)
		result.Values[key] = delta
		return result
	}
	added := ksAdd(current, delta)
	if failure, ok := added.(*KsError); ok {
		return failure
	}
	result.Values[key] = added
	return result
}

'''
    anchor = "func ksCallValueMethod(receiver any, method string, arguments ...any) any {"
    if "func ksMapAdd(" not in codegen.RUNTIME_PRELUDE:
        if anchor not in codegen.RUNTIME_PRELUDE:
            raise RuntimeError(
                "native value-method dispatcher changed; v0.10.13 patch refused"
            )
        codegen.RUNTIME_PRELUDE = codegen.RUNTIME_PRELUDE.replace(
            anchor, helper + anchor, 1
        )

    map_anchor = '''\t\tcase "merge":
\t\t\tif len(arguments) != 1 { return ksErrorf("KS4003: merge bir argüman alır") }
\t\t\treturn ksMapMerge(receiver, arguments[0])
'''
    map_replacement = map_anchor + '''\t\tcase "add":
\t\t\tif len(arguments) != 2 { return ksErrorf("KS4003: add anahtar ve delta alır") }
\t\t\treturn ksMapAdd(receiver, arguments[0], arguments[1])
'''
    if 'case "add":' not in codegen.RUNTIME_PRELUDE:
        if map_anchor not in codegen.RUNTIME_PRELUDE:
            raise RuntimeError(
                "native Map dispatcher changed; v0.10.13 patch refused"
            )
        codegen.RUNTIME_PRELUDE = codegen.RUNTIME_PRELUDE.replace(
            map_anchor, map_replacement, 1
        )


def install_map_add_v0113() -> None:
    global _INSTALLED
    if _INSTALLED:
        return

    semantic.MAP_METHODS.add(_METHOD)
    runtime.MAP_METHODS.add(_METHOD)
    codegen.MAP_METHODS.add(_METHOD)
    codegen.VALUE_METHODS.add(_METHOD)

    _semantic_method.original = semantic.SemanticChecker._check_method_call
    semantic.SemanticChecker._check_method_call = _semantic_method

    _typed_method.original = typed_ops.method_type
    typed_ops.method_type = _typed_method
    typed_expr.method_type = _typed_method

    _invoke_member.original = runtime.Interpreter._invoke_member
    runtime.Interpreter._invoke_member = _invoke_member

    _patch_native_runtime()
    _INSTALLED = True
