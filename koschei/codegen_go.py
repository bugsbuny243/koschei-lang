"""Koschei AST -> Go kaynak kodu üreteci.

v0.8 alpha 4, capability ABI, cebirsel tipler ve immutable koleksiyonları native binary’ye taşır:
SystemCaps kökü yalnızca main’e enjekte edilir; ağ origin’i ve disk yolu çalışma
anında fail-closed sınırlandırılır. Disk ABI bu aşamada Linux openat/O_NOFOLLOW
hedefinde desteklenir; daha zayıf yol doğrulamasına sessizce düşülmez.

Üretilen Go kodu kullanıcıya gösterilmek için değildir; Koschei için bir ara
temsildir (assembly gibi). Bu yüzden okunabilirlik değil, DAVRANIŞ EŞLİĞİ
önceliklidir: `ks run` ile üretilen binary aynı çıktıyı vermelidir.

Hata kodları:
    KS4001  Native hedefte güvenli uygulanamayan yetki sözleşmesi
    KS4002  Desteklenmeyen dil yapısı
    KS4003  Fonksiyon çağrısında argüman sayısı uyuşmuyor
"""

from __future__ import annotations

import sys

from .ast_nodes import (
    AssignmentExpression,
    ForStatement,
    ListLiteral,
    MapLiteral,
    StructLiteral,
    BinaryExpression,
    Block,
    CallExpression,
    Expression,
    ExpressionStatement,
    FunctionDeclaration,
    Identifier,
    IfStatement,
    InterpolatedString,
    LetStatement,
    Literal,
    MatchExpression,
    MemberExpression,
    OrBlockExpression,
    OrElseExpression,
    OrReturnExpression,
    Program,
    ReturnStatement,
    SourceLocation,
    Statement,
    UnaryExpression,
    WhileStatement,
)
from .semantic import (
    CAPABILITY_TYPES,
    GUARDED_METHODS,
    INT_MAX,
    INT_MIN,
    INT_MIN_MAGNITUDE,
)

MAX_CALL_DEPTH = 512

NATIVE_CAPABILITY_METHODS = {
    "allow",
    "allow_read_only",
    "get",
    "post",
    "put",
    "delete",
    "request",
    "read",
    "read_file",
    "write",
    "write_file",
    "list",
    "run",
    "spawn",
    "text",
    "status",
}

STRING_METHODS = {
    "length",
    "to_int",
    "to_float",
    "contains",
    "trim",
    "split",
    "join",
}

LIST_METHODS = {"length", "get", "push", "contains", "sort", "filter"}
MAP_METHODS = {"get", "set", "keys", "contains"}
VALUE_METHODS = STRING_METHODS | LIST_METHODS | MAP_METHODS

BINARY_HELPERS = {
    "+": "ksAdd",
    "-": "ksSub",
    "*": "ksMul",
    "/": "ksDiv",
    "==": "ksEq",
    "!=": "ksNotEq",
    "<": "ksLess",
    "<=": "ksLessEq",
    ">": "ksGreater",
    ">=": "ksGreaterEq",
}


class CodegenError(Exception):
    def __init__(self, code: str, message: str, location: SourceLocation) -> None:
        self.code = code
        self.message = message
        self.location = location
        super().__init__(
            f"{code} [satır {location.line}, sütun {location.column}]: {message}"
        )


RUNTIME_PRELUDE = '''// Koschei runtime — üretilmiş kod, elle düzenlemeyin.

type KsError struct {
	Message string
}

func (e *KsError) Error() string {
	return e.Message
}

type ksUnitType struct{}

var ksUnit any = ksUnitType{}

type KsEnum struct {
	EnumName   string
	Variant    string
	Payload    any
	HasPayload bool
}

func ksEnum(enumName string, variant string, payload any, hasPayload bool) any {
	if hasPayload && ksContainsCapability(payload) {
		return ksErrorf("KS3401: Capability taşıyan değerler enum/Option/Result payload'ına konamaz.")
	}
	return &KsEnum{EnumName: enumName, Variant: variant, Payload: payload, HasPayload: hasPayload}
}

func ksNewList(values []any) any {
	for _, value := range values {
		if ksContainsCapability(value) {
			return ksErrorf("KS3401: Capability taşıyan değerler List içine konamaz")
		}
	}
	return values
}

type KsMap struct {
	Keys   []string
	Values map[string]any
}

func ksNewMap(keys []any, values []any) any {
	if len(keys) != len(values) {
		return ksErrorf("KS3101: Map anahtar/değer sayısı uyuşmuyor")
	}
	result := &KsMap{Keys: make([]string, 0, len(keys)), Values: make(map[string]any, len(keys))}
	for index, rawKey := range keys {
		key, ok := rawKey.(string)
		if !ok {
			return ksErrorf("Map anahtarı String olmalıdır")
		}
		if _, exists := result.Values[key]; exists {
			return ksErrorf("KS3101: Yinelenen Map anahtarı: " + key)
		}
		if ksContainsCapability(values[index]) {
			return ksErrorf("KS3401: Capability taşıyan değerler Map içine konamaz")
		}
		result.Keys = append(result.Keys, key)
		result.Values[key] = values[index]
	}
	return result
}

func ksUnwrapFallible(value any) (bool, any) {
	if _, ok := value.(*KsError); ok {
		return false, value
	}
	if item, ok := value.(*KsEnum); ok {
		switch item.EnumName {
		case "Option":
			if item.Variant == "Some" && item.HasPayload {
				return true, item.Payload
			}
			if item.Variant == "None" {
				return false, value
			}
		case "Result":
			if item.Variant == "Ok" && item.HasPayload {
				return true, item.Payload
			}
			if item.Variant == "Err" {
				return false, value
			}
		}
	}
	return true, value
}

const ksMaxDepth = 512
const ksIntMin int64 = -9223372036854775808
const ksIntMax int64 = 9223372036854775807

var ksDepth int

func ksFatal(code string, message string) {
	fmt.Fprintln(os.Stderr, "KOSCHEI RUNTIME ERROR: "+code+": "+message)
	os.Exit(1)
}

func ksIsError(value any) bool {
	_, ok := value.(*KsError)
	return ok
}

func ksErrorf(message string) any {
	return &KsError{Message: message}
}

func ksToString(value any) string {
	switch item := value.(type) {
	case string:
		return item
	case bool:
		if item {
			return "true"
		}
		return "false"
	case int64:
		return strconv.FormatInt(item, 10)
	case float64:
		text := strconv.FormatFloat(item, 'g', -1, 64)
		if !strings.ContainsAny(text, ".eE") {
			text = text + ".0"
		}
		return text
	case ksUnitType:
		return "unit"
	case *KsError:
		return item.Message
	case *KsEnum:
		if !item.HasPayload {
			return item.Variant
		}
		return item.Variant + "(" + ksToString(item.Payload) + ")"
	case []string:
		parts := make([]string, len(item))
		for index, value := range item {
			parts[index] = strconv.Quote(value)
		}
		return "[" + strings.Join(parts, ", ") + "]"
	case []any:
		parts := make([]string, len(item))
		for index, value := range item {
			parts[index] = ksRepr(value)
		}
		return "[" + strings.Join(parts, ", ") + "]"
	case *KsMap:
		parts := make([]string, 0, len(item.Keys))
		for _, key := range item.Keys {
			parts = append(parts, strconv.Quote(key)+": "+ksRepr(item.Values[key]))
		}
		return "{" + strings.Join(parts, ", ") + "}"
	}
	return fmt.Sprintf("%v", value)
}

func ksRepr(value any) string {
	if item, ok := value.(string); ok {
		return strconv.Quote(item)
	}
	return ksToString(value)
}

func ksPrintln(value any) any {
	fmt.Println(ksToString(value))
	return ksUnit
}

func ksPrint(value any) any {
	fmt.Print(ksToString(value))
	return ksUnit
}

func ksTruthy(value any) bool {
	if item, ok := value.(bool); ok {
		return item
	}
	return false
}

func ksNot(value any) any {
	return !ksTruthy(value)
}

func ksIntOverflow(operation string) any {
	return ksErrorf("KS3501: Int taşması: '" + operation + "' işlemi işaretli 64-bit aralığın dışına çıktı.")
}

func ksNegate(value any) any {
	switch item := value.(type) {
	case int64:
		if item == ksIntMin {
			return ksIntOverflow("unary -")
		}
		return -item
	case float64:
		return -item
	}
	return ksErrorf("KS1301: '-' işleci sayısal tip bekler")
}

func ksAdd(left any, right any) any {
	switch a := left.(type) {
	case int64:
		if b, ok := right.(int64); ok {
			if (b > 0 && a > ksIntMax-b) || (b < 0 && a < ksIntMin-b) {
				return ksIntOverflow("+")
			}
			return a + b
		}
	case float64:
		if b, ok := right.(float64); ok {
			return a + b
		}
	case string:
		if b, ok := right.(string); ok {
			return a + b
		}
	}
	return ksErrorf("KS1301: '+' işleci bu tiplere uygulanamaz")
}

func ksSub(left any, right any) any {
	switch a := left.(type) {
	case int64:
		if b, ok := right.(int64); ok {
			if (b > 0 && a < ksIntMin+b) || (b < 0 && a > ksIntMax+b) {
				return ksIntOverflow("-")
			}
			return a - b
		}
	case float64:
		if b, ok := right.(float64); ok {
			return a - b
		}
	}
	return ksErrorf("KS1301: '-' işleci bu tiplere uygulanamaz")
}

func ksMul(left any, right any) any {
	switch a := left.(type) {
	case int64:
		if b, ok := right.(int64); ok {
			if a == 0 || b == 0 {
				return int64(0)
			}
			if (a == ksIntMin && b == -1) || (b == ksIntMin && a == -1) {
				return ksIntOverflow("*")
			}
			result := a * b
			if result/b != a {
				return ksIntOverflow("*")
			}
			return result
		}
	case float64:
		if b, ok := right.(float64); ok {
			return a * b
		}
	}
	return ksErrorf("KS1301: '*' işleci bu tiplere uygulanamaz")
}

func ksDiv(left any, right any) any {
	switch a := left.(type) {
	case int64:
		if b, ok := right.(int64); ok {
			if b == 0 {
				return ksErrorf("Sıfıra bölme")
			}
			return float64(a) / float64(b)
		}
	case float64:
		if b, ok := right.(float64); ok {
			if b == 0 {
				return ksErrorf("Sıfıra bölme")
			}
			return a / b
		}
	}
	return ksErrorf("KS1301: '/' işleci bu tiplere uygulanamaz")
}

func ksCompare(left any, right any) (int, bool) {
	switch a := left.(type) {
	case int64:
		if b, ok := right.(int64); ok {
			switch {
			case a < b:
				return -1, true
			case a > b:
				return 1, true
			}
			return 0, true
		}
	case float64:
		if b, ok := right.(float64); ok {
			switch {
			case a < b:
				return -1, true
			case a > b:
				return 1, true
			}
			return 0, true
		}
	case string:
		if b, ok := right.(string); ok {
			return strings.Compare(a, b), true
		}
	}
	return 0, false
}

func ksLess(left any, right any) any {
	order, ok := ksCompare(left, right)
	if !ok {
		return ksErrorf("KS1301: '<' iki farklı tipi karşılaştıramaz")
	}
	return order < 0
}

func ksLessEq(left any, right any) any {
	order, ok := ksCompare(left, right)
	if !ok {
		return ksErrorf("KS1301: '<=' iki farklı tipi karşılaştıramaz")
	}
	return order <= 0
}

func ksGreater(left any, right any) any {
	order, ok := ksCompare(left, right)
	if !ok {
		return ksErrorf("KS1301: '>' iki farklı tipi karşılaştıramaz")
	}
	return order > 0
}

func ksGreaterEq(left any, right any) any {
	order, ok := ksCompare(left, right)
	if !ok {
		return ksErrorf("KS1301: '>=' iki farklı tipi karşılaştıramaz")
	}
	return order >= 0
}

func ksEq(left any, right any) any {
	if a, ok := left.(*KsEnum); ok {
		b, ok := right.(*KsEnum)
		if !ok || a.EnumName != b.EnumName || a.Variant != b.Variant || a.HasPayload != b.HasPayload {
			return false
		}
		if !a.HasPayload {
			return true
		}
		return ksTruthy(ksEq(a.Payload, b.Payload))
	}
	if a, ok := left.(*KsError); ok {
		b, ok := right.(*KsError)
		return ok && a.Message == b.Message
	}
	if a, ok := left.([]any); ok {
		b, ok := right.([]any)
		if !ok || len(a) != len(b) {
			return false
		}
		for index := range a {
			if !ksTruthy(ksEq(a[index], b[index])) {
				return false
			}
		}
		return true
	}
	if a, ok := left.(*KsMap); ok {
		b, ok := right.(*KsMap)
		if !ok || len(a.Values) != len(b.Values) {
			return false
		}
		for key, value := range a.Values {
			other, exists := b.Values[key]
			if !exists || !ksTruthy(ksEq(value, other)) {
				return false
			}
		}
		return true
	}
	switch a := left.(type) {
	case string:
		b, ok := right.(string)
		return ok && a == b
	case bool:
		b, ok := right.(bool)
		return ok && a == b
	case int64:
		b, ok := right.(int64)
		return ok && a == b
	case float64:
		b, ok := right.(float64)
		return ok && a == b
	case ksUnitType:
		_, ok := right.(ksUnitType)
		return ok
	}
	return false
}

func ksNotEq(left any, right any) any {
	return !ksTruthy(ksEq(left, right))
}

func ksLength(value any) any {
	switch item := value.(type) {
	case string:
		return int64(len([]rune(item)))
	case []any:
		return int64(len(item))
	}
	return ksErrorf("KS1301: 'length' yalnızca String veya List üzerinde çağrılabilir")
}

func ksToInt(value any) any {
	item, ok := value.(string)
	if !ok {
		return ksErrorf("KS1301: 'to_int' yalnızca String üzerinde çağrılabilir")
	}
	parsed, err := strconv.ParseInt(strings.TrimSpace(item), 10, 64)
	if err != nil {
		return ksErrorf("Int dönüşümü başarısız: " + item)
	}
	return parsed
}

func ksToFloat(value any) any {
	item, ok := value.(string)
	if !ok {
		return ksErrorf("KS1301: 'to_float' yalnızca String üzerinde çağrılabilir")
	}
	parsed, err := strconv.ParseFloat(strings.TrimSpace(item), 64)
	if err != nil {
		return ksErrorf("Float dönüşümü başarısız: " + item)
	}
	return parsed
}

func ksContains(value any, needle any) any {
	switch item := value.(type) {
	case string:
		return strings.Contains(item, ksToString(needle))
	case []any:
		for _, candidate := range item {
			if ksTruthy(ksEq(candidate, needle)) {
				return true
			}
		}
		return false
	case *KsMap:
		key, ok := needle.(string)
		if !ok {
			return ksErrorf("Map anahtarı String olmalıdır")
		}
		_, exists := item.Values[key]
		return exists
	}
	return ksErrorf("KS1301: 'contains' bu değer üzerinde çağrılamaz")
}

func ksTrim(value any) any {
	item, ok := value.(string)
	if !ok {
		return ksErrorf("KS1301: 'trim' yalnızca String üzerinde çağrılabilir")
	}
	return strings.TrimSpace(item)
}

func ksSplit(value any, separator any) any {
	text, ok := value.(string)
	if !ok {
		return ksErrorf("String.split() yalnızca String üzerinde çağrılabilir")
	}
	sep, ok := separator.(string)
	if !ok {
		return ksErrorf("String.split() ayıracı String olmalıdır")
	}
	if sep == "" {
		return ksErrorf("String.split() ayıracı boş olamaz")
	}
	raw := strings.Split(text, sep)
	result := make([]any, len(raw))
	for index, item := range raw {
		result[index] = item
	}
	return result
}

func ksJoin(separator any, values any) any {
	sep, ok := separator.(string)
	if !ok {
		return ksErrorf("String.join() yalnızca String üzerinde çağrılabilir")
	}
	list, ok := values.([]any)
	if !ok {
		return ksErrorf("String.join() bir List bekler")
	}
	parts := make([]string, len(list))
	for index, item := range list {
		text, ok := item.(string)
		if !ok {
			return ksErrorf("String.join() yalnızca String öğeleri birleştirir")
		}
		parts[index] = text
	}
	return strings.Join(parts, sep)
}

func ksListGet(value any, index any) any {
	list, ok := value.([]any)
	if !ok {
		return ksErrorf("List.get() bir List bekler")
	}
	position, ok := index.(int64)
	if !ok {
		return ksErrorf("Liste indeksi Int olmalıdır")
	}
	if position < 0 || position >= int64(len(list)) {
		return ksErrorf("Liste indeksi aralık dışında: " + strconv.FormatInt(position, 10) + " (uzunluk " + strconv.Itoa(len(list)) + ")")
	}
	return list[position]
}

func ksListPush(value any, item any) any {
	list, ok := value.([]any)
	if !ok {
		return ksErrorf("List.push() bir List bekler")
	}
	if ksContainsCapability(item) {
		return ksErrorf("KS3401: Capability taşıyan değerler List içine konamaz")
	}
	result := make([]any, len(list), len(list)+1)
	copy(result, list)
	return append(result, item)
}

func ksListSort(value any) any {
	list, ok := value.([]any)
	if !ok {
		return ksErrorf("List.sort() bir List bekler")
	}
	result := append([]any(nil), list...)
	if len(result) == 0 {
		return result
	}
	allStrings := true
	allNumeric := true
	for _, item := range result {
		if _, ok := item.(string); !ok {
			allStrings = false
		}
		switch item.(type) {
		case int64, float64:
		default:
			allNumeric = false
		}
	}
	if !allStrings && !allNumeric {
		return ksErrorf("List.sort() yalnızca homojen String veya sayısal öğeleri sıralar")
	}
	if allStrings {
		sort.SliceStable(result, func(i, j int) bool { return result[i].(string) < result[j].(string) })
		return result
	}
	asFloat := func(value any) float64 {
		if integer, ok := value.(int64); ok {
			return float64(integer)
		}
		return value.(float64)
	}
	sort.SliceStable(result, func(i, j int) bool { return asFloat(result[i]) < asFloat(result[j]) })
	return result
}

func ksListFilter(value any, predicate any) any {
	list, ok := value.([]any)
	if !ok {
		return ksErrorf("List.filter() bir List bekler")
	}
	function, ok := predicate.(func(any) any)
	if !ok {
		return ksErrorf("List.filter() yerel, adlandırılmış bir predicate fonksiyonu bekler")
	}
	result := make([]any, 0, len(list))
	for _, item := range list {
		decision := function(item)
		if failure, ok := decision.(*KsError); ok {
			return failure
		}
		keep, ok := decision.(bool)
		if !ok {
			return ksErrorf("List.filter() predicate'i Bool döndürmelidir")
		}
		if keep {
			result = append(result, item)
		}
	}
	return result
}

func ksMapGet(value any, keyValue any) any {
	mapping, ok := value.(*KsMap)
	if !ok {
		return ksErrorf("Map.get() bir Map bekler")
	}
	key, ok := keyValue.(string)
	if !ok {
		return ksErrorf("Map anahtarı String olmalıdır")
	}
	item, exists := mapping.Values[key]
	if !exists {
		return ksErrorf("Map anahtarı bulunamadı: " + key)
	}
	return item
}

func ksMapSet(value any, keyValue any, item any) any {
	mapping, ok := value.(*KsMap)
	if !ok {
		return ksErrorf("Map.set() bir Map bekler")
	}
	key, ok := keyValue.(string)
	if !ok {
		return ksErrorf("Map anahtarı String olmalıdır")
	}
	if ksContainsCapability(item) {
		return ksErrorf("KS3401: Capability taşıyan değerler Map içine konamaz")
	}
	result := &KsMap{Keys: append([]string(nil), mapping.Keys...), Values: make(map[string]any, len(mapping.Values)+1)}
	for existing, existingValue := range mapping.Values {
		result.Values[existing] = existingValue
	}
	if _, exists := result.Values[key]; !exists {
		result.Keys = append(result.Keys, key)
	}
	result.Values[key] = item
	return result
}

func ksMapKeys(value any) any {
	mapping, ok := value.(*KsMap)
	if !ok {
		return ksErrorf("Map.keys() bir Map bekler")
	}
	result := make([]any, len(mapping.Keys))
	for index, key := range mapping.Keys {
		result[index] = key
	}
	return result
}

func ksCallValueMethod(receiver any, method string, arguments ...any) any {
	switch receiver.(type) {
	case string:
		switch method {
		case "length":
			if len(arguments) != 0 { return ksErrorf("KS4003: length argüman almaz") }
			return ksLength(receiver)
		case "to_int":
			if len(arguments) != 0 { return ksErrorf("KS4003: to_int argüman almaz") }
			return ksToInt(receiver)
		case "to_float":
			if len(arguments) != 0 { return ksErrorf("KS4003: to_float argüman almaz") }
			return ksToFloat(receiver)
		case "contains":
			if len(arguments) != 1 { return ksErrorf("KS4003: contains bir argüman alır") }
			return ksContains(receiver, arguments[0])
		case "trim":
			if len(arguments) != 0 { return ksErrorf("KS4003: trim argüman almaz") }
			return ksTrim(receiver)
		case "split":
			if len(arguments) != 1 { return ksErrorf("KS4003: split bir argüman alır") }
			return ksSplit(receiver, arguments[0])
		case "join":
			if len(arguments) != 1 { return ksErrorf("KS4003: join bir argüman alır") }
			return ksJoin(receiver, arguments[0])
		}
	case []any:
		switch method {
		case "length":
			if len(arguments) != 0 { return ksErrorf("KS4003: length argüman almaz") }
			return ksLength(receiver)
		case "get":
			if len(arguments) != 1 { return ksErrorf("KS4003: get bir argüman alır") }
			return ksListGet(receiver, arguments[0])
		case "push":
			if len(arguments) != 1 { return ksErrorf("KS4003: push bir argüman alır") }
			return ksListPush(receiver, arguments[0])
		case "contains":
			if len(arguments) != 1 { return ksErrorf("KS4003: contains bir argüman alır") }
			return ksContains(receiver, arguments[0])
		case "sort":
			if len(arguments) != 0 { return ksErrorf("KS4003: sort argüman almaz") }
			return ksListSort(receiver)
		case "filter":
			if len(arguments) != 1 { return ksErrorf("KS4003: filter bir argüman alır") }
			return ksListFilter(receiver, arguments[0])
		}
	case *KsMap:
		switch method {
		case "get":
			if len(arguments) != 1 { return ksErrorf("KS4003: get bir argüman alır") }
			return ksMapGet(receiver, arguments[0])
		case "set":
			if len(arguments) != 2 { return ksErrorf("KS4003: set iki argüman alır") }
			return ksMapSet(receiver, arguments[0], arguments[1])
		case "keys":
			if len(arguments) != 0 { return ksErrorf("KS4003: keys argüman almaz") }
			return ksMapKeys(receiver)
		case "contains":
			if len(arguments) != 1 { return ksErrorf("KS4003: contains bir argüman alır") }
			return ksContains(receiver, arguments[0])
		}
	}
	return ksErrorf("KS3101: Bu değer üzerinde '" + method + "' metodu yok")
}

func ksEnter(location string) {
	ksDepth++
	if ksDepth > ksMaxDepth {
		ksFatal("KS3105", "Çağrı derinliği sınırı aşıldı (512); sonsuz özyineleme olabilir. ["+location+"]")
	}
}

func ksLeave() {
	ksDepth--
}
'''

CAPABILITY_RUNTIME = r'''// Capability runtime ABI v1 alpha — Linux için fail-closed kapsam koruması.

type ksSystemCaps struct {
	net     *ksNetRoot
	disk    *ksDiskRoot
	env     *ksEnvRoot
	process *ksProcessRoot
}

type ksNetRoot struct{}
type ksDiskRoot struct{}
type ksEnvRoot struct{}
type ksProcessRoot struct{}

type ksOriginKey struct {
	scheme string
	host   string
	port   string
}

type ksNetCaps struct {
	origin string
	key    ksOriginKey
	valid  bool
}

type ksDiskCapability struct {
	rootPath  string
	rootFD    int
	openError string
	readOnly  bool
}

type ksDiskCaps struct{ capability *ksDiskCapability }
type ksDiskReadCaps struct{ capability *ksDiskCapability }
type ksEnvCaps struct{ name string }
type ksProcessCaps struct{ command string }

func ksContainsCapability(value any) bool {
	switch item := value.(type) {
	case *ksSystemCaps, *ksNetRoot, *ksDiskRoot, *ksEnvRoot, *ksProcessRoot,
		*ksNetCaps, *ksDiskCaps, *ksDiskReadCaps, *ksEnvCaps, *ksProcessCaps:
		return true
	case *KsEnum:
		return item.HasPayload && ksContainsCapability(item.Payload)
	case []any:
		for _, value := range item {
			if ksContainsCapability(value) { return true }
		}
	case *KsMap:
		for _, value := range item.Values {
			if ksContainsCapability(value) { return true }
		}
	}
	return false
}

type ksResponse struct {
	body   string
	status int64
}

type ksRedirectDenied struct{ target string }

func (e *ksRedirectDenied) Error() string {
	return "KS3402: Ağ yönlendirmesi kapsam dışına çıktı: " + e.target
}

func ksNewSystemCaps() any {
	return &ksSystemCaps{
		net:     &ksNetRoot{},
		disk:    &ksDiskRoot{},
		env:     &ksEnvRoot{},
		process: &ksProcessRoot{},
	}
}

func ksMember(value any, name string) any {
	if failure, ok := value.(*KsError); ok {
		return failure
	}
	switch item := value.(type) {
	case *ksSystemCaps:
		switch name {
		case "net":
			return item.net
		case "disk":
			return item.disk
		case "env":
			return item.env
		case "process":
			return item.process
		}
	}
	return ksErrorf("KS3101: Tanımsız alan: '" + name + "'.")
}

func ksMethodArity(method string, arguments []any, expected int) *KsError {
	if len(arguments) == expected {
		return nil
	}
	return &KsError{Message: fmt.Sprintf(
		"KS4003: '%s' için %d argüman bekleniyor, %d verildi.",
		method, expected, len(arguments),
	)}
}

func ksStringArgument(method string, arguments []any, index int) (string, *KsError) {
	if index >= len(arguments) {
		return "", &KsError{Message: "KS4003: Eksik metot argümanı: " + method}
	}
	value, ok := arguments[index].(string)
	if !ok {
		return "", &KsError{Message: "KS1301: '" + method + "' String argüman bekler."}
	}
	return value, nil
}

func ksParseOrigin(raw string) (ksOriginKey, bool) {
	parsed, err := url.Parse(raw)
	if err != nil || parsed.Scheme == "" || parsed.Hostname() == "" {
		return ksOriginKey{}, false
	}
	scheme := strings.ToLower(parsed.Scheme)
	if scheme != "http" && scheme != "https" {
		return ksOriginKey{}, false
	}
	port := parsed.Port()
	if port == "" {
		if scheme == "https" {
			port = "443"
		} else {
			port = "80"
		}
	}
	return ksOriginKey{scheme: scheme, host: strings.ToLower(parsed.Hostname()), port: port}, true
}

func ksNetGet(capability *ksNetCaps, rawURL string) any {
	key, ok := ksParseOrigin(rawURL)
	if !capability.valid || !ok || key != capability.key {
		return ksErrorf("KS3402: Ağ origin kapsamı dışında erişim reddedildi: " + rawURL)
	}
	client := &http.Client{
		Timeout: 10 * time.Second,
		CheckRedirect: func(request *http.Request, via []*http.Request) error {
			if len(via) >= 5 {
				return fmt.Errorf("çok fazla yönlendirme")
			}
			redirectKey, allowed := ksParseOrigin(request.URL.String())
			if !allowed || redirectKey != capability.key {
				return &ksRedirectDenied{target: request.URL.String()}
			}
			return nil
		},
	}
	request, err := http.NewRequest(http.MethodGet, rawURL, nil)
	if err != nil {
		return ksErrorf("API isteği başarısız: " + err.Error())
	}
	response, err := client.Do(request)
	if err != nil {
		var denied *ksRedirectDenied
		if errors.As(err, &denied) {
			return ksErrorf(denied.Error())
		}
		return ksErrorf("API isteği başarısız: " + err.Error())
	}
	defer response.Body.Close()
	body, err := io.ReadAll(response.Body)
	if err != nil {
		return ksErrorf("API yanıtı okunamadı: " + err.Error())
	}
	return &ksResponse{body: string(body), status: int64(response.StatusCode)}
}

func ksNewDiskCapability(prefix string, readOnly bool) *ksDiskCapability {
	capability := &ksDiskCapability{rootFD: -1, readOnly: readOnly}
	absolute, err := filepath.Abs(prefix)
	if err != nil {
		capability.openError = err.Error()
		return capability
	}
	resolved, err := filepath.EvalSymlinks(absolute)
	if err == nil {
		absolute = resolved
	}
	capability.rootPath = filepath.Clean(absolute)
	if runtime.GOOS != "linux" {
		capability.openError = "KS3406: Native disk ABI şu anda yalnızca Linux openat/O_NOFOLLOW hedefinde destekleniyor."
		return capability
	}
	fd, err := syscall.Open(
		capability.rootPath,
		syscall.O_RDONLY|syscall.O_DIRECTORY|syscall.O_NOFOLLOW|syscall.O_CLOEXEC,
		0,
	)
	if err != nil {
		capability.openError = err.Error()
		return capability
	}
	capability.rootFD = fd
	return capability
}

func (capability *ksDiskCapability) reject(path string) any {
	return ksErrorf("KS3402: Disk kapsamı dışında erişim reddedildi: " + path)
}

func (capability *ksDiskCapability) symlinkDenied(name string) any {
	return ksErrorf(
		"KS3402: Disk kapsamı sembolik bağ üzerinden aşılamaz; " +
			"KS3405: Kapsam içinde sembolik bağ takip edilmez: " + name,
	)
}

func (capability *ksDiskCapability) parts(path string) ([]string, any) {
	absolute, err := filepath.Abs(path)
	if err != nil {
		return nil, capability.reject(path)
	}
	relative, err := filepath.Rel(capability.rootPath, filepath.Clean(absolute))
	if err != nil {
		return nil, capability.reject(path)
	}
	if relative == "." {
		return []string{}, nil
	}
	parentPrefix := ".." + string(os.PathSeparator)
	if relative == ".." || strings.HasPrefix(relative, parentPrefix) || filepath.IsAbs(relative) {
		return nil, capability.reject(path)
	}
	parts := strings.Split(filepath.Clean(relative), string(os.PathSeparator))
	for _, part := range parts {
		if part == "" || part == "." || part == ".." {
			return nil, capability.reject(path)
		}
	}
	return parts, nil
}

func (capability *ksDiskCapability) rootDuplicate(operation string) (int, any) {
	if capability.rootFD < 0 {
		if strings.HasPrefix(capability.openError, "KS3406:") {
			return -1, ksErrorf(capability.openError)
		}
		return -1, ksErrorf(operation + ": " + capability.openError)
	}
	fd, err := syscall.Dup(capability.rootFD)
	if err != nil {
		return -1, ksErrorf(operation + ": " + err.Error())
	}
	return fd, nil
}

func (capability *ksDiskCapability) parent(parts []string, operation string) (int, any) {
	current, failure := capability.rootDuplicate(operation)
	if failure != nil {
		return -1, failure
	}
	for _, component := range parts[:len(parts)-1] {
		next, err := syscall.Openat(
			current,
			component,
			syscall.O_RDONLY|syscall.O_DIRECTORY|syscall.O_NOFOLLOW|syscall.O_CLOEXEC,
			0,
		)
		syscall.Close(current)
		if err != nil {
			if errors.Is(err, syscall.ELOOP) || errors.Is(err, syscall.ENOTDIR) {
				return -1, capability.symlinkDenied(component)
			}
			return -1, ksErrorf(operation + ": " + err.Error())
		}
		current = next
	}
	return current, nil
}

func (capability *ksDiskCapability) read(path string) any {
	parts, failure := capability.parts(path)
	if failure != nil {
		return failure
	}
	if len(parts) == 0 {
		return ksErrorf("Dosya okunamadı: kapsam kökü bir dizindir: " + path)
	}
	parent, failure := capability.parent(parts, "Dosya okunamadı")
	if failure != nil {
		return failure
	}
	defer syscall.Close(parent)
	fd, err := syscall.Openat(
		parent, parts[len(parts)-1],
		syscall.O_RDONLY|syscall.O_NOFOLLOW|syscall.O_CLOEXEC,
		0,
	)
	if err != nil {
		if errors.Is(err, syscall.ELOOP) {
			return capability.symlinkDenied(parts[len(parts)-1])
		}
		return ksErrorf("Dosya okunamadı: " + err.Error())
	}
	file := os.NewFile(uintptr(fd), parts[len(parts)-1])
	if file == nil {
		syscall.Close(fd)
		return ksErrorf("Dosya okunamadı: geçersiz dosya tanıtıcısı")
	}
	defer file.Close()
	content, err := io.ReadAll(file)
	if err != nil {
		return ksErrorf("Dosya okunamadı: " + err.Error())
	}
	return string(content)
}

func (capability *ksDiskCapability) list(path string) any {
	parts, failure := capability.parts(path)
	if failure != nil {
		return failure
	}
	var fd int
	if len(parts) == 0 {
		fd, failure = capability.rootDuplicate("Dizin listelenemedi")
	} else {
		parent, parentFailure := capability.parent(parts, "Dizin listelenemedi")
		if parentFailure != nil {
			return parentFailure
		}
		defer syscall.Close(parent)
		var err error
		fd, err = syscall.Openat(
			parent, parts[len(parts)-1],
			syscall.O_RDONLY|syscall.O_DIRECTORY|syscall.O_NOFOLLOW|syscall.O_CLOEXEC,
			0,
		)
		if err != nil {
			if errors.Is(err, syscall.ELOOP) || errors.Is(err, syscall.ENOTDIR) {
				return capability.symlinkDenied(parts[len(parts)-1])
			}
			return ksErrorf("Dizin listelenemedi: " + err.Error())
		}
	}
	if failure != nil {
		return failure
	}
	file := os.NewFile(uintptr(fd), "directory")
	if file == nil {
		syscall.Close(fd)
		return ksErrorf("Dizin listelenemedi: geçersiz dosya tanıtıcısı")
	}
	defer file.Close()
	names, err := file.Readdirnames(-1)
	if err != nil {
		return ksErrorf("Dizin listelenemedi: " + err.Error())
	}
	sort.Strings(names)
	return names
}

func (capability *ksDiskCapability) write(path string, value string) any {
	parts, failure := capability.parts(path)
	if failure != nil {
		return failure
	}
	if capability.readOnly {
		return ksErrorf("KS3404: DiskReadCaps 'write' işlemine izin vermez.")
	}
	if len(parts) == 0 {
		return ksErrorf("Dosya yazılamadı: kapsam kökü bir dizindir: " + path)
	}
	parent, failure := capability.parent(parts, "Dosya yazılamadı")
	if failure != nil {
		return failure
	}
	defer syscall.Close(parent)
	fd, err := syscall.Openat(
		parent, parts[len(parts)-1],
		syscall.O_WRONLY|syscall.O_CREAT|syscall.O_TRUNC|syscall.O_NOFOLLOW|syscall.O_CLOEXEC,
		0600,
	)
	if err != nil {
		if errors.Is(err, syscall.ELOOP) {
			return capability.symlinkDenied(parts[len(parts)-1])
		}
		return ksErrorf("Dosya yazılamadı: " + err.Error())
	}
	file := os.NewFile(uintptr(fd), parts[len(parts)-1])
	if file == nil {
		syscall.Close(fd)
		return ksErrorf("Dosya yazılamadı: geçersiz dosya tanıtıcısı")
	}
	defer file.Close()
	if _, err := file.WriteString(value); err != nil {
		return ksErrorf("Dosya yazılamadı: " + err.Error())
	}
	return ksUnit
}

func (capability *ksDiskCapability) delete(path string) any {
	parts, failure := capability.parts(path)
	if failure != nil {
		return failure
	}
	if capability.readOnly {
		return ksErrorf("KS3404: DiskReadCaps 'delete' işlemine izin vermez.")
	}
	if len(parts) == 0 {
		return ksErrorf("Dosya silinemedi: kapsam kökü silinemez: " + path)
	}
	parent, failure := capability.parent(parts, "Dosya silinemedi")
	if failure != nil {
		return failure
	}
	defer syscall.Close(parent)
	fd, err := syscall.Openat(
		parent, parts[len(parts)-1],
		syscall.O_RDONLY|syscall.O_NOFOLLOW|syscall.O_CLOEXEC,
		0,
	)
	if err != nil {
		if errors.Is(err, syscall.ELOOP) {
			return capability.symlinkDenied(parts[len(parts)-1])
		}
		return ksErrorf("Dosya silinemedi: " + err.Error())
	}
	syscall.Close(fd)
	anchored := filepath.Join("/proc/self/fd", strconv.Itoa(parent), parts[len(parts)-1])
	if _, err := os.Lstat(anchored); err != nil {
		return ksErrorf("Dosya silinemedi: " + err.Error())
	}
	if err := os.Remove(anchored); err != nil {
		return ksErrorf("Dosya silinemedi: " + err.Error())
	}
	return ksUnit
}

func ksCallMethod(receiver any, method string, arguments ...any) any {
	if failure, ok := receiver.(*KsError); ok {
		return failure
	}
	switch item := receiver.(type) {
	case *ksNetRoot:
		if method != "allow" {
			return ksErrorf("KS2402: NetRoot önce allow ile daraltılmalıdır.")
		}
		if failure := ksMethodArity(method, arguments, 1); failure != nil {
			return failure
		}
		origin, failure := ksStringArgument(method, arguments, 0)
		if failure != nil {
			return failure
		}
		key, valid := ksParseOrigin(origin)
		return &ksNetCaps{origin: origin, key: key, valid: valid}
	case *ksDiskRoot:
		if method != "allow" && method != "allow_read_only" {
			return ksErrorf("KS2402: DiskRoot önce allow ile daraltılmalıdır.")
		}
		if failure := ksMethodArity(method, arguments, 1); failure != nil {
			return failure
		}
		prefix, failure := ksStringArgument(method, arguments, 0)
		if failure != nil {
			return failure
		}
		readOnly := method == "allow_read_only"
		capability := ksNewDiskCapability(prefix, readOnly)
		if readOnly {
			return &ksDiskReadCaps{capability: capability}
		}
		return &ksDiskCaps{capability: capability}
	case *ksEnvRoot:
		if method != "allow" {
			return ksErrorf("KS2402: EnvRoot önce allow ile daraltılmalıdır.")
		}
		if failure := ksMethodArity(method, arguments, 1); failure != nil {
			return failure
		}
		name, failure := ksStringArgument(method, arguments, 0)
		if failure != nil {
			return failure
		}
		return &ksEnvCaps{name: name}
	case *ksProcessRoot:
		if method != "allow" {
			return ksErrorf("KS2402: ProcessRoot önce allow ile daraltılmalıdır.")
		}
		if failure := ksMethodArity(method, arguments, 1); failure != nil {
			return failure
		}
		command, failure := ksStringArgument(method, arguments, 0)
		if failure != nil {
			return failure
		}
		return &ksProcessCaps{command: command}
	case *ksNetCaps:
		if method != "get" {
			return ksErrorf(method + " henüz desteklenmiyor")
		}
		if failure := ksMethodArity(method, arguments, 1); failure != nil {
			return failure
		}
		rawURL, failure := ksStringArgument(method, arguments, 0)
		if failure != nil {
			return failure
		}
		return ksNetGet(item, rawURL)
	case *ksDiskCaps:
		return ksDiskCall(item.capability, method, arguments)
	case *ksDiskReadCaps:
		return ksDiskCall(item.capability, method, arguments)
	case *ksEnvCaps:
		if method != "get" {
			return ksErrorf("KS2404: EnvCaps yetkisi '" + method + "' işlemine izin vermez.")
		}
		if failure := ksMethodArity(method, arguments, 0); failure != nil {
			return failure
		}
		value, ok := os.LookupEnv(item.name)
		if !ok {
			return ksErrorf("Ortam değişkeni bulunamadı: " + item.name)
		}
		return value
	case *ksProcessCaps:
		if method == "run" || method == "spawn" {
			return ksErrorf("process yetkisi bu sürümde kapalı")
		}
		return ksErrorf("KS2404: ProcessCaps yetkisi '" + method + "' işlemine izin vermez.")
	case *ksResponse:
		switch method {
		case "text":
			if failure := ksMethodArity(method, arguments, 0); failure != nil {
				return failure
			}
			return item.body
		case "status":
			if failure := ksMethodArity(method, arguments, 0); failure != nil {
				return failure
			}
			return item.status
		}
	}
	return ksErrorf("KS3101: Native runtime'da tanımsız metot: '" + method + "'.")
}

func ksCallDynamicMethod(receiver any, method string, arguments ...any) any {
	switch receiver.(type) {
	case *ksNetRoot, *ksDiskRoot, *ksEnvRoot, *ksProcessRoot,
		*ksNetCaps, *ksDiskCaps, *ksDiskReadCaps, *ksEnvCaps,
		*ksProcessCaps, *ksResponse:
		return ksCallMethod(receiver, method, arguments...)
	default:
		return ksCallValueMethod(receiver, method, arguments...)
	}
}

func ksDiskCall(capability *ksDiskCapability, method string, arguments []any) any {
	switch method {
	case "read", "read_file":
		if failure := ksMethodArity(method, arguments, 1); failure != nil {
			return failure
		}
		path, failure := ksStringArgument(method, arguments, 0)
		if failure != nil {
			return failure
		}
		return capability.read(path)
	case "list":
		if failure := ksMethodArity(method, arguments, 1); failure != nil {
			return failure
		}
		path, failure := ksStringArgument(method, arguments, 0)
		if failure != nil {
			return failure
		}
		return capability.list(path)
	case "write", "write_file":
		if failure := ksMethodArity(method, arguments, 2); failure != nil {
			return failure
		}
		path, failure := ksStringArgument(method, arguments, 0)
		if failure != nil {
			return failure
		}
		value, failure := ksStringArgument(method, arguments, 1)
		if failure != nil {
			return failure
		}
		return capability.write(path, value)
	case "delete":
		if failure := ksMethodArity(method, arguments, 1); failure != nil {
			return failure
		}
		path, failure := ksStringArgument(method, arguments, 0)
		if failure != nil {
			return failure
		}
		return capability.delete(path)
	}
	return ksErrorf("KS2404: Disk capability '" + method + "' işlemine izin vermez.")
}
'''


class GoCodegen:
    def __init__(self, program: Program) -> None:
        self.program = program
        self.functions = {
            declaration.name: declaration for declaration in program.declarations
        }
        self.enum_variants: dict[str, tuple[str, bool]] = {
            "Some": ("Option", True),
            "None": ("Option", False),
            "Ok": ("Result", True),
            "Err": ("Result", True),
        }
        for enum in program.enums:
            for variant in enum.variants:
                self.enum_variants[variant.name] = (
                    enum.name,
                    variant.payload_type is not None,
                )
        self._temp_index = 0

    # ------------------------------------------------------------------
    # Genel akış
    # ------------------------------------------------------------------

    def generate(self) -> str:
        self._reject_unsupported()
        self._validate_capability_backend()

        lines: list[str] = [
            "// Bu dosya Koschei derleyicisi tarafından üretilmiştir.",
            "// Elle düzenlemeyin: kaynak .ks dosyasını değiştirip yeniden derleyin.",
            "",
            "package main",
            "",
            "import (",
            '\t"errors"',
            '\t"fmt"',
            '\t"io"',
            '\t"net/http"',
            '\t"net/url"',
            '\t"os"',
            '\t"path/filepath"',
            '\t"runtime"',
            '\t"sort"',
            '\t"strconv"',
            '\t"strings"',
            '\t"syscall"',
            '\t"time"',
            ")",
            "",
        ]
        lines.extend(RUNTIME_PRELUDE.splitlines())
        lines.append("")
        lines.extend(CAPABILITY_RUNTIME.splitlines())
        lines.append("")

        for declaration in self.program.declarations:
            lines.extend(self._function(declaration))
            lines.append("")

        lines.extend(self._entry_point())
        return "\n".join(lines) + "\n"

    def _reject_unsupported(self) -> None:
        if self.program.imports:
            raise CodegenError(
                "KS4002",
                "Modül içe aktarımı native derlemede henüz desteklenmiyor; şimdilik "
                "'koschei.py run' kullanın.",
                self.program.imports[0].location,
            )
        if self.program.structs:
            raise CodegenError(
                "KS4002",
                "Struct tanımları native derlemede henüz desteklenmiyor; şimdilik "
                "'koschei.py run' kullanın.",
                self.program.structs[0].location,
            )
        for declaration in self.program.declarations:
            for statement in declaration.body.statements:
                for expression in _walk_statement(statement):
                    if isinstance(expression, StructLiteral):
                        raise CodegenError(
                            "KS4002",
                            "Struct değerleri native derlemede henüz desteklenmiyor; "
                            "şimdilik 'koschei.py run' kullanın.",
                            expression.location,
                        )

    def _validate_capability_backend(self) -> None:
        """Native capability ABI güvenlik sınırlarını hedefe göre doğrular."""
        uses_disk = False
        for declaration in self.program.declarations:
            for parameter in declaration.parameters:
                if any(
                    name in {"DiskRoot", "DiskCaps", "DiskReadCaps"}
                    for name in parameter.type_ref.names
                ):
                    uses_disk = True
            for statement in declaration.body.statements:
                for expression in _walk_statement(statement):
                    if (
                        isinstance(expression, MemberExpression)
                        and expression.member
                        in {
                            "allow_read_only",
                            "read",
                            "read_file",
                            "write",
                            "write_file",
                            "list",
                            "delete",
                        }
                    ):
                        uses_disk = True
        if uses_disk and not sys.platform.startswith("linux"):
            raise CodegenError(
                "KS4001",
                "Native disk capability ABI bu alpha sürümünde yalnızca Linux "
                "openat/O_NOFOLLOW hedefinde desteklenir; daha zayıf yol "
                "doğrulamasına geri düşülmez.",
                SourceLocation(1, 1),
            )

    # ------------------------------------------------------------------
    # Fonksiyonlar
    # ------------------------------------------------------------------

    def _function(self, declaration: FunctionDeclaration) -> list[str]:
        parameters = ", ".join(
            f"{_var(parameter.name)} any" for parameter in declaration.parameters
        )
        lines = [f"func {_fn(declaration.name)}({parameters}) any {{"]
        lines.append(
            f'\tksEnter("{declaration.name}")'
        )
        lines.append("\tdefer ksLeave()")
        for parameter in declaration.parameters:
            lines.append(f"\t_ = {_var(parameter.name)}")
        lines.extend(self._block(declaration.body, 1))
        lines.append("\treturn ksUnit")
        lines.append("}")
        return lines

    def _entry_point(self) -> list[str]:
        main = self.functions.get("main")
        if main is None:
            raise CodegenError(
                "KS4002", "'main' fonksiyonu bulunamadı.", SourceLocation(1, 1)
            )
        if len(main.parameters) > 1:
            raise CodegenError(
                "KS4002",
                "'main' sıfır parametre veya tek SystemCaps parametresi alabilir.",
                main.location,
            )
        invocation = f"{_fn('main')}()"
        if main.parameters:
            parameter = main.parameters[0]
            if parameter.type_ref.names != ("SystemCaps",):
                raise CodegenError(
                    "KS4001",
                    "Native main parametresi yalnızca SystemCaps olabilir.",
                    parameter.location,
                )
            invocation = f"{_fn('main')}(ksNewSystemCaps())"
        return [
            "func main() {",
            f"\tresult := {invocation}",
            "\tif failure, ok := result.(*KsError); ok {",
            '\t\tfmt.Fprintln(os.Stderr, "KOSCHEI RUNTIME ERROR: "+failure.Message)',
            "\t\tos.Exit(1)",
            "\t}",
            "\tos.Exit(0)",
            "}",
        ]

    # ------------------------------------------------------------------
    # Statement üretimi
    # ------------------------------------------------------------------

    def _block(self, block: Block, depth: int) -> list[str]:
        lines: list[str] = []
        for statement in block.statements:
            lines.extend(self._statement(statement, depth))
        return lines

    def _statement(self, statement: Statement, depth: int) -> list[str]:
        pad = "\t" * depth

        if isinstance(statement, LetStatement):
            value, prelude = self._expression(statement.value, depth)
            lines = [pad + line for line in prelude]
            lines.append(f"{pad}var {_var(statement.name)} any = {value}")
            lines.append(f"{pad}_ = {_var(statement.name)}")
            return lines

        if isinstance(statement, ReturnStatement):
            if statement.value is None:
                return [f"{pad}return ksUnit"]
            value, prelude = self._expression(statement.value, depth)
            lines = [pad + line for line in prelude]
            lines.append(f"{pad}return {value}")
            return lines

        if isinstance(statement, ExpressionStatement):
            value, prelude = self._expression(statement.expression, depth)
            lines = [pad + line for line in prelude]
            lines.append(f"{pad}_ = {value}")
            return lines

        if isinstance(statement, ForStatement):
            iterable, prelude = self._expression(statement.iterable, depth)
            source = self._temp()
            list_value = self._temp()
            ok = self._temp()
            lines = [pad + line for line in prelude]
            lines.append(f"{pad}{source} := {iterable}")
            lines.append(f"{pad}{list_value}, {ok} := {source}.([]any)")
            lines.append(f"{pad}if !{ok} {{")
            lines.append(f'{pad}\treturn ksErrorf("KS3101: for yalnızca List üzerinde çalışır")')
            lines.append(f"{pad}}}")
            lines.append(f"{pad}for _, {_var(statement.variable)} := range {list_value} {{")
            lines.append(f"{pad}\t_ = {_var(statement.variable)}")
            lines.extend(self._block(statement.body, depth + 1))
            lines.append(f"{pad}}}")
            return lines

        if isinstance(statement, IfStatement):
            return self._if_statement(statement, depth)

        if isinstance(statement, WhileStatement):
            return self._while_statement(statement, depth)

        raise CodegenError(
            "KS4002",
            f"Desteklenmeyen yapı: {type(statement).__name__}.",
            getattr(statement, "location", SourceLocation(1, 1)),
        )

    def _if_statement(self, statement: IfStatement, depth: int) -> list[str]:
        pad = "\t" * depth
        condition, prelude = self._expression(statement.condition, depth)
        lines = [pad + line for line in prelude]
        lines.append(f"{pad}if ksTruthy({condition}) {{")
        lines.extend(self._block(statement.then_block, depth + 1))

        branch = statement.else_branch
        if branch is None:
            lines.append(f"{pad}}}")
            return lines

        lines.append(f"{pad}}} else {{")
        if isinstance(branch, Block):
            lines.extend(self._block(branch, depth + 1))
        else:
            lines.extend(self._statement(branch, depth + 1))
        lines.append(f"{pad}}}")
        return lines

    def _while_statement(self, statement: WhileStatement, depth: int) -> list[str]:
        pad = "\t" * depth
        inner = "\t" * (depth + 1)
        condition, prelude = self._expression(statement.condition, depth + 1)

        lines = [f"{pad}for {{"]
        lines.extend(inner + line for line in prelude)
        lines.append(f"{inner}if !ksTruthy({condition}) {{")
        lines.append(f"{inner}\tbreak")
        lines.append(f"{inner}}}")
        lines.extend(self._block(statement.body, depth + 1))
        lines.append(f"{pad}}}")
        return lines

    # ------------------------------------------------------------------
    # İfade üretimi: (go_ifadesi, önce_çalışacak_satırlar)
    # ------------------------------------------------------------------

    def _expression(self, expression: Expression, depth: int) -> tuple[str, list[str]]:
        if isinstance(expression, Literal):
            return _literal(expression.value), []

        if isinstance(expression, Identifier):
            if expression.name in self.functions:
                return _fn(expression.name), []
            return _var(expression.name), []

        if isinstance(expression, InterpolatedString):
            return self._interpolation(expression, depth)

        if isinstance(expression, UnaryExpression):
            if (
                expression.operator == "-"
                and isinstance(expression.operand, Literal)
                and isinstance(expression.operand.value, int)
                and not isinstance(expression.operand.value, bool)
                and expression.operand.value == INT_MIN_MAGNITUDE
            ):
                return f"int64({INT_MIN})", []
            operand, prelude = self._expression(expression.operand, depth)
            helper = "ksNot" if expression.operator == "!" else "ksNegate"
            return f"{helper}({operand})", prelude

        if isinstance(expression, BinaryExpression):
            return self._binary(expression, depth)

        if isinstance(expression, AssignmentExpression):
            return self._assignment(expression, depth)

        if isinstance(expression, CallExpression):
            return self._call(expression, depth)

        if isinstance(expression, MatchExpression):
            return self._match(expression, depth)

        if isinstance(expression, ListLiteral):
            values: list[str] = []
            prelude: list[str] = []
            for item in expression.items:
                value, item_prelude = self._expression(item, depth)
                prelude.extend(item_prelude)
                values.append(value)
            return f"ksNewList([]any{{{', '.join(values)}}})", prelude

        if isinstance(expression, MapLiteral):
            keys: list[str] = []
            values: list[str] = []
            prelude: list[str] = []
            for key_expression, value_expression in expression.entries:
                key, key_prelude = self._expression(key_expression, depth)
                value, value_prelude = self._expression(value_expression, depth)
                prelude.extend(key_prelude)
                prelude.extend(value_prelude)
                keys.append(key)
                values.append(value)
            return (
                f"ksNewMap([]any{{{', '.join(keys)}}}, []any{{{', '.join(values)}}})",
                prelude,
            )

        if isinstance(expression, StructLiteral):
            raise CodegenError(
                "KS4002",
                "Struct değerleri native derlemede henüz desteklenmiyor; "
                "şimdilik 'koschei.py run' kullanın.",
                expression.location,
            )

        if isinstance(expression, MemberExpression):
            receiver, prelude = self._expression(expression.object, depth)
            if expression.member in {"net", "disk", "env", "process"}:
                return f"ksMember({receiver}, {_go_string(expression.member)})", prelude
            raise CodegenError(
                "KS4002",
                f"Üye erişimi ('{expression.member}') yalnızca çağrı olarak desteklenir.",
                expression.location,
            )

        if isinstance(expression, OrReturnExpression):
            return self._or_return(expression, depth)

        if isinstance(expression, OrElseExpression):
            return self._or_else(expression, depth)

        if isinstance(expression, OrBlockExpression):
            return self._or_block(expression, depth)

        raise CodegenError(
            "KS4002",
            f"Desteklenmeyen ifade: {type(expression).__name__}.",
            getattr(expression, "location", SourceLocation(1, 1)),
        )

    def _interpolation(
        self, expression: InterpolatedString, depth: int
    ) -> tuple[str, list[str]]:
        prelude: list[str] = []
        parts: list[str] = []
        for part in expression.parts:
            value, part_prelude = self._expression(part, depth)
            prelude.extend(part_prelude)
            parts.append(f"ksToString({value})")
        if not parts:
            return '""', prelude
        return " + ".join(parts), prelude

    def _binary(self, expression: BinaryExpression, depth: int) -> tuple[str, list[str]]:
        operator = expression.operator

        if operator in {"&&", "||"}:
            left, prelude = self._expression(expression.left, depth)
            temp = self._temp()
            lines = list(prelude)
            lines.append(f"{temp} := {left}")
            if operator == "&&":
                lines.append(f"if ksTruthy({temp}) {{")
            else:
                lines.append(f"if !ksTruthy({temp}) {{")
            right, right_prelude = self._expression(expression.right, depth + 1)
            lines.extend("\t" + line for line in right_prelude)
            lines.append(f"\t{temp} = ksTruthy({right})")
            lines.append("} else {")
            lines.append(f"\t{temp} = {'false' if operator == '&&' else 'true'}")
            lines.append("}")
            return temp, lines

        helper = BINARY_HELPERS.get(operator)
        if helper is None:
            raise CodegenError(
                "KS4002",
                f"Desteklenmeyen işleç: '{operator}'.",
                expression.location,
            )
        left, left_prelude = self._expression(expression.left, depth)
        right, right_prelude = self._expression(expression.right, depth)
        return f"{helper}({left}, {right})", left_prelude + right_prelude

    def _assignment(
        self, expression: AssignmentExpression, depth: int
    ) -> tuple[str, list[str]]:
        if not isinstance(expression.target, Identifier):
            raise CodegenError(
                "KS4002",
                "Yalnızca değişkenlere atama yapılabilir.",
                expression.location,
            )
        value, prelude = self._expression(expression.value, depth)
        lines = list(prelude)
        lines.append(f"{_var(expression.target.name)} = {value}")
        return _var(expression.target.name), lines

    def _call(self, expression: CallExpression, depth: int) -> tuple[str, list[str]]:
        prelude: list[str] = []
        arguments: list[str] = []
        for argument in expression.arguments:
            value, argument_prelude = self._expression(argument, depth)
            prelude.extend(argument_prelude)
            arguments.append(value)

        callee = expression.callee

        if isinstance(callee, Identifier):
            name = callee.name
            constructor = self.enum_variants.get(name)
            if constructor is not None:
                enum_name, has_payload = constructor
                expected = 1 if has_payload else 0
                self._check_arity(name, arguments, expected, expression.location)
                payload = arguments[0] if has_payload else "ksUnit"
                return (
                    f"ksEnum({_go_string(enum_name)}, {_go_string(name)}, {payload}, "
                    f"{'true' if has_payload else 'false'})",
                    prelude,
                )
            if name in {"println", "print"}:
                self._check_arity(name, arguments, 1, expression.location)
                helper = "ksPrintln" if name == "println" else "ksPrint"
                return f"{helper}({arguments[0]})", prelude
            if name == "Error":
                self._check_arity(name, arguments, 1, expression.location)
                return f"ksErrorf(ksToString({arguments[0]}))", prelude

            function = self.functions.get(name)
            if function is None:
                raise CodegenError(
                    "KS4002",
                    f"Tanımsız fonksiyon: '{name}'.",
                    expression.location,
                )
            self._check_arity(
                name, arguments, len(function.parameters), expression.location
            )
            return f"{_fn(name)}({', '.join(arguments)})", prelude

        if isinstance(callee, MemberExpression):
            receiver, receiver_prelude = self._expression(callee.object, depth)
            prelude = receiver_prelude + prelude
            method = callee.member
            if method not in NATIVE_CAPABILITY_METHODS | VALUE_METHODS:
                raise CodegenError(
                    "KS4002",
                    f"Native derlemede desteklenmeyen metot: '{method}'.",
                    callee.location,
                )
            rendered = ", ".join(arguments)
            suffix = f", {rendered}" if rendered else ""
            return (
                f"ksCallDynamicMethod({receiver}, {_go_string(method)}{suffix})",
                prelude,
            )

        raise CodegenError(
            "KS4002", "Desteklenmeyen çağrı biçimi.", expression.location
        )

    def _match(
        self, expression: MatchExpression, depth: int
    ) -> tuple[str, list[str]]:
        value, prelude = self._expression(expression.value, depth)
        source = self._temp()
        enum_value = self._temp()
        result = self._temp()
        ok = self._temp()
        lines = list(prelude)
        lines.append(f"{source} := {value}")
        lines.append(f"{enum_value}, {ok} := {source}.(*KsEnum)")
        lines.append(f"var {result} any")
        lines.append(f"if !{ok} {{")
        lines.append(
            f'\t{result} = ksErrorf("KS3101: match çalışma anında enum, Option veya Result bekler")'
        )
        lines.append("} else {")
        lines.append(f"\tswitch {enum_value}.Variant {{")
        for arm in expression.arms:
            lines.append(f"\tcase {_go_string(arm.variant)}:")
            lines.append("\t\t{")
            if arm.binding is not None:
                lines.append(
                    f"\t\t\tvar {_var(arm.binding)} any = {enum_value}.Payload"
                )
                lines.append(f"\t\t\t_ = {_var(arm.binding)}")
            body, body_prelude = self._expression(arm.body, depth + 3)
            lines.extend("\t\t\t" + line for line in body_prelude)
            lines.append(f"\t\t\t{result} = {body}")
            lines.append("\t\t}")
        lines.append("\tdefault:")
        lines.append(
            f'\t\t{result} = ksErrorf("KS3101: match içinde varyant kolu yok: " + {enum_value}.Variant)'
        )
        lines.append("\t}")
        lines.append("}")
        return result, lines

    def _or_return(
        self, expression: OrReturnExpression, depth: int
    ) -> tuple[str, list[str]]:
        value, prelude = self._expression(expression.value, depth)
        temp = self._temp()
        lines = list(prelude)
        lines.append(f"{temp} := {value}")
        success = self._temp()
        payload = self._temp()
        lines.append(f"{success}, {payload} := ksUnwrapFallible({temp})")
        lines.append(f"if !{success} {{")
        if expression.error is None:
            lines.append(f"\treturn {temp}")
        else:
            error, error_prelude = self._expression(expression.error, depth + 1)
            lines.extend("\t" + line for line in error_prelude)
            lines.append(f"\treturn {error}")
        lines.append("}")
        lines.append(f"{temp} = {payload}")
        return temp, lines

    def _or_else(
        self, expression: OrElseExpression, depth: int
    ) -> tuple[str, list[str]]:
        value, prelude = self._expression(expression.value, depth)
        temp = self._temp()
        lines = list(prelude)
        lines.append(f"{temp} := {value}")
        success = self._temp()
        payload = self._temp()
        lines.append(f"{success}, {payload} := ksUnwrapFallible({temp})")
        lines.append(f"if !{success} {{")
        fallback, fallback_prelude = self._expression(expression.fallback, depth + 1)
        lines.extend("\t" + line for line in fallback_prelude)
        lines.append(f"\t{temp} = {fallback}")
        lines.append("} else {")
        lines.append(f"\t{temp} = {payload}")
        lines.append("}")
        return temp, lines

    def _or_block(
        self, expression: OrBlockExpression, depth: int
    ) -> tuple[str, list[str]]:
        value, prelude = self._expression(expression.value, depth)
        temp = self._temp()
        lines = list(prelude)
        lines.append(f"{temp} := {value}")
        success = self._temp()
        payload = self._temp()
        lines.append(f"{success}, {payload} := ksUnwrapFallible({temp})")
        lines.append(f"if !{success} {{")

        statements = expression.handler.statements
        body_statements = statements
        tail_value: str | None = None
        tail_prelude: list[str] = []

        if statements and isinstance(statements[-1], ExpressionStatement):
            body_statements = statements[:-1]
            tail_value, tail_prelude = self._expression(
                statements[-1].expression, depth + 1
            )

        for statement in body_statements:
            lines.extend(self._statement(statement, depth + 1))

        if tail_value is not None:
            lines.extend("\t" + line for line in tail_prelude)
            lines.append(f"\t{temp} = {tail_value}")
        elif not (statements and isinstance(statements[-1], ReturnStatement)):
            lines.append(f"\t{temp} = ksUnit")

        lines.append("} else {")
        lines.append(f"\t{temp} = {payload}")
        lines.append("}")
        return temp, lines

    # ------------------------------------------------------------------
    # Yardımcılar
    # ------------------------------------------------------------------

    def _temp(self) -> str:
        self._temp_index += 1
        return f"kstmp{self._temp_index}"

    @staticmethod
    def _check_arity(
        name: str, arguments: list[str], expected: int, location: SourceLocation
    ) -> None:
        if len(arguments) != expected:
            raise CodegenError(
                "KS4003",
                f"'{name}' için {expected} argüman bekleniyor, "
                f"{len(arguments)} verildi.",
                location,
            )


def _walk_statement(statement: Statement):
    """Statement içindeki tüm ifadeleri dolaşır (yetki taraması için)."""
    if isinstance(statement, LetStatement):
        yield from _walk_expression(statement.value)
    elif isinstance(statement, ReturnStatement):
        if statement.value is not None:
            yield from _walk_expression(statement.value)
    elif isinstance(statement, ExpressionStatement):
        yield from _walk_expression(statement.expression)
    elif isinstance(statement, IfStatement):
        yield from _walk_expression(statement.condition)
        for inner in statement.then_block.statements:
            yield from _walk_statement(inner)
        branch = statement.else_branch
        if isinstance(branch, Block):
            for inner in branch.statements:
                yield from _walk_statement(inner)
        elif isinstance(branch, IfStatement):
            yield from _walk_statement(branch)
    elif isinstance(statement, WhileStatement):
        yield from _walk_expression(statement.condition)
        for inner in statement.body.statements:
            yield from _walk_statement(inner)
    elif isinstance(statement, ForStatement):
        yield from _walk_expression(statement.iterable)
        for inner in statement.body.statements:
            yield from _walk_statement(inner)


def _walk_expression(expression: Expression):
    yield expression
    if isinstance(expression, MemberExpression):
        yield from _walk_expression(expression.object)
    elif isinstance(expression, CallExpression):
        yield from _walk_expression(expression.callee)
        for argument in expression.arguments:
            yield from _walk_expression(argument)
    elif isinstance(expression, BinaryExpression):
        yield from _walk_expression(expression.left)
        yield from _walk_expression(expression.right)
    elif isinstance(expression, UnaryExpression):
        yield from _walk_expression(expression.operand)
    elif isinstance(expression, AssignmentExpression):
        yield from _walk_expression(expression.target)
        yield from _walk_expression(expression.value)
    elif isinstance(expression, InterpolatedString):
        for part in expression.parts:
            yield from _walk_expression(part)
    elif isinstance(expression, ListLiteral):
        for item in expression.items:
            yield from _walk_expression(item)
    elif isinstance(expression, MapLiteral):
        for key, value in expression.entries:
            yield from _walk_expression(key)
            yield from _walk_expression(value)
    elif isinstance(expression, StructLiteral):
        for _, value in expression.fields:
            yield from _walk_expression(value)
    elif isinstance(expression, OrReturnExpression):
        yield from _walk_expression(expression.value)
        if expression.error is not None:
            yield from _walk_expression(expression.error)
    elif isinstance(expression, OrElseExpression):
        yield from _walk_expression(expression.value)
        yield from _walk_expression(expression.fallback)
    elif isinstance(expression, OrBlockExpression):
        yield from _walk_expression(expression.value)
        for statement in expression.handler.statements:
            yield from _walk_statement(statement)
    elif isinstance(expression, MatchExpression):
        yield from _walk_expression(expression.value)
        for arm in expression.arms:
            yield from _walk_expression(arm.body)


def _fn(name: str) -> str:
    return f"ksfn_{name}"


def _var(name: str) -> str:
    return f"ksv_{name}"


def _literal(value: object) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, int):
        if not INT_MIN <= value <= INT_MAX:
            raise CodegenError(
                "KS4002",
                f"Int literal native 64-bit aralığın dışında: {value}",
                SourceLocation(1, 1),
            )
        return f"int64({value})"
    if isinstance(value, float):
        return f"float64({value!r})"
    if isinstance(value, str):
        return _go_string(value)
    raise CodegenError(
        "KS4002", f"Desteklenmeyen sabit: {value!r}", SourceLocation(1, 1)
    )


def _go_string(value: str) -> str:
    escaped = (
        value.replace("\\", "\\\\")
        .replace('"', '\\"')
        .replace("\n", "\\n")
        .replace("\r", "\\r")
        .replace("\t", "\\t")
    )
    return f'"{escaped}"'


def generate_go(program: Program) -> str:
    """Koschei programını Go kaynak koduna çevirir."""
    return GoCodegen(program).generate()
