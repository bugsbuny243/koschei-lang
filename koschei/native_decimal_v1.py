"""Exact financial Decimal in native binaries (``financial_decimal``).

Programs that call a Decimal builtin carry this fragment: the same int64
atoms, the same scale and rounding rules and the same ``KS380x`` messages as
every ``ks run`` executor. Products and quotients are formed in ``math/big``
and rounded once, in integers, like the Python ``int`` arithmetic they mirror.
"""

from __future__ import annotations

from . import financial_decimal as _decimal

BUILTINS = {
    "decimal": "_ksDecimalParse",
    "decimal_add": "_ksDecimalAdd",
    "decimal_sub": "_ksDecimalSub",
    "decimal_mul": "_ksDecimalMul",
    "decimal_div": "_ksDecimalDiv",
    "decimal_rescale": "_ksDecimalRescale",
    "decimal_cmp": "_ksDecimalCmp",
    "decimal_text": "_ksDecimalTextOf",
}
DECIMAL_IMPORTS = ("math/big", "strconv", "strings")


def _go(value: str) -> str:
    from .mir_go_native import _go_string

    return _go_string(value)


def decimal_runtime() -> str:
    overflow_prefix, overflow_suffix = _decimal.OVERFLOW_MESSAGE.split("{operation}")
    modes = "\n".join(f"\t{_go(mode)}: true," for mode in _decimal.ROUNDING_MODES)
    return _DECIMAL_RUNTIME.format(
        max_scale=_decimal.MAX_SCALE,
        max_digits=_decimal._MAX_ATOM_DIGITS,
        modes=modes,
        text_message=_go(_decimal.TEXT_MESSAGE),
        fraction_message=_go(_decimal.FRACTION_MESSAGE),
        scale_message=_go(_decimal.SCALE_MESSAGE),
        differ_message=_go(_decimal.SCALES_DIFFER_MESSAGE),
        atoms_message=_go(_decimal.ATOMS_MESSAGE),
        rounding_message=_go(_decimal.ROUNDING_MESSAGE),
        zero_message=_go(_decimal.DIVISION_BY_ZERO_MESSAGE),
        overflow_prefix=_go(overflow_prefix),
        overflow_suffix=_go(overflow_suffix),
    )


_DECIMAL_RUNTIME = r'''
// ---- exact Decimal (native_decimal_v1) ------------------------------------

var _ksDecimalModes = map[string]bool{{
{modes}
}}

func _ksDecimalArg(raw any, name string) _ksDecimal {{
	value, ok := raw.(_ksDecimal)
	if !ok {{
		_ksAbort("KS5002", name+" Decimal argument drifted")
	}}
	return value
}}

func _ksDecimalInt(raw any, name string) int64 {{
	value, ok := raw.(int64)
	if !ok {{
		_ksAbort("KS5002", name+" Int argument drifted")
	}}
	return value
}}

func _ksDecimalString(raw any, name string) string {{
	value, ok := raw.(string)
	if !ok {{
		_ksAbort("KS5002", name+" String argument drifted")
	}}
	return value
}}

func _ksDecimalOverflow(operation string) _ksError {{
	return _ksError{{message: {overflow_prefix} + operation + {overflow_suffix}}}
}}

// The scale, then the rounding mode: financial_decimal checks them in this order.
func _ksDecimalContract(scale int64, mode string) any {{
	if scale < 0 || scale > {max_scale} {{
		return _ksError{{message: {scale_message}}}
	}}
	if !_ksDecimalModes[mode] {{
		return _ksError{{message: {rounding_message}}}
	}}
	return nil
}}

// -?(?:0|[1-9][0-9]*)(?:\.[0-9]+)?, the whole text.
func _ksDecimalCanonical(text string) bool {{
	index := 0
	if index < len(text) && text[index] == '-' {{
		index++
	}}
	start := index
	for index < len(text) && text[index] >= '0' && text[index] <= '9' {{
		index++
	}}
	whole := text[start:index]
	if whole == "" || (len(whole) > 1 && whole[0] == '0') {{
		return false
	}}
	if index == len(text) {{
		return true
	}}
	if text[index] != '.' {{
		return false
	}}
	index++
	start = index
	for index < len(text) && text[index] >= '0' && text[index] <= '9' {{
		index++
	}}
	return index > start && index == len(text)
}}

func _ksDecimalParse(rawText any, rawScale any) any {{
	text := _ksDecimalString(rawText, "decimal")
	scale := _ksDecimalInt(rawScale, "decimal")
	if scale < 0 || scale > {max_scale} {{
		return _ksError{{message: {scale_message}}}
	}}
	if !_ksDecimalCanonical(text) {{
		return _ksError{{message: {text_message}}}
	}}
	negative := strings.HasPrefix(text, "-")
	unsigned := strings.TrimPrefix(text, "-")
	whole, fraction := unsigned, ""
	if dot := strings.IndexByte(unsigned, '.'); dot >= 0 {{
		whole, fraction = unsigned[:dot], unsigned[dot+1:]
	}}
	if int64(len(fraction)) > scale {{
		return _ksError{{message: {fraction_message}}}
	}}
	digits := strings.TrimLeft(whole+fraction+strings.Repeat("0", int(scale)-len(fraction)), "0")
	if len(digits) > {max_digits} {{
		return _ksError{{message: {atoms_message}}}
	}}
	if digits == "" {{
		digits = "0"
	}}
	if negative {{
		digits = "-" + digits
	}}
	atoms, err := strconv.ParseInt(digits, 10, 64)
	if err != nil {{
		return _ksError{{message: {atoms_message}}}
	}}
	return _ksDecimal{{atoms: atoms, scale: scale}}
}}

func _ksDecimalPair(left any, right any, name string) (_ksDecimal, _ksDecimal, any) {{
	a, b := _ksDecimalArg(left, name), _ksDecimalArg(right, name)
	if a.scale != b.scale {{
		return a, b, _ksError{{message: {differ_message}}}
	}}
	return a, b, nil
}}

func _ksDecimalAdd(left any, right any) any {{
	a, b, failure := _ksDecimalPair(left, right, "decimal_add")
	if failure != nil {{
		return failure
	}}
	if (b.atoms > 0 && a.atoms > math.MaxInt64-b.atoms) || (b.atoms < 0 && a.atoms < math.MinInt64-b.atoms) {{
		return _ksDecimalOverflow("addition")
	}}
	return _ksDecimal{{atoms: a.atoms + b.atoms, scale: a.scale}}
}}

func _ksDecimalSub(left any, right any) any {{
	a, b, failure := _ksDecimalPair(left, right, "decimal_sub")
	if failure != nil {{
		return failure
	}}
	if (b.atoms > 0 && a.atoms < math.MinInt64+b.atoms) || (b.atoms < 0 && a.atoms > math.MaxInt64+b.atoms) {{
		return _ksDecimalOverflow("subtraction")
	}}
	return _ksDecimal{{atoms: a.atoms - b.atoms, scale: a.scale}}
}}

func _ksDecimalCmp(left any, right any) any {{
	a, b, failure := _ksDecimalPair(left, right, "decimal_cmp")
	if failure != nil {{
		return failure
	}}
	switch {{
	case a.atoms > b.atoms:
		return int64(1)
	case a.atoms < b.atoms:
		return int64(-1)
	}}
	return int64(0)
}}

func _ksDecimalTextOf(value any) any {{
	return _ksDecimalText(_ksDecimalArg(value, "decimal_text"))
}}

func _ksDecimalPow10(exponent int64) *big.Int {{
	return new(big.Int).Exp(big.NewInt(10), big.NewInt(exponent), nil)
}}

// financial_decimal._scaled: numerator/denominator atoms of 10^-fromScale as
// atoms of 10^-scale, rounded once. The contract is already checked.
func _ksDecimalScaled(numerator *big.Int, fromScale int64, denominator *big.Int, scale int64, mode string, operation string) any {{
	if scale >= fromScale {{
		numerator.Mul(numerator, _ksDecimalPow10(scale-fromScale))
	}} else {{
		denominator.Mul(denominator, _ksDecimalPow10(fromScale-scale))
	}}
	if denominator.Sign() < 0 {{
		numerator.Neg(numerator)
		denominator.Neg(denominator)
	}}
	atoms := _ksDecimalRound(numerator, denominator, mode)
	if !atoms.IsInt64() {{
		return _ksDecimalOverflow(operation)
	}}
	return _ksDecimal{{atoms: atoms.Int64(), scale: scale}}
}}

// financial_decimal._round_quotient (denominator > 0).
func _ksDecimalRound(numerator *big.Int, denominator *big.Int, mode string) *big.Int {{
	negative := numerator.Sign() < 0
	quotient, remainder := new(big.Int).QuoRem(new(big.Int).Abs(numerator), denominator, new(big.Int))
	if remainder.Sign() != 0 {{
		half := new(big.Int).Lsh(remainder, 1).Cmp(denominator)
		up := false
		switch mode {{
		case "up":
			up = true
		case "floor":
			up = negative
		case "ceiling":
			up = !negative
		case "half_up":
			up = half >= 0
		case "half_down":
			up = half > 0
		case "half_even":
			up = half > 0 || (half == 0 && quotient.Bit(0) == 1)
		}}
		if up {{
			quotient.Add(quotient, big.NewInt(1))
		}}
	}}
	if negative {{
		quotient.Neg(quotient)
	}}
	return quotient
}}

func _ksDecimalMul(left any, right any, rawScale any, rawMode any) any {{
	a, b := _ksDecimalArg(left, "decimal_mul"), _ksDecimalArg(right, "decimal_mul")
	scale, mode := _ksDecimalInt(rawScale, "decimal_mul"), _ksDecimalString(rawMode, "decimal_mul")
	if failure := _ksDecimalContract(scale, mode); failure != nil {{
		return failure
	}}
	product := new(big.Int).Mul(big.NewInt(a.atoms), big.NewInt(b.atoms))
	return _ksDecimalScaled(product, a.scale+b.scale, big.NewInt(1), scale, mode, "multiplication")
}}

func _ksDecimalDiv(left any, right any, rawScale any, rawMode any) any {{
	a, b := _ksDecimalArg(left, "decimal_div"), _ksDecimalArg(right, "decimal_div")
	scale, mode := _ksDecimalInt(rawScale, "decimal_div"), _ksDecimalString(rawMode, "decimal_div")
	if failure := _ksDecimalContract(scale, mode); failure != nil {{
		return failure
	}}
	if b.atoms == 0 {{
		return _ksError{{message: {zero_message}}}
	}}
	// (l / 10^ls) / (r / 10^rs) = l * 10^rs / (r * 10^ls)
	numerator := new(big.Int).Mul(big.NewInt(a.atoms), _ksDecimalPow10(b.scale))
	denominator := new(big.Int).Mul(big.NewInt(b.atoms), _ksDecimalPow10(a.scale))
	return _ksDecimalScaled(numerator, 0, denominator, scale, mode, "division")
}}

func _ksDecimalRescale(value any, rawScale any, rawMode any) any {{
	a := _ksDecimalArg(value, "decimal_rescale")
	scale, mode := _ksDecimalInt(rawScale, "decimal_rescale"), _ksDecimalString(rawMode, "decimal_rescale")
	if failure := _ksDecimalContract(scale, mode); failure != nil {{
		return failure
	}}
	return _ksDecimalScaled(big.NewInt(a.atoms), a.scale, big.NewInt(1), scale, mode, "rescale")
}}
'''


__all__ = ["BUILTINS", "DECIMAL_IMPORTS", "decimal_runtime"]
