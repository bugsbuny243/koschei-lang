from __future__ import annotations

import io
import pathlib
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout

from koschei.formatter import check_source, format_source
from koschei.cli import main
from koschei.lexer import TokenType, tokenize

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
EXAMPLES = sorted((REPO_ROOT / "examples").glob("*.ks"))

MESSY = '''// Koschei örneği
fn   load_config( disk:DiskReadCaps , path:String )->String or Error{
let content=disk.read(path)or return Error("Config okunamadı: {path}")
        return content
}


fn main(caps:SystemCaps){
let cfg_read=caps.disk.allow_read_only("/etc/app/")
let mut attempts=0
while attempts<3{
attempts=attempts+1   // sayaç
}
if attempts==3&&true{
println("tamam: {attempts}")
}else{
println("olmadı")
}
let score=(2+3)*4- -1
}
'''


def token_stream(source: str) -> list[tuple[TokenType, object]]:
    """Yorumlar hariç token akışı — biçimlendirmenin anlamı bozmadığının ölçüsü."""
    return [(token.type, token.value) for token in tokenize(source)]


class FormatterInvariantTests(unittest.TestCase):
    """Biçimlendiricinin ihlal edemeyeceği iki kural."""

    def assert_invariants(self, source: str) -> str:
        formatted = format_source(source)
        self.assertEqual(
            formatted,
            format_source(formatted),
            "değişmezlik ihlali: format(format(x)) != format(x)",
        )
        self.assertEqual(
            token_stream(source),
            token_stream(formatted),
            "anlam ihlali: biçimlendirme token akışını değiştirdi",
        )
        return formatted

    def test_invariants_hold_for_every_example(self) -> None:
        for path in EXAMPLES:
            with self.subTest(example=path.name):
                self.assert_invariants(path.read_text(encoding="utf-8"))

    def test_invariants_hold_for_messy_source(self) -> None:
        self.assert_invariants(MESSY)

    def test_escapes_and_interpolation_survive(self) -> None:
        source = (
            'fn main(user: String) { '
            r'let s = "json: \{a\} satır\nsonu \"tırnak\"" '
            'println("selam {user}") '
            "}"
        )
        self.assert_invariants(source)

    def test_expression_interpolation_survives_formatting(self) -> None:
        source = (
            'fn main() { let items = [1, 2] '
            'println("n={items.length()} toplam={1 + 2}") }'
        )
        formatted = self.assert_invariants(source)
        self.assertIn('{items.length()}', formatted)
        self.assertIn('{1 + 2}', formatted)

    def test_floats_and_unary_minus_survive(self) -> None:
        self.assert_invariants("fn main() { let pi = 3.14 let z = (2 + 3) * 4 - -1 }")


class FormatterOutputTests(unittest.TestCase):
    def test_indentation_and_spacing_are_canonical(self) -> None:
        formatted = format_source(MESSY)
        self.assertIn(
            "fn load_config(disk: DiskReadCaps, path: String) -> String or Error {",
            formatted,
        )
        self.assertIn("    let content = disk.read(path)", formatted)
        self.assertIn("        attempts = attempts + 1", formatted)
        self.assertIn("    } else {", formatted)

    def test_comments_are_preserved(self) -> None:
        source = (
            "// başlık\n"
            "fn main() {\n"
            "    // iç yorum\n"
            "    let x = 1 // satır sonu\n"
            "}\n"
            "// son\n"
        )
        formatted = format_source(source)
        for comment in ("// başlık", "// iç yorum", "// satır sonu", "// son"):
            self.assertIn(comment, formatted)

    def test_repeated_blank_lines_collapse_to_one(self) -> None:
        formatted = format_source(
            "fn main() {\n\n\n\n    let x = 1\n\n\n\n    let y = 2\n\n\n}\n"
        )
        self.assertNotIn("\n\n\n", formatted)

    def test_file_ends_with_single_newline(self) -> None:
        formatted = format_source("fn main() { let x = 1 }")
        self.assertTrue(formatted.endswith("}\n"))
        self.assertFalse(formatted.endswith("\n\n"))

    def test_examples_are_already_canonical(self) -> None:
        # Depodaki örnekler kanonik biçimde tutulur; CI de bunu doğrular.
        for path in EXAMPLES:
            with self.subTest(example=path.name):
                self.assertTrue(
                    check_source(path.read_text(encoding="utf-8")),
                    f"{path.name} kanonik biçimde değil",
                )


class LexerCommentTokenTests(unittest.TestCase):
    def test_comments_are_skipped_by_default(self) -> None:
        tokens = tokenize("// gizli\nlet x = 1")
        self.assertFalse(any(t.type is TokenType.COMMENT for t in tokens))

    def test_comments_are_kept_when_requested(self) -> None:
        tokens = tokenize("// gizli\nlet x = 1 // son", keep_comments=True)
        comments = [t.value for t in tokens if t.type is TokenType.COMMENT]
        self.assertEqual(comments, ["// gizli", "// son"])


class FmtCommandTests(unittest.TestCase):
    def run_cli(self, argv: list[str]) -> tuple[int, str, str]:
        output = io.StringIO()
        error = io.StringIO()
        with redirect_stdout(output), redirect_stderr(error):
            exit_code = main(argv)
        return exit_code, output.getvalue(), error.getvalue()

    def temp_source(self, content: str) -> pathlib.Path:
        handle = tempfile.NamedTemporaryFile(
            "w", suffix=".ks", delete=False, encoding="utf-8"
        )
        handle.write(content)
        handle.close()
        path = pathlib.Path(handle.name)
        self.addCleanup(path.unlink, missing_ok=True)
        return path

    def test_fmt_prints_formatted_source(self) -> None:
        path = self.temp_source("fn main(){let x=1}")
        code, output, _ = self.run_cli(["fmt", str(path)])
        self.assertEqual(code, 0)
        self.assertIn("    let x = 1", output)
        # varsayılan olarak dosya değişmez
        self.assertEqual(path.read_text(encoding="utf-8"), "fn main(){let x=1}")

    def test_check_fails_on_unformatted_source(self) -> None:
        path = self.temp_source("fn main(){let x=1}")
        code, _, error = self.run_cli(["fmt", "--check", str(path)])
        self.assertEqual(code, 1)
        self.assertIn("is not canonical", error)

    def test_check_passes_on_formatted_source(self) -> None:
        path = self.temp_source(format_source("fn main(){let x=1}"))
        code, _, _ = self.run_cli(["fmt", "--check", str(path)])
        self.assertEqual(code, 0)

    def test_write_updates_file_in_place(self) -> None:
        path = self.temp_source("fn main(){let x=1}")
        code, _, _ = self.run_cli(["fmt", "--write", str(path)])
        self.assertEqual(code, 0)
        self.assertEqual(path.read_text(encoding="utf-8"), "fn main() {\n    let x = 1\n}\n")

    def test_write_is_idempotent(self) -> None:
        path = self.temp_source("fn main(){let x=1}")
        self.run_cli(["fmt", "--write", str(path)])
        first = path.read_text(encoding="utf-8")
        self.run_cli(["fmt", "--write", str(path)])
        self.assertEqual(path.read_text(encoding="utf-8"), first)


if __name__ == "__main__":
    unittest.main()
