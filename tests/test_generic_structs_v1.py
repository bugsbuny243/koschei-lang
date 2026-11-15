"""Generic structs under ks run: annotations, generic functions, swapped parameters."""
from __future__ import annotations

from contextlib import redirect_stderr, redirect_stdout
import io
from pathlib import Path
import tempfile
import unittest

from koschei.cli_entry import main as cli_main

STRUCTS = """struct Pair<A, B> {
    first: A,
    second: B,
}

struct Page<T> {
    items: List<T>,
    total: Int,
}

fn swap<A, B>(pair: Pair<A, B>) -> Pair<B, A> {
    return Pair { first: pair.second, second: pair.first }
}

fn count<T>(page: Page<T>) -> Int {
    return page.items.length()
}

fn first_item<T>(page: Page<T>) -> Option<T> {
    let item = page.items.get(0) or return None()
    return Some(item)
}
"""


class GenericStructTests(unittest.TestCase):
    def cli(self, source: str, command: str = "run") -> tuple[int, str]:
        with tempfile.TemporaryDirectory(prefix="koschei-generic-") as directory:
            path = Path(directory) / "main.ks"
            path.write_text(source, encoding="utf-8")
            stdout = io.StringIO()
            with redirect_stdout(stdout), redirect_stderr(stdout):
                code = cli_main([command, str(path)])
        return code, stdout.getvalue()

    def test_instances_annotations_and_generic_functions(self) -> None:
        code, out = self.cli(STRUCTS + """
fn main() {
    let p = Pair { first: 1, second: "one" }
    let q = swap(p)
    println("{q.first} {q.second}")
    let back = swap(q)
    println("{back.first} {back.second}")
    let annotated: Pair<String, Int> = Pair { first: "x", second: 2 }
    println(annotated.first)
    let page: Page<String> = Page { items: ["a", "b"], total: 2 }
    println(count(page))
    let head = first_item(page)
    match head {
        Some(item) => println(item),
        None => println("empty"),
    }
    let pages = [page, Page { items: ["c"], total: 1 }]
    println(pages.length())
    let nested: Pair<Page<Int>, List<String>> = Pair { first: Page { items: [7], total: 1 }, second: ["z"] }
    println(nested.first.items.length())
}
""")
        self.assertEqual(code, 0, out)
        self.assertEqual(out.splitlines(), ["one 1", "1 one", "x", "2", "a", "2", "1"])

    def test_wrong_type_arguments_are_refused(self) -> None:
        for body in (
            'let wrong: Pair<Int, Int> = Pair { first: 1, second: "x" }',
            'let page: Page<Int> = Page { items: ["a"], total: 1 }',
            'let p: Pair<Int, String> = swap(Pair { first: 1, second: "one" })',
        ):
            code, out = self.cli(STRUCTS + f"\nfn main() {{\n    {body}\n}}\n", "check")
            self.assertEqual(code, 1, body)
            self.assertIn("KS13", out, body)
        code, out = self.cli(STRUCTS + '\nfn main() {\n    let wrong: Pair<Int, Int> = Pair { first: 1, second: "x" }\n}\n', "check")
        self.assertIn("Expected Pair<Int, Int>, found Pair<Int, String>", out)

    def test_a_capability_cannot_hide_in_a_generic_field(self) -> None:
        code, out = self.cli(STRUCTS + """
fn main(caps: SystemCaps) {
    let clock = caps.clock.allow(1000)
    let hidden = Pair { first: clock, second: 1 }
}
""", "check")
        self.assertEqual(code, 1)
        self.assertIn("KS24", out)


if __name__ == "__main__":
    unittest.main()
