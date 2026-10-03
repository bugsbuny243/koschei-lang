package lexer

// High-assurance declaration prefixes are kept in a small extension file so the
// native bootstrap lexer stays mechanically aligned with the Python language
// oracle without rewriting the core scanner.
const (
	PURE     Kind = "PURE"
	STATEFUL Kind = "STATEFUL"
	KA       Kind = "KA"
	VOR      Kind = "VOR"
	SHI      Kind = "SHI"
	THAL     Kind = "THAL"
	NUR      Kind = "NUR"
)

func init() {
	keywords["pure"] = PURE
	keywords["stateful"] = STATEFUL
	keywords["ka"] = KA
	keywords["vor"] = VOR
	keywords["shi"] = SHI
	keywords["thal"] = THAL
	keywords["nur"] = NUR
}
