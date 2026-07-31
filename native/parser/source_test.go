package parser

import (
	"errors"
	"testing"

	"github.com/bugsbuny243/koschei-lang/native/lexer"
)

func TestParseSourceCoversV5DeclarationAndExpressionSlice(t *testing.T) {
	source := `import risk
struct Box<T> { value: T }
enum Outcome<T> { Ok(T), Err(Error), }
fn count<T>(items: List<T>) -> Int {
    let mut total = 0
    for item in items {
        total = total + 1
    }
    if total > 0 && true {
        println("count={items.length()}")
    } else {
        return 0
    }
    return total
}`
	document, err := ParseSource(source, lexer.Config{}, Config{})
	if err != nil {
		t.Fatal(err)
	}
	if document.Schema != "koschei.syntax/v1" {
		t.Fatalf("schema=%q", document.Schema)
	}
	if len(document.Imports) != 1 || len(document.Structs) != 1 || len(document.Enums) != 1 || len(document.Functions) != 1 {
		t.Fatalf("unexpected declarations: %#v", document)
	}
	if got := document.Functions[0].TypeParameters; len(got) != 1 || got[0].Name != "T" {
		t.Fatalf("generic function parameters=%#v", got)
	}
	statements := document.Functions[0].Body.Statements
	if len(statements) != 4 || statements[1].Kind != "ForStatement" || statements[2].Kind != "IfStatement" {
		t.Fatalf("unexpected function statements: %#v", statements)
	}
}

func TestParseSourcePreservesEmptyAndPreciseLiterals(t *testing.T) {
	source := `fn main() {
    let empty = ""
    let precise = 1.0000000000000001
}`
	document, err := ParseSource(source, lexer.Config{}, Config{})
	if err != nil {
		t.Fatal(err)
	}
	statements := document.Functions[0].Body.Statements
	empty := statements[0].Value
	if empty == nil || empty.Literal == nil || empty.Literal.Text == nil || *empty.Literal.Text != "" {
		t.Fatalf("empty string disappeared: %#v", empty)
	}
	precise := statements[1].Value
	if precise == nil || precise.Literal == nil || precise.Literal.Text == nil || *precise.Literal.Text != "1.0000000000000001" {
		t.Fatalf("number text changed: %#v", precise)
	}
}

func TestParseSourceBudgetsFailClosed(t *testing.T) {
	_, err := ParseSource("fn main() {}", lexer.Config{}, Config{MaxNodes: 1})
	if !errors.Is(err, ErrNodeBudget) {
		t.Fatalf("node budget error=%v", err)
	}
	_, err = ParseSource("fn main() { return [[1]] }", lexer.Config{}, Config{MaxDepth: 3})
	if !errors.Is(err, ErrDepthBudget) {
		t.Fatalf("depth budget error=%v", err)
	}
}

func FuzzParseSourceNeverPanics(f *testing.F) {
	for _, seed := range []string{
		"",
		"fn main() {}",
		"fn main() { return [1, 2, 3] }",
		"struct Box<T> { value: T }",
		"fn main() { println(\"x={1 + 2}\") }",
	} {
		f.Add(seed)
	}
	f.Fuzz(func(t *testing.T, source string) {
		if len(source) > 16_384 {
			t.Skip()
		}
		_, _ = ParseSource(
			source,
			lexer.Config{MaxSourceBytes: 16_384, MaxTokens: 8_192},
			Config{MaxNodes: 8_192, MaxDepth: 128, MaxInterpolationBytes: 4_096, MaxInterpolationTokens: 2_048},
		)
	})
}
