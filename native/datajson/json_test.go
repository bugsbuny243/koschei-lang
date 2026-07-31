package datajson

import (
	"encoding/json"
	"os"
	"path/filepath"
	"testing"
)

type sharedCases struct {
	Canonical []struct {
		Source  string `json:"source"`
		Encoded string `json:"encoded"`
	} `json:"canonical"`
	Errors []struct {
		Source string `json:"source"`
		Code   string `json:"code"`
	} `json:"errors"`
}

func loadCases(t *testing.T) sharedCases {
	t.Helper()
	path := filepath.Join("..", "..", "spec", "data-json-v1-cases.json")
	content, err := os.ReadFile(path)
	if err != nil {
		t.Fatal(err)
	}
	var cases sharedCases
	if err := json.Unmarshal(content, &cases); err != nil {
		t.Fatal(err)
	}
	return cases
}

func TestSharedCanonicalCases(t *testing.T) {
	for _, test := range loadCases(t).Canonical {
		value, err := Decode(test.Source, DefaultLimits)
		if err != nil {
			t.Fatalf("Decode(%q): %v", test.Source, err)
		}
		encoded, err := Encode(value, DefaultLimits)
		if err != nil {
			t.Fatalf("Encode(%q): %v", test.Source, err)
		}
		if encoded != test.Encoded {
			t.Fatalf("Encode(Decode(%q)) = %q, want %q", test.Source, encoded, test.Encoded)
		}
	}
}

func TestSharedErrorCases(t *testing.T) {
	for _, test := range loadCases(t).Errors {
		_, err := Decode(test.Source, DefaultLimits)
		dataErr, ok := err.(*Error)
		if !ok || dataErr.Code != test.Code {
			t.Fatalf("Decode(%q) error = %#v, want code %s", test.Source, err, test.Code)
		}
	}
}

func TestInputDepthNodeAndOutputBudgets(t *testing.T) {
	limits := DefaultLimits
	limits.MaxInputBytes = 3
	if _, err := Decode("\"é\"", limits); err == nil || err.(*Error).Code != "KS3601" {
		t.Fatalf("input limit error = %#v", err)
	}
	limits = DefaultLimits
	limits.MaxDepth = 3
	if _, err := Decode("[[[0]]]", limits); err == nil || err.(*Error).Code != "KS3602" {
		t.Fatalf("depth limit error = %#v", err)
	}
	limits = DefaultLimits
	limits.MaxNodes = 3
	if _, err := Decode("[0,1,2]", limits); err == nil || err.(*Error).Code != "KS3603" {
		t.Fatalf("node limit error = %#v", err)
	}
	limits = DefaultLimits
	limits.MaxOutputBytes = 8
	if _, err := Encode(map[string]any{"x": "12345"}, limits); err == nil || err.(*Error).Code != "KS3607" {
		t.Fatalf("output limit error = %#v", err)
	}
}

func TestHostNumbersAndArbitraryValuesAreRejected(t *testing.T) {
	for _, value := range []any{int64(1), 1.5, struct{}{}, []string{"x"}} {
		if _, err := Encode(value, DefaultLimits); err == nil || err.(*Error).Code != "KS3608" {
			t.Fatalf("Encode(%T) error = %#v", value, err)
		}
	}
	encoded, err := Encode(Number("42"), DefaultLimits)
	if err != nil || encoded != "42" {
		t.Fatalf("Encode(Number(42)) = %q, %v", encoded, err)
	}
}

func TestErrorOffsetsAreUTF8ByteOffsets(t *testing.T) {
	_, err := Decode("[\"😀\",]", DefaultLimits)
	dataErr, ok := err.(*Error)
	if !ok || dataErr.Offset != 8 {
		t.Fatalf("error = %#v, want byte offset 8", err)
	}
}
