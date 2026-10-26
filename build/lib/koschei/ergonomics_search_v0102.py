"""First-match collection search for Koschei v0.10.2."""
from __future__ import annotations

from . import _typed_expr as typed_expr
from . import _typed_ops as typed_ops
from . import ast_nodes as ast
from . import codegen_go as codegen
from . import interpreter as runtime
from . import semantic
from .type_contracts import require_assignable
from .type_system import BOOL, GenericType, UnknownType, generic, is_named

_INSTALLED = False


def _semantic_method(
    self,
    receiver_type,
    method_name,
    location,
    argument_types=None,
    arguments=None,
):
    if receiver_type == "List" and method_name == "find":
        values = argument_types or []
        expressions = arguments or []
        if len(values) != 1:
            raise semantic.SemanticError(
                "KS1301",
                f"List.find() 1 argüman bekler, {len(values)} verildi.",
                location,
            )
        predicate = expressions[0] if expressions else None
        if not isinstance(predicate, ast.Identifier) or predicate.name not in self.functions:
            raise semantic.SemanticError(
                "KS1301",
                "List.find() yerel, adlandırılmış bir predicate fonksiyonu bekler.",
                location,
            )
        function = self.functions[predicate.name]
        if len(function.parameters) != 1:
            raise semantic.SemanticError(
                "KS1301",
                f"List.find() predicate'i 1 argüman almalıdır; "
                f"'{function.name}' {len(function.parameters)} argüman alıyor.",
                location,
            )
        if function.return_type is None or function.return_type.names != ("Bool",):
            raise semantic.SemanticError(
                "KS1301",
                "List.find() predicate'i Bool döndürmelidir.",
                location,
            )
        return "Option<_>"
    return _semantic_method.original(
        self,
        receiver_type,
        method_name,
        location,
        argument_types,
        arguments,
    )


def _typed_method(receiver, method, arguments, location):
    if isinstance(receiver, GenericType) and receiver.name == "List" and method == "find":
        if len(arguments) != 1:
            raise semantic.SemanticError(
                "KS1301",
                f"List.find() 1 argüman bekler, {len(arguments)} verildi.",
                location,
            )
        require_assignable(BOOL, arguments[0], "List.find() predicate sonucu", location)
        item = receiver.arguments[0] if receiver.arguments else UnknownType()
        return generic("Option", item)
    if is_named(receiver, "List") and method == "find":
        if len(arguments) != 1:
            raise semantic.SemanticError(
                "KS1301",
                f"List.find() 1 argüman bekler, {len(arguments)} verildi.",
                location,
            )
        require_assignable(BOOL, arguments[0], "List.find() predicate sonucu", location)
        return generic("Option", UnknownType())
    return _typed_method.original(receiver, method, arguments, location)


def _invoke_member(self, member, arguments):
    if isinstance(member.receiver, list) and member.name == "find":
        self._require_arity("find", arguments, 1, member.location)
        predicate = arguments[0]
        if not isinstance(predicate, ast.FunctionDeclaration):
            return runtime.KsError(
                "List.find() yerel, adlandırılmış bir predicate fonksiyonu bekler"
            )
        for value in member.receiver:
            decision = self._call_function(predicate, [value])
            if isinstance(decision, runtime.KsError):
                return decision
            if not isinstance(decision, bool):
                return runtime.KsError("List.find() predicate'i Bool döndürmelidir")
            if decision:
                return runtime.EnumValue("Option", "Some", value)
        return runtime.EnumValue("Option", "None")
    return _invoke_member.original(self, member, arguments)


def _patch_native_runtime() -> None:
    helper = r'''
func ksListFind(value any, predicate any) any {
	list, ok := value.([]any)
	if !ok {
		return ksErrorf("List.find() bir List bekler")
	}
	function, ok := predicate.(func(any) any)
	if !ok {
		return ksErrorf("List.find() yerel, adlandırılmış bir predicate fonksiyonu bekler")
	}
	for _, item := range list {
		decision := function(item)
		if failure, ok := decision.(*KsError); ok {
			return failure
		}
		keep, ok := decision.(bool)
		if !ok {
			return ksErrorf("List.find() predicate'i Bool döndürmelidir")
		}
		if keep {
			return ksEnum("Option", "Some", item, true)
		}
	}
	return ksEnum("Option", "None", ksUnit, false)
}

'''
    anchor = "func ksCallValueMethod(receiver any, method string, arguments ...any) any {"
    if "func ksListFind(" not in codegen.RUNTIME_PRELUDE:
        if anchor not in codegen.RUNTIME_PRELUDE:
            raise RuntimeError("native value-method dispatcher changed; v0.10.2 patch refused")
        codegen.RUNTIME_PRELUDE = codegen.RUNTIME_PRELUDE.replace(
            anchor, helper + anchor, 1
        )

    dispatch_anchor = '''\t\tcase "filter":
\t\t\tif len(arguments) != 1 { return ksErrorf("KS4003: filter bir argüman alır") }
\t\t\treturn ksListFilter(receiver, arguments[0])
'''
    dispatch_replacement = dispatch_anchor + '''\t\tcase "find":
\t\t\tif len(arguments) != 1 { return ksErrorf("KS4003: find bir argüman alır") }
\t\t\treturn ksListFind(receiver, arguments[0])
'''
    if 'case "find":' not in codegen.RUNTIME_PRELUDE:
        if dispatch_anchor not in codegen.RUNTIME_PRELUDE:
            raise RuntimeError("native List dispatcher changed; v0.10.2 patch refused")
        codegen.RUNTIME_PRELUDE = codegen.RUNTIME_PRELUDE.replace(
            dispatch_anchor, dispatch_replacement, 1
        )


def install_search_v0102() -> None:
    global _INSTALLED
    if _INSTALLED:
        return

    semantic.LIST_METHODS.add("find")
    runtime.LIST_METHODS.add("find")
    codegen.LIST_METHODS.add("find")
    codegen.VALUE_METHODS.add("find")

    _semantic_method.original = semantic.SemanticChecker._check_method_call
    semantic.SemanticChecker._check_method_call = _semantic_method

    _typed_method.original = typed_ops.method_type
    typed_ops.method_type = _typed_method
    typed_expr.method_type = _typed_method

    _invoke_member.original = runtime.Interpreter._invoke_member
    runtime.Interpreter._invoke_member = _invoke_member

    _patch_native_runtime()
    _INSTALLED = True
