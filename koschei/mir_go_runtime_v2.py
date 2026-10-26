"""Go runtime embedded by the MIR-Go v2 projection.

Every helper mirrors one rule of the canonical sealed-MIR executor
(``koschei/mir_executor_v1.py``) and the canonical value renderer
(``interpreter.ks_to_string``). The runtime holds no authority and imports no
filesystem, network, environment or process API: it only computes values and
writes program output.

Value model (Go dynamic types inside ``any``):

* ``int64``/``float64``/``string``/``bool`` for the scalar types;
* ``[]any`` for ``List<T>`` values, never mutated after construction;
* ``_ksEnumValue`` for ``Option``/``Result``/user enum values;
* ``_ksStruct`` for struct values, which have value semantics: a field
  assignment builds an updated copy and never changes a shared value;
* ``_ksError`` for runtime Error values, which flow like any other value;
* ``_ksUnit`` for ``Void``.
"""

from __future__ import annotations

MIR_GO_RUNTIME_V2 = r'''
type _ksUnit struct{}

type _ksError struct {
	message string
}

type _ksEnumValue struct {
	owner      string
	variant    string
	hasPayload bool
	payload    any
	typeArgs   []string
}

type _ksStruct struct {
	name     string
	fields   []string
	values   []any
	typeArgs []string
}

type _ksStructBuilder struct {
	name     string
	fields   []string
	values   map[string]any
	consumed bool
}

type _ksMember struct {
	receiver any
	name     string
}

type _ksIter struct {
	values []any
	index  int
}

// Bytes (bytes_v1): an immutable byte sequence; a Go string holds any bytes.
type _ksBytes struct {
	data string
}

const _ksHexDigits = "0123456789abcdef"

func _ksHexText(data string) string {
	out := make([]byte, 0, 2*len(data))
	for index := 0; index < len(data); index++ {
		out = append(out, _ksHexDigits[data[index]>>4], _ksHexDigits[data[index]&15])
	}
	return string(out)
}

// Authority tokens. Program input is the only domain a native binary may
// carry (program_input_v1); every other domain fails closed before Go is
// generated.
type _ksSystemCaps struct{}

type _ksInputRoot struct{}

type _ksInputCaps struct {
	maxBytes int
}

type _ksClockRoot struct{}

// Read-only disk and environment tokens; their operations go through the
// native capability broker (native_broker_v1).
type _ksDiskRoot struct{}

type _ksDiskReadCaps struct {
	scope string
}

type _ksDiskCaps struct {
	scope string
}

type _ksEnvRoot struct{}

type _ksEnvCaps struct {
	name string
}

// Network tokens (native_net_v1); requests go through the broker.
type _ksNetRoot struct{}

type _ksNetCaps struct {
	scope string
}

// Loopback server tokens (native_serve_v1); the listener lives in the broker.
type _ksServeRoot struct{}

type _ksServeCaps struct {
	scope string
}

// One received request: data only (serve_knowhere_v1.HttpRequest).
type _ksHttpRequest struct {
	method  string
	path    string
	headers [][2]string
	body    string
}

// The result of NetCaps.get: read through text() and status() only.
type _ksResponse struct {
	status int64
	body   string
}

type _ksClockCaps struct {
	resolution int64
}

type _ksRandomRoot struct{}

// A pointer: the budget is shared by every holder of the token, like the
// interpreter's object.
type _ksRandomCaps struct {
	maxBytes  int64
	remaining int64
}

const _ksMaxCallDepth = 512
const _ksIntMin = -9223372036854775808
const _ksIntMax = 9223372036854775807

var _ksDepth = 0

func _ksAbort(code string, message string) {
	fmt.Fprintln(os.Stderr, "KOSCHEI RUNTIME ERROR: "+code+": "+message)
	os.Exit(1)
}

// canonical_mir_budget_runtime_v1: an Error returned by main is reported
// and the process exits with status 1.
func _ksFinish(result any) {
	if failure, ok := result.(_ksError); ok {
		fmt.Fprintln(os.Stderr, "KOSCHEI RUNTIME ERROR: "+failure.message)
		os.Exit(1)
	}
}

func _ksEnter() {
	if _ksDepth >= _ksMaxCallDepth {
		_ksAbort("KS3105", "call depth limit exceeded ("+strconv.Itoa(_ksMaxCallDepth)+")")
	}
	_ksDepth++
}

func _ksLeave() {
	_ksDepth--
}

// ---- rendering: interpreter.ks_to_string -------------------------------

func _ksFloatText(value float64) string {
	var text string
	switch {
	case math.IsInf(value, 1):
		text = "inf"
	case math.IsInf(value, -1):
		text = "-inf"
	case math.IsNaN(value):
		text = "nan"
	default:
		// Python repr: shortest round-trip digits; scientific notation when
		// the decimal exponent is below -4 or at least 16.
		scientific := strconv.FormatFloat(value, 'e', -1, 64)
		exponent, _ := strconv.Atoi(scientific[strings.LastIndexByte(scientific, 'e')+1:])
		if exponent < -4 || exponent >= 16 {
			text = scientific
		} else {
			text = strconv.FormatFloat(value, 'f', -1, 64)
		}
	}
	if !strings.ContainsAny(text, ".eE") {
		text += ".0"
	}
	return text
}

func _ksToString(value any) string {
	switch item := value.(type) {
	case bool:
		if item {
			return "true"
		}
		return "false"
	case float64:
		return _ksFloatText(item)
	case []any:
		parts := make([]string, len(item))
		for index, element := range item {
			parts[index] = _ksRepr(element)
		}
		return "[" + strings.Join(parts, ", ") + "]"
	case _ksEnumValue:
		if !item.hasPayload {
			return item.variant
		}
		return item.variant + "(" + _ksRepr(item.payload) + ")"
	case _ksStruct:
		parts := make([]string, len(item.fields))
		for index, name := range item.fields {
			parts[index] = name + ": " + _ksRepr(item.values[index])
		}
		return item.name + " { " + strings.Join(parts, ", ") + " }"
	case int64:
		return strconv.FormatInt(item, 10)
	case string:
		return item
	case _ksError:
		return item.message
	case _ksUnit:
		return "unit"
	case _ksBytes:
		return "Bytes(" + _ksHexText(item.data) + ")"
	case _ksSystemCaps:
		return "<SystemCaps>"
	case _ksInputRoot:
		return "<InputRoot>"
	case _ksInputCaps:
		return "<InputCaps>"
	case _ksDiskRoot:
		return "<DiskRoot>"
	case _ksDiskReadCaps:
		return "<DiskReadCaps>"
	case _ksDiskCaps:
		return "<DiskCaps>"
	case _ksEnvRoot:
		return "<EnvRoot>"
	case _ksEnvCaps:
		return "<EnvCaps>"
	case _ksNetRoot:
		return "<NetRoot>"
	case _ksNetCaps:
		return "<NetCaps>"
	case _ksResponse:
		return "<Response>"
	case _ksServeRoot:
		return "<ServeRoot>"
	case _ksServeCaps:
		return "<ServeCaps>"
	case _ksHttpRequest:
		return "HttpRequest(" + item.method + " " + item.path + ")"
	case _ksClockRoot:
		return "<ClockRoot>"
	case _ksClockCaps:
		return "<ClockCaps>"
	case _ksRandomRoot:
		return "<RandomRoot>"
	case *_ksRandomCaps:
		return "<RandomCaps>"
	}
	_ksAbort("KS5002", "unrenderable runtime value")
	return ""
}

func _ksRepr(value any) string {
	if text, ok := value.(string); ok {
		return "\"" + text + "\""
	}
	return _ksToString(value)
}

// ---- equality and ordering ---------------------------------------------

func _ksEqual(left any, right any) bool {
	switch a := left.(type) {
	case bool:
		b, ok := right.(bool)
		return ok && a == b
	case int64:
		b, ok := right.(int64)
		return ok && a == b
	case float64:
		b, ok := right.(float64)
		return ok && a == b
	case string:
		b, ok := right.(string)
		return ok && a == b
	case []any:
		b, ok := right.([]any)
		if !ok || len(a) != len(b) {
			return false
		}
		for index := range a {
			if !_ksEqual(a[index], b[index]) {
				return false
			}
		}
		return true
	case _ksEnumValue:
		b, ok := right.(_ksEnumValue)
		if !ok || a.owner != b.owner || a.variant != b.variant || a.hasPayload != b.hasPayload {
			return false
		}
		return !a.hasPayload || _ksEqual(a.payload, b.payload)
	case _ksStruct:
		// StructValue equality: type name, type evidence and every field.
		b, ok := right.(_ksStruct)
		if !ok || a.name != b.name || len(a.fields) != len(b.fields) || len(a.typeArgs) != len(b.typeArgs) {
			return false
		}
		for index := range a.typeArgs {
			if a.typeArgs[index] != b.typeArgs[index] {
				return false
			}
		}
		for index, name := range a.fields {
			found := false
			for other := range b.fields {
				if b.fields[other] == name {
					if !_ksEqual(a.values[index], b.values[other]) {
						return false
					}
					found = true
					break
				}
			}
			if !found {
				return false
			}
		}
		return true
	case _ksError:
		b, ok := right.(_ksError)
		return ok && a.message == b.message
	case _ksBytes:
		b, ok := right.(_ksBytes)
		return ok && a.data == b.data
	case _ksUnit:
		_, ok := right.(_ksUnit)
		return ok
	case _ksHttpRequest:
		// A frozen dataclass: every field, headers in order.
		b, ok := right.(_ksHttpRequest)
		if !ok || a.method != b.method || a.path != b.path || a.body != b.body || len(a.headers) != len(b.headers) {
			return false
		}
		for index := range a.headers {
			if a.headers[index] != b.headers[index] {
				return false
			}
		}
		return true
	}
	return false
}

func _ksOrder(operator string, left any, right any) bool {
	switch a := left.(type) {
	case int64:
		if b, ok := right.(int64); ok {
			switch operator {
			case "<":
				return a < b
			case "<=":
				return a <= b
			case ">":
				return a > b
			default:
				return a >= b
			}
		}
	case float64:
		if b, ok := right.(float64); ok {
			switch operator {
			case "<":
				return a < b
			case "<=":
				return a <= b
			case ">":
				return a > b
			default:
				return a >= b
			}
		}
	case string:
		if b, ok := right.(string); ok {
			switch operator {
			case "<":
				return a < b
			case "<=":
				return a <= b
			case ">":
				return a > b
			default:
				return a >= b
			}
		}
	case _ksBytes:
		if b, ok := right.(_ksBytes); ok {
			return _ksOrder(operator, a.data, b.data)
		}
	case bool:
		if b, ok := right.(bool); ok {
			x, y := int64(0), int64(0)
			if a {
				x = 1
			}
			if b {
				y = 1
			}
			return _ksOrder(operator, x, y)
		}
	case []any:
		if b, ok := right.([]any); ok {
			// Python sequence ordering: the first unequal pair decides,
			// otherwise the lengths do.
			for index := 0; index < len(a) && index < len(b); index++ {
				if !_ksEqual(a[index], b[index]) {
					return _ksOrder(operator, a[index], b[index])
				}
			}
			return _ksOrder(operator, int64(len(a)), int64(len(b)))
		}
	}
	_ksAbort("KS5002", "unsupported operands for '"+operator+"'")
	return false
}

// ---- operators: MirExecutorV1._binary / MirUnary ------------------------

func _ksIsError(value any) bool {
	_, ok := value.(_ksError)
	return ok
}

func _ksIntOverflow(operator string) any {
	return _ksError{message: "KS3501: Int taşması: '" + operator + "' işlemi işaretli 64-bit aralığın dışına çıktı."}
}

func _ksBinary(operator string, left any, right any) any {
	if _ksIsError(left) {
		return left
	}
	if operator == "&&" || operator == "||" {
		truth := _ksTruthy(left)
		if operator == "&&" && !truth {
			return false
		}
		if operator == "||" && truth {
			return true
		}
		if _ksIsError(right) {
			return right
		}
		return _ksTruthy(right)
	}
	if _ksIsError(right) {
		return right
	}
	a, leftInt := left.(int64)
	b, rightInt := right.(int64)
	bothInt := leftInt && rightInt
	switch operator {
	case "+":
		if bothInt {
			result := a + b
			if (a > 0 && b > 0 && result < 0) || (a < 0 && b < 0 && result >= 0) {
				return _ksIntOverflow("+")
			}
			return result
		}
		switch x := left.(type) {
		case float64:
			if y, ok := right.(float64); ok {
				return x + y
			}
		case string:
			if y, ok := right.(string); ok {
				if len(x)+len(y) > _ksMaxStringBytes {
					return _ksStringBudgetError
				}
				return x + y
			}
		case _ksBytes:
			if y, ok := right.(_ksBytes); ok {
				if len(x.data)+len(y.data) > _ksMaxStringBytes {
					return _ksBytesBudgetError
				}
				return _ksBytes{data: x.data + y.data}
			}
		case []any:
			if y, ok := right.([]any); ok {
				if len(x)+len(y) > _ksMaxListItems {
					return _ksListBudgetError
				}
				joined := make([]any, 0, len(x)+len(y))
				return append(append(joined, x...), y...)
			}
		}
	case "-":
		if bothInt {
			result := a - b
			if (a >= 0 && b < 0 && result < 0) || (a < 0 && b > 0 && result >= 0) {
				return _ksIntOverflow("-")
			}
			return result
		}
		if x, ok := left.(float64); ok {
			if y, ok := right.(float64); ok {
				return x - y
			}
		}
	case "*":
		if bothInt {
			if a == 0 || b == 0 {
				return int64(0)
			}
			result := a * b
			if (a == -1 && b == _ksIntMin) || (b == -1 && a == _ksIntMin) || result/b != a {
				return _ksIntOverflow("*")
			}
			return result
		}
		if x, ok := left.(float64); ok {
			if y, ok := right.(float64); ok {
				return x * y
			}
		}
	case "/":
		if _ksIsZero(right) {
			return _ksError{message: "Sıfıra bölme"}
		}
		if bothInt {
			if a == _ksIntMin && b == -1 {
				return _ksIntOverflow("/")
			}
			return a / b
		}
		if x, ok := left.(float64); ok {
			if y, ok := right.(float64); ok {
				return x / y
			}
		}
	case "%":
		if bothInt {
			if b == 0 {
				return _ksError{message: "Sıfıra bölme"}
			}
			if a == _ksIntMin && b == -1 {
				return _ksIntOverflow("%")
			}
			return a % b
		}
	case "==":
		return _ksEqual(left, right)
	case "!=":
		return !_ksEqual(left, right)
	case "<", "<=", ">", ">=":
		return _ksOrder(operator, left, right)
	}
	_ksAbort("KS5002", "unsupported operands for '"+operator+"'")
	return nil
}

func _ksIsZero(value any) bool {
	switch item := value.(type) {
	case int64:
		return item == 0
	case float64:
		return item == 0
	case bool:
		return !item
	}
	return false
}

func _ksTruthy(value any) bool {
	if truth, ok := value.(bool); ok {
		return truth
	}
	_ksAbort("KS5002", "logical operand is not Bool")
	return false
}

func _ksNot(value any) any {
	if _ksIsError(value) {
		return value
	}
	return !_ksTruthy(value)
}

func _ksNegate(value any) any {
	switch item := value.(type) {
	case _ksError:
		return item
	case int64:
		if item == _ksIntMin {
			return _ksIntOverflow("unary -")
		}
		return -item
	case float64:
		return -item
	}
	_ksAbort("KS5002", "unsupported operand for unary '-'")
	return nil
}

func _ksCondition(value any) bool {
	if _ksIsError(value) {
		_ksAbort("KS5002", "MIR branch condition produced a runtime Error value")
	}
	return _ksTruthy(value)
}

// ---- Option/Result/Error fallibility ------------------------------------

func _ksFallibleSuccess(value any) bool {
	success, _ := _ksUnwrapFallible(value)
	return success
}

func _ksFalliblePayload(value any) any {
	success, payload := _ksUnwrapFallible(value)
	if !success {
		_ksAbort("KS5002", "MirFalliblePayload reached a failed value")
	}
	return payload
}

func _ksUnwrapFallible(value any) (bool, any) {
	switch item := value.(type) {
	case _ksError:
		return false, item
	case _ksEnumValue:
		if item.owner == "Option" {
			if item.variant == "Some" {
				return true, item.payload
			}
			if item.variant == "None" {
				return false, item
			}
		}
		if item.owner == "Result" {
			if item.variant == "Ok" {
				return true, item.payload
			}
			if item.variant == "Err" {
				return false, item
			}
		}
	}
	return true, value
}

func _ksAsEnum(value any) _ksEnumValue {
	item, ok := value.(_ksEnumValue)
	if !ok {
		_ksAbort("KS5002", "MIR variant comparison requires an enum value")
	}
	return item
}

// ---- structs: StructBuilderV1 and struct_field_set_v1 -------------------

func _ksStructNew(name string, fields []string) any {
	return &_ksStructBuilder{name: name, fields: fields, values: map[string]any{}}
}

func _ksAsStructBuilder(value any) *_ksStructBuilder {
	builder, ok := value.(*_ksStructBuilder)
	if !ok {
		_ksAbort("KS5002", "invalid MIR struct builder")
	}
	return builder
}

func _ksStructSet(value any, field string, item any, expected []string) {
	builder := _ksAsStructBuilder(value)
	if builder.consumed {
		_ksAbort("KS5002", "consumed MIR struct builder cannot accept fields")
	}
	admitted := false
	for _, name := range builder.fields {
		if name == field {
			admitted = true
			break
		}
	}
	if !admitted {
		_ksAbort("KS5002", "sealed MIR struct did not admit field '"+field+"'")
	}
	if _, seen := builder.values[field]; seen {
		_ksAbort("KS5002", "sealed MIR struct field '"+field+"' was assigned more than once")
	}
	if !_ksMatchesType(item, expected, nil, nil) {
		_ksAbort("KS3401", "'"+builder.name+"."+field+"' field received "+_ksTypeName(item))
	}
	builder.values[field] = item
}

func _ksStructFinish(value any) any {
	builder := _ksAsStructBuilder(value)
	if builder.consumed {
		_ksAbort("KS5002", "MIR struct builder may be finished exactly once")
	}
	if len(builder.values) != len(builder.fields) {
		_ksAbort("KS3101", "'"+builder.name+"' struct field contract is incomplete")
	}
	builder.consumed = true
	values := make([]any, len(builder.fields))
	for index, name := range builder.fields {
		values[index] = builder.values[name]
	}
	return _ksStruct{name: builder.name, fields: builder.fields, values: values}
}

// A field assignment returns an updated copy; the receiver is never changed.
func _ksStructWith(receiver any, owner string, field string, item any, expected []string) any {
	value, ok := receiver.(_ksStruct)
	if !ok || value.name != owner {
		_ksAbort("KS5002", "sealed MIR struct field assignment received a non-struct receiver")
	}
	index := -1
	for position, name := range value.fields {
		if name == field {
			index = position
			break
		}
	}
	if index < 0 {
		_ksAbort("KS5002", "sealed MIR struct value is missing declared field '"+field+"'")
	}
	if !_ksMatchesType(item, expected, nil, nil) {
		_ksAbort("KS3401", "'"+owner+"."+field+"' field assignment received "+_ksTypeName(item))
	}
	values := make([]any, len(value.values))
	copy(values, value.values)
	values[index] = item
	return _ksStruct{name: value.name, fields: value.fields, values: values, typeArgs: value.typeArgs}
}

func _ksField(receiver any, name string) any {
	if value, ok := receiver.(_ksStruct); ok {
		for index, field := range value.fields {
			if field == name {
				return value.values[index]
			}
		}
	}
	_ksAbort("KS3101", "undefined field '"+name+"'")
	return nil
}

// ---- iteration -----------------------------------------------------------

func _ksIterInit(value any) any {
	items, ok := value.([]any)
	if !ok {
		_ksAbort("KS3101", "MIR iterator requires a List")
	}
	return &_ksIter{values: items}
}

func _ksIterHasNext(value any) any {
	iterator := value.(*_ksIter)
	return iterator.index < len(iterator.values)
}

func _ksIterNext(value any) any {
	iterator := value.(*_ksIter)
	if iterator.index >= len(iterator.values) {
		_ksAbort("KS5002", "MIR iterator advanced past its end")
	}
	item := iterator.values[iterator.index]
	iterator.index++
	return item
}

// ---- builtins and String/List members -----------------------------------

func _ksPrintln(arguments ...any) any {
	if len(arguments) != 1 {
		_ksAbort("KS3101", "println expects one argument")
	}
	fmt.Println(_ksToString(arguments[0]))
	return _ksUnit{}
}

func _ksPrint(arguments ...any) any {
	if len(arguments) != 1 {
		_ksAbort("KS3101", "print expects one argument")
	}
	fmt.Print(_ksToString(arguments[0]))
	return _ksUnit{}
}

func _ksErrorValue(arguments ...any) any {
	if len(arguments) != 1 {
		_ksAbort("KS3101", "Error expects one argument")
	}
	return _ksError{message: _ksToString(arguments[0])}
}

func _ksMemberOf(receiver any, name string) any {
	switch receiver.(type) {
	case string:
		switch name {
		case "length", "contains", "trim", "split", "join", "to_int", "to_bytes":
			return _ksMember{receiver: receiver, name: name}
		}
	case _ksBytes:
		switch name {
		case "length", "hex", "to_text", "slice", "get":
			return _ksMember{receiver: receiver, name: name}
		}
	case _ksResponse:
		switch name {
		case "text", "status":
			return _ksMember{receiver: receiver, name: name}
		}
	case _ksHttpRequest:
		switch name {
		case "method", "path", "header", "body", "body_bytes":
			return _ksMember{receiver: receiver, name: name}
		}
	case []any:
		switch name {
		case "length", "get", "push", "contains", "take":
			return _ksMember{receiver: receiver, name: name}
		}
	}
	_ksAbort("KS3101", "undefined member '"+name+"'")
	return nil
}

func _ksArity(name string, arguments []any, expected int) {
	if len(arguments) != expected {
		_ksAbort("KS3101", "'"+name+"' expects "+strconv.Itoa(expected)+" argument(s)")
	}
}

func _ksIsSpace(r rune) bool {
	switch {
	case r >= 0x09 && r <= 0x0d, r >= 0x1c && r <= 0x20:
		return true
	case r == 0x85, r == 0xa0, r == 0x1680, r >= 0x2000 && r <= 0x200a:
		return true
	case r == 0x2028, r == 0x2029, r == 0x202f, r == 0x205f, r == 0x3000:
		return true
	}
	return false
}

func _ksInvokeMember(callee any, arguments ...any) any {
	member, ok := callee.(_ksMember)
	if !ok {
		_ksAbort("KS5002", "MIR call target is not a member")
	}
	switch receiver := member.receiver.(type) {
	case _ksBytes:
		return _ksBytesMember(receiver, member.name, arguments)
	case _ksHttpRequest:
		return _ksRequestMember(receiver, member.name, arguments)
	case _ksResponse:
		_ksArity(member.name, arguments, 0)
		if member.name == "status" {
			return receiver.status
		}
		return receiver.body
	case string:
		switch member.name {
		case "to_bytes":
			_ksArity("to_bytes", arguments, 0)
			return _ksBytes{data: receiver}
		case "length":
			_ksArity("length", arguments, 0)
			return int64(utf8.RuneCountInString(receiver))
		case "contains":
			_ksArity("contains", arguments, 1)
			switch needle := arguments[0].(type) {
			case string:
				return strings.Contains(receiver, needle)
			case _ksError:
				return strings.Contains(receiver, needle.message)
			}
		case "trim":
			_ksArity("trim", arguments, 0)
			return strings.TrimFunc(receiver, _ksIsSpace)
		case "to_int":
			// interpreter.ks_parse_int: trimmed, optional sign, ASCII digits,
			// signed 64-bit range.
			_ksArity("to_int", arguments, 0)
			trimmed := strings.TrimFunc(receiver, _ksIsSpace)
			digits := trimmed
			if len(digits) > 0 && (digits[0] == '+' || digits[0] == '-') {
				digits = digits[1:]
			}
			valid := len(digits) > 0
			for index := 0; index < len(digits); index++ {
				if digits[index] < '0' || digits[index] > '9' {
					valid = false
					break
				}
			}
			if valid {
				if value, err := strconv.ParseInt(trimmed, 10, 64); err == nil {
					return value
				}
			}
			return _ksError{message: "Int dönüşümü başarısız: " + receiver}
		case "split":
			_ksArity("split", arguments, 1)
			separator, ok := arguments[0].(string)
			if !ok {
				return _ksError{message: "String.split() ayıracı String olmalıdır"}
			}
			if separator == "" {
				return _ksError{message: "String.split() ayıracı boş olamaz"}
			}
			if strings.Count(receiver, separator)+1 > _ksMaxListItems {
				return _ksListBudgetError
			}
			pieces := strings.Split(receiver, separator)
			items := make([]any, len(pieces))
			for index, piece := range pieces {
				items[index] = piece
			}
			return items
		case "join":
			_ksArity("join", arguments, 1)
			values, ok := arguments[0].([]any)
			if !ok {
				return _ksError{message: "String.join() bir List bekler"}
			}
			pieces := make([]string, len(values))
			total := 0
			for index, value := range values {
				text, ok := value.(string)
				if !ok {
					return _ksError{message: "String.join() yalnızca String öğeleri birleştirir"}
				}
				pieces[index] = text
				total += len(text)
			}
			if len(pieces) > 1 {
				total += len(receiver) * (len(pieces) - 1)
			}
			if total > _ksMaxStringBytes {
				return _ksStringBudgetError
			}
			return strings.Join(pieces, receiver)
		}
	case []any:
		switch member.name {
		case "length":
			_ksArity("length", arguments, 0)
			return int64(len(receiver))
		case "get":
			_ksArity("get", arguments, 1)
			index, ok := arguments[0].(int64)
			if !ok {
				return _ksError{message: "Liste indeksi Int olmalıdır"}
			}
			if index < 0 || index >= int64(len(receiver)) {
				return _ksEnumValue{owner: "Option", variant: "None"}
			}
			return _ksEnumValue{owner: "Option", variant: "Some", hasPayload: true, payload: receiver[index]}
		case "push":
			_ksArity("push", arguments, 1)
			if len(receiver)+1 > _ksMaxListItems {
				return _ksListBudgetError
			}
			items := make([]any, 0, len(receiver)+1)
			return append(append(items, receiver...), arguments[0])
		case "contains":
			_ksArity("contains", arguments, 1)
			for _, item := range receiver {
				if _ksEqual(item, arguments[0]) {
					return true
				}
			}
			return false
		case "take":
			_ksArity("take", arguments, 1)
			count, ok := arguments[0].(int64)
			if !ok {
				return _ksError{message: "List.take() öğe sayısı Int olmalıdır"}
			}
			if count <= 0 {
				return []any{}
			}
			if count > int64(len(receiver)) {
				count = int64(len(receiver))
			}
			items := make([]any, count)
			copy(items, receiver[:count])
			return items
		}
	}
	_ksAbort("KS3101", "unsupported member call '"+member.name+"'")
	return nil
}

// ---- runtime type evidence: Interpreter._runtime_matches_type -----------

func _ksTypeName(value any) string {
	switch item := value.(type) {
	case _ksUnit:
		return "Void"
	case _ksEnumValue:
		if item.owner == "Option" || item.owner == "Result" {
			inner := "_"
			if item.hasPayload {
				inner = _ksTypeName(item.payload)
			}
			return item.owner + "<" + inner + ">"
		}
		if len(item.typeArgs) > 0 {
			return item.owner + "<" + strings.Join(item.typeArgs, ", ") + ">"
		}
		return item.owner
	case _ksStruct:
		if len(item.typeArgs) > 0 {
			return item.name + "<" + strings.Join(item.typeArgs, ", ") + ">"
		}
		return item.name
	case _ksError:
		return "Error"
	case []any:
		if len(item) == 0 {
			return "List<_>"
		}
		names := []string{}
		for _, element := range item {
			name := _ksTypeName(element)
			seen := false
			for _, existing := range names {
				if existing == name {
					seen = true
					break
				}
			}
			if !seen {
				names = append(names, name)
			}
		}
		if len(names) == 1 {
			return "List<" + names[0] + ">"
		}
		return "List<_>"
	case bool:
		return "Bool"
	case string:
		return "String"
	case float64:
		return "Float"
	case int64:
		return "Int"
	case _ksBytes:
		return "Bytes"
	case _ksSystemCaps:
		return "SystemCaps"
	case _ksInputRoot:
		return "InputRoot"
	case _ksInputCaps:
		return "InputCaps"
	case _ksDiskRoot:
		return "DiskRoot"
	case _ksDiskReadCaps:
		return "DiskReadCaps"
	case _ksDiskCaps:
		return "DiskCaps"
	case _ksEnvRoot:
		return "EnvRoot"
	case _ksEnvCaps:
		return "EnvCaps"
	case _ksNetRoot:
		return "NetRoot"
	case _ksNetCaps:
		return "NetCaps"
	case _ksResponse:
		return "Response"
	case _ksServeRoot:
		return "ServeRoot"
	case _ksServeCaps:
		return "ServeCaps"
	case _ksHttpRequest:
		return "HttpRequest"
	case _ksClockRoot:
		return "ClockRoot"
	case _ksClockCaps:
		return "ClockCaps"
	case _ksRandomRoot:
		return "RandomRoot"
	case *_ksRandomCaps:
		return "RandomCaps"
	}
	return "unknown"
}

func _ksSplitGenericArguments(text string) []string {
	arguments := []string{}
	depth := 0
	start := 0
	for index, char := range text {
		switch char {
		case '<':
			depth++
		case '>':
			depth--
		case ',':
			if depth == 0 {
				arguments = append(arguments, strings.TrimSpace(text[start:index]))
				start = index + 1
			}
		}
	}
	arguments = append(arguments, strings.TrimSpace(text[start:]))
	result := []string{}
	for _, argument := range arguments {
		if argument != "" {
			result = append(result, argument)
		}
	}
	return result
}

func _ksGenericType(name string) (string, []string) {
	if !strings.Contains(name, "<") || !strings.HasSuffix(name, ">") {
		return name, nil
	}
	cut := strings.Index(name, "<")
	return strings.TrimSpace(name[:cut]), _ksSplitGenericArguments(name[cut+1 : len(name)-1])
}

func _ksMatchTypeName(actual string, expected string, parameters map[string]bool, bindings map[string]string) bool {
	if expected == "_" {
		return true
	}
	expectedBase, expectedArguments := _ksGenericType(expected)
	if len(expectedArguments) == 0 && parameters[expectedBase] {
		previous, bound := bindings[expectedBase]
		if !bound {
			bindings[expectedBase] = actual
			return true
		}
		return previous == actual
	}
	actualBase, actualArguments := _ksGenericType(actual)
	if len(expectedArguments) > 0 {
		if actualBase != expectedBase {
			return false
		}
		if len(actualArguments) > 0 && len(actualArguments) == len(expectedArguments) {
			for index := range actualArguments {
				if actualArguments[index] == "_" {
					continue
				}
				if !_ksMatchTypeName(actualArguments[index], expectedArguments[index], parameters, bindings) {
					return false
				}
			}
		}
		return true
	}
	return actual == expected || actualBase == expectedBase
}

func _ksMatchPattern(value any, expected string, parameters map[string]bool, bindings map[string]string) bool {
	if expected == "_" {
		return true
	}
	base, arguments := _ksGenericType(expected)
	if len(arguments) == 0 && parameters[base] {
		actual := _ksTypeName(value)
		previous, bound := bindings[base]
		if !bound {
			bindings[base] = actual
			return true
		}
		return _ksMatchTypeName(actual, previous, map[string]bool{}, map[string]string{})
	}
	if base == "List" && len(arguments) == 1 {
		items, ok := value.([]any)
		if !ok {
			return false
		}
		for _, item := range items {
			if !_ksMatchPattern(item, arguments[0], parameters, bindings) {
				return false
			}
		}
		return true
	}
	if base == "Map" && len(arguments) == 2 {
		return false
	}
	if base == "Option" && len(arguments) == 1 {
		item, ok := value.(_ksEnumValue)
		if !ok || item.owner != "Option" {
			return false
		}
		if item.variant == "None" {
			return true
		}
		return item.variant == "Some" && item.hasPayload && _ksMatchPattern(item.payload, arguments[0], parameters, bindings)
	}
	if base == "Result" && len(arguments) == 2 {
		item, ok := value.(_ksEnumValue)
		if !ok || item.owner != "Result" {
			return false
		}
		if item.variant == "Ok" && item.hasPayload {
			return _ksMatchPattern(item.payload, arguments[0], parameters, bindings)
		}
		if item.variant == "Err" && item.hasPayload {
			return _ksMatchPattern(item.payload, arguments[1], parameters, bindings)
		}
		return false
	}
	if item, ok := value.(_ksStruct); ok && item.name == base {
		if len(arguments) == 0 {
			return true
		}
		if len(item.typeArgs) > 0 && len(item.typeArgs) == len(arguments) {
			for index := range item.typeArgs {
				if item.typeArgs[index] == "_" {
					continue
				}
				if !_ksMatchTypeName(item.typeArgs[index], arguments[index], parameters, bindings) {
					return false
				}
			}
		}
		return true
	}
	if item, ok := value.(_ksEnumValue); ok && item.owner == base {
		if len(arguments) == 0 {
			return true
		}
		if len(item.typeArgs) > 0 && len(item.typeArgs) == len(arguments) {
			for index := range item.typeArgs {
				if item.typeArgs[index] == "_" {
					continue
				}
				if !_ksMatchTypeName(item.typeArgs[index], arguments[index], parameters, bindings) {
					return false
				}
			}
		}
		return true
	}
	switch value.(type) {
	case _ksError:
		return base == "Error"
	case _ksUnit:
		return base == "Void"
	case string:
		return base == "String"
	case bool:
		return base == "Bool"
	case int64:
		return base == "Int"
	case float64:
		return base == "Float"
	case []any:
		return base == "List"
	case _ksBytes:
		return base == "Bytes"
	case _ksSystemCaps:
		return base == "SystemCaps"
	case _ksInputRoot:
		return base == "InputRoot"
	case _ksInputCaps:
		return base == "InputCaps"
	case _ksDiskRoot:
		return base == "DiskRoot"
	case _ksDiskReadCaps:
		return base == "DiskReadCaps"
	case _ksDiskCaps:
		return base == "DiskCaps"
	case _ksEnvRoot:
		return base == "EnvRoot"
	case _ksEnvCaps:
		return base == "EnvCaps"
	case _ksNetRoot:
		return base == "NetRoot"
	case _ksNetCaps:
		return base == "NetCaps"
	case _ksResponse:
		return base == "Response"
	case _ksServeRoot:
		return base == "ServeRoot"
	case _ksServeCaps:
		return base == "ServeCaps"
	case _ksHttpRequest:
		return base == "HttpRequest"
	case _ksClockRoot:
		return base == "ClockRoot"
	case _ksClockCaps:
		return base == "ClockCaps"
	case _ksRandomRoot:
		return base == "RandomRoot"
	case *_ksRandomCaps:
		return base == "RandomCaps"
	}
	return false
}

// Replaces the generic function's type parameters in enum evidence with
// their runtime bindings; an unbound parameter matches anything ("_").
func _ksBindTypeArgs(arguments []string, parameters map[string]bool, bindings map[string]string) []string {
	bound := make([]string, len(arguments))
	for index, argument := range arguments {
		var out strings.Builder
		start := -1
		flush := func(end int) {
			if start < 0 {
				return
			}
			name := argument[start:end]
			if parameters[name] {
				if value, ok := bindings[name]; ok {
					name = value
				} else {
					name = "_"
				}
			}
			out.WriteString(name)
			start = -1
		}
		for position := 0; position < len(argument); position++ {
			character := argument[position]
			word := character == '_' || (character >= '0' && character <= '9') ||
				(character >= 'a' && character <= 'z') || (character >= 'A' && character <= 'Z')
			if word {
				if start < 0 {
					start = position
				}
				continue
			}
			flush(position)
			out.WriteByte(character)
		}
		flush(len(argument))
		bound[index] = out.String()
	}
	return bound
}

func _ksMatchesType(value any, expected []string, parameters map[string]bool, bindings map[string]string) bool {
	if bindings == nil {
		bindings = map[string]string{}
	}
	for _, name := range expected {
		trial := make(map[string]string, len(bindings))
		for key, bound := range bindings {
			trial[key] = bound
		}
		if _ksMatchPattern(value, name, parameters, trial) {
			for key := range bindings {
				delete(bindings, key)
			}
			for key, bound := range trial {
				bindings[key] = bound
			}
			return true
		}
	}
	return false
}
'''

MIR_GO_RUNTIME_V2_IMPORTS = ("fmt", "math", "os", "strconv", "strings", "unicode/utf8")

# Emitted only for programs that call the kernel digest (``secure_hash_v1``).
# Go's standard ``crypto/sha3`` is the audited provider; Koschei implements no
# cryptographic primitive of its own.
MIR_GO_SHA3_IMPORTS_V2 = ("crypto/sha3", "encoding/hex")
MIR_GO_SHA3_RUNTIME_V2 = r'''
const _ksSha3MaxInputBytes = {max_bytes}

func _ksSha3_256(arguments ...any) any {{
	if len(arguments) != 1 {{
		_ksAbort("KS3101", "sha3_256 expects one argument")
	}}
	text, ok := arguments[0].(string)
	if !ok {{
		return _ksError{{message: "sha3_256: input must be a String"}}
	}}
	if len(text) > _ksSha3MaxInputBytes {{
		return _ksError{{message: "sha3_256: input exceeds {max_bytes} bytes"}}
	}}
	sum := sha3.Sum256([]byte(text))
	return hex.EncodeToString(sum[:])
}}
'''

# Titan value budget (``value_budget_v1``): formatted with the Python constants
# and messages so every executor reports the same bound with the same text.
MIR_GO_VALUE_BUDGET_RUNTIME_V2 = r'''
const _ksMaxStringBytes = {max_string_bytes}
const _ksMaxListItems = {max_list_items}

var _ksStringBudgetError = _ksError{{message: {string_message}}}
var _ksListBudgetError = _ksError{{message: {list_message}}}
var _ksBytesBudgetError = _ksError{{message: {bytes_message}}}

// Interpolation builds its text first, like the canonical executor.
func _ksBudgetText(text string) any {{
	if len(text) > _ksMaxStringBytes {{
		return _ksStringBudgetError
	}}
	return text
}}
'''


# Emitted only for programs that use program input (``program_input_v1``).
# Arguments and standard input are data the invoker handed to the process; no
# file, network, environment or process API is linked. Messages come from the
# Python constants so both executors produce the same Error values.
MIR_GO_INPUT_IMPORTS_V2 = ("io",)
MIR_GO_INPUT_RUNTIME_V2 = r'''
const _ksInputMinBytes = {min_bytes}
const _ksInputMaxBytes = {max_bytes}

func _ksCapsInput(receiver any) any {{
	if _, ok := receiver.(_ksSystemCaps); !ok {{
		_ksAbort("KS5002", "SystemCaps.input receiver drifted")
	}}
	return _ksInputRoot{{}}
}}

func _ksInputAllow(receiver any, budget any) any {{
	if _, ok := receiver.(_ksInputRoot); !ok {{
		_ksAbort("KS5002", "InputRoot.allow receiver drifted")
	}}
	value, ok := budget.(int64)
	if !ok {{
		return _ksError{{message: {type_message}}}
	}}
	if value < _ksInputMinBytes || value > _ksInputMaxBytes {{
		return _ksError{{message: {range_message}}}
	}}
	return _ksInputCaps{{maxBytes: int(value)}}
}}

func _ksInputArgs(receiver any) any {{
	if _, ok := receiver.(_ksInputCaps); !ok {{
		_ksAbort("KS5002", "InputCaps.args receiver drifted")
	}}
	raw := os.Args[1:]
	if len(raw) > _ksMaxListItems {{
		return _ksListBudgetError
	}}
	items := make([]any, 0, len(raw))
	for index, argument := range raw {{
		if !utf8.ValidString(argument) {{
			return _ksError{{message: {argument_prefix} + strconv.Itoa(index+1) + {argument_suffix}}}
		}}
		if len(argument) > _ksMaxStringBytes {{
			return _ksStringBudgetError
		}}
		items = append(items, argument)
	}}
	return items
}}

func _ksInputReadText(receiver any) any {{
	data := _ksInputReadRaw(receiver)
	raw, ok := data.(_ksBytes)
	if !ok {{
		return data
	}}
	if !utf8.ValidString(raw.data) {{
		return _ksError{{message: {not_text_message}}}
	}}
	return raw.data
}}

func _ksInputReadBytes(receiver any) any {{
	return _ksInputReadRaw(receiver)
}}

func _ksInputReadRaw(receiver any) any {{
	input, ok := receiver.(_ksInputCaps)
	if !ok {{
		_ksAbort("KS5002", "InputCaps.read receiver drifted")
	}}
	limit := input.maxBytes + 1
	chunk := make([]byte, 65536)
	data := []byte{{}}
	for len(data) < limit {{
		want := limit - len(data)
		if want > len(chunk) {{
			want = len(chunk)
		}}
		n, err := os.Stdin.Read(chunk[:want])
		data = append(data, chunk[:n]...)
		if err == io.EOF {{
			break
		}}
		if err != nil {{
			return _ksError{{message: {unavailable_message}}}
		}}
	}}
	if len(data) > input.maxBytes {{
		return _ksError{{message: {budget_prefix} + strconv.Itoa(input.maxBytes) + {budget_suffix}}}
	}}
	return _ksBytes{{data: string(data)}}
}}
'''

# Emitted only for programs that read the clock (``clock_random_v1``).
MIR_GO_CLOCK_IMPORTS_V2 = ("time",)
MIR_GO_CLOCK_RUNTIME_V2 = r'''
var _ksMonotonicOrigin = time.Now()

func _ksCapsClock(receiver any) any {{
	if _, ok := receiver.(_ksSystemCaps); !ok {{
		_ksAbort("KS5002", "SystemCaps.clock receiver drifted")
	}}
	return _ksClockRoot{{}}
}}

func _ksClockAllow(receiver any, resolution any) any {{
	if _, ok := receiver.(_ksClockRoot); !ok {{
		_ksAbort("KS5002", "ClockRoot.allow receiver drifted")
	}}
	value, ok := resolution.(int64)
	if !ok {{
		return _ksError{{message: {type_message}}}
	}}
	if value < {min_resolution} || value > {max_resolution} {{
		return _ksError{{message: {range_message}}}
	}}
	return _ksClockCaps{{resolution: value}}
}}

func _ksClockCapsOf(receiver any) _ksClockCaps {{
	clock, ok := receiver.(_ksClockCaps)
	if !ok {{
		_ksAbort("KS5002", "ClockCaps receiver drifted")
	}}
	return clock
}}

func _ksClockNow(receiver any) any {{
	clock := _ksClockCapsOf(receiver)
	now := time.Now().UnixMilli()
	return now - now%clock.resolution
}}

func _ksClockMonotonic(receiver any) any {{
	clock := _ksClockCapsOf(receiver)
	elapsed := time.Since(_ksMonotonicOrigin).Milliseconds()
	return elapsed - elapsed%clock.resolution
}}
'''

# Emitted only for programs that draw randomness. crypto/rand is the
# operating system's secure source; Koschei implements no generator.
MIR_GO_RANDOM_IMPORTS_V2 = ("crypto/rand", "encoding/hex", "math/big")
MIR_GO_RANDOM_RUNTIME_V2 = r'''
func _ksCapsRandom(receiver any) any {{
	if _, ok := receiver.(_ksSystemCaps); !ok {{
		_ksAbort("KS5002", "SystemCaps.random receiver drifted")
	}}
	return _ksRandomRoot{{}}
}}

func _ksRandomAllow(receiver any, budget any) any {{
	if _, ok := receiver.(_ksRandomRoot); !ok {{
		_ksAbort("KS5002", "RandomRoot.allow receiver drifted")
	}}
	value, ok := budget.(int64)
	if !ok {{
		return _ksError{{message: {type_message}}}
	}}
	if value < {min_bytes} || value > {max_bytes} {{
		return _ksError{{message: {range_message}}}
	}}
	return &_ksRandomCaps{{maxBytes: value, remaining: value}}
}}

func _ksRandomCapsOf(receiver any) *_ksRandomCaps {{
	random, ok := receiver.(*_ksRandomCaps)
	if !ok {{
		_ksAbort("KS5002", "RandomCaps receiver drifted")
	}}
	return random
}}

func _ksRandomCharge(random *_ksRandomCaps, cost int64) any {{
	if cost > random.remaining {{
		return _ksError{{message: {budget_prefix} + strconv.FormatInt(random.maxBytes, 10) + {budget_suffix}}}
	}}
	random.remaining -= cost
	return nil
}}

func _ksRandomFailed() {{
	_ksAbort("KS5002", "secure random source failed; no weak value is produced")
}}

func _ksRandomHex(receiver any, count any) any {{
	random := _ksRandomCapsOf(receiver)
	n, ok := count.(int64)
	if !ok || n < 1 || n > {max_hex} {{
		return _ksError{{message: {hex_message}}}
	}}
	if refused := _ksRandomCharge(random, n); refused != nil {{
		return refused
	}}
	buffer := make([]byte, n)
	if _, err := rand.Read(buffer); err != nil {{
		_ksRandomFailed()
	}}
	return hex.EncodeToString(buffer)
}}

func _ksRandomBytes(receiver any, count any) any {{
	random := _ksRandomCapsOf(receiver)
	n, ok := count.(int64)
	if !ok || n < 1 || n > {max_hex} {{
		return _ksError{{message: {bytes_message}}}
	}}
	if refused := _ksRandomCharge(random, n); refused != nil {{
		return refused
	}}
	buffer := make([]byte, n)
	if _, err := rand.Read(buffer); err != nil {{
		_ksRandomFailed()
	}}
	return _ksBytes{{data: string(buffer)}}
}}

func _ksRandomBelow(receiver any, bound any) any {{
	random := _ksRandomCapsOf(receiver)
	n, ok := bound.(int64)
	if !ok || n < 1 {{
		return _ksError{{message: {below_message}}}
	}}
	if refused := _ksRandomCharge(random, {below_cost}); refused != nil {{
		return refused
	}}
	value, err := rand.Int(rand.Reader, big.NewInt(n))
	if err != nil {{
		_ksRandomFailed()
	}}
	return value.Int64()
}}
'''

# Bytes members and builtins (``bytes_v1``); always emitted with the base
# runtime because _ksInvokeMember dispatches to them. Messages come from the
# Python constants.
MIR_GO_BYTES_RUNTIME_V2 = r'''
func _ksBytesMember(receiver _ksBytes, name string, arguments []any) any {{
	data := receiver.data
	switch name {{
	case "length":
		_ksArity("length", arguments, 0)
		return int64(len(data))
	case "hex":
		_ksArity("hex", arguments, 0)
		if 2*len(data) > _ksMaxStringBytes {{
			return _ksStringBudgetError
		}}
		return _ksHexText(data)
	case "to_text":
		_ksArity("to_text", arguments, 0)
		if !utf8.ValidString(data) {{
			return _ksError{{message: {not_text_message}}}
		}}
		return data
	case "slice":
		_ksArity("slice", arguments, 2)
		start, okStart := arguments[0].(int64)
		end, okEnd := arguments[1].(int64)
		if !okStart || !okEnd || start < 0 || start > end || end > int64(len(data)) {{
			return _ksError{{message: {slice_prefix} + _ksToString(arguments[0]) + ".." + _ksToString(arguments[1]) + {slice_middle} + strconv.Itoa(len(data)) + {slice_suffix}}}
		}}
		return _ksBytes{{data: data[start:end]}}
	case "get":
		_ksArity("get", arguments, 1)
		index, ok := arguments[0].(int64)
		if !ok || index < 0 || index >= int64(len(data)) {{
			return _ksError{{message: {get_prefix} + _ksToString(arguments[0]) + {get_middle} + strconv.Itoa(len(data)) + {get_suffix}}}
		}}
		return int64(data[index])
	}}
	_ksAbort("KS3101", "undefined member '"+name+"'")
	return nil
}}

func _ksBytesFromHex(arguments ...any) any {{
	_ksArity("bytes_from_hex", arguments, 1)
	text, ok := arguments[0].(string)
	if !ok || len(text)%2 != 0 {{
		return _ksError{{message: {hex_message}}}
	}}
	out := make([]byte, len(text)/2)
	for index := 0; index < len(text); index++ {{
		symbol := text[index]
		var value byte
		switch {{
		case symbol >= '0' && symbol <= '9':
			value = symbol - '0'
		case symbol >= 'a' && symbol <= 'f':
			value = symbol - 'a' + 10
		case symbol >= 'A' && symbol <= 'F':
			value = symbol - 'A' + 10
		default:
			return _ksError{{message: {hex_message}}}
		}}
		if index%2 == 0 {{
			out[index/2] = value << 4
		}} else {{
			out[index/2] |= value
		}}
	}}
	return _ksBytes{{data: string(out)}}
}}
'''

# Emitted with the SHA3 runtime when a program digests Bytes.
MIR_GO_SHA3_BYTES_RUNTIME_V2 = r'''
func _ksSha3_256Bytes(arguments ...any) any {{
	_ksArity("sha3_256_bytes", arguments, 1)
	data, ok := arguments[0].(_ksBytes)
	if !ok {{
		return _ksError{{message: {type_message}}}
	}}
	if len(data.data) > _ksSha3MaxInputBytes {{
		return _ksError{{message: {size_message}}}
	}}
	sum := sha3.Sum256([]byte(data.data))
	return hex.EncodeToString(sum[:])
}}
'''
