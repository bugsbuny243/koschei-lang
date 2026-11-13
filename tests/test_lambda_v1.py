"""Lambdas: anonymous functions lifted to top-level functions, no captures."""
from __future__ import annotations

from contextlib import redirect_stderr, redirect_stdout
import io
from pathlib import Path
import tempfile
import unittest

from koschei.cli_entry import main as cli_main


class LambdaTests(unittest.TestCase):
    def cli(self, source: str, command: str = "run") -> tuple[int, str]:
        with tempfile.TemporaryDirectory(prefix="koschei-lambda-") as directory:
            path = Path(directory) / "main.ks"
            path.write_text(source, encoding="utf-8")
            stdout = io.StringIO()
            with redirect_stdout(stdout), redirect_stderr(stdout):
                code = cli_main([command, str(path)])
        return code, stdout.getvalue()

    def test_lambdas_go_where_function_names_go(self) -> None:
        code, out = self.cli("""import text

fn main() {
    let xs = [3, -1, 2]
    println(xs.filter(fn(x: Int) -> Bool { return x > 0 }) or [])
    println(xs.map(fn(x: Int) -> String { return "n{x}" }) or [])
    println(xs.any(fn(x: Int) -> Bool { return x > 2 }) or false)
    println(xs.partition(fn(x: Int) -> Bool { return x % 2 == 0 }) or [])
    println(xs.scan(0, fn(total: Int, x: Int) -> Int { return total + x }) or [])
    let square = fn(x: Int) -> Int { return x * x }
    println(square(9))
    let upper = fn(word: String) -> Bool { return text.starts_with(word, "K") }
    println(upper("Koschei"))
    println(xs.filter(fn(x: Int) -> Bool {
        let doubled = [x].map(fn(y: Int) -> Int { return y * 2 }) or []
        return doubled.length() == 1 && x < 3
    }) or [])
}
""")
        self.assertEqual(code, 0, out)
        self.assertEqual(
            out.splitlines(),
            ["[3, 2]", '["n3", "n-1", "n2"]', "true", "[[2], [3, -1]]", "[3, 2, 4]", "81", "true", "[-1, 2]"],
        )

    def test_a_lambda_cannot_capture(self) -> None:
        # A variable is KS1103; reaching a token's operation is refused even
        # earlier, as a capability use without a token in scope (KS2401).
        for body, expected in (
            ("let limit = 3\n    println([1, 5].filter(fn(x: Int) -> Bool { return x > limit }) or [])", "KS1103"),
            ("let limit = 3\n    let f = fn(x: Int) -> Int { return x + limit }", "KS1103"),
            ("let disk = caps.disk.allow_read_only(\"/tmp\")\n    let f = fn(path: String) -> String { return disk.read(path) or \"\" }", "KS2401"),
        ):
            code, out = self.cli(f"fn main(caps: SystemCaps) {{\n    {body}\n}}\n", "check")
            self.assertEqual(code, 1, body)
            self.assertIn(expected, out, body)

    def test_reserved_names_and_interpolation(self) -> None:
        code, out = self.cli("fn __lambda_1_1() {\n}\n\nfn main() {\n}\n", "check")
        self.assertEqual(code, 1)
        self.assertIn("__lambda_", out)
        code, out = self.cli('fn main() {\n    println("{fn(x: Int) -> Int { return x }}")\n}\n', "check")
        self.assertEqual(code, 1)

    def test_lambda_types_are_checked(self) -> None:
        code, out = self.cli("fn main() {\n    let f = fn(x: Int) -> Int { return \"no\" }\n}\n", "check")
        self.assertEqual(code, 1)
        self.assertIn("KS13", out)


if __name__ == "__main__":
    unittest.main()
