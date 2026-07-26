// Bu dosya Koschei derleyicisi tarafından üretilmiştir.
// Elle düzenlemeyin: kaynak .ks dosyasını değiştirip yeniden derleyin.

package main

import (
	"errors"
	"fmt"
	"io"
	"net/http"
	"net/url"
	"os"
	"path/filepath"
	"runtime"
	"sort"
	"strconv"
	"strings"
	"syscall"
	"time"
)

// Koschei runtime — üretilmiş kod, elle düzenlemeyin.

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

type KsStruct struct {
	TypeName string
	Order    []string
	Fields   map[string]any
}

func ksNewStruct(typeName string, names []string, values []any) any {
	if len(names) != len(values) {
		return ksErrorf("KS3101: Struct alan/değer sayısı uyuşmuyor")
	}
	result := &KsStruct{TypeName: typeName, Order: append([]string(nil), names...), Fields: make(map[string]any, len(names))}
	for index, name := range names {
		if _, exists := result.Fields[name]; exists {
			return ksErrorf("KS3101: Yinelenen struct alanı: " + name)
		}
		if ksContainsCapability(values[index]) {
			return ksErrorf("KS3401: Capability taşıyan değerler struct içine konamaz")
		}
		result.Fields[name] = values[index]
	}
	return result
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
	case *KsStruct:
		parts := make([]string, 0, len(item.Order))
		for _, name := range item.Order {
			parts = append(parts, name+": "+ksRepr(item.Fields[name]))
		}
		return item.TypeName + " { " + strings.Join(parts, ", ") + " }"
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
	if a, ok := left.(*KsStruct); ok {
		b, ok := right.(*KsStruct)
		if !ok || a.TypeName != b.TypeName || len(a.Fields) != len(b.Fields) {
			return false
		}
		for name, value := range a.Fields {
			other, exists := b.Fields[name]
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

// Capability runtime ABI v1 alpha — Linux için fail-closed kapsam koruması.

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
	case *KsStruct:
		for _, value := range item.Fields {
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
	case *KsStruct:
		if field, exists := item.Fields[name]; exists {
			return field
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

func ksfn___module_0_risk_label(ksv_percent any) any {
	ksEnter("__module_0_risk_label")
	defer ksLeave()
	_ = ksv_percent
	if ksTruthy(ksGreaterEq(ksv_percent, int64(50))) {
		return "KRITIK"
	} else {
		if ksTruthy(ksGreaterEq(ksv_percent, int64(20))) {
			return "YUKSEK"
		}
	}
	return "NORMAL"
	return ksUnit
}

func ksfn___module_0_risk_total(ksv_holders any) any {
	ksEnter("__module_0_risk_total")
	defer ksLeave()
	_ = ksv_holders
	var ksv_sum any = int64(0)
	_ = ksv_sum
	kstmp1 := ksv_holders
	kstmp2, kstmp3 := kstmp1.([]any)
	if !kstmp3 {
		return ksErrorf("KS3101: for yalnızca List üzerinde çalışır")
	}
	for _, ksv_holder := range kstmp2 {
		_ = ksv_holder
		ksv_sum = ksAdd(ksv_sum, ksMember(ksv_holder, "percent"))
		_ = ksv_sum
	}
	return ksv_sum
	return ksUnit
}

func ksfn_main() any {
	ksEnter("main")
	defer ksLeave()
	var ksv_holders any = ksNewList([]any{ksNewStruct("Holder", []string{"address", "percent"}, []any{"7xKq...aB1", int64(62)}), ksNewStruct("Holder", []string{"address", "percent"}, []any{"9mPz...cD2", int64(24)}), ksNewStruct("Holder", []string{"address", "percent"}, []any{"4nRw...eF3", int64(5)})})
	_ = ksv_holders
	kstmp4 := ksv_holders
	kstmp5, kstmp6 := kstmp4.([]any)
	if !kstmp6 {
		return ksErrorf("KS3101: for yalnızca List üzerinde çalışır")
	}
	for _, ksv_holder := range kstmp5 {
		_ = ksv_holder
		var ksv_etiket any = ksfn___module_0_risk_label(ksMember(ksv_holder, "percent"))
		_ = ksv_etiket
		_ = ksPrintln(ksToString(ksMember(ksv_holder, "address")) + ksToString(" -> %") + ksToString(ksMember(ksv_holder, "percent")) + ksToString(" [") + ksToString(ksv_etiket) + ksToString("]"))
	}
	var ksv_toplam any = ksfn___module_0_risk_total(ksv_holders)
	_ = ksv_toplam
	_ = ksPrintln(ksToString("Toplam: %") + ksToString(ksv_toplam))
	return ksUnit
}

func main() {
	result := ksfn_main()
	if failure, ok := result.(*KsError); ok {
		fmt.Fprintln(os.Stderr, "KOSCHEI RUNTIME ERROR: "+failure.Message)
		os.Exit(1)
	}
	os.Exit(0)
}
