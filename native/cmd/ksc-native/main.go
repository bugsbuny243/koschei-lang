// ksc-native is a narrow bootstrap executable for the native Koschei frontend.
// It only tokenizes source today; it is not yet the default compiler.
package main

import (
	"encoding/json"
	"errors"
	"flag"
	"fmt"
	"io"
	"os"

	"github.com/bugsbuny243/koschei-lang/native/lexer"
)

func main() {
	os.Exit(run(os.Args[1:], os.Stdin, os.Stdout, os.Stderr))
}

func run(args []string, stdin io.Reader, stdout, stderr io.Writer) int {
	flags := flag.NewFlagSet("ksc-native", flag.ContinueOnError)
	flags.SetOutput(stderr)
	comments := flags.Bool("comments", false, "preserve // comments")
	maxBytes := flags.Int("max-source-bytes", lexer.DefaultMaxSourceBytes, "maximum UTF-8 source size")
	maxTokens := flags.Int("max-tokens", lexer.DefaultMaxTokens, "maximum emitted tokens including EOF")
	if err := flags.Parse(args); err != nil {
		return 2
	}
	if flags.NArg() > 1 {
		fmt.Fprintln(stderr, "usage: ksc-native [flags] [source.ks]")
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
		fmt.Fprintln(stderr, "KOSCHEI NATIVE ERROR: budgets must be positive")
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
		var located *lexer.Error
		if errors.As(err, &located) {
			fmt.Fprintln(stderr, "KOSCHEI NATIVE ERROR:", located)
			return 1
		}
		fmt.Fprintln(stderr, "KOSCHEI NATIVE ERROR:", err)
		return 1
	}
	encoder := json.NewEncoder(stdout)
	encoder.SetIndent("", "  ")
	if err := encoder.Encode(tokens); err != nil {
		fmt.Fprintln(stderr, "KOSCHEI NATIVE ERROR:", err)
		return 1
	}
	return 0
}
