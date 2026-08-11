package lexer

// High-assurance declaration prefixes are kept in a small extension file so the
// native bootstrap lexer stays mechanically aligned with the Python language
// oracle without rewriting the core scanner.
const (
	PURE     Kind = "PURE"
	STATEFUL Kind = "STATEFUL"
)

func init() {
	keywords["pure"] = PURE
	keywords["stateful"] = STATEFUL
}
