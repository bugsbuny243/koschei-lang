"""JSON ``Data`` in native binaries (``data_access_v1``).

Programs that call ``parse_json``, ``encode_json`` or ``json_quote`` carry the
audited ``native/datajson`` core and this fragment: the same codec, the same
public ``KS370x`` codes, the same ``KS3709`` reads and the same quoting as
every ``ks run`` executor. Other programs link neither.
"""

from __future__ import annotations

from pathlib import Path
import re

from . import data_access_v1 as _access
from .value_budget_v1 import MAX_STRING_BYTES, STRING_MESSAGE

BUILTINS = {
    "parse_json": "_ksParseJSON",
    "encode_json": "_ksEncodeJSON",
    _access.QUOTE: "_ksJSONQuote",
}
DATA_IMPORTS = ("fmt", "sort", "strconv", "strings", "unicode/utf16", "unicode/utf8")
_CORE = Path(__file__).resolve().parents[1] / "native" / "datajson" / "json.go"


def _go(value: str) -> str:
    from .mir_go_native import _go_string

    return _go_string(value)


def _core_source() -> str:
    """The codec core as declarations of package main; a changed shape fails closed."""

    source = _CORE.read_text(encoding="utf-8")
    body = re.sub(
        r"\A// Package datajson.*?\npackage datajson\n\nimport \(\n.*?\n\)\n\n",
        "",
        source,
        count=1,
        flags=re.DOTALL,
    )
    if body == source:
        raise RuntimeError("native data-json/v1 source shape changed; embedding refused")
    return body


def data_runtime() -> str:
    kind_prefix, kind_middle = _access.KIND_MESSAGE.split("{expected}")
    kind_middle = kind_middle.split("{actual}")[0]
    missing_prefix, missing_suffix = _access.MISSING_MESSAGE.split("{key}")
    index_prefix, index_rest = _access.INDEX_MESSAGE.split("{index}")
    index_middle, index_suffix = index_rest.split("{length}")
    int_prefix = _access.INT_MESSAGE.split("{number}")[0]
    return _core_source() + _DATA_RUNTIME.format(
        kind_prefix=_go(kind_prefix),
        kind_middle=_go(kind_middle),
        missing_prefix=_go(missing_prefix),
        missing_suffix=_go(missing_suffix),
        index_prefix=_go(index_prefix),
        index_middle=_go(index_middle),
        index_suffix=_go(index_suffix),
        int_prefix=_go(int_prefix),
        container=_go(_access.CONTAINER),
        max_string=MAX_STRING_BYTES,
        string_budget=_go(STRING_MESSAGE),
    )


_DATA_RUNTIME = r'''
// ---- JSON Data (native_data_v1) -------------------------------------------

func init() {{
	_ksDataMemberHook = _ksDataMember
	_ksDataEqualHook = _ksDataEqual
}}

// data_access_v1.public_message: the core's KS360x are the public KS370x.
func _ksJSONFailure(err error) _ksError {{
	message := err.Error()
	if strings.HasPrefix(message, "KS36") {{
		message = "KS37" + message[4:]
	}}
	return _ksError{{message: message}}
}}

func _ksParseJSON(raw any) any {{
	text, ok := raw.(string)
	if !ok {{
		_ksAbort("KS5002", "parse_json argument drifted")
	}}
	value, err := Decode(text, DefaultLimits)
	if err != nil {{
		return _ksJSONFailure(err)
	}}
	return _ksData{{value: value}}
}}

func _ksEncodeJSON(raw any) any {{
	data, ok := raw.(_ksData)
	if !ok {{
		_ksAbort("KS5002", "encode_json argument drifted")
	}}
	text, err := Encode(data.value, DefaultLimits)
	if err != nil {{
		return _ksJSONFailure(err)
	}}
	return text
}}

func _ksJSONQuote(raw any) any {{
	text, ok := raw.(string)
	if !ok {{
		_ksAbort("KS5002", "json_quote argument drifted")
	}}
	quoted := Quote(text)
	if len(quoted) > {max_string} {{
		return _ksError{{message: {string_budget}}}
	}}
	return quoted
}}

// data_access_v1.kind_of
func _ksDataKind(value any) string {{
	switch value.(type) {{
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
	case map[string]any:
		return "object"
	}}
	_ksAbort("KS5002", "JSON Data value drifted")
	return ""
}}

func _ksDataWrong(expected string, value any) _ksError {{
	return _ksError{{message: {kind_prefix} + expected + {kind_middle} + _ksDataKind(value)}}
}}

// data_access_v1.data_method
func _ksDataMember(receiver _ksData, name string, arguments []any) any {{
	value := receiver.value
	kind := _ksDataKind(value)
	switch name {{
	case "kind":
		_ksArity(name, arguments, 0)
		return kind
	case "is_null":
		_ksArity(name, arguments, 0)
		return value == nil
	case "get":
		_ksArity(name, arguments, 1)
		key, ok := arguments[0].(string)
		if !ok {{
			_ksAbort("KS5002", "Data.get key drifted")
		}}
		members, isObject := value.(map[string]any)
		if !isObject {{
			return _ksDataWrong("object", value)
		}}
		member, found := members[key]
		if !found {{
			return _ksError{{message: {missing_prefix} + Quote(key) + {missing_suffix}}}
		}}
		return _ksData{{value: member}}
	case "at":
		_ksArity(name, arguments, 1)
		index, ok := arguments[0].(int64)
		if !ok {{
			_ksAbort("KS5002", "Data.at index drifted")
		}}
		items, isArray := value.([]any)
		if !isArray {{
			return _ksDataWrong("array", value)
		}}
		if index < 0 || index >= int64(len(items)) {{
			return _ksError{{message: {index_prefix} + strconv.FormatInt(index, 10) + {index_middle} + strconv.Itoa(len(items)) + {index_suffix}}}
		}}
		return _ksData{{value: items[index]}}
	case "length":
		_ksArity(name, arguments, 0)
		switch typed := value.(type) {{
		case []any:
			return int64(len(typed))
		case map[string]any:
			return int64(len(typed))
		}}
		return _ksDataWrong({container}, value)
	case "keys":
		_ksArity(name, arguments, 0)
		members, isObject := value.(map[string]any)
		if !isObject {{
			return _ksDataWrong("object", value)
		}}
		// Code point order: UTF-8 byte order is the same.
		keys := make([]string, 0, len(members))
		for key := range members {{
			keys = append(keys, key)
		}}
		sort.Strings(keys)
		result := make([]any, len(keys))
		for index, key := range keys {{
			result[index] = key
		}}
		return result
	case "text":
		_ksArity(name, arguments, 0)
		if text, ok := value.(string); ok {{
			return text
		}}
		return _ksDataWrong("string", value)
	case "number":
		_ksArity(name, arguments, 0)
		if number, ok := value.(Number); ok {{
			return string(number)
		}}
		return _ksDataWrong("number", value)
	case "int":
		_ksArity(name, arguments, 0)
		number, ok := value.(Number)
		if !ok {{
			return _ksDataWrong("number", value)
		}}
		// Canonical number text has no sign but '-' and no leading zero, so
		// ParseInt accepts exactly the integers data_access_v1 accepts.
		parsed, err := strconv.ParseInt(string(number), 10, 64)
		if err != nil {{
			return _ksError{{message: {int_prefix} + string(number)}}
		}}
		return parsed
	case "bool":
		_ksArity(name, arguments, 0)
		if flag, ok := value.(bool); ok {{
			return flag
		}}
		return _ksDataWrong("bool", value)
	}}
	_ksAbort("KS5002", "Data member drifted: "+name)
	return nil
}}

// The equality of the Python values: objects by members, arrays in order,
// numbers by canonical text.
func _ksDataEqual(left any, right any) bool {{
	switch a := left.(type) {{
	case nil:
		return right == nil
	case bool:
		b, ok := right.(bool)
		return ok && a == b
	case string:
		b, ok := right.(string)
		return ok && a == b
	case Number:
		b, ok := right.(Number)
		return ok && a == b
	case []any:
		b, ok := right.([]any)
		if !ok || len(a) != len(b) {{
			return false
		}}
		for index := range a {{
			if !_ksDataEqual(a[index], b[index]) {{
				return false
			}}
		}}
		return true
	case map[string]any:
		b, ok := right.(map[string]any)
		if !ok || len(a) != len(b) {{
			return false
		}}
		for key, item := range a {{
			other, found := b[key]
			if !found || !_ksDataEqual(item, other) {{
				return false
			}}
		}}
		return true
	}}
	return false
}}
'''


__all__ = ["BUILTINS", "DATA_IMPORTS", "data_runtime"]
