package lexer

import (
	"encoding/json"
	"errors"
	"reflect"
	"strings"
	"testing"
)

func kinds(tokens []Token) []Kind {
	result := make([]Kind, len(tokens))
	for index, token := range tokens {
		result[index] = token.Kind
	}
	return result
}

func TestCoreTokenParity(t *testing.T) {
	source := `// guard
fn main(caps: SystemCaps) {
    let mut sayı = 42
    let ratio = 1.5
    if true && sayı >= 2 || false { println("ok") }
    for item in [1, 2] { println("item={item}") }
    match Some(sayı) { Some(value) => value, None => 0 }
}`
	tokens, err := Tokenize(source, Config{})
	if err != nil {
		t.Fatal(err)
	}
	wantPrefix := []Kind{FN, IDENTIFIER, LEFTPAREN, IDENTIFIER, COLON, TYPE, RIGHTPAREN, LEFTBRACE, LET, MUT, IDENTIFIER, EQUAL, NUMBER}
	if got := kinds(tokens[:len(wantPrefix)]); !reflect.DeepEqual(got, wantPrefix) {
		t.Fatalf("prefix mismatch\n got: %v\nwant: %v", got, wantPrefix)
	}
	if tokens[len(tokens)-1].Kind != EOF {
		t.Fatalf("missing EOF: %#v", tokens[len(tokens)-1])
	}
}

func TestCommentsAreExplicitlyOptIn(t *testing.T) {
	without, err := Tokenize("// hello\nlet x = 1", Config{})
	if err != nil {
		t.Fatal(err)
	}
	with, err := Tokenize("// hello\nlet x = 1", Config{KeepComments: true})
	if err != nil {
		t.Fatal(err)
	}
	if without[0].Kind != LET {
		t.Fatalf("comment leaked into compiler path: %#v", without[0])
	}
	if with[0].Kind != COMMENT || with[0].Value != "// hello" {
		t.Fatalf("comment not preserved: %#v", with[0])
	}
}

func TestInterpolationKeepsBalancedSource(t *testing.T) {
	tokens, err := Tokenize(`"hello {User { name: "A" }.name} / {items.get(0)}"`, Config{})
	if err != nil {
		t.Fatal(err)
	}
	if tokens[0].Kind != STRINGINTERP {
		t.Fatalf("got %s", tokens[0].Kind)
	}
	want := []Segment{
		{Kind: "text", Value: "hello "},
		{Kind: "expr", Value: `User { name: "A" }.name`},
		{Kind: "text", Value: " / "},
		{Kind: "expr", Value: "items.get(0)"},
	}
	if !reflect.DeepEqual(tokens[0].Segments, want) {
		t.Fatalf("segments mismatch\n got: %#v\nwant: %#v", tokens[0].Segments, want)
	}
}

func TestUnicodeColumnsCountCharactersNotBytes(t *testing.T) {
	tokens, err := Tokenize("let sayı = 1\nlet x = 2", Config{})
	if err != nil {
		t.Fatal(err)
	}
	if tokens[1].Column != 5 {
		t.Fatalf("unicode identifier column = %d", tokens[1].Column)
	}
	if tokens[4].Line != 2 || tokens[4].Column != 1 {
		t.Fatalf("second line location = %d:%d", tokens[4].Line, tokens[4].Column)
	}
}

func TestIdentifierContinuationMatchesPythonAlnum(t *testing.T) {
	tokens, err := Tokenize("let a² = 1\nlet aⅣ = 2\nlet a¼ = 3", Config{})
	if err != nil {
		t.Fatal(err)
	}
	want := []string{"a²", "aⅣ", "a¼"}
	for index, tokenIndex := range []int{1, 5, 9} {
		token := tokens[tokenIndex]
		if token.Kind != IDENTIFIER || token.Value != want[index] {
			t.Fatalf("token %d = %#v; want identifier %q", tokenIndex, token, want[index])
		}
	}
}

func TestExactLargeIntegerDoesNotOverflowLexer(t *testing.T) {
	raw := strings.Repeat("9", 200)
	tokens, err := Tokenize(raw, Config{})
	if err != nil {
		t.Fatal(err)
	}
	if tokens[0].Kind != NUMBER || tokens[0].Value != raw {
		t.Fatalf("number changed: %#v", tokens[0])
	}
}

func TestExactDecimalTextDoesNotLosePrecision(t *testing.T) {
	raw := "1.0000000000000001"
	tokens, err := Tokenize(raw, Config{})
	if err != nil {
		t.Fatal(err)
	}
	if tokens[0].Kind != NUMBER || tokens[0].Value != raw {
		t.Fatalf("decimal changed: %#v", tokens[0])
	}
}

func TestEmptyStringJSONPreservesValue(t *testing.T) {
	tokens, err := Tokenize(`""`, Config{})
	if err != nil {
		t.Fatal(err)
	}
	encoded, err := json.Marshal(tokens[0])
	if err != nil {
		t.Fatal(err)
	}
	if !strings.Contains(string(encoded), `"value":""`) {
		t.Fatalf("empty string value disappeared from JSON: %s", encoded)
	}
}

func TestInterpolationUsesPythonWhitespace(t *testing.T) {
	_, err := Tokenize("\"{\x1c}\"", Config{})
	if err == nil {
		t.Fatal("expected Python-empty interpolation to be rejected")
	}
	var located *Error
	if !errors.As(err, &located) || located.Line != 1 || located.Column != 1 {
		t.Fatalf("expected located failure at 1:1, got %v", err)
	}
}

func TestFailClosedBudgets(t *testing.T) {
	_, err := Tokenize("let value = 1", Config{MaxSourceBytes: 4})
	if !errors.Is(err, ErrSourceTooLarge) {
		t.Fatalf("source budget error = %v", err)
	}
	_, err = Tokenize("let value = 1", Config{MaxTokens: 2})
	if !errors.Is(err, ErrTokenBudget) {
		t.Fatalf("token budget error = %v", err)
	}
}

func TestDeterministicOutput(t *testing.T) {
	source := `fn main() { println("value={1 + 2}") }`
	first, err := Tokenize(source, Config{})
	if err != nil {
		t.Fatal(err)
	}
	second, err := Tokenize(source, Config{})
	if err != nil {
		t.Fatal(err)
	}
	if !reflect.DeepEqual(first, second) {
		t.Fatal("same source produced different token streams")
	}
}

func TestMalformedInputsFail(t *testing.T) {
	cases := []string{"&", "|", `"unterminated`, `"{}"`, `"bad \q"`, `"bad }"`, `"{value"`}
	for _, source := range cases {
		t.Run(source, func(t *testing.T) {
			if _, err := Tokenize(source, Config{}); err == nil {
				t.Fatalf("expected failure for %q", source)
			}
		})
	}
}

func FuzzLexerNeverPanics(f *testing.F) {
	for _, seed := range []string{"", "fn main() {}", `"{Map { a: 1 }}"`, "// x\nlet y = 3", "\xff", "let a² = 1", "\"{\x1c}\""} {
		f.Add(seed)
	}
	f.Fuzz(func(t *testing.T, source string) {
		if len(source) > 16_384 {
			t.Skip()
		}
		_, _ = Tokenize(source, Config{MaxSourceBytes: 16_384, MaxTokens: 8_192})
	})
}
