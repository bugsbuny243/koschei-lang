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

const _ksMaxCallDepth = 512
const _ksIntMin = -9223372036854775808
const _ksIntMax = 9223372036854775807

var _ksDepth = 0

func _ksAbort(code string, message string) {
	fmt.Fprintln(os.Stderr, "KOSCHEI RUNTIME ERROR: "+code+": "+message)
	os.Exit(1)
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
	case _ksUnit:
		_, ok := right.(_ksUnit)
		return ok
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
				return x + y
			}
		case []any:
			if y, ok := right.([]any); ok {
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
		case "length", "contains", "trim", "split", "join":
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
	case string:
		switch member.name {
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
		case "split":
			_ksArity("split", arguments, 1)
			separator, ok := arguments[0].(string)
			if !ok {
				return _ksError{message: "String.split() ayıracı String olmalıdır"}
			}
			if separator == "" {
				return _ksError{message: "String.split() ayıracı boş olamaz"}
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
			for index, value := range values {
				text, ok := value.(string)
				if !ok {
					return _ksError{message: "String.join() yalnızca String öğeleri birleştirir"}
				}
				pieces[index] = text
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
	}
	return false
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
