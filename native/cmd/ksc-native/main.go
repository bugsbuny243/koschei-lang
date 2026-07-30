// ksc-native is the narrow bootstrap executable for the native Koschei frontend.
// Token JSON remains the default; --ast emits the versioned native syntax tree.
package main

import (
	"encoding/json"
	"errors"
	"flag"
	"fmt"
	"io"
	"os"

	"github.com/bugsbuny243/koschei-lang/native/lexer"
	nativeparser "github.com/bugsbuny243/koschei-lang/native/parser"
)

func main() {
	os.Exit(run(os.Args[1:], os.Stdin, os.Stdout, os.Stderr))
}

func run(args []string, stdin io.Reader, stdout, stderr io.Writer) int {
	flags := flag.NewFlagSet("ksc-native", flag.ContinueOnError)
	flags.SetOutput(stderr)
	comments := flags.Bool("comments", false, "preserve // comments in token mode")
	astMode := flags.Bool("ast", false, "emit koschei.syntax/v1 AST instead of tokens")
	maxBytes := flags.Int("max-source-bytes", lexer.DefaultMaxSourceBytes, "maximum UTF-8 source size")
	maxTokens := flags.Int("max-tokens", lexer.DefaultMaxTokens, "maximum emitted tokens including EOF")
	maxNodes := flags.Int("max-nodes", nativeparser.DefaultMaxNodes, "maximum AST nodes in --ast mode")
	maxDepth := flags.Int("max-depth", nativeparser.DefaultMaxDepth, "maximum syntax nesting depth in --ast mode")
	maxInterpolationBytes := flags.Int("max-interpolation-bytes", nativeparser.DefaultMaxInterpolationBytes, "maximum total bytes re-lexed inside interpolations")
	maxInterpolationTokens := flags.Int("max-interpolation-tokens", nativeparser.DefaultMaxInterpolationTokens, "maximum total tokens emitted inside interpolations")
	if err := flags.Parse(args); err != nil {
		return 2
	}
	if flags.NArg() > 1 {
		fmt.Fprintln(stderr, "usage: ksc-native [flags] [source.ks]")
		return 2
	}
	if *astMode && *comments {
		fmt.Fprintln(stderr, "KOSCHEI NATIVE ERROR: --comments is only valid in token mode")
		return 2
	}

	var reader io.Reader = stdin
	if flags.NArg() == 1 {
		file, err := os.Open(flags.Arg(0))
		if err != nil {
			fmt.Fprintln(stderr, "KOSCHEI NATIVE ERROR:", err)
			return 1
		}
		defer file.Close()
		reader = file
	}
	if *maxBytes < 1 || *maxTokens < 1 {
		fmt.Fprintln(stderr, "KOSCHEI NATIVE ERROR: lexer budgets must be positive")
		return 2
	}
	if *astMode && (*maxNodes < 1 || *maxDepth < 1 || *maxInterpolationBytes < 1 || *maxInterpolationTokens < 1) {
		fmt.Fprintln(stderr, "KOSCHEI NATIVE ERROR: parser budgets must be positive")
		return 2
	}
	data, err := io.ReadAll(io.LimitReader(reader, int64(*maxBytes)+1))
	if err != nil {
		fmt.Fprintln(stderr, "KOSCHEI NATIVE ERROR:", err)
		return 1
	}
	if len(data) > *maxBytes {
		fmt.Fprintf(stderr, "KOSCHEI NATIVE ERROR: source exceeds %d-byte budget\n", *maxBytes)
		return 1
	}
	tokens, err := lexer.Tokenize(string(data), lexer.Config{KeepComments: *comments, MaxSourceBytes: *maxBytes, MaxTokens: *maxTokens})
	if err != nil {
		return printFailure(stderr, err)
	}

	var payload any = tokens
	if *astMode {
		document, err := nativeparser.Parse(tokens, nativeparser.Config{
			MaxNodes:               *maxNodes,
			MaxDepth:               *maxDepth,
			MaxInterpolationBytes:  *maxInterpolationBytes,
			MaxInterpolationTokens: *maxInterpolationTokens,
		})
		if err != nil {
			return printFailure(stderr, err)
		}
		payload = document
	}

	encoder := json.NewEncoder(stdout)
	encoder.SetIndent("", "  ")
	if err := encoder.Encode(payload); err != nil {
		fmt.Fprintln(stderr, "KOSCHEI NATIVE ERROR:", err)
		return 1
	}
	return 0
}

func printFailure(stderr io.Writer, err error) int {
	var lexerFailure *lexer.Error
	if errors.As(err, &lexerFailure) {
		fmt.Fprintln(stderr, "KOSCHEI NATIVE ERROR:", lexerFailure)
		return 1
	}
	var parserFailure *nativeparser.Error
	if errors.As(err, &parserFailure) {
		fmt.Fprintln(stderr, "KOSCHEI NATIVE ERROR:", parserFailure)
		return 1
	}
	fmt.Fprintln(stderr, "KOSCHEI NATIVE ERROR:", err)
	return 1
}
