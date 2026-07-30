// Package parser implements the bounded native Koschei recursive-descent parser.
package parser

import (
	"errors"
	"fmt"

	"github.com/bugsbuny243/koschei-lang/native/lexer"
	"github.com/bugsbuny243/koschei-lang/native/syntax"
)

const (
	DefaultMaxNodes               = 250_000
	DefaultMaxDepth               = 256
	DefaultMaxInterpolationBytes  = 64 << 10
	DefaultMaxInterpolationTokens = 32_768
)

var (
	ErrNodeBudget  = errors.New("parser node budget exhausted")
	ErrDepthBudget = errors.New("parser depth budget exhausted")
	ErrTokenStream = errors.New("invalid parser token stream")
	ErrConfig      = errors.New("invalid parser configuration")
)

type Config struct {
	MaxNodes               int
	MaxDepth               int
	MaxInterpolationBytes  int
	MaxInterpolationTokens int
}

func (config Config) normalized() Config {
	if config.MaxNodes == 0 {
		config.MaxNodes = DefaultMaxNodes
	}
	if config.MaxDepth == 0 {
		config.MaxDepth = DefaultMaxDepth
	}
	if config.MaxInterpolationBytes == 0 {
		config.MaxInterpolationBytes = DefaultMaxInterpolationBytes
	}
	if config.MaxInterpolationTokens == 0 {
		config.MaxInterpolationTokens = DefaultMaxInterpolationTokens
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

type budget struct {
	config              Config
	nodes               int
	interpolationBytes  int
	interpolationTokens int
}

type Parser struct {
	tokens  []lexer.Token
	current int
	budget  *budget
}

func ParseSource(source string, lexerConfig lexer.Config, config Config) (syntax.Document, error) {
	if lexerConfig.KeepComments {
		return syntax.Document{}, &Error{Line: 1, Column: 1, Message: "native parser does not accept comment tokens", Cause: ErrTokenStream}
	}
	tokens, err := lexer.Tokenize(source, lexerConfig)
	if err != nil {
		return syntax.Document{}, err
	}
	return Parse(tokens, config)
}

func Parse(tokens []lexer.Token, config Config) (syntax.Document, error) {
	config = config.normalized()
	if config.MaxNodes < 1 || config.MaxDepth < 1 || config.MaxInterpolationBytes < 1 || config.MaxInterpolationTokens < 1 {
		return syntax.Document{}, &Error{Line: 1, Column: 1, Message: "parser budgets must be positive", Cause: ErrConfig}
	}
	if len(tokens) == 0 {
		return syntax.Document{}, &Error{Line: 1, Column: 1, Message: "token stream is empty", Cause: ErrTokenStream}
	}
	if tokens[len(tokens)-1].Kind != lexer.EOF {
		last := tokens[len(tokens)-1]
		return syntax.Document{}, &Error{Line: last.Line, Column: last.Column, Message: "token stream must end with EOF", Cause: ErrTokenStream}
	}
	for index, token := range tokens {
		if token.Kind == lexer.COMMENT {
			return syntax.Document{}, &Error{Line: token.Line, Column: token.Column, Message: "comment token reached parser", Cause: ErrTokenStream}
		}
		if token.Kind == lexer.EOF && index != len(tokens)-1 {
			return syntax.Document{}, &Error{Line: token.Line, Column: token.Column, Message: "EOF token appears before end of stream", Cause: ErrTokenStream}
		}
	}
	machine := &Parser{tokens: tokens, budget: &budget{config: config}}
	return machine.program()
}

func (parser *Parser) program() (syntax.Document, error) {
	document := syntax.NewDocument()
	if err := parser.claim(parser.peek()); err != nil {
		return syntax.Document{}, err
	}
	for !parser.atEnd() {
		switch parser.peek().Kind {
		case lexer.IMPORT:
			declaration, err := parser.importDeclaration()
			if err != nil {
				return syntax.Document{}, err
			}
			document.Imports = append(document.Imports, declaration)
		case lexer.STRUCT:
			declaration, err := parser.structDeclaration(1)
			if err != nil {
				return syntax.Document{}, err
			}
			document.Structs = append(document.Structs, declaration)
		case lexer.ENUM:
			declaration, err := parser.enumDeclaration(1)
			if err != nil {
				return syntax.Document{}, err
			}
			document.Enums = append(document.Enums, declaration)
		default:
			declaration, err := parser.functionDeclaration(1)
			if err != nil {
				return syntax.Document{}, err
			}
			document.Functions = append(document.Functions, declaration)
		}
	}
	return document, nil
}
