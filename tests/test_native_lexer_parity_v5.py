from __future__ import annotations

import json
import os
from pathlib import Path
import random
import re
import shutil
import subprocess
import tempfile
import unittest

from koschei.lexer import LexerError, tokenize


ROOT = Path(__file__).resolve().parents[1]
_ERROR_LOCATION = re.compile(
    r"\[(?:satır|line) (?P<line>\d+), (?:sütun|column) (?P<column>\d+)\]"
)


def _number_value(text: str) -> tuple[str, int | float]:
    if "." in text:
        return ("float", float(text))
    return ("int", int(text))


def _normalize_python(source: str, *, keep_comments: bool) -> list[tuple[object, ...]]:
    result: list[tuple[object, ...]] = []
    for token in tokenize(source, keep_comments=keep_comments):
        kind = token.type.name
        value: object = token.value
        if kind == "NUMBER":
            number_kind = "float" if isinstance(token.value, float) else "int"
            value = (number_kind, token.value)
        elif kind == "STRING_INTERP":
            value = tuple((segment_kind, segment_value) for segment_kind, segment_value in token.value)
        result.append((kind, value, token.line, token.column))
    return result


def _normalize_native(payload: str) -> list[tuple[object, ...]]:
    result: list[tuple[object, ...]] = []
    for token in json.loads(payload):
        kind = token["kind"]
        value: object = token.get("value")
        if kind == "NUMBER":
            value = _number_value(token["value"])
        elif kind == "STRING_INTERP":
            value = tuple(
                (segment["kind"], segment["value"])
                for segment in token.get("segments", [])
            )
        result.append((kind, value, token["line"], token["column"]))
    return result


def _failure_location(message: str) -> tuple[int, int] | None:
    match = _ERROR_LOCATION.search(message)
    if match is None:
        return None
    return (int(match.group("line")), int(match.group("column")))


@unittest.skipUnless(shutil.which("go"), "Go toolchain is not installed")
class NativeLexerParityV5Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls._temporary_directory = tempfile.TemporaryDirectory()
        executable = "ksc-native.exe" if os.name == "nt" else "ksc-native"
        cls.native_binary = Path(cls._temporary_directory.name) / executable
        build = subprocess.run(
            ["go", "build", "-trimpath", "-o", str(cls.native_binary), "./cmd/ksc-native"],
            cwd=ROOT / "native",
            text=True,
            capture_output=True,
            timeout=120,
            check=False,
        )
        if build.returncode != 0:
            raise AssertionError(build.stdout + build.stderr)

    @classmethod
    def tearDownClass(cls) -> None:
        cls._temporary_directory.cleanup()

    def _native(self, source: str, *, keep_comments: bool) -> subprocess.CompletedProcess[str]:
        arguments = [str(self.native_binary)]
        if keep_comments:
            arguments.append("--comments")
        return subprocess.run(
            arguments,
            input=source,
            text=True,
            capture_output=True,
            timeout=10,
            check=False,
        )

    def _assert_parity(self, source: str, *, keep_comments: bool = False) -> None:
        try:
            python_tokens = _normalize_python(source, keep_comments=keep_comments)
        except LexerError as error:
            python_failure = str(error)
            python_tokens = None
        else:
            python_failure = None

        native = self._native(source, keep_comments=keep_comments)
        native_succeeded = native.returncode == 0
        python_succeeded = python_failure is None
        self.assertEqual(
            native_succeeded,
            python_succeeded,
            "lexer acceptance diverged\n"
            f"source={source!r}\n"
            f"python_error={python_failure!r}\n"
            f"native_stdout={native.stdout!r}\n"
            f"native_stderr={native.stderr!r}",
        )

        if python_succeeded:
            self.assertEqual(
                _normalize_native(native.stdout),
                python_tokens,
                f"token stream diverged for source={source!r}",
            )
            return

        python_location = _failure_location(python_failure or "")
        native_location = _failure_location(native.stderr)
        if python_location is not None and native_location is not None:
            self.assertEqual(
                native_location,
                python_location,
                f"failure location diverged for source={source!r}",
            )

    def test_checked_in_koschei_corpus_matches(self) -> None:
        sources = sorted(
            path
            for path in ROOT.rglob("*.ks")
            if ".git" not in path.parts and "__pycache__" not in path.parts
        )
        self.assertGreaterEqual(len(sources), 10, "expected a meaningful checked-in .ks corpus")
        for path in sources:
            source = path.read_text(encoding="utf-8")
            relative = path.relative_to(ROOT)
            with self.subTest(path=str(relative), comments=False):
                self._assert_parity(source)
            with self.subTest(path=str(relative), comments=True):
                self._assert_parity(source, keep_comments=True)

    def test_curated_edge_contract_matches(self) -> None:
        cases = [
            "",
            "// yalnızca yorum",
            "let sayı_1 = 000123",
            "let Büyük = 1",
            "let value = 99999999999999999999999999999999999999999999999999",
            "let value = 00000000000000000000000000000000000000000000000001.2500",
            'let text = "satır\\nsekme\\t\\{güvenli\\}"',
            'let text = "değer={Map { anahtar: \"}\" }}"',
            'let text = "liste={[1, 2, 3].length()}"',
            "fn main() { if true && !false { println(\"tamam\") } }",
            "&",
            "|",
            '"{}"',
            '"kapanmadı',
            '"geçersiz \\q"',
            '"tek }"',
            '"{value"',
            '"{\"satır\n\"}"',
        ]
        for index, source in enumerate(cases):
            with self.subTest(case=index, comments=False):
                self._assert_parity(source)
            with self.subTest(case=index, comments=True):
                self._assert_parity(source, keep_comments=True)

    def test_generated_adversarial_sources_match(self) -> None:
        generator = random.Random(0x4B4F5343484549)
        alphabet = (
            "abcdefghijklmnopqrstuvwxyz"
            "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
            "çğıöşüÇĞİÖŞÜ"
            "0123456789_ \t\r\n"
            "(){}[],:.=+-*/;!<>&|\\\""
        )
        for index in range(128):
            length = generator.randrange(0, 385)
            source = "".join(generator.choice(alphabet) for _ in range(length))
            with self.subTest(case=index, comments=False):
                self._assert_parity(source)
            if index < 32:
                with self.subTest(case=index, comments=True):
                    self._assert_parity(source, keep_comments=True)


if __name__ == "__main__":
    unittest.main()
