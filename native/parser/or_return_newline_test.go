package parser

import (
	"testing"

	"github.com/bugsbuny243/koschei-lang/native/lexer"
)

func TestBareOrReturnStopsAtNewlineBeforeAssignment(t *testing.T) {
	source := `fn fallible() -> Int or Error { return 1 }
fn main() {
    let mut value = 0
    value = fallible() or return
    value = fallible() or return
    println(value)
}
`
	if _, err := ParseSource(source, lexer.Config{}, Config{}); err != nil {
		t.Fatalf("bare or-return must not consume the next-line assignment: %v", err)
	}
}

func TestOrReturnExplicitSameLineErrorStillParses(t *testing.T) {
	source := `fn fallible() -> Int or Error { return 1 }
fn main() {
    let value = fallible() or return Error("failed")
    println(value)
}
`
	if _, err := ParseSource(source, lexer.Config{}, Config{}); err != nil {
		t.Fatalf("same-line explicit or-return error must remain valid: %v", err)
	}
}
