"""Exact financial decimals for MIR-Go native binaries.

decimal, decimal_add, decimal_sub, decimal_cmp and decimal_text with the
results and messages of the Python core (financial_decimal): int64 atoms at
an explicit scale, no Float, no implicit rounding or rescaling.
"""

from __future__ import annotations

DECIMAL_BUILTINS = {
    "decimal": "_ksDecimalParse",
    "decimal_add": "_ksDecimalAdd",
    "decimal_sub": "_ksDecimalSub",
    "decimal_cmp": "_ksDecimalCmp",
    "decimal_text": "_ksDecimalTextOf",
}
DECIMAL_ARITY = {"decimal": 2, "decimal_add": 2, "decimal_sub": 2, "decimal_cmp": 2}

DECIMAL_RUNTIME = r"""
func _ksDecimalParse(rawValue any, scaleValue any) any {
	raw, ok := rawValue.(string)
	if !ok {
		return _ksError{message: "KS3801: decimal() expects canonical String input"}
	}
	scale, ok := scaleValue.(int64)
	if !ok {
		return _ksError{message: "KS3801: decimal scale must be Int"}
	}
	if scale < 0 || scale > 18 {
		return _ksError{message: "KS3801: decimal scale must be 0..18"}
	}
	unsigned := strings.TrimPrefix(raw, "-")
	negative := len(unsigned) != len(raw)
	whole, fraction, dotted := strings.Cut(unsigned, ".")
	digitsOnly := func(text string) bool {
		if text == "" {
			return false
		}
		for index := 0; index < len(text); index++ {
			if text[index] < '0' || text[index] > '9' {
				return false
			}
		}
		return true
	}
	if !digitsOnly(whole) || (len(whole) > 1 && whole[0] == '0') || (dotted && !digitsOnly(fraction)) {
		return _ksError{message: "KS3801: invalid decimal text; exponent, whitespace, plus sign and " +
			"non-canonical leading zeroes are forbidden"}
	}
	if int64(len(fraction)) > scale {
		return _ksError{message: "KS3801: decimal input has more fractional digits than the declared scale; " +
			"implicit rounding is forbidden"}
	}
	digits := whole + fraction + strings.Repeat("0", int(scale)-len(fraction))
	if negative {
		digits = "-" + digits
	}
	atoms, err := strconv.ParseInt(digits, 10, 64)
	if err != nil {
		return _ksError{message: "KS3803: decimal atoms overflow signed int64"}
	}
	return _ksDecimal{atoms: atoms, scale: scale}
}

func _ksDecimalPair(left any, right any) (_ksDecimal, _ksDecimal, any) {
	a, okA := left.(_ksDecimal)
	if !okA {
		return a, a, _ksError{message: "KS3801: operation expects Decimal values"}
	}
	b, okB := right.(_ksDecimal)
	if !okB {
		return a, b, _ksError{message: "KS3801: operation expects Decimal values"}
	}
	if a.scale != b.scale {
		return a, b, _ksError{message: "KS3802: decimal scales differ; implicit rescaling is forbidden"}
	}
	return a, b, nil
}

func _ksDecimalAdd(left any, right any) any {
	a, b, failure := _ksDecimalPair(left, right)
	if failure != nil {
		return failure
	}
	if (b.atoms > 0 && a.atoms > math.MaxInt64-b.atoms) || (b.atoms < 0 && a.atoms < math.MinInt64-b.atoms) {
		return _ksError{message: "KS3803: decimal addition overflow"}
	}
	return _ksDecimal{atoms: a.atoms + b.atoms, scale: a.scale}
}

func _ksDecimalSub(left any, right any) any {
	a, b, failure := _ksDecimalPair(left, right)
	if failure != nil {
		return failure
	}
	if (b.atoms < 0 && a.atoms > math.MaxInt64+b.atoms) || (b.atoms > 0 && a.atoms < math.MinInt64+b.atoms) {
		return _ksError{message: "KS3803: decimal subtraction overflow"}
	}
	return _ksDecimal{atoms: a.atoms - b.atoms, scale: a.scale}
}

func _ksDecimalCmp(left any, right any) any {
	a, b, failure := _ksDecimalPair(left, right)
	if failure != nil {
		return failure
	}
	switch {
	case a.atoms > b.atoms:
		return int64(1)
	case a.atoms < b.atoms:
		return int64(-1)
	}
	return int64(0)
}

func _ksDecimalTextOf(value any) any {
	item, ok := value.(_ksDecimal)
	if !ok {
		return _ksError{message: "KS3801: operation expects Decimal values"}
	}
	return _ksDecimalText(item)
}
"""
