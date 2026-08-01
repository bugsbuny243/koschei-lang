// Package datajson implements the bounded Koschei data-json/v1 contract.
package datajson

import (
	"fmt"
	"sort"
	"strconv"
	"strings"
	"unicode/utf16"
	"unicode/utf8"
)

const Schema = "koschei.data-json/v1"

type Limits struct {
	MaxInputBytes  int
	MaxOutputBytes int
	MaxNodes       int
	MaxDepth       int
}

var DefaultLimits = Limits{
	MaxInputBytes:  1_048_576,
	MaxOutputBytes: 1_048_576,
	MaxNodes:       100_000,
	MaxDepth:       64,
}

func (l Limits) validate() error {
	if l.MaxInputBytes < 1 || l.MaxOutputBytes < 1 || l.MaxNodes < 1 || l.MaxDepth < 1 {
		return fmt.Errorf("all data-json limits must be at least 1")
	}
	return nil
}

type Number string

type Error struct {
	Code    string
	Message string
	Offset  int
}

func (e *Error) Error() string {
	return fmt.Sprintf("%s [byte %d]: %s", e.Code, e.Offset, e.Message)
}

func CanonicalNumber(text string) (string, error) {
	if text == "" {
		return "", fmt.Errorf("JSON number must be non-empty")
	}
	index := 0
	negative := false
	if text[index] == '-' {
		negative = true
		index++
		if index == len(text) {
			return "", fmt.Errorf("missing digits after '-' in JSON number")
		}
	}
	intStart := index
	if text[index] == '0' {
		index++
		if index < len(text) && isDigit(text[index]) {
			return "", fmt.Errorf("leading zero in JSON number")
		}
	} else if text[index] >= '1' && text[index] <= '9' {
		index++
		for index < len(text) && isDigit(text[index]) {
			index++
		}
	} else {
		return "", fmt.Errorf("invalid integer part in JSON number")
	}
	integer := text[intStart:index]
	fraction := ""
	if index < len(text) && text[index] == '.' {
		index++
		start := index
		for index < len(text) && isDigit(text[index]) {
			index++
		}
		if index == start {
			return "", fmt.Errorf("fraction requires at least one digit")
		}
		fraction = text[start:index]
	}
	exponent := 0
	if index < len(text) && (text[index] == 'e' || text[index] == 'E') {
		index++
		expNegative := false
		if index < len(text) && (text[index] == '+' || text[index] == '-') {
			expNegative = text[index] == '-'
			index++
		}
		start := index
		for index < len(text) && isDigit(text[index]) {
			index++
		}
		if index == start {
			return "", fmt.Errorf("exponent requires at least one digit")
		}
		digits := strings.TrimLeft(text[start:index], "0")
		if digits == "" {
			digits = "0"
		}
		if len(digits) > 9 {
			return "", fmt.Errorf("JSON exponent magnitude exceeds data/v1 limit")
		}
		parsed, err := strconv.Atoi(digits)
		if err != nil || parsed > 1_000_000 {
			return "", fmt.Errorf("JSON exponent magnitude exceeds data/v1 limit")
		}
		exponent = parsed
		if expNegative {
			exponent = -exponent
		}
	}
	if index != len(text) {
		return "", fmt.Errorf("trailing characters in JSON number")
	}

	digits := strings.TrimLeft(integer+fraction, "0")
	if digits == "" {
		return "0", nil
	}
	scale := exponent - len(fraction)
	trimmed := strings.TrimRight(digits, "0")
	trailing := len(digits) - len(trimmed)
	if trailing > 0 {
		digits = trimmed
		scale += trailing
	}
	sciExp := scale + len(digits) - 1
	sign := ""
	if negative {
		sign = "-"
	}
	if sciExp >= 21 || sciExp <= -7 {
		coefficient := digits[:1]
		if len(digits) > 1 {
			coefficient += "." + digits[1:]
		}
		return sign + coefficient + "e" + strconv.Itoa(sciExp), nil
	}
	position := len(digits) + scale
	var body string
	if position <= 0 {
		body = "0." + strings.Repeat("0", -position) + digits
	} else if position >= len(digits) {
		body = digits + strings.Repeat("0", position-len(digits))
	} else {
		body = digits[:position] + "." + digits[position:]
	}
	return sign + body, nil
}

func isDigit(value byte) bool { return value >= '0' && value <= '9' }

type parser struct {
	text   string
	limits Limits
	index  int
	nodes  int
}

func Decode(text string, limits Limits) (any, error) {
	if err := limits.validate(); err != nil {
		return nil, err
	}
	if !utf8.ValidString(text) {
		return nil, &Error{Code: "KS3605", Message: "input is not valid UTF-8", Offset: 0}
	}
	if len(text) > limits.MaxInputBytes {
		return nil, &Error{Code: "KS3601", Message: fmt.Sprintf("JSON input bytes exceed limit %d", limits.MaxInputBytes), Offset: 0}
	}
	p := &parser{text: text, limits: limits}
	p.skipSpace()
	value, err := p.value(1)
	if err != nil {
		return nil, err
	}
	p.skipSpace()
	if p.index != len(p.text) {
		return nil, p.fail("KS3605", "trailing data after JSON value", p.index)
	}
	return value, nil
}

func (p *parser) fail(code, message string, offset int) error {
	return &Error{Code: code, Message: message, Offset: offset}
}

func (p *parser) node(depth int) error {
	if depth > p.limits.MaxDepth {
		return p.fail("KS3602", fmt.Sprintf("JSON depth exceeds limit %d", p.limits.MaxDepth), p.index)
	}
	p.nodes++
	if p.nodes > p.limits.MaxNodes {
		return p.fail("KS3603", fmt.Sprintf("JSON node count exceeds limit %d", p.limits.MaxNodes), p.index)
	}
	return nil
}

func (p *parser) skipSpace() {
	for p.index < len(p.text) {
		switch p.text[p.index] {
		case ' ', '\t', '\r', '\n':
			p.index++
		default:
			return
		}
	}
}

func (p *parser) value(depth int) (any, error) {
	if err := p.node(depth); err != nil {
		return nil, err
	}
	if p.index >= len(p.text) {
		return nil, p.fail("KS3605", "unexpected end of JSON input", p.index)
	}
	switch p.text[p.index] {
	case '"':
		return p.string()
	case '{':
		return p.object(depth)
	case '[':
		return p.array(depth)
	case 't':
		if strings.HasPrefix(p.text[p.index:], "true") {
			p.index += 4
			return true, nil
		}
	case 'f':
		if strings.HasPrefix(p.text[p.index:], "false") {
			p.index += 5
			return false, nil
		}
	case 'n':
		if strings.HasPrefix(p.text[p.index:], "null") {
			p.index += 4
			return nil, nil
		}
	default:
		if p.text[p.index] == '-' || isDigit(p.text[p.index]) {
			return p.number()
		}
	}
	return nil, p.fail("KS3605", fmt.Sprintf("unexpected character %q", p.text[p.index]), p.index)
}

func (p *parser) array(depth int) ([]any, error) {
	p.index++
	items := []any{}
	p.skipSpace()
	if p.index < len(p.text) && p.text[p.index] == ']' {
		p.index++
		return items, nil
	}
	for {
		item, err := p.value(depth + 1)
		if err != nil {
			return nil, err
		}
		items = append(items, item)
		p.skipSpace()
		if p.index >= len(p.text) {
			return nil, p.fail("KS3605", "unterminated JSON array", p.index)
		}
		char := p.text[p.index]
		p.index++
		if char == ']' {
			return items, nil
		}
		if char != ',' {
			return nil, p.fail("KS3605", "expected ',' or ']' in JSON array", p.index-1)
		}
		p.skipSpace()
	}
}

func (p *parser) object(depth int) (map[string]any, error) {
	p.index++
	result := map[string]any{}
	p.skipSpace()
	if p.index < len(p.text) && p.text[p.index] == '}' {
		p.index++
		return result, nil
	}
	for {
		if p.index >= len(p.text) || p.text[p.index] != '"' {
			return nil, p.fail("KS3605", "JSON object key must be a string", p.index)
		}
		keyOffset := p.index
		key, err := p.string()
		if err != nil {
			return nil, err
		}
		if _, exists := result[key]; exists {
			return nil, p.fail("KS3604", fmt.Sprintf("duplicate JSON object key %q", key), keyOffset)
		}
		p.skipSpace()
		if p.index >= len(p.text) || p.text[p.index] != ':' {
			return nil, p.fail("KS3605", "expected ':' after JSON object key", p.index)
		}
		p.index++
		p.skipSpace()
		value, err := p.value(depth + 1)
		if err != nil {
			return nil, err
		}
		result[key] = value
		p.skipSpace()
		if p.index >= len(p.text) {
			return nil, p.fail("KS3605", "unterminated JSON object", p.index)
		}
		char := p.text[p.index]
		p.index++
		if char == '}' {
			return result, nil
		}
		if char != ',' {
			return nil, p.fail("KS3605", "expected ',' or '}' in JSON object", p.index-1)
		}
		p.skipSpace()
	}
}

func (p *parser) string() (string, error) {
	p.index++
	var builder strings.Builder
	start := p.index
	for p.index < len(p.text) {
		char := p.text[p.index]
		if char == '"' {
			builder.WriteString(p.text[start:p.index])
			p.index++
			return builder.String(), nil
		}
		if char == '\\' {
			builder.WriteString(p.text[start:p.index])
			p.index++
			if p.index >= len(p.text) {
				return "", p.fail("KS3605", "unterminated escape in JSON string", p.index)
			}
			escape := p.text[p.index]
			p.index++
			switch escape {
			case '"', '\\', '/':
				builder.WriteByte(escape)
			case 'b':
				builder.WriteByte('\b')
			case 'f':
				builder.WriteByte('\f')
			case 'n':
				builder.WriteByte('\n')
			case 'r':
				builder.WriteByte('\r')
			case 't':
				builder.WriteByte('\t')
			case 'u':
				decoded, err := p.unicodeEscape()
				if err != nil {
					return "", err
				}
				builder.WriteRune(decoded)
			default:
				return "", p.fail("KS3605", fmt.Sprintf("invalid JSON escape \\%c", escape), p.index-2)
			}
			start = p.index
			continue
		}
		if char < 0x20 {
			return "", p.fail("KS3605", "unescaped control character in JSON string", p.index)
		}
		_, size := utf8.DecodeRuneInString(p.text[p.index:])
		p.index += size
	}
	return "", p.fail("KS3605", "unterminated JSON string", p.index)
}

func (p *parser) unicodeEscape() (rune, error) {
	first, err := p.hex4()
	if err != nil {
		return 0, err
	}
	if first >= 0xDC00 && first <= 0xDFFF {
		return 0, p.fail("KS3605", "lone low surrogate in JSON string", p.index-4)
	}
	if first < 0xD800 || first > 0xDBFF {
		return rune(first), nil
	}
	if p.index+6 > len(p.text) || p.text[p.index:p.index+2] != "\\u" {
		return 0, p.fail("KS3605", "high surrogate requires a low surrogate", p.index-4)
	}
	p.index += 2
	second, err := p.hex4()
	if err != nil {
		return 0, err
	}
	if second < 0xDC00 || second > 0xDFFF {
		return 0, p.fail("KS3605", "high surrogate requires a low surrogate", p.index-4)
	}
	return utf16.DecodeRune(rune(first), rune(second)), nil
}

func (p *parser) hex4() (uint16, error) {
	if p.index+4 > len(p.text) {
		return 0, p.fail("KS3605", "short \\u escape in JSON string", p.index)
	}
	value := uint16(0)
	for i := 0; i < 4; i++ {
		char := p.text[p.index+i]
		value <<= 4
		switch {
		case char >= '0' && char <= '9':
			value += uint16(char - '0')
		case char >= 'a' && char <= 'f':
			value += uint16(char-'a') + 10
		case char >= 'A' && char <= 'F':
			value += uint16(char-'A') + 10
		default:
			return 0, p.fail("KS3605", "invalid hex digit in \\u escape", p.index+i)
		}
	}
	p.index += 4
	return value, nil
}

func (p *parser) number() (Number, error) {
	start := p.index
	if p.text[p.index] == '-' {
		p.index++
	}
	if p.index >= len(p.text) {
		return "", p.fail("KS3605", "missing digits in JSON number", p.index)
	}
	if p.text[p.index] == '0' {
		p.index++
		if p.index < len(p.text) && isDigit(p.text[p.index]) {
			return "", p.fail("KS3605", "leading zero in JSON number", p.index)
		}
	} else if p.text[p.index] >= '1' && p.text[p.index] <= '9' {
		for p.index < len(p.text) && isDigit(p.text[p.index]) {
			p.index++
		}
	} else {
		return "", p.fail("KS3605", "invalid integer part in JSON number", p.index)
	}
	if p.index < len(p.text) && p.text[p.index] == '.' {
		p.index++
		fractionStart := p.index
		for p.index < len(p.text) && isDigit(p.text[p.index]) {
			p.index++
		}
		if p.index == fractionStart {
			return "", p.fail("KS3605", "fraction requires at least one digit", p.index)
		}
	}
	if p.index < len(p.text) && (p.text[p.index] == 'e' || p.text[p.index] == 'E') {
		p.index++
		if p.index < len(p.text) && (p.text[p.index] == '+' || p.text[p.index] == '-') {
			p.index++
		}
		exponentStart := p.index
		for p.index < len(p.text) && isDigit(p.text[p.index]) {
			p.index++
		}
		if p.index == exponentStart {
			return "", p.fail("KS3605", "exponent requires at least one digit", p.index)
		}
	}
	canonical, err := CanonicalNumber(p.text[start:p.index])
	if err != nil {
		return "", p.fail("KS3605", err.Error(), start)
	}
	return Number(canonical), nil
}

type writer struct {
	limits Limits
	text   strings.Builder
	size   int
	nodes  int
}

func Encode(value any, limits Limits) (string, error) {
	if err := limits.validate(); err != nil {
		return "", err
	}
	w := &writer{limits: limits}
	if err := w.value(value, 1); err != nil {
		return "", err
	}
	return w.text.String(), nil
}

func (w *writer) add(text string) error {
	if w.size+len(text) > w.limits.MaxOutputBytes {
		return &Error{Code: "KS3607", Message: fmt.Sprintf("JSON output bytes exceed limit %d", w.limits.MaxOutputBytes), Offset: w.size}
	}
	w.text.WriteString(text)
	w.size += len(text)
	return nil
}

func (w *writer) value(value any, depth int) error {
	if depth > w.limits.MaxDepth {
		return &Error{Code: "KS3602", Message: fmt.Sprintf("JSON depth exceeds limit %d", w.limits.MaxDepth), Offset: w.size}
	}
	w.nodes++
	if w.nodes > w.limits.MaxNodes {
		return &Error{Code: "KS3603", Message: fmt.Sprintf("JSON node count exceeds limit %d", w.limits.MaxNodes), Offset: w.size}
	}
	switch typed := value.(type) {
	case nil:
		return w.add("null")
	case bool:
		if typed {
			return w.add("true")
		}
		return w.add("false")
	case string:
		return w.string(typed)
	case Number:
		canonical, err := CanonicalNumber(string(typed))
		if err != nil || canonical != string(typed) {
			return &Error{Code: "KS3608", Message: "Number must contain canonical data/v1 text", Offset: w.size}
		}
		return w.add(string(typed))
	case []any:
		if err := w.add("["); err != nil {
			return err
		}
		for index, item := range typed {
			if index > 0 {
				if err := w.add(","); err != nil {
					return err
				}
			}
			if err := w.value(item, depth+1); err != nil {
				return err
			}
		}
		return w.add("]")
	case map[string]any:
		keys := make([]string, 0, len(typed))
		for key := range typed {
			if !utf8.ValidString(key) {
				return &Error{Code: "KS3608", Message: "JSON object key is not valid UTF-8", Offset: w.size}
			}
			keys = append(keys, key)
		}
		sort.Strings(keys)
		if err := w.add("{"); err != nil {
			return err
		}
		for index, key := range keys {
			if index > 0 {
				if err := w.add(","); err != nil {
					return err
				}
			}
			if err := w.string(key); err != nil {
				return err
			}
			if err := w.add(":"); err != nil {
				return err
			}
			if err := w.value(typed[key], depth+1); err != nil {
				return err
			}
		}
		return w.add("}")
	default:
		return &Error{Code: "KS3608", Message: fmt.Sprintf("value of type %T is not data/v1 encodable", value), Offset: w.size}
	}
}

func (w *writer) string(value string) error {
	if !utf8.ValidString(value) {
		return &Error{Code: "KS3608", Message: "string is not valid UTF-8", Offset: w.size}
	}
	if err := w.add("\""); err != nil {
		return err
	}
	start := 0
	for index, r := range value {
		replacement := ""
		switch r {
		case '"':
			replacement = "\\\""
		case '\\':
			replacement = "\\\\"
		case '\b':
			replacement = "\\b"
		case '\f':
			replacement = "\\f"
		case '\n':
			replacement = "\\n"
		case '\r':
			replacement = "\\r"
		case '\t':
			replacement = "\\t"
		default:
			if r < 0x20 {
				replacement = fmt.Sprintf("\\u%04x", r)
			}
		}
		if replacement == "" {
			continue
		}
		if start < index {
			if err := w.add(value[start:index]); err != nil {
				return err
			}
		}
		if err := w.add(replacement); err != nil {
			return err
		}
		start = index + utf8.RuneLen(r)
	}
	if start < len(value) {
		if err := w.add(value[start:]); err != nil {
			return err
		}
	}
	return w.add("\"")
}
