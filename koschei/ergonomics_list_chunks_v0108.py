"""Deterministic generic List chunking for Koschei v0.10.8.

``List<T>.chunks(Int) -> Result<List<List<T>>, Error>`` preserves source order,
returns fresh lists, and keeps the final short chunk.  Non-positive chunk sizes
are explicit errors rather than silent empty output or an infinite loop.
"""
from __future__ import annotations

from . import _typed_expr as typed_expr
from . import _typed_ops as typed_ops
from . import codegen_go as codegen
from . import interpreter as runtime
from . import semantic
from .type_contracts import require_assignable
from .type_system import ERROR, INT, GenericType, UnknownType, generic, is_named

_INSTALLED = False
_METHOD = "chunks"


def _require_one_argument(values, location) -> None:
    if len(values) != 1:
        raise semantic.SemanticError(
            "KS1301",
            f"List.chunks() 1 argüman bekler, {len(values)} verildi.",
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
        values = argument_types or []
        _require_one_argument(values, location)
        self._require_assignable(
            ("Int",), values[0], "List.chunks() parça boyutu", location
        )
        # Typed HIR owns the exact nested generic result.  The compatibility
        # checker carries a wildcard and cannot invent the element type.
        return "Result<_, Error>"
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
        require_assignable(
            INT, arguments[0], "List.chunks() parça boyutu", location
        )
        if isinstance(receiver, GenericType) and receiver.name == "List":
            item = receiver.arguments[0] if receiver.arguments else UnknownType()
            return generic(
                "Result",
                generic("List", generic("List", item)),
                ERROR,
            )
        if is_named(receiver, "List"):
            return generic(
                "Result",
                generic("List", generic("List", UnknownType())),
                ERROR,
            )
    return _typed_method.original(receiver, method, arguments, location)


def _result_ok(value):
    return runtime.EnumValue("Result", "Ok", value)


def _result_error(message: str):
    return runtime.EnumValue("Result", "Err", runtime.KsError(message))


def _invoke_member(self, member, arguments):
    receiver = member.receiver
    if isinstance(receiver, list) and member.name == _METHOD:
        self._require_arity(_METHOD, arguments, 1, member.location)
        if runtime._contains_capability(receiver):
            raise runtime.KoscheiRuntimeError(
                "KS3401",
                "Capability taşıyan List üzerinde chunks() çalıştırılamaz.",
                member.location,
            )
        size = arguments[0]
        if type(size) is not int:
            return _result_error("List.chunks() parça boyutu Int olmalıdır")
        if size <= 0:
            return _result_error(
                "List.chunks() parça boyutu sıfırdan büyük olmalıdır"
            )
        result = [
            list(receiver[start : start + size])
            for start in range(0, len(receiver), size)
        ]
        return _result_ok(result)
    return _invoke_member.original(self, member, arguments)


def _patch_native_runtime() -> None:
    helpers = r'''
func ksListChunks(value any, sizeValue any) any {
	list, ok := value.([]any)
	if !ok {
		return ksEnum("Result", "Err", ksErrorf("List.chunks() bir List bekler"), true)
	}
	if ksContainsCapability(list) {
		return ksErrorf("KS3401: Capability taşıyan List üzerinde chunks() çalıştırılamaz")
	}
	size, ok := sizeValue.(int64)
	if !ok {
		return ksEnum("Result", "Err", ksErrorf("List.chunks() parça boyutu Int olmalıdır"), true)
	}
	if size <= 0 {
		return ksEnum("Result", "Err", ksErrorf("List.chunks() parça boyutu sıfırdan büyük olmalıdır"), true)
	}
	result := make([]any, 0)
	length := int64(len(list))
	for start := int64(0); start < length; start += size {
		end := start + size
		if end > length {
			end = length
		}
		chunk := make([]any, int(end-start))
		copy(chunk, list[int(start):int(end)])
		result = append(result, chunk)
	}
	return ksEnum("Result", "Ok", result, true)
}

'''
    anchor = "func ksCallValueMethod(receiver any, method string, arguments ...any) any {"
    if "func ksListChunks(" not in codegen.RUNTIME_PRELUDE:
        if anchor not in codegen.RUNTIME_PRELUDE:
            raise RuntimeError("native value-method dispatcher changed; v0.10.8 patch refused")
        codegen.RUNTIME_PRELUDE = codegen.RUNTIME_PRELUDE.replace(
            anchor, helpers + anchor, 1
        )

    list_anchor = '''\t\tcase "flatten":
\t\t\tif len(arguments) != 0 { return ksErrorf("KS4003: flatten argüman almaz") }
\t\t\treturn ksListFlatten(receiver)
'''
    list_replacement = list_anchor + '''\t\tcase "chunks":
\t\t\tif len(arguments) != 1 { return ksErrorf("KS4003: chunks bir argüman alır") }
\t\t\treturn ksListChunks(receiver, arguments[0])
'''
    if 'case "chunks":' not in codegen.RUNTIME_PRELUDE:
        if list_anchor not in codegen.RUNTIME_PRELUDE:
            raise RuntimeError("native List dispatcher changed; v0.10.8 patch refused")
        codegen.RUNTIME_PRELUDE = codegen.RUNTIME_PRELUDE.replace(
            list_anchor, list_replacement, 1
        )


def install_list_chunks_v0108() -> None:
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
