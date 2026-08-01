"""Language-level bridge for the bounded ``koschei.data-json/v1`` core.

This bootstrap bridge keeps the public Data ABI in one isolated module while the
interpreter and generated Go runtime still consume the legacy AST directly. It
can be removed when both backends consume native Typed HIR stdlib declarations.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Any

from . import codegen_go as _codegen
from . import interpreter as _runtime
from . import runtime_alignment as _alignment
from . import semantic as _semantic
from . import stdlib_catalog as _stdlib
from .ast_nodes import CallExpression, Identifier
from .data_json_v1 import DataError, decode, encode
from .type_system import NamedType

_INSTALLED = False
_ORIGINAL_SEMANTIC_CHECK_EXPRESSION = None
_ORIGINAL_SEMANTIC_IS_FALLIBLE = None
_ORIGINAL_SEMANTIC_RECEIVER_TYPE = None
_ORIGINAL_RUNTIME_EVALUATE = None
_ORIGINAL_RUNTIME_INVOKE = None
_ORIGINAL_RUNTIME_TO_STRING = None
_ORIGINAL_RUNTIME_TYPE_NODE = None
_ORIGINAL_CODEGEN_CALL = None
_ORIGINAL_CODEGEN_GENERATE = None


@dataclass(frozen=True, slots=True)
class DataValue:
    """Opaque Koschei Data value.

    User code cannot reach the host representation. The only initial public
    operations are bounded decode and canonical encode.
    """

    value: Any


def _semantic_check_expression(self, expression):
    if isinstance(expression, CallExpression) and isinstance(
        expression.callee, Identifier
    ):
        name = expression.callee.name
        if name in {"parse_json", "encode_json"}:
            if len(expression.arguments) != 1:
                raise _semantic.SemanticError(
                    "KS1301",
                    f"{name}() 1 argüman bekler, {len(expression.arguments)} verildi.",
                    expression.location,
                )
            actual = self._check_expression(expression.arguments[0])
            expected = "String" if name == "parse_json" else "Data"
            self._require_assignable(
                (expected,), actual, f"{name}() argümanı", expression.location
            )
            return "Data" if name == "parse_json" else "String"

        if name in {"print", "println", "Error"} and len(expression.arguments) == 1:
            actual = self._check_expression(expression.arguments[0])
            if actual == "Data":
                raise _semantic.SemanticError(
                    "KS3608",
                    "Data değeri doğrudan metne çevrilemez; önce encode_json(data) kullanın.",
                    expression.location,
                )

    return _ORIGINAL_SEMANTIC_CHECK_EXPRESSION(self, expression)


def _semantic_is_fallible(self, expression):
    if (
        isinstance(expression, CallExpression)
        and isinstance(expression.callee, Identifier)
        and expression.callee.name in {"parse_json", "encode_json"}
    ):
        return True
    return _ORIGINAL_SEMANTIC_IS_FALLIBLE(self, expression)


def _semantic_receiver_type(self, expression):
    if isinstance(expression, CallExpression) and isinstance(
        expression.callee, Identifier
    ):
        if expression.callee.name == "parse_json":
            return "Data"
        if expression.callee.name == "encode_json":
            return "String"
    return _ORIGINAL_SEMANTIC_RECEIVER_TYPE(self, expression)


def _runtime_evaluate(self, expression):
    if isinstance(expression, Identifier) and expression.name in {
        "parse_json",
        "encode_json",
    }:
        return expression.name
    return _ORIGINAL_RUNTIME_EVALUATE(self, expression)


def _runtime_invoke(self, callee, arguments, location):
    if callee == "parse_json":
        self._require_arity("parse_json", arguments, 1, location)
        raw = arguments[0]
        if not isinstance(raw, str):
            return _runtime.KsError("KS3608: parse_json() String bekler")
        try:
            return DataValue(decode(raw))
        except DataError as error:
            return _runtime.KsError(str(error))

    if callee == "encode_json":
        self._require_arity("encode_json", arguments, 1, location)
        value = arguments[0]
        if not isinstance(value, DataValue):
            return _runtime.KsError("KS3608: encode_json() Data bekler")
        try:
            return encode(value.value)
        except DataError as error:
            return _runtime.KsError(str(error))

    return _ORIGINAL_RUNTIME_INVOKE(self, callee, arguments, location)


def _runtime_to_string(value: Any) -> str:
    if isinstance(value, DataValue):
        return "<data>"
    return _ORIGINAL_RUNTIME_TO_STRING(value)


def _runtime_type_node(value: Any):
    if isinstance(value, DataValue):
        return NamedType("Data")
    return _ORIGINAL_RUNTIME_TYPE_NODE(value)


def _go_data_runtime() -> str:
    """Load the audited native data-json/v1 core into standalone output.

    Generated binaries are self-contained. The source is transformed from
    package datajson into declarations inside the generated package main.
    Missing or unexpectedly shaped source fails closed.
    """
    from pathlib import Path
    import re

    path = Path(__file__).resolve().parents[1] / "native" / "datajson" / "json.go"
    try:
        source = path.read_text(encoding="utf-8")
    except OSError as error:
        raise RuntimeError(
            "native/datajson/json.go is required to generate the Data ABI"
        ) from error
    body = re.sub(
        r"\A// Package datajson.*?\npackage datajson\n\nimport \(\n.*?\n\)\n\n",
        "",
        source,
        count=1,
        flags=re.DOTALL,
    )
    if body == source:
        raise RuntimeError("native data-json/v1 source shape changed; embedding refused")
    wrappers = r'''
type KsData struct {
	Value any
}

func ksDataParse(raw any) any {
	text, ok := raw.(string)
	if !ok {
		return ksErrorf("KS3608 [byte 0]: parse_json() expects String")
	}
	value, err := Decode(text, DefaultLimits)
	if err != nil {
		return ksErrorf(err.Error())
	}
	return &KsData{Value: value}
}

func ksDataEncode(raw any) any {
	data, ok := raw.(*KsData)
	if !ok {
		return ksErrorf("KS3608 [byte 0]: encode_json() expects Data")
	}
	text, err := Encode(data.Value, DefaultLimits)
	if err != nil {
		return ksErrorf(err.Error())
	}
	return text
}
'''
    return body + "\n" + wrappers


def _codegen_call(self, expression, depth):
    if isinstance(expression.callee, Identifier) and expression.callee.name in {
        "parse_json",
        "encode_json",
    }:
        prelude: list[str] = []
        arguments: list[str] = []
        for argument in expression.arguments:
            value, argument_prelude = self._expression(argument, depth)
            prelude.extend(argument_prelude)
            arguments.append(value)
        self._check_arity(expression.callee.name, arguments, 1, expression.location)
        helper = (
            "ksDataParse"
            if expression.callee.name == "parse_json"
            else "ksDataEncode"
        )
        return f"{helper}({arguments[0]})", prelude
    return _ORIGINAL_CODEGEN_CALL(self, expression, depth)


def _codegen_generate(self) -> str:
    source = _ORIGINAL_CODEGEN_GENERATE(self)
    if '"unicode/utf16"' not in source:
        source = source.replace(
            "import (\n",
            'import (\n\t"unicode/utf16"\n\t"unicode/utf8"\n',
            1,
        )
    marker = "\nfunc main() {"
    runtime = _go_data_runtime()
    if "func ksDataParse" not in source:
        source = source.replace(marker, "\n" + runtime + marker, 1)
    source = source.replace(
        "\tcase *KsError:\n\t\treturn item.Message",
        "\tcase *KsData:\n\t\treturn \"<data>\"\n\tcase *KsError:\n\t\treturn item.Message",
        1,
    )
    return source


def _register_diagnostics() -> None:
    from .diagnostics import CATALOG, ENGLISH_CATALOG, Diagnostic

    descriptions = {
        "KS3601": ("JSON girdi boyutu aşıldı", "JSON input byte limit exceeded"),
        "KS3602": ("JSON derinlik sınırı aşıldı", "JSON depth limit exceeded"),
        "KS3603": ("JSON düğüm sınırı aşıldı", "JSON node limit exceeded"),
        "KS3604": ("Yinelenen JSON anahtarı", "Duplicate JSON object key"),
        "KS3605": ("Geçersiz JSON", "Invalid JSON"),
        "KS3607": ("JSON çıktı boyutu aşıldı", "JSON output byte limit exceeded"),
        "KS3608": (
            "Data kodlama sözleşmesi ihlali",
            "Data encoding contract violation",
        ),
    }
    for code, (tr, en) in descriptions.items():
        CATALOG.setdefault(
            code,
            Diagnostic(
                code,
                tr,
                tr + ".",
                "data-json/v1 işlemi fail-closed reddedildi.",
                "Girdiyi veya bütçeyi düzeltin.",
                'let data = parse_json("{}") or return',
            ),
        )
        ENGLISH_CATALOG.setdefault(
            code,
            Diagnostic(
                code,
                en,
                en + ".",
                "The data-json/v1 operation failed closed.",
                "Fix the input or resource budget.",
                'let data = parse_json("{}") or return',
            ),
        )


def _promote_stdlib_contract() -> None:
    operations = (
        _stdlib.Operation(
            "parse_json",
            "supported",
            True,
            True,
            None,
            ("input_bytes", "nodes", "depth"),
            ("input_bytes", "nodes", "depth"),
            True,
            "Returns opaque Data or a KS360x error value.",
        ),
        _stdlib.Operation(
            "encode_json",
            "supported",
            True,
            True,
            None,
            ("output_bytes", "nodes", "depth"),
            ("output_bytes", "nodes", "depth"),
            True,
            "Accepts only opaque Data and emits canonical JSON.",
        ),
        _stdlib.Operation(
            "validate",
            "planned",
            False,
            False,
            None,
            ("nodes", "depth", "work"),
            (),
            True,
            "Schema-guided validation remains planned.",
        ),
    )
    _stdlib.CATALOG = tuple(
        replace(family, status="bootstrap", operations=operations)
        if family.name == "data"
        else family
        for family in _stdlib.CATALOG
    )
    _stdlib.validate_catalog.__defaults__ = (_stdlib.CATALOG,)
    _stdlib.document.__defaults__ = (_stdlib.CATALOG,)


def install_data_language_v1() -> None:
    global _INSTALLED
    global _ORIGINAL_SEMANTIC_CHECK_EXPRESSION, _ORIGINAL_SEMANTIC_IS_FALLIBLE
    global _ORIGINAL_SEMANTIC_RECEIVER_TYPE
    global _ORIGINAL_RUNTIME_EVALUATE, _ORIGINAL_RUNTIME_INVOKE
    global _ORIGINAL_RUNTIME_TO_STRING, _ORIGINAL_RUNTIME_TYPE_NODE
    global _ORIGINAL_CODEGEN_CALL, _ORIGINAL_CODEGEN_GENERATE

    if _INSTALLED:
        return

    _ORIGINAL_SEMANTIC_CHECK_EXPRESSION = _semantic.SemanticChecker._check_expression
    _ORIGINAL_SEMANTIC_IS_FALLIBLE = _semantic.SemanticChecker._is_fallible_call
    _ORIGINAL_SEMANTIC_RECEIVER_TYPE = _semantic.SemanticChecker._receiver_type
    _semantic.BUILTIN_CALLS.add("encode_json")
    _semantic.SemanticChecker._check_expression = _semantic_check_expression
    _semantic.SemanticChecker._is_fallible_call = _semantic_is_fallible
    _semantic.SemanticChecker._receiver_type = _semantic_receiver_type

    _ORIGINAL_RUNTIME_EVALUATE = _runtime.Interpreter._evaluate
    _ORIGINAL_RUNTIME_INVOKE = _runtime.Interpreter._invoke
    _ORIGINAL_RUNTIME_TO_STRING = _runtime.ks_to_string
    _runtime.Interpreter._evaluate = _runtime_evaluate
    _runtime.Interpreter._invoke = _runtime_invoke
    _runtime.ks_to_string = _runtime_to_string
    _runtime.DataValue = DataValue

    _ORIGINAL_RUNTIME_TYPE_NODE = _alignment._runtime_type_node
    _alignment._runtime_type_node = _runtime_type_node

    _ORIGINAL_CODEGEN_CALL = _codegen.GoCodegen._call
    _ORIGINAL_CODEGEN_GENERATE = _codegen.GoCodegen.generate
    _codegen.GoCodegen._call = _codegen_call
    _codegen.GoCodegen.generate = _codegen_generate

    _register_diagnostics()
    _promote_stdlib_contract()
    _INSTALLED = True
