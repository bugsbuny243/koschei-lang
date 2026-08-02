package parser

import (
	"fmt"

	"github.com/bugsbuny243/koschei-lang/native/lexer"
	"github.com/bugsbuny243/koschei-lang/native/syntax"
)

func (parser *Parser) claim(token lexer.Token) error {
	if parser.budget.nodes >= parser.budget.config.MaxNodes {
		return parser.failure(token, fmt.Sprintf("parser node budget exhausted at %d nodes", parser.budget.config.MaxNodes), ErrNodeBudget)
	}
	parser.budget.nodes++
	return nil
}

func (parser *Parser) ensureDepth(depth int, token lexer.Token) error {
	if depth > parser.budget.config.MaxDepth {
		return parser.failure(token, fmt.Sprintf("parser depth budget exhausted at depth %d", parser.budget.config.MaxDepth), ErrDepthBudget)
	}
	return nil
}

func (parser *Parser) match(kinds ...lexer.Kind) bool {
	for _, kind := range kinds {
		if parser.check(kind) {
			parser.advance()
			return true
		}
	}
	return false
}

func (parser *Parser) consume(kind lexer.Kind, message string) (lexer.Token, error) {
	if parser.check(kind) {
		return parser.advance(), nil
	}
	return lexer.Token{}, parser.failure(parser.peek(), message, nil)
}

func (parser *Parser) check(kind lexer.Kind) bool {
	if parser.atEnd() {
		return kind == lexer.EOF
	}
	return parser.peek().Kind == kind
}

func (parser *Parser) advance() lexer.Token {
	if !parser.atEnd() {
		parser.current++
	}
	return parser.previous()
}

func (parser *Parser) atEnd() bool           { return parser.peek().Kind == lexer.EOF }
func (parser *Parser) peek() lexer.Token     { return parser.tokens[parser.current] }
func (parser *Parser) previous() lexer.Token { return parser.tokens[parser.current-1] }

func (parser *Parser) failure(token lexer.Token, message string, cause error) error {
	return &Error{Line: token.Line, Column: token.Column, Message: message, Cause: cause}
}

func location(token lexer.Token) syntax.Location {
	return syntax.Location{Line: token.Line, Column: token.Column}
}

func boolPointer(value bool) *bool       { return &value }
func stringPointer(value string) *string { return &value }

func orReturnStop(kind lexer.Kind) bool {
	switch kind {
	case lexer.RIGHTBRACE, lexer.SEMICOLON, lexer.LET, lexer.RETURN, lexer.IF,
		lexer.WHILE, lexer.FOR, lexer.BREAK, lexer.CONTINUE, lexer.FN, lexer.STRUCT,
		lexer.ENUM, lexer.IMPORT, lexer.EOF:
		return true
	default:
		return false
	}
}

func operatorText(token lexer.Token) string {
	if token.Value != "" {
		return token.Value
	}
	switch token.Kind {
	case lexer.PIPEPIPE:
		return "||"
	case lexer.AMPAMP:
		return "&&"
	case lexer.EQUALEQUAL:
		return "=="
	case lexer.BANGEQUAL:
		return "!="
	case lexer.LESSEQUAL:
		return "<="
	case lexer.GREATEREQUAL:
		return ">="
	case lexer.LESS:
		return "<"
	case lexer.GREATER:
		return ">"
	case lexer.PLUS:
		return "+"
	case lexer.MINUS:
		return "-"
	case lexer.STAR:
		return "*"
	case lexer.SLASH:
		return "/"
	case lexer.PERCENT:
		return "%"
	case lexer.BANG:
		return "!"
	default:
		return string(token.Kind)
	}
}

func tokenForExpression(expression syntax.Expression) lexer.Token {
	return lexer.Token{Line: expression.Location.Line, Column: expression.Location.Column}
}
