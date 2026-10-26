"""Exact named-callback List mapping for Koschei v0.10.9.

``List<T>.map(fn(T) -> U) -> List<U>`` preserves source order, returns a fresh
list, and carries the callback's exact structural result type into Typed HIR.
Only local named functions are accepted in this slice; lambdas remain a
separate language feature rather than hidden syntax inside one collection API.
"""
from __future__ import annotations

from . import _typed_expr as typed_expr
from . import _typed_ops as typed_ops
from . import codegen_go as codegen
from . import interpreter as runtime
from . import semantic
from .ast_nodes import CallExpression, Identifier, MemberExpression
from .type_contracts import function_type, is_assignable, require_assignable
from .type_system import (
    ERROR,
    GenericType,
    NamedType,
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
_METHOD = "map"
_FUNCTION = "Fn"


def _require_one_argument(values, location) -> None:
    if len(values) != 1:
        raise semantic.SemanticError(
            "KS1301",
            f"List.map() 1 callback bekler, {len(values)} verildi.",
            location,
        )


def _function_value_type(function) -> GenericType:
    parameters = tuple(
        function_type(function, parameter.type_ref)
        for parameter in function.parameters
    )
    result = function_type(function, function.return_type)
    return generic(_FUNCTION, *parameters, result)


def _function_parts(type_node: TypeNode, location):
    if not isinstance(type_node, GenericType) or type_node.name != _FUNCTION:
        raise semantic.SemanticError(
            "KS1301",
            "List.map() yerel, adlandırılmış bir fonksiyon bekler.",
            location,
        )
    if not type_node.arguments:
        raise semantic.SemanticError(
            "KS1301",
            "List.map() callback imzası kanıtlanamadı.",
            location,
        )
    return type_node.arguments[:-1], type_node.arguments[-1]


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
                f"List.map() callback'i '{pattern.name}' için hem "
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


def _instantiate_callback(
    callback: TypeNode,
    item: TypeNode,
    location,
) -> tuple[TypeNode, TypeNode]:
    parameters, result_pattern = _function_parts(callback, location)
    if len(parameters) != 1:
        raise semantic.SemanticError(
            "KS1301",
            f"List.map() callback'i 1 parametre almalıdır, {len(parameters)} bulundu.",
            location,
        )

    mapping: dict[str, TypeNode] = {}
    _infer_pattern(parameters[0], item, mapping, location)
    expected_item = substitute_type(parameters[0], mapping)
    require_assignable(
        expected_item,
        item,
        "List.map() callback giriş tipi",
        location,
    )

    result = substitute_type(result_pattern, mapping)
    unresolved = unresolved_type_variables(result)
    if unresolved:
        raise semantic.SemanticError(
            "KS1307",
            "List.map() callback dönüş tipinde çözülemeyen tip parametresi: "
            + ", ".join(sorted(unresolved)),
            location,
        )
    if _contains_raw_error(result):
        raise semantic.SemanticError(
            "KS1306",
            "List.map() ham Error döndüren callback kabul etmez; "
            "fallible sonucu Result<T, Error> olarak taşıyın.",
            location,
        )
    return expected_item, result


def _typed_map_result(
    receiver: TypeNode,
    callback: TypeNode,
    location,
) -> tuple[TypeNode, tuple[TypeNode, ...], tuple[TypeNode, ...]]:
    if isinstance(receiver, UnionType):
        results: list[TypeNode] = []
        parameters: list[TypeNode] = []
        mapped_items: list[TypeNode] = []
        for option in alternatives(receiver):
            result, option_parameters, option_items = _typed_map_result(
                option, callback, location
            )
            results.append(result)
            parameters.extend(option_parameters)
            mapped_items.extend(option_items)
        return union_type(*results), tuple(parameters), tuple(mapped_items)

    if isinstance(receiver, GenericType) and receiver.name == "List":
        item = receiver.arguments[0] if receiver.arguments else UnknownType()
        parameter, mapped = _instantiate_callback(callback, item, location)
        return generic("List", mapped), (parameter,), (mapped,)

    if is_named(receiver, "List"):
        parameter, mapped = _instantiate_callback(
            callback, UnknownType(), location
        )
        return generic("List", mapped), (parameter,), (mapped,)

    raise semantic.SemanticError(
        "KS1306",
        f"List.map() yalnızca List üzerinde güvenlidir; {render_type(receiver)} bulundu.",
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
        and method_name == _METHOD
    ):
        _require_one_argument(argument_types or [], location)
        # Typed HIR owns the exact callback signature and List<U> result.
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
        _require_one_argument(arguments, location)
        result, parameters, mapped_items = _typed_map_result(
            receiver, arguments[0], location
        )
        for type_node in (*parameters, *mapped_items):
            if contains_named(type_node, set(semantic.CAPABILITY_TYPES)):
                raise semantic.SemanticError(
                    "KS2402",
                    "List.map() callback'i capability kabul edemez veya döndüremez.",
                    location,
                )
        return result
    return _typed_method.original(receiver, method, arguments, location)


def _infer_expression(checker, expression):
    if isinstance(expression, Identifier):
        local = checker.resolve(expression.name)
        if isinstance(local, UnknownType):
            function = checker.functions.get(expression.name)
            if function is not None:
                return checker.record(expression, _function_value_type(function))

    if (
        isinstance(expression, CallExpression)
        and isinstance(expression.callee, MemberExpression)
        and expression.callee.member == _METHOD
    ):
        arguments = tuple(checker.infer(item) for item in expression.arguments)
        _require_one_argument(arguments, expression.location)
        receiver = checker.infer(expression.callee.object)
        result, parameters, mapped_items = _typed_map_result(
            receiver, arguments[0], expression.location
        )
        for parameter in parameters:
            if checker.contracts.is_sensitive(parameter):
                raise semantic.SemanticError(
                    "KS2402",
                    "List.map() callback giriş tipi capability taşıyamaz.",
                    expression.location,
                )
        for mapped in mapped_items:
            if checker.contracts.is_sensitive(mapped):
                raise semantic.SemanticError(
                    "KS2402",
                    "List.map() callback dönüşü capability taşıyamaz.",
                    expression.location,
                )
        return checker.record(expression, result)

    return _infer_expression.original(checker, expression)


def _invoke_member(self, member, arguments):
    receiver = member.receiver
    if isinstance(receiver, list) and member.name == _METHOD:
        self._require_arity(_METHOD, arguments, 1, member.location)
        if runtime._contains_capability(receiver):
            raise runtime.KoscheiRuntimeError(
                "KS3401",
                "Capability taşıyan List üzerinde map() çalıştırılamaz.",
                member.location,
            )
        transform = arguments[0]
        if not isinstance(transform, runtime.FunctionDeclaration):
            return runtime.KsError(
                "List.map() yerel, adlandırılmış bir fonksiyon bekler"
            )
        if len(transform.parameters) != 1:
            return runtime.KsError("List.map() callback'i 1 parametre almalıdır")

        result = []
        for value in receiver:
            mapped = self._call_function(transform, [value])
            if isinstance(mapped, runtime.KsError):
                return mapped
            if runtime._contains_capability(mapped):
                raise runtime.KoscheiRuntimeError(
                    "KS3401",
                    "List.map() callback'i capability döndüremez.",
                    member.location,
                )
            result.append(mapped)
        return result
    return _invoke_member.original(self, member, arguments)


def _patch_native_runtime() -> None:
    helpers = r'''
func ksListMap(value any, transform any) any {
	list, ok := value.([]any)
	if !ok {
		return ksErrorf("List.map() bir List bekler")
	}
	if ksContainsCapability(list) {
		return ksErrorf("KS3401: Capability taşıyan List üzerinde map() çalıştırılamaz")
	}
	function, ok := transform.(func(any) any)
	if !ok {
		return ksErrorf("List.map() yerel, adlandırılmış ve tek parametreli bir fonksiyon bekler")
	}
	result := make([]any, 0, len(list))
	for _, item := range list {
		mapped := function(item)
		if failure, ok := mapped.(*KsError); ok {
			return failure
		}
		if ksContainsCapability(mapped) {
			return ksErrorf("KS3401: List.map() callback'i capability döndüremez")
		}
		result = append(result, mapped)
	}
	return result
}

'''
    anchor = "func ksCallValueMethod(receiver any, method string, arguments ...any) any {"
    if "func ksListMap(" not in codegen.RUNTIME_PRELUDE:
        if anchor not in codegen.RUNTIME_PRELUDE:
            raise RuntimeError("native value-method dispatcher changed; v0.10.9 patch refused")
        codegen.RUNTIME_PRELUDE = codegen.RUNTIME_PRELUDE.replace(
            anchor, helpers + anchor, 1
        )

    list_anchor = '''\t\tcase "filter":
\t\t\tif len(arguments) != 1 { return ksErrorf("KS4003: filter bir argüman alır") }
\t\t\treturn ksListFilter(receiver, arguments[0])
'''
    list_replacement = list_anchor + '''\t\tcase "map":
\t\t\tif len(arguments) != 1 { return ksErrorf("KS4003: map bir callback alır") }
\t\t\treturn ksListMap(receiver, arguments[0])
'''
    if 'case "map":' not in codegen.RUNTIME_PRELUDE:
        if list_anchor not in codegen.RUNTIME_PRELUDE:
            raise RuntimeError("native List dispatcher changed; v0.10.9 patch refused")
        codegen.RUNTIME_PRELUDE = codegen.RUNTIME_PRELUDE.replace(
            list_anchor, list_replacement, 1
        )


def install_list_map_v0109() -> None:
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

    _infer_expression.original = typed_expr.infer_expression
    typed_expr.infer_expression = _infer_expression

    _invoke_member.original = runtime.Interpreter._invoke_member
    runtime.Interpreter._invoke_member = _invoke_member

    _patch_native_runtime()
    _INSTALLED = True
