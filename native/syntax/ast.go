// Package syntax defines the versioned, language-neutral Koschei syntax tree.
package syntax

const SchemaV1 = "koschei.syntax/v1"

type Location struct {
	Line   int `json:"line"`
	Column int `json:"column"`
}

type Document struct {
	Schema    string                `json:"schema"`
	Kind      string                `json:"kind"`
	Imports   []ImportDeclaration   `json:"imports"`
	Structs   []StructDeclaration   `json:"structs"`
	Enums     []EnumDeclaration     `json:"enums"`
	Functions []FunctionDeclaration `json:"functions"`
}

func NewDocument() Document {
	return Document{
		Schema:    SchemaV1,
		Kind:      "Program",
		Imports:   make([]ImportDeclaration, 0),
		Structs:   make([]StructDeclaration, 0),
		Enums:     make([]EnumDeclaration, 0),
		Functions: make([]FunctionDeclaration, 0),
	}
}

type TypeExpression struct {
	Name      string           `json:"name"`
	Arguments []TypeExpression `json:"arguments"`
}

type TypeRef struct {
	Kind         string           `json:"kind"`
	Alternatives []TypeExpression `json:"alternatives"`
	Location     Location         `json:"location"`
}

type ImportDeclaration struct {
	Kind     string   `json:"kind"`
	Name     string   `json:"name"`
	Location Location `json:"location"`
}

type TypeParameter struct {
	Name     string   `json:"name"`
	Location Location `json:"location"`
}

type StructField struct {
	Name     string   `json:"name"`
	Type     TypeRef  `json:"type"`
	Location Location `json:"location"`
}

type StructDeclaration struct {
	Kind           string          `json:"kind"`
	Name           string          `json:"name"`
	TypeParameters []TypeParameter `json:"type_parameters"`
	Fields         []StructField   `json:"fields"`
	Location       Location        `json:"location"`
}

type EnumVariant struct {
	Name        string   `json:"name"`
	PayloadType *TypeRef `json:"payload_type,omitempty"`
	Location    Location `json:"location"`
}

type EnumDeclaration struct {
	Kind           string          `json:"kind"`
	Name           string          `json:"name"`
	TypeParameters []TypeParameter `json:"type_parameters"`
	Variants       []EnumVariant   `json:"variants"`
	Location       Location        `json:"location"`
}

type Parameter struct {
	Name     string   `json:"name"`
	Type     TypeRef  `json:"type"`
	Location Location `json:"location"`
}

type FunctionDeclaration struct {
	Kind           string          `json:"kind"`
	Name           string          `json:"name"`
	TypeParameters []TypeParameter `json:"type_parameters"`
	Parameters     []Parameter     `json:"parameters"`
	ReturnType     *TypeRef        `json:"return_type,omitempty"`
	Body           Block           `json:"body"`
	Location       Location        `json:"location"`
}

type Block struct {
	Kind       string      `json:"kind"`
	Statements []Statement `json:"statements"`
	Location   Location    `json:"location"`
}

type Statement struct {
	Kind       string      `json:"kind"`
	Location   Location    `json:"location"`
	Name       string      `json:"name,omitempty"`
	Mutable    *bool       `json:"mutable,omitempty"`
	Annotation *TypeRef    `json:"annotation,omitempty"`
	Value      *Expression `json:"value,omitempty"`
	Expression *Expression `json:"expression,omitempty"`
	Condition  *Expression `json:"condition,omitempty"`
	Then       *Block      `json:"then,omitempty"`
	Else       *Block      `json:"else,omitempty"`
	ElseIf     *Statement  `json:"else_if,omitempty"`
	Body       *Block      `json:"body,omitempty"`
	Variable   string      `json:"variable,omitempty"`
	Iterable   *Expression `json:"iterable,omitempty"`
}

type LiteralValue struct {
	Kind string  `json:"kind"`
	Text *string `json:"text,omitempty"`
	Bool *bool   `json:"bool,omitempty"`
}

type NamedExpression struct {
	Name  string     `json:"name"`
	Value Expression `json:"value"`
}

type MapEntry struct {
	Key   Expression `json:"key"`
	Value Expression `json:"value"`
}

type MatchArm struct {
	Variant  string     `json:"variant"`
	Binding  string     `json:"binding,omitempty"`
	Body     Expression `json:"body"`
	Location Location   `json:"location"`
}

type Expression struct {
	Kind      string            `json:"kind"`
	Location  Location          `json:"location"`
	Name      string            `json:"name,omitempty"`
	Literal   *LiteralValue     `json:"literal,omitempty"`
	Parts     []Expression      `json:"parts,omitempty"`
	TypeName  string            `json:"type_name,omitempty"`
	Fields    []NamedExpression `json:"fields,omitempty"`
	Items     []Expression      `json:"items,omitempty"`
	Entries   []MapEntry        `json:"entries,omitempty"`
	Object    *Expression       `json:"object,omitempty"`
	Member    string            `json:"member,omitempty"`
	Callee    *Expression       `json:"callee,omitempty"`
	Arguments []Expression      `json:"arguments,omitempty"`
	Target    *Expression       `json:"target,omitempty"`
	Value     *Expression       `json:"value,omitempty"`
	Operator  string            `json:"operator,omitempty"`
	Left      *Expression       `json:"left,omitempty"`
	Right     *Expression       `json:"right,omitempty"`
	Operand   *Expression       `json:"operand,omitempty"`
	Fallback  *Expression       `json:"fallback,omitempty"`
	Handler   *Block            `json:"handler,omitempty"`
	Error     *Expression       `json:"error,omitempty"`
	Arms      []MatchArm        `json:"arms,omitempty"`
}
