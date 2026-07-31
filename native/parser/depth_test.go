package parser

import (
	"errors"
	"strings"
	"testing"

	"github.com/bugsbuny243/koschei-lang/native/lexer"
)

func TestIterativeExpressionChainsHonorDepthBudget(t *testing.T) {
	cases := map[string]string{
		"binary": "1" + strings.Repeat(" + 1", 64),
		"or":     "value" + strings.Repeat(" or value", 64),
		"call":   "value" + strings.Repeat("()", 64),
		"member": "value" + strings.Repeat(".field", 64),
	}

	for name, expression := range cases {
		t.Run(name, func(t *testing.T) {
			source := "fn main() { return " + expression + " }"
			_, err := ParseSource(source, lexer.Config{}, Config{
				MaxNodes:               10_000,
				MaxDepth:               16,
				MaxInterpolationBytes:  4_096,
				MaxInterpolationTokens: 2_048,
			})
			if !errors.Is(err, ErrDepthBudget) {
				t.Fatalf("expected depth budget failure, got %v", err)
			}
			var located *Error
			if !errors.As(err, &located) || located.Line != 1 || located.Column < 1 {
				t.Fatalf("expected located parser failure, got %v", err)
			}
		})
	}
}

func TestIterativeExpressionChainBelowBudgetStillParses(t *testing.T) {
	source := "fn main() { return 1" + strings.Repeat(" + 1", 6) + " }"
	if _, err := ParseSource(source, lexer.Config{}, Config{MaxDepth: 16}); err != nil {
		t.Fatalf("short chain rejected: %v", err)
	}
}

func TestActualDepthValidationIsNotRecursive(t *testing.T) {
	// This chain is deliberately much deeper than the configured limit. The
	// validator must reject it with an explicit stack rather than recursing over
	// the left-deep AST and risking a host stack overflow.
	source := "fn main() { return 1" + strings.Repeat(" + 1", 4_096) + " }"
	_, err := ParseSource(source, lexer.Config{MaxTokens: 20_000}, Config{
		MaxNodes:               20_000,
		MaxDepth:               32,
		MaxInterpolationBytes:  4_096,
		MaxInterpolationTokens: 2_048,
	})
	if !errors.Is(err, ErrDepthBudget) {
		t.Fatalf("expected depth budget failure, got %v", err)
	}
}
