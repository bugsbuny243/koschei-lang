package main

import (
	"bytes"
	"strings"
	"testing"
)

func TestCLIFromStdin(t *testing.T) {
	var stdout, stderr bytes.Buffer
	code := run(nil, strings.NewReader("fn main() {}"), &stdout, &stderr)
	if code != 0 {
		t.Fatalf("code=%d stderr=%s", code, stderr.String())
	}
	if !strings.Contains(stdout.String(), `"kind": "FN"`) || !strings.Contains(stdout.String(), `"kind": "EOF"`) {
		t.Fatalf("unexpected JSON: %s", stdout.String())
	}
}

func TestCLIIncludesEmptyStringValue(t *testing.T) {
	var stdout, stderr bytes.Buffer
	code := run(nil, strings.NewReader(`""`), &stdout, &stderr)
	if code != 0 {
		t.Fatalf("code=%d stderr=%s", code, stderr.String())
	}
	if !strings.Contains(stdout.String(), `"kind": "STRING"`) || !strings.Contains(stdout.String(), `"value": ""`) {
		t.Fatalf("empty string value missing from JSON: %s", stdout.String())
	}
}

func TestCLIASTFromStdin(t *testing.T) {
	var stdout, stderr bytes.Buffer
	source := `fn main() { let empty = "" let precise = 1.0000000000000001 }`
	code := run([]string{"--ast"}, strings.NewReader(source), &stdout, &stderr)
	if code != 0 {
		t.Fatalf("code=%d stderr=%s", code, stderr.String())
	}
	output := stdout.String()
	for _, expected := range []string{
		`"schema": "koschei.syntax/v1"`,
		`"kind": "Program"`,
		`"text": ""`,
		`"text": "1.0000000000000001"`,
	} {
		if !strings.Contains(output, expected) {
			t.Fatalf("missing %s in AST JSON: %s", expected, output)
		}
	}
}

func TestCLIASTBudgetsFailClosed(t *testing.T) {
	var stdout, stderr bytes.Buffer
	code := run([]string{"--ast", "--max-nodes", "1"}, strings.NewReader("fn main() {}"), &stdout, &stderr)
	if code != 1 || !strings.Contains(stderr.String(), "node budget exhausted") || !strings.Contains(stderr.String(), "[line ") {
		t.Fatalf("code=%d stderr=%s", code, stderr.String())
	}
}

func TestCLIASTRejectsCommentsMode(t *testing.T) {
	var stdout, stderr bytes.Buffer
	code := run([]string{"--ast", "--comments"}, strings.NewReader("fn main() {}"), &stdout, &stderr)
	if code != 2 || !strings.Contains(stderr.String(), "--comments is only valid in token mode") {
		t.Fatalf("code=%d stderr=%s", code, stderr.String())
	}
}

func TestCLIRejectsOversizedInputBeforeLexing(t *testing.T) {
	var stdout, stderr bytes.Buffer
	code := run([]string{"-max-source-bytes", "4"}, strings.NewReader("fn main() {}"), &stdout, &stderr)
	if code != 1 || !strings.Contains(stderr.String(), "exceeds 4-byte budget") {
		t.Fatalf("code=%d stderr=%s", code, stderr.String())
	}
}
