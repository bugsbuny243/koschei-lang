"""Stable structural List deduplication for Koschei v0.10.6.

``List<T>.unique() -> List<T>`` keeps the first occurrence of every value and
preserves source order.  It deliberately uses Koschei structural equality
instead of host-language hashing, so nested lists, maps, enums and structs stay
deterministic across the interpreter and generated Go runtime.
"""
from __future__ import annotations

from . import _typed_expr as typed_expr
from . import _typed_ops as typed_ops
from . import codegen_go as codegen
from . import interpreter as runtime
from . import semantic
from .type_system import GenericType, UnknownType, generic, is_named

_INSTALLED = False
_METHOD = "unique"


def _require_zero_arity(values, location) -> None:
    if values:
        raise semantic.SemanticError(
            "KS1301",
            f"List.unique() argüman almaz, {len(values)} verildi.",
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
        _require_zero_arity(argument_types or [], location)
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
        if isinstance(receiver, GenericType) and receiver.name == "List":
            _require_zero_arity(arguments, location)
            return receiver
        if is_named(receiver, "List"):
            _require_zero_arity(arguments, location)
            return generic("List", UnknownType())
    return _typed_method.original(receiver, method, arguments, location)


def _structurally_equal(left, right) -> bool:
    # Interpreter values are immutable value objects, lists and dictionaries;
    # Python equality is structural for those representations and matches the
    # generated runtime's ksEq contract.
    return left == right


def _invoke_member(self, member, arguments):
    receiver = member.receiver
    if isinstance(receiver, list) and member.name == _METHOD:
        self._require_arity(_METHOD, arguments, 0, member.location)
        if runtime._contains_capability(receiver):
            raise runtime.KoscheiRuntimeError(
                "KS3401",
                "Capability taşıyan List üzerinde unique() çalıştırılamaz.",
                member.location,
            )
        result = []
        for candidate in receiver:
            if any(_structurally_equal(existing, candidate) for existing in result):
                continue
            result.append(candidate)
        return result
    return _invoke_member.original(self, member, arguments)


def _patch_native_runtime() -> None:
    helpers = r'''
func ksListUnique(value any) any {
	list, ok := value.([]any)
	if !ok {
		return ksErrorf("List.unique() bir List bekler")
	}
	if ksContainsCapability(list) {
		return ksErrorf("KS3401: Capability taşıyan List üzerinde unique() çalıştırılamaz")
	}
	result := make([]any, 0, len(list))
	for _, candidate := range list {
		seen := false
		for _, existing := range result {
			if ksTruthy(ksEq(existing, candidate)) {
				seen = true
				break
			}
		}
		if !seen {
			result = append(result, candidate)
		}
	}
	return result
}

'''
    anchor = "func ksCallValueMethod(receiver any, method string, arguments ...any) any {"
    if "func ksListUnique(" not in codegen.RUNTIME_PRELUDE:
        if anchor not in codegen.RUNTIME_PRELUDE:
            raise RuntimeError("native value-method dispatcher changed; v0.10.6 patch refused")
        codegen.RUNTIME_PRELUDE = codegen.RUNTIME_PRELUDE.replace(
            anchor, helpers + anchor, 1
        )

    list_anchor = '''\t\tcase "sum", "min", "max":
\t\t\tif len(arguments) != 0 { return ksErrorf("KS4003: " + method + " argüman almaz") }
\t\t\treturn ksListNumericReduction(receiver, method)
'''
    list_replacement = list_anchor + '''\t\tcase "unique":
\t\t\tif len(arguments) != 0 { return ksErrorf("KS4003: unique argüman almaz") }
\t\t\treturn ksListUnique(receiver)
'''
    if 'case "unique":' not in codegen.RUNTIME_PRELUDE:
        if list_anchor not in codegen.RUNTIME_PRELUDE:
            raise RuntimeError("native List dispatcher changed; v0.10.6 patch refused")
        codegen.RUNTIME_PRELUDE = codegen.RUNTIME_PRELUDE.replace(
            list_anchor, list_replacement, 1
        )


def install_stable_unique_v0106() -> None:
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
