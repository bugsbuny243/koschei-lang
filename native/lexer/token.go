package lexer

// Kind is a stable, language-neutral token name. The names intentionally match
// the current Koschei bootstrap compiler so parity can be checked mechanically.
type Kind string

const (
	FN           Kind = "FN"
	LET          Kind = "LET"
	MUT          Kind = "MUT"
	OR           Kind = "OR"
	RETURN       Kind = "RETURN"
	IF           Kind = "IF"
	ELSE         Kind = "ELSE"
	WHILE        Kind = "WHILE"
	FOR          Kind = "FOR"
	IN           Kind = "IN"
	STRUCT       Kind = "STRUCT"
	ENUM         Kind = "ENUM"
	MATCH        Kind = "MATCH"
	IMPORT       Kind = "IMPORT"
	TRUE         Kind = "TRUE"
	FALSE        Kind = "FALSE"
	TYPE         Kind = "TYPE"
	IDENTIFIER   Kind = "IDENTIFIER"
	STRING       Kind = "STRING"
	STRINGINTERP Kind = "STRING_INTERP"
	NUMBER       Kind = "NUMBER"
	COMMENT      Kind = "COMMENT"
	LEFTPAREN    Kind = "LEFT_PAREN"
	RIGHTPAREN   Kind = "RIGHT_PAREN"
	LEFTBRACE    Kind = "LEFT_BRACE"
	RIGHTBRACE   Kind = "RIGHT_BRACE"
	COMMA        Kind = "COMMA"
	COLON        Kind = "COLON"
	DOT          Kind = "DOT"
	EQUAL        Kind = "EQUAL"
	PLUS         Kind = "PLUS"
	MINUS        Kind = "MINUS"
	STAR         Kind = "STAR"
	SLASH        Kind = "SLASH"
	SEMICOLON    Kind = "SEMICOLON"
	BANG         Kind = "BANG"
	LEFTBRACKET  Kind = "LEFT_BRACKET"
	RIGHTBRACKET Kind = "RIGHT_BRACKET"
	ARROW        Kind = "ARROW"
	FATARROW     Kind = "FAT_ARROW"
	EQUALEQUAL   Kind = "EQUAL_EQUAL"
	BANGEQUAL    Kind = "BANG_EQUAL"
	LESS         Kind = "LESS"
	LESSEQUAL    Kind = "LESS_EQUAL"
	GREATER      Kind = "GREATER"
	GREATEREQUAL Kind = "GREATER_EQUAL"
	AMPAMP       Kind = "AMP_AMP"
	PIPEPIPE     Kind = "PIPE_PIPE"
	EOF          Kind = "EOF"
)

// Segment preserves either literal text or a source expression inside an
// interpolated string. Expression validity remains the parser's responsibility.
type Segment struct {
	Kind  string `json:"kind"`
	Value string `json:"value"`
}

// Token deliberately keeps numeric values as exact source text. Value is always
// emitted in JSON because an empty string is a meaningful STRING token value.
type Token struct {
	Kind     Kind      `json:"kind"`
	Lexeme   string    `json:"lexeme,omitempty"`
	Value    string    `json:"value"`
	Segments []Segment `json:"segments,omitempty"`
	Line     int       `json:"line"`
	Column   int       `json:"column"`
}
