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

func TestCLIRejectsOversizedInputBeforeLexing(t *testing.T) {
	var stdout, stderr bytes.Buffer
	code := run([]string{"-max-source-bytes", "4"}, strings.NewReader("fn main() {}"), &stdout, &stderr)
	if code != 1 || !strings.Contains(stderr.String(), "exceeds 4-byte budget") {
		t.Fatalf("code=%d stderr=%s", code, stderr.String())
	}
}
