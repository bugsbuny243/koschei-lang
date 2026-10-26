"""Stable exact-callback List partitioning for Koschei v0.10.11.

``List<T>.partition(fn(T) -> Bool) -> List<List<T>>`` returns two fresh lists:
matching values first, rejected values second. Source order is preserved in both
partitions and the receiver is never mutated.
"""
from __future__ import annotations

from . import _typed_expr as typed_expr
from . import _typed_ops as typed_ops
from . import codegen_go as codegen
from . import interpreter as runtime
from . import semantic
from .ergonomics_list_map_v0109 import _instantiate_callback
from .type_contracts import require_assignable
from .type_system import (
    BOOL,
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
_METHOD = "partition"


def _require_one_argument(values, location) -> None:
    if len(values) != 1:
        raise semantic.SemanticError(
            "KS1301",
            f"List.partition() 1 predicate bekler, {len(values)} verildi.",
            location,
        )


def _typed_partition(receiver: TypeNode, callback: TypeNode, location) -> TypeNode:
    if isinstance(receiver, UnionType):
        return union_type(
            *(
                _typed_partition(option, callback, location)
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
            f"List.partition() yalnızca List üzerinde güvenlidir; "
            f"{render_type(receiver)} bulundu.",
            location,
        )

    parameter, result = _instantiate_callback(callback, item, location)
    require_assignable(
        BOOL,
        result,
        "List.partition() predicate dönüş tipi",
        location,
    )
    for type_node in (item, parameter, result):
        if contains_named(type_node, set(semantic.CAPABILITY_TYPES)):
            raise semantic.SemanticError(
                "KS2402",
                "List.partition() capability taşıyan değer veya callback kabul etmez.",
                location,
            )
    return generic("List", generic("List", item))


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
        # Typed HIR owns the exact List<List<T>> result and callback contract.
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
        return _typed_partition(receiver, arguments[0], location)
    return _typed_method.original(receiver, method, arguments, location)


def _invoke_member(self, member, arguments):
    receiver = member.receiver
    if isinstance(receiver, list) and member.name == _METHOD:
        self._require_arity(_METHOD, arguments, 1, member.location)
        if runtime._contains_capability(receiver):
            raise runtime.KoscheiRuntimeError(
                "KS3401",
                "Capability taşıyan List üzerinde partition() çalıştırılamaz.",
                member.location,
            )
        predicate = arguments[0]
        if not isinstance(predicate, runtime.FunctionDeclaration):
            return runtime.KsError(
                "List.partition() yerel, adlandırılmış ve tek parametreli "
                "bir predicate bekler"
            )
        if len(predicate.parameters) != 1:
            return runtime.KsError(
                "List.partition() predicate'i 1 parametre almalıdır"
            )

        matching = []
        rejected = []
        for value in receiver:
            decision = self._call_function(predicate, [value])
            if isinstance(decision, runtime.KsError):
                return decision
            if not isinstance(decision, bool):
                return runtime.KsError(
                    "List.partition() predicate'i Bool döndürmelidir"
                )
            if decision:
                matching.append(value)
            else:
                rejected.append(value)
        return [matching, rejected]
    return _invoke_member.original(self, member, arguments)


def _patch_native_runtime() -> None:
    helper = r'''
func ksListPartition(value any, predicate any) any {
	list, ok := value.([]any)
	if !ok {
		return ksErrorf("List.partition() bir List bekler")
	}
	if ksContainsCapability(list) {
		return ksErrorf("KS3401: Capability taşıyan List üzerinde partition() çalıştırılamaz")
	}
	function, ok := predicate.(func(any) any)
	if !ok {
		return ksErrorf("List.partition() yerel, adlandırılmış ve tek parametreli bir predicate bekler")
	}
	matching := make([]any, 0, len(list))
	rejected := make([]any, 0, len(list))
	for _, item := range list {
		decision := function(item)
		if failure, ok := decision.(*KsError); ok {
			return failure
		}
		match, ok := decision.(bool)
		if !ok {
			return ksErrorf("List.partition() predicate'i Bool döndürmelidir")
		}
		if match {
			matching = append(matching, item)
		} else {
			rejected = append(rejected, item)
		}
	}
	return []any{matching, rejected}
}

'''
    anchor = "func ksCallValueMethod(receiver any, method string, arguments ...any) any {"
    if "func ksListPartition(" not in codegen.RUNTIME_PRELUDE:
        if anchor not in codegen.RUNTIME_PRELUDE:
            raise RuntimeError(
                "native value-method dispatcher changed; v0.10.11 patch refused"
            )
        codegen.RUNTIME_PRELUDE = codegen.RUNTIME_PRELUDE.replace(
            anchor, helper + anchor, 1
        )

    list_anchor = '''\t\tcase "any":
\t\t\tif len(arguments) != 1 { return ksErrorf("KS4003: any bir predicate alır") }
\t\t\treturn ksListAny(receiver, arguments[0])
'''
    list_replacement = list_anchor + '''\t\tcase "partition":
\t\t\tif len(arguments) != 1 { return ksErrorf("KS4003: partition bir predicate alır") }
\t\t\treturn ksListPartition(receiver, arguments[0])
'''
    if 'case "partition":' not in codegen.RUNTIME_PRELUDE:
        if list_anchor not in codegen.RUNTIME_PRELUDE:
            raise RuntimeError(
                "native List dispatcher changed; v0.10.11 patch refused"
            )
        codegen.RUNTIME_PRELUDE = codegen.RUNTIME_PRELUDE.replace(
            list_anchor, list_replacement, 1
        )


def install_list_partition_v0111() -> None:
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
