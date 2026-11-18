"""Data (parse_json/encode_json and json_* access) for MIR-Go native binaries.

The decoder and encoder are the audited data-json/v1 Go core
(native/datajson/json.go, the one the legacy generator embedded); it matches
the Python core (data_json_v1) value for value and message for message. The
access builtins follow data_access_v1.access. Emitted only when a program
uses Data.
"""

from __future__ import annotations

import re

from .data_native_source_v1 import _source_path

JSON_BUILTINS = {
    "parse_json": "_ksJsonParse",
    "encode_json": "_ksJsonEncode",
    "json_kind": "_ksJsonKind",
    "json_has": "_ksJsonHas",
    "json_get": "_ksJsonGet",
    "json_at": "_ksJsonAt",
    "json_text": "_ksJsonText",
    "json_bool": "_ksJsonBool",
    "json_int": "_ksJsonInt",
    "json_float": "_ksJsonFloat",
    "json_length": "_ksJsonLength",
    "json_keys": "_ksJsonKeys",
    "json_items": "_ksJsonItems",
}
JSON_ARITY = {"json_has": 2, "json_get": 2, "json_at": 2}
JSON_IMPORTS = ("fmt", "math", "sort", "strconv", "strings", "unicode/utf16", "unicode/utf8")

_WRAPPERS = r'''
func _ksJsonParse(raw any) any {
	text, ok := raw.(string)
	if !ok {
		return _ksError{message: "KS3608: parse_json() String bekler"}
	}
	value, err := Decode(text, DefaultLimits)
	if err != nil {
		return _ksError{message: err.Error()}
	}
	return _ksData{value: value}
}

func _ksJsonEncode(raw any) any {
	data, ok := raw.(_ksData)
	if !ok {
		return _ksError{message: "KS3608: encode_json() Data bekler"}
	}
	text, err := Encode(data.value, DefaultLimits)
	if err != nil {
		return _ksError{message: err.Error()}
	}
	return text
}

func _ksJsonValue(name string, raw any) (any, any) {
	data, ok := raw.(_ksData)
	if !ok {
		return nil, _ksError{message: "KS3709: " + name + "() expects Data"}
	}
	return data.value, nil
}

func _ksJsonKindOf(value any) string {
	switch value.(type) {
	case nil:
		return "null"
	case bool:
		return "bool"
	case string:
		return "string"
	case Number:
		return "number"
	case []any:
		return "array"
	case Object, map[string]any:
		return "object"
	}
	return "unknown"
}

func _ksJsonExpect(name string, value any, wanted string) any {
	if found := _ksJsonKindOf(value); found != wanted {
		return _ksError{message: "KS3709: " + name + "() expects a JSON " + wanted + ", found " + found}
	}
	return nil
}

func _ksJsonKind(raw any) any {
	value, failure := _ksJsonValue("json_kind", raw)
	if failure != nil {
		return failure
	}
	return _ksJsonKindOf(value)
}

func _ksJsonHas(raw any, key any) any {
	value, failure := _ksJsonValue("json_has", raw)
	if failure != nil {
		return failure
	}
	object, isObject := value.(Object)
	text, isText := key.(string)
	if !isObject || !isText {
		return false
	}
	_, found := object.Values[text]
	return found
}

func _ksJsonGet(raw any, key any) any {
	value, failure := _ksJsonValue("json_get", raw)
	if failure != nil {
		return failure
	}
	text, ok := key.(string)
	if !ok {
		return _ksError{message: "KS3709: json_get() expects a String key"}
	}
	if failure := _ksJsonExpect("json_get", value, "object"); failure != nil {
		return failure
	}
	member, found := value.(Object).Values[text]
	if !found {
		return _ksError{message: "KS3710: json_get(): no member named \"" + text + "\""}
	}
	return _ksData{value: member}
}

func _ksJsonAt(raw any, index any) any {
	value, failure := _ksJsonValue("json_at", raw)
	if failure != nil {
		return failure
	}
	position, ok := index.(int64)
	if !ok {
		return _ksError{message: "KS3709: json_at() expects an Int index"}
	}
	if failure := _ksJsonExpect("json_at", value, "array"); failure != nil {
		return failure
	}
	items := value.([]any)
	if len(items) == 0 {
		return _ksError{message: "KS3710: json_at(): index " + strconv.FormatInt(position, 10) + " in an empty array"}
	}
	if position < 0 || position >= int64(len(items)) {
		return _ksError{message: "KS3710: json_at(): index " + strconv.FormatInt(position, 10) +
			" is outside 0.." + strconv.Itoa(len(items)-1)}
	}
	return _ksData{value: items[position]}
}

func _ksJsonText(raw any) any {
	value, failure := _ksJsonValue("json_text", raw)
	if failure != nil {
		return failure
	}
	if failure := _ksJsonExpect("json_text", value, "string"); failure != nil {
		return failure
	}
	return value
}

func _ksJsonBool(raw any) any {
	value, failure := _ksJsonValue("json_bool", raw)
	if failure != nil {
		return failure
	}
	if failure := _ksJsonExpect("json_bool", value, "bool"); failure != nil {
		return failure
	}
	return value
}

func _ksJsonInt(raw any) any {
	value, failure := _ksJsonValue("json_int", raw)
	if failure != nil {
		return failure
	}
	if failure := _ksJsonExpect("json_int", value, "number"); failure != nil {
		return failure
	}
	text := string(value.(Number))
	if strings.Contains(text, ".") || strings.Contains(text, "e-") {
		return _ksError{message: "KS3709: json_int(): " + text + " is not an integer"}
	}
	number, err := strconv.ParseInt(text, 10, 64)
	if err != nil {
		return _ksError{message: "KS3709: json_int(): " + text + " is outside the Int range"}
	}
	return number
}

func _ksJsonFloat(raw any) any {
	value, failure := _ksJsonValue("json_float", raw)
	if failure != nil {
		return failure
	}
	if failure := _ksJsonExpect("json_float", value, "number"); failure != nil {
		return failure
	}
	text := string(value.(Number))
	number, err := strconv.ParseFloat(text, 64)
	if err != nil || math.IsInf(number, 0) {
		return _ksError{message: "KS3709: json_float(): " + text + " is outside the Float range"}
	}
	return number
}

func _ksJsonLength(raw any) any {
	value, failure := _ksJsonValue("json_length", raw)
	if failure != nil {
		return failure
	}
	switch typed := value.(type) {
	case []any:
		return int64(len(typed))
	case Object:
		return int64(len(typed.Keys))
	}
	return _ksError{message: "KS3709: json_length() expects a JSON array or object, found " + _ksJsonKindOf(value)}
}

func _ksJsonKeys(raw any) any {
	value, failure := _ksJsonValue("json_keys", raw)
	if failure != nil {
		return failure
	}
	if failure := _ksJsonExpect("json_keys", value, "object"); failure != nil {
		return failure
	}
	keys := value.(Object).Keys
	out := make([]any, len(keys))
	for index, key := range keys {
		out[index] = key
	}
	return out
}

func _ksJsonItems(raw any) any {
	value, failure := _ksJsonValue("json_items", raw)
	if failure != nil {
		return failure
	}
	if failure := _ksJsonExpect("json_items", value, "array"); failure != nil {
		return failure
	}
	items := value.([]any)
	out := make([]any, len(items))
	for index, item := range items {
		out[index] = _ksData{value: item}
	}
	return out
}
'''


def json_runtime() -> str:
    """The audited core without its package clause and imports, plus the builtins."""

    source = _source_path().read_text(encoding="utf-8")
    body = re.sub(
        r"\A// Package datajson.*?\npackage datajson\n\nimport \(\n.*?\n\)\n\n",
        "",
        source,
        count=1,
        flags=re.DOTALL,
    )
    if body == source:
        raise RuntimeError("native data-json/v1 source shape changed; embedding refused")
    return body + "\n" + _WRAPPERS
