package parser

import (
	"encoding/json"
	"errors"
	"strings"
	"testing"

	"github.com/bugsbuny243/koschei-lang/native/lexer"
)

func token(kind lexer.Kind, value string, column int) lexer.Token {
	return lexer.Token{Kind: kind, Value: value, Lexeme: value, Line: 1, Column: column}
}

func TestProgramProducesVersionedASTAndPrecedence(t *testing.T) {
	tokens := []lexer.Token{
		token(lexer.FN, "fn", 1), token(lexer.IDENTIFIER, "main", 4), token(lexer.LEFTPAREN, "(", 8), token(lexer.RIGHTPAREN, ")", 9), token(lexer.LEFTBRACE, "{", 11),
		token(lexer.LET, "let", 13), token(lexer.IDENTIFIER, "x", 17), token(lexer.EQUAL, "=", 19), token(lexer.NUMBER, "1", 21), token(lexer.PLUS, "+", 23), token(lexer.NUMBER, "2", 25), token(lexer.STAR, "*", 27), token(lexer.NUMBER, "3", 29),
		token(lexer.RETURN, "return", 31), token(lexer.IDENTIFIER, "x", 38), token(lexer.RIGHTBRACE, "}", 40), token(lexer.EOF, "", 41),
	}
	document, err := Parse(tokens, Config{})
	if err != nil {
		t.Fatal(err)
	}
	if document.Schema != "koschei.syntax/v1" || document.Kind != "Program" {
		t.Fatalf("unexpected document header: %#v", document)
	}
	if len(document.Functions) != 1 || len(document.Functions[0].Body.Statements) != 2 {
		t.Fatalf("unexpected function tree: %#v", document.Functions)
	}
	value := document.Functions[0].Body.Statements[0].Value
	if value == nil || value.Kind != "BinaryExpression" || value.Operator != "+" {
		t.Fatalf("unexpected sum: %#v", value)
	}
	if value.Right == nil || value.Right.Kind != "BinaryExpression" || value.Right.Operator != "*" {
		t.Fatalf("factor precedence lost: %#v", value.Right)
	}
}

func TestGenericDeclarationsAndExactNumberJSON(t *testing.T) {
	tokens := []lexer.Token{
		token(lexer.STRUCT, "struct", 1), token(lexer.TYPE, "Box", 8), token(lexer.LESS, "<", 11), token(lexer.TYPE, "T", 12), token(lexer.GREATER, ">", 13), token(lexer.LEFTBRACE, "{", 15), token(lexer.IDENTIFIER, "value", 17), token(lexer.COLON, ":", 22), token(lexer.TYPE, "T", 24), token(lexer.RIGHTBRACE, "}", 26),
		token(lexer.FN, "fn", 28), token(lexer.IDENTIFIER, "main", 31), token(lexer.LEFTPAREN, "(", 35), token(lexer.RIGHTPAREN, ")", 36), token(lexer.LEFTBRACE, "{", 38), token(lexer.RETURN, "return", 40), token(lexer.NUMBER, "1.0000000000000001", 47), token(lexer.RIGHTBRACE, "}", 65), token(lexer.EOF, "", 66),
	}
	document, err := Parse(tokens, Config{})
	if err != nil {
		t.Fatal(err)
	}
	if len(document.Structs) != 1 || len(document.Structs[0].TypeParameters) != 1 {
		t.Fatalf("generic declaration missing: %#v", document.Structs)
	}
	encoded, err := json.Marshal(document)
	if err != nil {
		t.Fatal(err)
	}
	if !strings.Contains(string(encoded), `"text":"1.0000000000000001"`) {
		t.Fatalf("exact number text disappeared: %s", encoded)
	}
}

func TestNodeBudgetFailsClosed(t *testing.T) {
	tokens := []lexer.Token{token(lexer.FN, "fn", 1), token(lexer.IDENTIFIER, "main", 4), token(lexer.LEFTPAREN, "(", 8), token(lexer.RIGHTPAREN, ")", 9), token(lexer.LEFTBRACE, "{", 11), token(lexer.RIGHTBRACE, "}", 12), token(lexer.EOF, "", 13)}
	_, err := Parse(tokens, Config{MaxNodes: 1})
	if !errors.Is(err, ErrNodeBudget) {
		t.Fatalf("expected node budget failure, got %v", err)
	}
	var located *Error
	if !errors.As(err, &located) || located.Line != 1 {
		t.Fatalf("expected located parser failure, got %v", err)
	}
}

func TestDepthBudgetFailsClosed(t *testing.T) {
	tokens := []lexer.Token{
		token(lexer.FN, "fn", 1), token(lexer.IDENTIFIER, "main", 4), token(lexer.LEFTPAREN, "(", 8), token(lexer.RIGHTPAREN, ")", 9), token(lexer.LEFTBRACE, "{", 11),
		token(lexer.RETURN, "return", 13), token(lexer.LEFTBRACKET, "[", 20), token(lexer.LEFTBRACKET, "[", 21), token(lexer.NUMBER, "1", 22), token(lexer.RIGHTBRACKET, "]", 23), token(lexer.RIGHTBRACKET, "]", 24),
		token(lexer.RIGHTBRACE, "}", 26), token(lexer.EOF, "", 27),
	}
	_, err := Parse(tokens, Config{MaxDepth: 3})
	if !errors.Is(err, ErrDepthBudget) {
		t.Fatalf("expected depth budget failure, got %v", err)
	}
}

func TestRejectsCommentTokensAndMissingEOF(t *testing.T) {
	_, err := Parse([]lexer.Token{token(lexer.COMMENT, "// x", 1), token(lexer.EOF, "", 5)}, Config{})
	if !errors.Is(err, ErrTokenStream) {
		t.Fatalf("expected comment rejection, got %v", err)
	}
	_, err = Parse([]lexer.Token{token(lexer.FN, "fn", 1)}, Config{})
	if !errors.Is(err, ErrTokenStream) {
		t.Fatalf("expected EOF rejection, got %v", err)
	}
}
