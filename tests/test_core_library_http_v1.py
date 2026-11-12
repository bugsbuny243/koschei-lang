"""The `http` Core Library module reads request targets the way standard parsers do."""
from __future__ import annotations

from contextlib import redirect_stderr, redirect_stdout
import html
import io
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from urllib.parse import parse_qsl, unquote, unquote_plus

from koschei.cli_entry import main as cli_main

GO = shutil.which("go")

# Valid percent-encoded text, fed to the program as hex.
COMPONENTS = [
    "",
    "plain",
    "a+b",
    "caf%C3%A9+au+lait",
    "%e2%9c%93%20ok",
    "a%3Db%26c%3Fd%2F",
    "%25%2B%20",
    "%F0%9F%98%80",
    "~-._!*'()",
]
QUERIES = [
    "",
    "a=1",
    "a=1&b=two+words&c=%C4%B0stanbul",
    "flag&&x=&=v&y=a=b",
    "q=1&q=2&r=3",
]
# Escapes that are not valid: refused, never guessed.
INVALID = ["%", "%4", "%zz", "a%g1", "%ff", "%C3"]
HTML_SAMPLES = ["", "plain", "<a href=\"x\">Tom & 'Jerry'</a>", "é ✓ <😀>"]
ROUTES = [
    ("/users/:id", "/users/42", {"id": "42"}),
    ("/users/:id", "/users/42/", {"id": "42"}),
    ("/users/:id", "/users/a%2Fb?x=1", {"id": "a/b"}),
    ("/users/:id/posts/:post", "/users/ada/posts/7", {"id": "ada", "post": "7"}),
    ("/café", "/caf%C3%A9", {}),
    ("/café", "/café", {}),
    ("/", "/", {}),
    ("/", "/?q=1", {}),
    ("/users/:id", "/users", None),
    ("/users/:id", "/users/1/2", None),
    ("/users/:id", "/people/1", None),
    ("/users/:id", "/users/%zz", None),
]


def hex_of(text: str) -> str:
    return text.encode("utf-8").hex()


def program() -> str:
    lines = []
    for text in COMPONENTS:
        lines.append(f'    show_decode("{hex_of(text)}")')
    for text in QUERIES:
        lines.append(f'    show_query("{hex_of(text)}")')
    for text in INVALID:
        lines.append(f'    show_decode("{hex_of(text)}")')
    for text in HTML_SAMPLES:
        lines.append(f'    show_html("{hex_of(text)}")')
    for pattern, target, _ in ROUTES:
        lines.append(f'    show_route("{hex_of(pattern)}", "{hex_of(target)}")')
    body = "\n".join(lines)
    return f"""import http
import json

fn text_of(hex: String) -> String {{
    let raw = bytes_from_hex(hex) or "".to_bytes()
    return raw.to_text() or ""
}}

fn show_decode(hex: String) {{
    let text = text_of(hex)
    let path = http.decode(text) or "REFUSED"
    let form = http.decode_form(text) or "REFUSED"
    println(json.array([json.string(path), json.string(form)]))
}}

fn encode_map(found: Map<String, String>) -> String {{
    let mut members: Map<String, String> = {{}}
    for key in found.keys() {{
        let value = found.get(key) or ""
        members = members.set(key, json.string(value))
    }}
    return json.object(members)
}}

fn show_query(hex: String) {{
    let text = text_of(hex)
    let empty: Map<String, String> = {{}}
    let found = http.query("/p?" + text) or empty
    println(encode_map(found))
}}

fn show_html(hex: String) {{
    println(json.string(http.escape_html(text_of(hex))))
}}

fn show_route(pattern_hex: String, target_hex: String) {{
    let captured = http.route(text_of(pattern_hex), text_of(target_hex))
    match captured {{
        Some(found) => println(encode_map(found)),
        None => println("null"),
    }}
}}

fn main() {{
{body}
}}
"""


def expected_lines() -> list[object]:
    out: list[object] = []
    for text in COMPONENTS:
        out.append([unquote(text, errors="strict"), unquote_plus(text, errors="strict")])
    for text in QUERIES:
        found: dict[str, str] = {}
        for name, value in parse_qsl(text, keep_blank_values=True, errors="strict"):
            found[name] = value
        out.append(found)
    for _ in INVALID:
        out.append(["REFUSED", "REFUSED"])
    for text in HTML_SAMPLES:
        out.append(html.escape(text, quote=True).replace("&#x27;", "&#39;"))
    for _, _, captured in ROUTES:
        out.append(captured)
    return out


class CoreLibraryHttpTests(unittest.TestCase):
    def write(self, source: str) -> Path:
        temporary = tempfile.TemporaryDirectory(prefix="koschei-http-")
        self.addCleanup(temporary.cleanup)
        path = Path(temporary.name) / "main.ks"
        path.write_text(source, encoding="utf-8")
        return path

    def ks_run(self, path: Path) -> str:
        stdout = io.StringIO()
        with redirect_stdout(stdout), redirect_stderr(io.StringIO()) as errors:
            self.assertEqual(cli_main(["run", str(path)]), 0, errors.getvalue())
        return stdout.getvalue()

    def test_matches_python_urllib_and_html(self) -> None:
        lines = self.ks_run(self.write(program())).splitlines()
        expected = expected_lines()
        self.assertEqual(len(lines), len(expected))
        for line, wanted in zip(lines, expected):
            self.assertEqual(json.loads(line), wanted, line)

    def test_path_and_query_parts(self) -> None:
        source = """import http

fn main() {
    println(http.path_of("/a/b?x=1?y"))
    println(http.query_of("/a/b?x=1?y"))
    println(http.query_of("/a/b"))
    println(http.segments("//a//b/?c/d"))
}
"""
        self.assertEqual(
            self.ks_run(self.write(source)).splitlines(),
            ["/a/b", "x=1?y", "", '["a", "b"]'],
        )

    @unittest.skipIf(GO is None, "Go is not installed")
    def test_native_binary_prints_the_same(self) -> None:
        path = self.write(program())
        expected = self.ks_run(path)
        binary = path.parent / "app"
        with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()) as errors:
            self.assertEqual(cli_main(["build", str(path), "-o", str(binary)]), 0, errors.getvalue())
        completed = subprocess.run([str(binary)], capture_output=True, text=True, timeout=60, check=False)
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertEqual(completed.stdout, expected)


if __name__ == "__main__":
    unittest.main()
