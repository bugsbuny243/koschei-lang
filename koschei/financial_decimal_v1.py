"""Language ABI for exact fixed-scale financial decimals.

This bridge is intentionally explicit. Decimal construction and arithmetic that
can fail return Koschei Error values; no operation converts through Float and no
implicit rescaling or rounding is performed.
"""

from __future__ import annotations

from . import codegen_go as _codegen
from . import interpreter as _runtime
from . import runtime_alignment as _alignment
from . import semantic as _semantic
from . import type_contracts as _contracts
from . import typed_hir as _typed_hir
from .ast_nodes import CallExpression, Identifier
from .financial_decimal import (
    DecimalValue,
    FinancialDecimalError,
    add_decimal,
    compare_decimal,
    decimal_text,
    parse_decimal,
    sub_decimal,
)
from .type_system import ERROR, INT, STRING, NamedType, union_type

_DECIMAL = NamedType("Decimal")
_BUILTINS = {
    "decimal",
    "decimal_add",
    "decimal_sub",
    "decimal_cmp",
    "decimal_text",
}
_FALLIBLE = {"decimal", "decimal_add", "decimal_sub", "decimal_cmp"}
_RETURN_NAMES = {
    "decimal": "Decimal or Error",
    "decimal_add": "Decimal or Error",
    "decimal_sub": "Decimal or Error",
    "decimal_cmp": "Int or Error",
    "decimal_text": "String",
}
_INSTALLED = False
_ORIGINAL_SEMANTIC_EXPRESSION = None
_ORIGINAL_SEMANTIC_FALLIBLE = None
_ORIGINAL_SEMANTIC_RECEIVER = None
_ORIGINAL_TYPED_CALL_TYPE = None
_ORIGINAL_RUNTIME_EVALUATE = None
_ORIGINAL_RUNTIME_INVOKE = None
_ORIGINAL_RUNTIME_TYPE_NODE = None
_ORIGINAL_RUNTIME_TO_STRING = None
_ORIGINAL_CODEGEN_CALL = None


_GO_RUNTIME = r'''
type KsDecimal struct {
	Atoms int64
	Scale int64
}

func ksDecimalDigits(text string) bool {
	if text == "" {
		return false
	}
	for _, char := range text {
		if char < '0' || char > '9' {
			return false
		}
	}
	return true
}

func ksDecimalParse(raw any, scaleValue any) any {
	text, ok := raw.(string)
	if !ok {
		return ksErrorf("KS3801: decimal() expects canonical String input")
	}
	scale, ok := scaleValue.(int64)
	if !ok || scale < 0 || scale > 18 {
		return ksErrorf("KS3801: decimal scale must be Int in 0..18")
	}
	if text == "" || strings.TrimSpace(text) != text || strings.HasPrefix(text, "+") {
		return ksErrorf("KS3801: invalid decimal text")
	}
	negative := strings.HasPrefix(text, "-")
	unsigned := text
	if negative {
		unsigned = strings.TrimPrefix(text, "-")
	}
	if unsigned == "" || strings.Count(unsigned, ".") > 1 {
		return ksErrorf("KS3801: invalid decimal text")
	}
	whole := unsigned
	fraction := ""
	if dot := strings.IndexByte(unsigned, '.'); dot >= 0 {
		whole = unsigned[:dot]
		fraction = unsigned[dot+1:]
		if fraction == "" {
			return ksErrorf("KS3801: invalid decimal text")
		}
	}
	if !ksDecimalDigits(whole) || (fraction != "" && !ksDecimalDigits(fraction)) {
		return ksErrorf("KS3801: invalid decimal text")
	}
	if len(whole) > 1 && whole[0] == '0' {
		return ksErrorf("KS3801: non-canonical leading zeroes are forbidden")
	}
	if int64(len(fraction)) > scale {
		return ksErrorf("KS3801: implicit decimal rounding is forbidden")
	}
	digits := whole + fraction + strings.Repeat("0", int(scale)-len(fraction))
	if negative {
		digits = "-" + digits
	}
	atoms, err := strconv.ParseInt(digits, 10, 64)
	if err != nil {
		return ksErrorf("KS3803: decimal atoms overflow signed int64")
	}
	return &KsDecimal{Atoms: atoms, Scale: scale}
}

func ksDecimalFormat(value *KsDecimal) string {
	digits := strconv.FormatInt(value.Atoms, 10)
	negative := strings.HasPrefix(digits, "-")
	if negative {
		digits = strings.TrimPrefix(digits, "-")
	}
	if value.Scale > 0 {
		needed := int(value.Scale) + 1
		if len(digits) < needed {
			digits = strings.Repeat("0", needed-len(digits)) + digits
		}
		cut := len(digits) - int(value.Scale)
		digits = digits[:cut] + "." + digits[cut:]
	}
	if negative && value.Atoms != 0 {
		return "-" + digits
	}
	return digits
}

func ksDecimalPair(left any, right any) (*KsDecimal, *KsDecimal, any) {
	a, ok := left.(*KsDecimal)
	if !ok {
		return nil, nil, ksErrorf("KS3801: operation expects Decimal values")
	}
	b, ok := right.(*KsDecimal)
	if !ok {
		return nil, nil, ksErrorf("KS3801: operation expects Decimal values")
	}
	if a.Scale != b.Scale {
		return nil, nil, ksErrorf("KS3802: decimal scales differ; implicit rescaling is forbidden")
	}
	return a, b, nil
}

func ksDecimalAdd(left any, right any) any {
	a, b, failure := ksDecimalPair(left, right)
	if failure != nil {
		return failure
	}
	if (b.Atoms > 0 && a.Atoms > ksIntMax-b.Atoms) ||
		(b.Atoms < 0 && a.Atoms < ksIntMin-b.Atoms) {
		return ksErrorf("KS3803: decimal addition overflow")
	}
	return &KsDecimal{Atoms: a.Atoms + b.Atoms, Scale: a.Scale}
}

func ksDecimalSub(left any, right any) any {
	a, b, failure := ksDecimalPair(left, right)
	if failure != nil {
		return failure
	}
	if (b.Atoms > 0 && a.Atoms < ksIntMin+b.Atoms) ||
		(b.Atoms < 0 && a.Atoms > ksIntMax+b.Atoms) {
		return ksErrorf("KS3803: decimal subtraction overflow")
	}
	return &KsDecimal{Atoms: a.Atoms - b.Atoms, Scale: a.Scale}
}

func ksDecimalCmp(left any, right any) any {
	a, b, failure := ksDecimalPair(left, right)
	if failure != nil {
		return failure
	}
	if a.Atoms < b.Atoms {
		return int64(-1)
	}
	if a.Atoms > b.Atoms {
		return int64(1)
	}
	return int64(0)
}

func ksDecimalText(value any) any {
	item, ok := value.(*KsDecimal)
	if !ok {
		return ksErrorf("KS3801: decimal_text() expects Decimal")
	}
	return ksDecimalFormat(item)
}
'''


def _semantic_expression(self, expression):
    if (
        isinstance(expression, CallExpression)
        and isinstance(expression.callee, Identifier)
        and expression.callee.name in _BUILTINS
    ):
        name = expression.callee.name
        types = [self._check_expression(item) for item in expression.arguments]
        expected = {
            "decimal": ("String", "Int"),
            "decimal_add": ("Decimal", "Decimal"),
            "decimal_sub": ("Decimal", "Decimal"),
            "decimal_cmp": ("Decimal", "Decimal"),
            "decimal_text": ("Decimal",),
        }[name]
        if len(types) != len(expected):
            raise _semantic.SemanticError(
                "KS1301",
                f"'{name}' {len(expected)} argüman bekler, {len(types)} verildi.",
                expression.location,
            )
        for index, (wanted, actual) in enumerate(zip(expected, types), start=1):
            self._require_assignable(
                (wanted,),
                actual,
                f"'{name}' çağrısının {index}. argümanı",
                expression.location,
            )
        return _RETURN_NAMES[name]
    return _ORIGINAL_SEMANTIC_EXPRESSION(self, expression)


def _semantic_fallible(self, expression):
    if (
        isinstance(expression, CallExpression)
        and isinstance(expression.callee, Identifier)
        and expression.callee.name in _FALLIBLE
    ):
        return True
    return _ORIGINAL_SEMANTIC_FALLIBLE(self, expression)


def _semantic_receiver(self, expression):
    if (
        isinstance(expression, CallExpression)
        and isinstance(expression.callee, Identifier)
        and expression.callee.name in _RETURN_NAMES
    ):
        return _RETURN_NAMES[expression.callee.name]
    return _ORIGINAL_SEMANTIC_RECEIVER(self, expression)


def _typed_call_type(self, name, arguments, location):
    if name not in _BUILTINS:
        return _ORIGINAL_TYPED_CALL_TYPE(self, name, arguments, location)
    expected = {
        "decimal": (STRING, INT),
        "decimal_add": (_DECIMAL, _DECIMAL),
        "decimal_sub": (_DECIMAL, _DECIMAL),
        "decimal_cmp": (_DECIMAL, _DECIMAL),
        "decimal_text": (_DECIMAL,),
    }[name]
    if len(arguments) != len(expected):
        raise _semantic.SemanticError(
            "KS1301",
            f"'{name}' {len(expected)} argüman bekler, {len(arguments)} verildi.",
            location,
        )
    for index, (wanted, actual) in enumerate(zip(expected, arguments), start=1):
        _contracts.require_assignable(
            wanted,
            actual,
            f"'{name}' çağrısının {index}. argümanı",
            location,
        )
    if name in {"decimal", "decimal_add", "decimal_sub"}:
        return union_type(_DECIMAL, ERROR)
    if name == "decimal_cmp":
        return union_type(INT, ERROR)
    return STRING


def _runtime_evaluate(self, expression):
    if isinstance(expression, Identifier) and expression.name in _BUILTINS:
        return expression.name
    return _ORIGINAL_RUNTIME_EVALUATE(self, expression)


def _runtime_invoke(self, callee, arguments, expression):
    if callee not in _BUILTINS:
        return _ORIGINAL_RUNTIME_INVOKE(self, callee, arguments, expression)
    expected = {
        "decimal": 2,
        "decimal_add": 2,
        "decimal_sub": 2,
        "decimal_cmp": 2,
        "decimal_text": 1,
    }[callee]
    self._require_arity(callee, arguments, expected, expression.location)
    try:
        if callee == "decimal":
            return parse_decimal(arguments[0], arguments[1])
        if callee == "decimal_add":
            return add_decimal(arguments[0], arguments[1])
        if callee == "decimal_sub":
            return sub_decimal(arguments[0], arguments[1])
        if callee == "decimal_cmp":
            return compare_decimal(arguments[0], arguments[1])
        if callee == "decimal_text":
            return decimal_text(arguments[0])
    except (FinancialDecimalError, TypeError, ValueError) as error:
        return _runtime.KsError(str(error))
    raise AssertionError(callee)


def _runtime_type_node(value):
    if isinstance(value, DecimalValue):
        return _DECIMAL
    return _ORIGINAL_RUNTIME_TYPE_NODE(value)


def _runtime_to_string(value):
    if isinstance(value, DecimalValue):
        return decimal_text(value)
    return _ORIGINAL_RUNTIME_TO_STRING(value)


def _codegen_call(self, expression, depth):
    if (
        isinstance(expression.callee, Identifier)
        and expression.callee.name in _BUILTINS
    ):
        name = expression.callee.name
        prelude: list[str] = []
        arguments: list[str] = []
        for argument in expression.arguments:
            value, argument_prelude = self._expression(argument, depth)
            prelude.extend(argument_prelude)
            arguments.append(value)
        expected = {
            "decimal": 2,
            "decimal_add": 2,
            "decimal_sub": 2,
            "decimal_cmp": 2,
            "decimal_text": 1,
        }[name]
        self._check_arity(name, arguments, expected, expression.location)
        helper = {
            "decimal": "ksDecimalParse",
            "decimal_add": "ksDecimalAdd",
            "decimal_sub": "ksDecimalSub",
            "decimal_cmp": "ksDecimalCmp",
            "decimal_text": "ksDecimalText",
        }[name]
        return f"{helper}({', '.join(arguments)})", prelude
    return _ORIGINAL_CODEGEN_CALL(self, expression, depth)


def _install_go_runtime() -> None:
    if "type KsDecimal struct" not in _codegen.RUNTIME_PRELUDE:
        _codegen.RUNTIME_PRELUDE += "\n" + _GO_RUNTIME
    marker = "\tcase ksUnitType:\n"
    decimal_case = "\tcase *KsDecimal:\n\t\treturn ksDecimalFormat(item)\n"
    if decimal_case not in _codegen.RUNTIME_PRELUDE:
        if marker not in _codegen.RUNTIME_PRELUDE:
            raise RuntimeError("Koschei native string ABI marker changed")
        _codegen.RUNTIME_PRELUDE = _codegen.RUNTIME_PRELUDE.replace(
            marker, decimal_case + marker, 1
        )


def install_financial_decimal_v1() -> None:
    global _INSTALLED
    global _ORIGINAL_SEMANTIC_EXPRESSION
    global _ORIGINAL_SEMANTIC_FALLIBLE
    global _ORIGINAL_SEMANTIC_RECEIVER
    global _ORIGINAL_TYPED_CALL_TYPE
    global _ORIGINAL_RUNTIME_EVALUATE
    global _ORIGINAL_RUNTIME_INVOKE
    global _ORIGINAL_RUNTIME_TYPE_NODE
    global _ORIGINAL_RUNTIME_TO_STRING
    global _ORIGINAL_CODEGEN_CALL
    if _INSTALLED:
        return

    _semantic.BUILTIN_CALLS.update(_BUILTINS)
    _contracts.RESERVED_TYPE_PARAMETERS.add("Decimal")

    _ORIGINAL_SEMANTIC_EXPRESSION = _semantic.SemanticChecker._check_expression
    _semantic.SemanticChecker._check_expression = _semantic_expression
    _ORIGINAL_SEMANTIC_FALLIBLE = _semantic.SemanticChecker._is_fallible_call
    _semantic.SemanticChecker._is_fallible_call = _semantic_fallible
    _ORIGINAL_SEMANTIC_RECEIVER = _semantic.SemanticChecker._receiver_type
    _semantic.SemanticChecker._receiver_type = _semantic_receiver

    _ORIGINAL_TYPED_CALL_TYPE = _typed_hir.TypedHIRChecker.call_type
    _typed_hir.TypedHIRChecker.call_type = _typed_call_type

    _ORIGINAL_RUNTIME_EVALUATE = _runtime.Interpreter._evaluate
    _runtime.Interpreter._evaluate = _runtime_evaluate
    _ORIGINAL_RUNTIME_INVOKE = _runtime.Interpreter._invoke
    _runtime.Interpreter._invoke = _runtime_invoke
    _ORIGINAL_RUNTIME_TYPE_NODE = _alignment._runtime_type_node
    _alignment._runtime_type_node = _runtime_type_node
    _ORIGINAL_RUNTIME_TO_STRING = _runtime.ks_to_string
    _runtime.ks_to_string = _runtime_to_string

    _ORIGINAL_CODEGEN_CALL = _codegen.GoCodegen._call
    _codegen.GoCodegen._call = _codegen_call
    _install_go_runtime()
    _INSTALLED = True
