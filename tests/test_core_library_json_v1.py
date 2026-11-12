"""The `json` Core Library module writes JSON that standard parsers read back exactly."""
from __future__ import annotations

from contextlib import redirect_stderr, redirect_stdout
import io
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

from koschei.cli_entry import main as cli_main

GO = shutil.which("go")

# Every ASCII character (controls, quote, backslash, braces) and multi-byte UTF-8.
SAMPLES = [
    "".join(chr(code) for code in range(0, 32)),
    "".join(chr(code) for code in range(32, 128)),
    'say "hi"\\ok\nnext',
    "é ✓ 日本 😀",
    "",
]


def strings_program() -> str:
    # Samples travel as hex so the test does not depend on string-literal escapes.
    lines = "\n".join(
        f'    show("{sample.encode("utf-8").hex()}")' for sample in SAMPLES
    )
    return f"""import json

fn show(hex: String) {{
    let raw = bytes_from_hex(hex) or "".to_bytes()
    let text = raw.to_text() or ""
    println(json.string(text))
}}

fn main() {{
{lines}
}}
"""


DOCUMENT = """import json

fn main() {
    let big = 100000000000000000000.0 * 100000000000000000000.0
    let huge = big * big * big * big * big * big * big * big * big * big * big * big * big * big * big * big
    println(json.float(huge))
    let tags = json.array([json.string("a"), json.string("b")])
    let empty: Map<String, String> = {}
    let price = json.float(2.5) or json.null()
    let doc = json.object({
        "name": json.string("Ada \\"Lovelace\\""),
        "age": json.int(36),
        "neg": json.int(-9223372036854775807 - 1),
        "price": price,
        "ok": json.bool(true),
        "off": json.bool(false),
        "none": json.null(),
        "tags": tags,
        "nothing": json.array([]),
        "inner": json.object(empty),
    })
    println(doc)
    let data = parse_json(doc) or return Error("not valid JSON")
    let name = json_get(data, "name") or return Error("no name")
    println(json_text(name) or "?")
}
"""


class CoreLibraryJsonTests(unittest.TestCase):
    def write(self, source: str) -> Path:
        temporary = tempfile.TemporaryDirectory(prefix="koschei-json-")
        self.addCleanup(temporary.cleanup)
        path = Path(temporary.name) / "main.ks"
        path.write_text(source, encoding="utf-8")
        return path

    def ks_run(self, path: Path) -> str:
        stdout = io.StringIO()
        with redirect_stdout(stdout), redirect_stderr(io.StringIO()) as errors:
            self.assertEqual(cli_main(["run", str(path)]), 0, errors.getvalue())
        return stdout.getvalue()

    def test_strings_round_trip_through_a_standard_parser(self) -> None:
        path = self.write(strings_program())
        lines = self.ks_run(path).splitlines()
        self.assertEqual(len(lines), len(SAMPLES))
        for sample, line in zip(SAMPLES, lines):
            self.assertEqual(json.loads(line), sample, line)
            # Raw control characters never appear inside the encoded text.
            self.assertFalse(any(ord(char) < 32 for char in line), line)

    @unittest.skipIf(GO is None, "Go is not installed")
    def test_native_binary_writes_the_same_strings(self) -> None:
        path = self.write(strings_program())
        expected = self.ks_run(path)
        binary = path.parent / "app"
        with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()) as errors:
            self.assertEqual(cli_main(["build", str(path), "-o", str(binary)]), 0, errors.getvalue())
        completed = subprocess.run([str(binary)], capture_output=True, text=True, timeout=60, check=False)
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertEqual(completed.stdout, expected)

    def test_documents_nest_and_parse(self) -> None:
        lines = self.ks_run(self.write(DOCUMENT)).splitlines()
        self.assertEqual(lines[0], "json.float: inf.0 is not a finite number")
        self.assertEqual(
            json.loads(lines[1]),
            {
                "name": 'Ada "Lovelace"', "age": 36, "neg": -9223372036854775808, "price": 2.5,
                "ok": True, "off": False, "none": None, "tags": ["a", "b"], "nothing": [], "inner": {},
            },
        )
        # Members keep the order they were written in.
        self.assertTrue(lines[1].startswith('{"name":'), lines[1])
        self.assertEqual(lines[2], 'Ada "Lovelace"')


if __name__ == "__main__":
    unittest.main()
