package main

import (
	"bytes"
	"strings"
	"testing"
)

func TestCLIASTRejectsDeepIterativeChainBeforeJSONEncoding(t *testing.T) {
	source := "fn main() { return 1" + strings.Repeat(" + 1", 4_096) + " }"
	var stdout, stderr bytes.Buffer
	code := run(
		[]string{"--ast", "--max-depth", "32", "--max-tokens", "20000", "--max-nodes", "20000"},
		strings.NewReader(source),
		&stdout,
		&stderr,
	)
	if code != 1 {
		t.Fatalf("code=%d stderr=%s", code, stderr.String())
	}
	if stdout.Len() != 0 {
		t.Fatalf("partial AST escaped before depth rejection: %s", stdout.String())
	}
	if !strings.Contains(stderr.String(), "parser depth budget exhausted") || !strings.Contains(stderr.String(), "[line ") {
		t.Fatalf("unexpected stderr: %s", stderr.String())
	}
}
