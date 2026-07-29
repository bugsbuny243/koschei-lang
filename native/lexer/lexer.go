// Package lexer is the first native Koschei compiler slice.
//
// It is dependency-free, deterministic, UTF-8 aware, and fail-closed on source
// and token budgets. It does not execute code, import packages, or touch ambient
// authority. The current Python frontend remains the compatibility oracle until
// native parity is complete.
package lexer

import (
	"errors"
	"fmt"
	"unicode"
	"unicode/utf8"
)

const (
	DefaultMaxSourceBytes = 4 << 20
	DefaultMaxTokens      = 1_000_000
)

var (
	ErrInvalidUTF8    = errors.New("source is not valid UTF-8")
	ErrSourceTooLarge = errors.New("source exceeds configured byte budget")
	ErrTokenBudget    = errors.New("token budget exhausted")
)

type Config struct {
	KeepComments   bool
	MaxSourceBytes int
	MaxTokens      int
}

func (config Config) normalized() Config {
	if config.MaxSourceBytes == 0 {
		config.MaxSourceBytes = DefaultMaxSourceBytes
	}
	if config.MaxTokens == 0 {
		config.MaxTokens = DefaultMaxTokens
	}
	return config
}

type Error struct {
	Line    int
	Column  int
	Message string
	Cause   error
}

func (failure *Error) Error() string {
	return fmt.Sprintf("[line %d, column %d] %s", failure.Line, failure.Column, failure.Message)
}

func (failure *Error) Unwrap() error { return failure.Cause }

type Lexer struct {
	source      []rune
	config      Config
	start       int
	current     int
	line        int
	column      int
	startLine   int
	startColumn int
	tokens      []Token
}

var keywords = map[string]Kind{
	"fn": FN, "let": LET, "mut": MUT, "or": OR, "return": RETURN,
	"if": IF, "else": ELSE, "while": WHILE, "for": FOR, "in": IN,
	"struct": STRUCT, "enum": ENUM, "match": MATCH, "import": IMPORT,
	"true": TRUE, "false": FALSE,
}

var builtinTypes = map[string]struct{}{
	"SystemCaps": {}, "NetRoot": {}, "DiskRoot": {}, "EnvRoot": {},
	"ProcessRoot": {}, "NetCaps": {}, "DiskCaps": {}, "DiskReadCaps": {},
	"EnvCaps": {}, "ProcessCaps": {}, "List": {}, "Map": {}, "String": {},
	"Int": {}, "Float": {}, "Bool": {}, "Void": {}, "Error": {},
	"Result": {}, "Option": {},
}

var single = map[rune]Kind{
	'(': LEFTPAREN, ')': RIGHTPAREN, '{': LEFTBRACE, '}': RIGHTBRACE,
	',': COMMA, ':': COLON, '.': DOT, '+': PLUS, '*': STAR,
	';': SEMICOLON, '[': LEFTBRACKET, ']': RIGHTBRACKET,
}

var escapes = map[rune]rune{
	'n': '\n', 'r': '\r', 't': '\t', '"': '"', '\\': '\\', '{': '{', '}': '}',
}

func Tokenize(source string, config Config) ([]Token, error) {
	config = config.normalized()
	if config.MaxSourceBytes < 1 {
		return nil, &Error{Line: 1, Column: 1, Message: "max source byte budget must be positive", Cause: ErrSourceTooLarge}
	}
	if config.MaxTokens < 1 {
		return nil, &Error{Line: 1, Column: 1, Message: "max token budget must be positive", Cause: ErrTokenBudget}
	}
	if len(source) > config.MaxSourceBytes {
		return nil, &Error{Line: 1, Column: 1, Message: fmt.Sprintf("source exceeds %d-byte budget", config.MaxSourceBytes), Cause: ErrSourceTooLarge}
	}
	if !utf8.ValidString(source) {
		return nil, &Error{Line: 1, Column: 1, Message: ErrInvalidUTF8.Error(), Cause: ErrInvalidUTF8}
	}
	machine := &Lexer{
		source: []rune(source), config: config, line: 1, column: 1,
		tokens: make([]Token, 0, min(len(source)/3+1, config.MaxTokens)),
	}
	return machine.tokenize()
}

func (lexer *Lexer) tokenize() ([]Token, error) {
	for !lexer.atEnd() {
		lexer.start = lexer.current
		lexer.startLine = lexer.line
		lexer.startColumn = lexer.column
		if err := lexer.scan(); err != nil {
			return nil, err
		}
	}
	if err := lexer.add(Token{Kind: EOF, Line: lexer.line, Column: lexer.column}); err != nil {
		return nil, err
	}
	return lexer.tokens, nil
}

func (lexer *Lexer) scan() error {
	char := lexer.advance()
	if char == ' ' || char == '\r' || char == '\t' || char == '\n' {
		return nil
	}
	if char == '/' {
		if lexer.match('/') {
			for lexer.peek() != '\n' && lexer.peek() != 0 {
				lexer.advance()
			}
			if lexer.config.KeepComments {
				text := lexer.slice()
				return lexer.emit(COMMENT, text, text, nil)
			}
			return nil
		}
		return lexer.emit(SLASH, "/", "/", nil)
	}
	if char == '"' {
		return lexer.stringValue()
	}
	if unicode.IsDigit(char) {
		return lexer.number()
	}
	if unicode.IsLetter(char) || char == '_' {
		return lexer.identifier()
	}
	switch char {
	case '-':
		if lexer.match('>') {
			return lexer.emit(ARROW, "->", "->", nil)
		}
		return lexer.emit(MINUS, "-", "-", nil)
	case '=':
		if lexer.match('>') {
			return lexer.emit(FATARROW, "=>", "=>", nil)
		}
		if lexer.match('=') {
			return lexer.emit(EQUALEQUAL, "==", "==", nil)
		}
		return lexer.emit(EQUAL, "=", "=", nil)
	case '!':
		if lexer.match('=') {
			return lexer.emit(BANGEQUAL, "!=", "!=", nil)
		}
		return lexer.emit(BANG, "!", "!", nil)
	case '&':
		if lexer.match('&') {
			return lexer.emit(AMPAMP, "&&", "&&", nil)
		}
		return lexer.failure("unexpected '&'; use '&&' for logical and", nil)
	case '|':
		if lexer.match('|') {
			return lexer.emit(PIPEPIPE, "||", "||", nil)
		}
		return lexer.failure("unexpected '|'; use '||' for logical or", nil)
	case '<':
		if lexer.match('=') {
			return lexer.emit(LESSEQUAL, "<=", "<=", nil)
		}
		return lexer.emit(LESS, "<", "<", nil)
	case '>':
		if lexer.match('=') {
			return lexer.emit(GREATEREQUAL, ">=", ">=", nil)
		}
		return lexer.emit(GREATER, ">", ">", nil)
	}
	if kind, ok := single[char]; ok {
		text := string(char)
		return lexer.emit(kind, text, text, nil)
	}
	return lexer.failure(fmt.Sprintf("invalid character: %q", char), nil)
}

// isPythonAlnum mirrors Python str.isalnum for identifier continuations:
// Unicode letters plus every Unicode numeric category (Nd, Nl, and No).
func isPythonAlnum(char rune) bool {
	return unicode.IsLetter(char) || unicode.IsNumber(char)
}

func (lexer *Lexer) identifier() error {
	for isPythonAlnum(lexer.peek()) || lexer.peek() == '_' {
		lexer.advance()
	}
	text := lexer.slice()
	kind, ok := keywords[text]
	if !ok {
		_, builtin := builtinTypes[text]
		first, _ := utf8.DecodeRuneInString(text)
		if builtin || unicode.IsUpper(first) {
			kind = TYPE
		} else {
			kind = IDENTIFIER
		}
	}
	return lexer.emit(kind, text, text, nil)
}

func (lexer *Lexer) number() error {
	for unicode.IsDigit(lexer.peek()) {
		lexer.advance()
	}
	if lexer.peek() == '.' && unicode.IsDigit(lexer.peekNext()) {
		lexer.advance()
		for unicode.IsDigit(lexer.peek()) {
			lexer.advance()
		}
	}
	text := lexer.slice()
	return lexer.emit(NUMBER, text, text, nil)
}

func (lexer *Lexer) stringValue() error {
	segments := make([]Segment, 0, 4)
	text := make([]rune, 0, 32)
	flush := func() {
		if len(text) != 0 {
			segments = append(segments, Segment{Kind: "text", Value: string(text)})
			text = text[:0]
		}
	}
	for !lexer.atEnd() {
		char := lexer.advance()
		switch char {
		case '"':
			flush()
			for _, segment := range segments {
				if segment.Kind == "expr" {
					return lexer.emit(STRINGINTERP, lexer.slice(), "", segments)
				}
			}
			value := ""
			if len(segments) != 0 {
				value = segments[0].Value
			}
			return lexer.emit(STRING, lexer.slice(), value, nil)
		case '\\':
			if lexer.atEnd() {
				return lexer.failure("unfinished escape sequence", nil)
			}
			escaped := lexer.advance()
			decoded, ok := escapes[escaped]
			if !ok {
				return lexer.failure(fmt.Sprintf("invalid escape sequence: \\%c", escaped), nil)
			}
			text = append(text, decoded)
		case '{':
			expression, err := lexer.interpolationExpression()
			if err != nil {
				return err
			}
			if expression == "" {
				return lexer.failure("empty interpolation '{}' is invalid", nil)
			}
			flush()
			segments = append(segments, Segment{Kind: "expr", Value: expression})
		case '}':
			return lexer.failure("single '}' in a string is invalid; use '\\}'", nil)
		default:
			text = append(text, char)
		}
	}
	return lexer.failure("unterminated string value", nil)
}

func (lexer *Lexer) interpolationExpression() (string, error) {
	depth := 1
	expression := make([]rune, 0, 32)
	inString := false
	escaped := false
	for !lexer.atEnd() {
		char := lexer.advance()
		if inString {
			expression = append(expression, char)
			if escaped {
				escaped = false
			} else if char == '\\' {
				escaped = true
			} else if char == '"' {
				inString = false
			} else if char == '\n' {
				return "", lexer.failure("string inside interpolation cannot cross a line", nil)
			}
			continue
		}
		switch char {
		case '"':
			inString = true
			expression = append(expression, char)
		case '{':
			depth++
			expression = append(expression, char)
		case '}':
			depth--
			if depth == 0 {
				return trimSpace(string(expression)), nil
			}
			expression = append(expression, char)
		case '\n':
			return "", lexer.failure("interpolation must close with '}' on the same line", nil)
		default:
			expression = append(expression, char)
		}
	}
	return "", lexer.failure("interpolation must close with '}'", nil)
}

// isPythonSpace mirrors the whitespace set used by Python str.strip. Go's
// unicode.IsSpace matches it except for the four information separators below.
func isPythonSpace(char rune) bool {
	return unicode.IsSpace(char) || (char >= '\u001c' && char <= '\u001f')
}

func trimSpace(value string) string {
	runes := []rune(value)
	start, end := 0, len(runes)
	for start < end && isPythonSpace(runes[start]) {
		start++
	}
	for end > start && isPythonSpace(runes[end-1]) {
		end--
	}
	return string(runes[start:end])
}

func (lexer *Lexer) emit(kind Kind, lexeme, value string, segments []Segment) error {
	return lexer.add(Token{Kind: kind, Lexeme: lexeme, Value: value, Segments: segments, Line: lexer.startLine, Column: lexer.startColumn})
}

func (lexer *Lexer) add(token Token) error {
	if len(lexer.tokens) >= lexer.config.MaxTokens {
		return lexer.failure(fmt.Sprintf("token budget exhausted at %d tokens", lexer.config.MaxTokens), ErrTokenBudget)
	}
	lexer.tokens = append(lexer.tokens, token)
	return nil
}

func (lexer *Lexer) advance() rune {
	char := lexer.source[lexer.current]
	lexer.current++
	if char == '\n' {
		lexer.line++
		lexer.column = 1
	} else {
		lexer.column++
	}
	return char
}

func (lexer *Lexer) match(expected rune) bool {
	if lexer.atEnd() || lexer.source[lexer.current] != expected {
		return false
	}
	lexer.advance()
	return true
}

func (lexer *Lexer) peek() rune {
	if lexer.atEnd() {
		return 0
	}
	return lexer.source[lexer.current]
}

func (lexer *Lexer) peekNext() rune {
	if lexer.current+1 >= len(lexer.source) {
		return 0
	}
	return lexer.source[lexer.current+1]
}

func (lexer *Lexer) atEnd() bool   { return lexer.current >= len(lexer.source) }
func (lexer *Lexer) slice() string { return string(lexer.source[lexer.start:lexer.current]) }

func (lexer *Lexer) failure(message string, cause error) error {
	return &Error{Line: lexer.startLine, Column: lexer.startColumn, Message: message, Cause: cause}
}
