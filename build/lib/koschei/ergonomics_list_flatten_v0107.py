"""One-level structural List flattening for Koschei v0.10.7.

``List<List<T>>.flatten() -> List<T>`` preserves left-to-right order and
returns a fresh list.  Flattening is deliberately one level only: a
``List<List<List<T>>>`` becomes ``List<List<T>>`` rather than recursively
changing the data shape.
"""
from __future__ import annotations

from . import _typed_expr as typed_expr
from . import _typed_ops as typed_ops
from . import codegen_go as codegen
from . import interpreter as runtime
from . import semantic
from .type_system import GenericType, is_named, render_type

_INSTALLED = False
_METHOD = "flatten"


def _require_zero_arity(values, location) -> None:
    if values:
        raise semantic.SemanticError(
            "KS1301",
            f"List.flatten() argüman almaz, {len(values)} verildi.",
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
        # Typed HIR has already proved List<List<T>> and owns the exact T.
        # The compatibility checker sees erased collection names only.
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
        _require_zero_arity(arguments, location)
        if isinstance(receiver, GenericType) and receiver.name == "List":
            item = receiver.arguments[0] if receiver.arguments else None
            if isinstance(item, GenericType) and item.name == "List":
                return item
            raise semantic.SemanticError(
                "KS1306",
                "List.flatten() yalnızca kanıtlanmış List<List<T>> üzerinde "
                f"kullanılabilir; {render_type(receiver)} bulundu.",
                location,
            )
        if is_named(receiver, "List"):
            raise semantic.SemanticError(
                "KS1306",
                "List.flatten() için öğe tipinin List<T> olduğu kanıtlanmalıdır.",
                location,
            )
    return _typed_method.original(receiver, method, arguments, location)


def _invoke_member(self, member, arguments):
    receiver = member.receiver
    if isinstance(receiver, list) and member.name == _METHOD:
        self._require_arity(_METHOD, arguments, 0, member.location)
        if runtime._contains_capability(receiver):
            raise runtime.KoscheiRuntimeError(
                "KS3401",
                "Capability taşıyan List üzerinde flatten() çalıştırılamaz.",
                member.location,
            )
        result = []
        for group in receiver:
            if not isinstance(group, list):
                return runtime.KsError(
                    "List.flatten() tüm öğelerin List olmasını bekler"
                )
            result.extend(group)
        return result
    return _invoke_member.original(self, member, arguments)


def _patch_native_runtime() -> None:
    helpers = r'''
func ksListFlatten(value any) any {
	groups, ok := value.([]any)
	if !ok {
		return ksErrorf("List.flatten() bir List bekler")
	}
	if ksContainsCapability(groups) {
		return ksErrorf("KS3401: Capability taşıyan List üzerinde flatten() çalıştırılamaz")
	}
	total := 0
	for _, raw := range groups {
		group, ok := raw.([]any)
		if !ok {
			return ksErrorf("List.flatten() tüm öğelerin List olmasını bekler")
		}
		total += len(group)
	}
	result := make([]any, 0, total)
	for _, raw := range groups {
		group := raw.([]any)
		result = append(result, group...)
	}
	return result
}

'''
    anchor = "func ksCallValueMethod(receiver any, method string, arguments ...any) any {"
    if "func ksListFlatten(" not in codegen.RUNTIME_PRELUDE:
        if anchor not in codegen.RUNTIME_PRELUDE:
            raise RuntimeError("native value-method dispatcher changed; v0.10.7 patch refused")
        codegen.RUNTIME_PRELUDE = codegen.RUNTIME_PRELUDE.replace(
            anchor, helpers + anchor, 1
        )

    list_anchor = '''\t\tcase "unique":
\t\t\tif len(arguments) != 0 { return ksErrorf("KS4003: unique argüman almaz") }
\t\t\treturn ksListUnique(receiver)
'''
    list_replacement = list_anchor + '''\t\tcase "flatten":
\t\t\tif len(arguments) != 0 { return ksErrorf("KS4003: flatten argüman almaz") }
\t\t\treturn ksListFlatten(receiver)
'''
    if 'case "flatten":' not in codegen.RUNTIME_PRELUDE:
        if list_anchor not in codegen.RUNTIME_PRELUDE:
            raise RuntimeError("native List dispatcher changed; v0.10.7 patch refused")
        codegen.RUNTIME_PRELUDE = codegen.RUNTIME_PRELUDE.replace(
            list_anchor, list_replacement, 1
        )


def install_list_flatten_v0107() -> None:
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
