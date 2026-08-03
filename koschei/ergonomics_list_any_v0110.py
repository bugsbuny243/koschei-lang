"""Short-circuiting exact-callback List.any for Koschei v0.10.10.

``List<T>.any(fn(T) -> Bool) -> Bool`` accepts the structural callback values
introduced in v0.10.9.  It preserves the source, returns false for an empty
list, and stops evaluating as soon as one predicate call returns true.
"""
from __future__ import annotations

from . import _typed_expr as typed_expr
from . import _typed_ops as typed_ops
from . import codegen_go as codegen
from . import interpreter as runtime
from . import semantic
from .ergonomics_list_map_v0109 import _instantiate_callback, _require_one_argument
from .type_contracts import require_assignable
from .type_system import (
    BOOL,
    GenericType,
    TypeNode,
    UnionType,
    UnknownType,
    alternatives,
    contains_named,
    is_named,
    render_type,
)

_INSTALLED = False
_METHOD = "any"


def _typed_any(receiver: TypeNode, callback: TypeNode, location) -> TypeNode:
    if isinstance(receiver, UnionType):
        for option in alternatives(receiver):
            _typed_any(option, callback, location)
        return BOOL

    if isinstance(receiver, GenericType) and receiver.name == "List":
        item = receiver.arguments[0] if receiver.arguments else UnknownType()
    elif is_named(receiver, "List"):
        item = UnknownType()
    else:
        raise semantic.SemanticError(
            "KS1306",
            f"List.any() yalnızca List üzerinde güvenlidir; {render_type(receiver)} bulundu.",
            location,
        )

    parameter, result = _instantiate_callback(callback, item, location)
    require_assignable(
        BOOL,
        result,
        "List.any() predicate dönüş tipi",
        location,
    )
    for type_node in (parameter, result):
        if contains_named(type_node, set(semantic.CAPABILITY_TYPES)):
            raise semantic.SemanticError(
                "KS2402",
                "List.any() callback'i capability kabul edemez veya döndüremez.",
                location,
            )
    return BOOL


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
        # Exact callback validation belongs to Typed HIR.
        return "Bool"
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
        return _typed_any(receiver, arguments[0], location)
    return _typed_method.original(receiver, method, arguments, location)


def _invoke_member(self, member, arguments):
    receiver = member.receiver
    if isinstance(receiver, list) and member.name == _METHOD:
        self._require_arity(_METHOD, arguments, 1, member.location)
        if runtime._contains_capability(receiver):
            raise runtime.KoscheiRuntimeError(
                "KS3401",
                "Capability taşıyan List üzerinde any() çalıştırılamaz.",
                member.location,
            )
        predicate = arguments[0]
        if not isinstance(predicate, runtime.FunctionDeclaration):
            return runtime.KsError(
                "List.any() yerel, adlandırılmış ve tek parametreli bir predicate bekler"
            )
        if len(predicate.parameters) != 1:
            return runtime.KsError("List.any() predicate'i 1 parametre almalıdır")

        for value in receiver:
            decision = self._call_function(predicate, [value])
            if isinstance(decision, runtime.KsError):
                return decision
            if not isinstance(decision, bool):
                return runtime.KsError("List.any() predicate'i Bool döndürmelidir")
            if decision:
                return True
        return False
    return _invoke_member.original(self, member, arguments)


def _patch_native_runtime() -> None:
    helper = r'''
func ksListAny(value any, predicate any) any {
	list, ok := value.([]any)
	if !ok {
		return ksErrorf("List.any() bir List bekler")
	}
	if ksContainsCapability(list) {
		return ksErrorf("KS3401: Capability taşıyan List üzerinde any() çalıştırılamaz")
	}
	function, ok := predicate.(func(any) any)
	if !ok {
		return ksErrorf("List.any() yerel, adlandırılmış ve tek parametreli bir predicate bekler")
	}
	for _, item := range list {
		decision := function(item)
		if failure, ok := decision.(*KsError); ok {
			return failure
		}
		match, ok := decision.(bool)
		if !ok {
			return ksErrorf("List.any() predicate'i Bool döndürmelidir")
		}
		if match {
			return true
		}
	}
	return false
}

'''
    anchor = "func ksCallValueMethod(receiver any, method string, arguments ...any) any {"
    if "func ksListAny(" not in codegen.RUNTIME_PRELUDE:
        if anchor not in codegen.RUNTIME_PRELUDE:
            raise RuntimeError("native value-method dispatcher changed; v0.10.10 patch refused")
        codegen.RUNTIME_PRELUDE = codegen.RUNTIME_PRELUDE.replace(
            anchor, helper + anchor, 1
        )

    list_anchor = '''\t\tcase "map":
\t\t\tif len(arguments) != 1 { return ksErrorf("KS4003: map bir callback alır") }
\t\t\treturn ksListMap(receiver, arguments[0])
'''
    list_replacement = list_anchor + '''\t\tcase "any":
\t\t\tif len(arguments) != 1 { return ksErrorf("KS4003: any bir predicate alır") }
\t\t\treturn ksListAny(receiver, arguments[0])
'''
    if 'case "any":' not in codegen.RUNTIME_PRELUDE:
        if list_anchor not in codegen.RUNTIME_PRELUDE:
            raise RuntimeError("native List dispatcher changed; v0.10.10 patch refused")
        codegen.RUNTIME_PRELUDE = codegen.RUNTIME_PRELUDE.replace(
            list_anchor, list_replacement, 1
        )


def install_list_any_v0110() -> None:
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
