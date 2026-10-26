"""Exact typed prefix accumulation for Koschei v0.10.12.

``List<T>.scan(U, fn(U, T) -> U) -> List<U>`` evaluates the reducer once per
source item, stores each updated accumulator, preserves source order, and never
mutates the receiver or initial value.
"""
from __future__ import annotations

from . import _typed_expr as typed_expr
from . import _typed_ops as typed_ops
from . import codegen_go as codegen
from . import interpreter as runtime
from . import semantic
from .type_contracts import is_assignable, require_assignable
from .type_system import (
    ERROR,
    GenericType,
    TypeNode,
    TypeVariable,
    UnionType,
    UnknownType,
    alternatives,
    contains_named,
    generic,
    is_named,
    render_type,
    substitute_type,
    union_type,
    unresolved_type_variables,
)

_INSTALLED = False
_METHOD = "scan"
_FUNCTION = "Fn"


def _require_two_arguments(values, location) -> None:
    if len(values) != 2:
        raise semantic.SemanticError(
            "KS1301",
            f"List.scan() başlangıç değeri ve reducer olmak üzere 2 argüman "
            f"bekler, {len(values)} verildi.",
            location,
        )


def _function_parts(type_node: TypeNode, location):
    if not isinstance(type_node, GenericType) or type_node.name != _FUNCTION:
        raise semantic.SemanticError(
            "KS1301",
            "List.scan() yerel, adlandırılmış bir reducer fonksiyonu bekler.",
            location,
        )
    if not type_node.arguments:
        raise semantic.SemanticError(
            "KS1301",
            "List.scan() reducer imzası kanıtlanamadı.",
            location,
        )
    parameters = type_node.arguments[:-1]
    if len(parameters) != 2:
        raise semantic.SemanticError(
            "KS1301",
            f"List.scan() reducer'ı 2 parametre almalıdır, "
            f"{len(parameters)} bulundu.",
            location,
        )
    return parameters, type_node.arguments[-1]


def _same_inference(left: TypeNode, right: TypeNode) -> bool:
    return is_assignable(left, right) and is_assignable(right, left)


def _infer_pattern(
    pattern: TypeNode,
    actual: TypeNode,
    mapping: dict[str, TypeNode],
    location,
) -> None:
    if isinstance(pattern, TypeVariable):
        if isinstance(actual, UnknownType):
            return
        previous = mapping.get(pattern.name)
        if previous is None:
            mapping[pattern.name] = actual
            return
        if not _same_inference(previous, actual):
            raise semantic.SemanticError(
                "KS1307",
                f"List.scan() reducer'ı '{pattern.name}' için hem "
                f"{render_type(previous)} hem {render_type(actual)} gerektiriyor.",
                location,
            )
        return

    if isinstance(pattern, GenericType) and isinstance(actual, GenericType):
        if pattern.name != actual.name or len(pattern.arguments) != len(actual.arguments):
            return
        for expected_item, actual_item in zip(pattern.arguments, actual.arguments):
            _infer_pattern(expected_item, actual_item, mapping, location)
        return

    if isinstance(pattern, UnionType):
        candidates = [
            option for option in pattern.options if is_assignable(option, actual)
        ]
        if len(candidates) == 1:
            _infer_pattern(candidates[0], actual, mapping, location)


def _contains_raw_error(type_node: TypeNode) -> bool:
    if type_node == ERROR:
        return True
    if isinstance(type_node, UnionType):
        return any(_contains_raw_error(option) for option in type_node.options)
    return False


def _instantiate_reducer(
    callback: TypeNode,
    accumulator: TypeNode,
    item: TypeNode,
    location,
) -> tuple[TypeNode, TypeNode, TypeNode]:
    parameters, result_pattern = _function_parts(callback, location)
    mapping: dict[str, TypeNode] = {}
    _infer_pattern(parameters[0], accumulator, mapping, location)
    _infer_pattern(parameters[1], item, mapping, location)

    expected_accumulator = substitute_type(parameters[0], mapping)
    expected_item = substitute_type(parameters[1], mapping)
    require_assignable(
        expected_accumulator,
        accumulator,
        "List.scan() reducer başlangıç tipi",
        location,
    )
    require_assignable(
        expected_item,
        item,
        "List.scan() reducer eleman tipi",
        location,
    )

    result = substitute_type(result_pattern, mapping)
    unresolved = unresolved_type_variables(result)
    if unresolved:
        raise semantic.SemanticError(
            "KS1307",
            "List.scan() reducer dönüş tipinde çözülemeyen tip parametresi: "
            + ", ".join(sorted(unresolved)),
            location,
        )
    if _contains_raw_error(result):
        raise semantic.SemanticError(
            "KS1306",
            "List.scan() ham Error döndüren reducer kabul etmez; "
            "fallible durumu Result<T, Error> içinde taşıyın.",
            location,
        )
    require_assignable(
        accumulator,
        result,
        "List.scan() reducer dönüş tipi",
        location,
    )
    return expected_accumulator, expected_item, result


def _typed_scan(
    receiver: TypeNode,
    accumulator: TypeNode,
    callback: TypeNode,
    location,
) -> TypeNode:
    if isinstance(receiver, UnionType):
        return union_type(
            *(
                _typed_scan(option, accumulator, callback, location)
                for option in alternatives(receiver)
            )
        )

    if isinstance(receiver, GenericType) and receiver.name == "List":
        item = receiver.arguments[0] if receiver.arguments else UnknownType()
    elif is_named(receiver, "List"):
        item = UnknownType()
    else:
        raise semantic.SemanticError(
            "KS1306",
            f"List.scan() yalnızca List üzerinde güvenlidir; "
            f"{render_type(receiver)} bulundu.",
            location,
        )

    expected_accumulator, expected_item, result = _instantiate_reducer(
        callback, accumulator, item, location
    )
    for type_node in (
        item,
        accumulator,
        expected_accumulator,
        expected_item,
        result,
    ):
        if contains_named(type_node, set(semantic.CAPABILITY_TYPES)):
            raise semantic.SemanticError(
                "KS2402",
                "List.scan() capability taşıyan değer veya reducer kabul etmez.",
                location,
            )

    output = result if isinstance(accumulator, UnknownType) else accumulator
    return generic("List", output)


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
        and method_name == _METHOD
    ):
        _require_two_arguments(argument_types or [], location)
        return "List"
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
        return _typed_scan(receiver, arguments[0], arguments[1], location)
    return _typed_method.original(receiver, method, arguments, location)


def _invoke_member(self, member, arguments):
    receiver = member.receiver
    if isinstance(receiver, list) and member.name == _METHOD:
        self._require_arity(_METHOD, arguments, 2, member.location)
        initial, reducer = arguments
        if runtime._contains_capability(receiver) or runtime._contains_capability(initial):
            raise runtime.KoscheiRuntimeError(
                "KS3401",
                "Capability taşıyan List veya başlangıç değeri üzerinde "
                "scan() çalıştırılamaz.",
                member.location,
            )
        if not isinstance(reducer, runtime.FunctionDeclaration):
            return runtime.KsError(
                "List.scan() yerel, adlandırılmış ve iki parametreli "
                "bir reducer bekler"
            )
        if len(reducer.parameters) != 2:
            return runtime.KsError(
                "List.scan() reducer'ı 2 parametre almalıdır"
            )

        accumulator = initial
        result = []
        for value in receiver:
            accumulator = self._call_function(reducer, [accumulator, value])
            if isinstance(accumulator, runtime.KsError):
                return accumulator
            if runtime._contains_capability(accumulator):
                raise runtime.KoscheiRuntimeError(
                    "KS3401",
                    "List.scan() reducer'ı capability döndüremez.",
                    member.location,
                )
            result.append(accumulator)
        return result
    return _invoke_member.original(self, member, arguments)


def _patch_native_runtime() -> None:
    helper = r'''
func ksListScan(value any, initial any, reducer any) any {
	list, ok := value.([]any)
	if !ok {
		return ksErrorf("List.scan() bir List bekler")
	}
	if ksContainsCapability(list) || ksContainsCapability(initial) {
		return ksErrorf("KS3401: Capability taşıyan List veya başlangıç değeri üzerinde scan() çalıştırılamaz")
	}
	function, ok := reducer.(func(any, any) any)
	if !ok {
		return ksErrorf("List.scan() yerel, adlandırılmış ve iki parametreli bir reducer bekler")
	}
	accumulator := initial
	result := make([]any, 0, len(list))
	for _, item := range list {
		accumulator = function(accumulator, item)
		if failure, ok := accumulator.(*KsError); ok {
			return failure
		}
		if ksContainsCapability(accumulator) {
			return ksErrorf("KS3401: List.scan() reducer'ı capability döndüremez")
		}
		result = append(result, accumulator)
	}
	return result
}

'''
    anchor = "func ksCallValueMethod(receiver any, method string, arguments ...any) any {"
    if "func ksListScan(" not in codegen.RUNTIME_PRELUDE:
        if anchor not in codegen.RUNTIME_PRELUDE:
            raise RuntimeError(
                "native value-method dispatcher changed; v0.10.12 patch refused"
            )
        codegen.RUNTIME_PRELUDE = codegen.RUNTIME_PRELUDE.replace(
            anchor, helper + anchor, 1
        )

    list_anchor = '''\t\tcase "partition":
\t\t\tif len(arguments) != 1 { return ksErrorf("KS4003: partition bir predicate alır") }
\t\t\treturn ksListPartition(receiver, arguments[0])
'''
    list_replacement = list_anchor + '''\t\tcase "scan":
\t\t\tif len(arguments) != 2 { return ksErrorf("KS4003: scan başlangıç değeri ve reducer alır") }
\t\t\treturn ksListScan(receiver, arguments[0], arguments[1])
'''
    if 'case "scan":' not in codegen.RUNTIME_PRELUDE:
        if list_anchor not in codegen.RUNTIME_PRELUDE:
            raise RuntimeError(
                "native List dispatcher changed; v0.10.12 patch refused"
            )
        codegen.RUNTIME_PRELUDE = codegen.RUNTIME_PRELUDE.replace(
            list_anchor, list_replacement, 1
        )


def install_list_scan_v0112() -> None:
    global _INSTALLED
    if _INSTALLED:
        return

    semantic.LIST_METHODS.add(_METHOD)
    runtime.LIST_METHODS.add(_METHOD)
    codegen.LIST_METHODS.add(_METHOD)
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
