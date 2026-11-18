"""Data in native binaries: parse_json, encode_json and the json_* builtins.

`ks build` refused any program that used Data (KS4004). Binaries now embed
the audited data-json/v1 Go core (native/datajson/json.go) and must print
what `ks run` prints, errors included. The Go and Python cores are also
compared directly on random documents, valid and broken.
"""
from __future__ import annotations

import json
from pathlib import Path
import random
import shutil
import subprocess
import sys
import tempfile
import unittest

from koschei.data_json_v1 import DataError, decode, encode
from tests.test_data_access_v1 import EXPECTED, SURFACE

ROOT = Path(__file__).resolve().parent.parent
GO = shutil.which("go")

ORDER = r'''
fn main() {
    let d = parse_json("\{\"z\":1,\"é\":2.50,\"a\":\{\"q\":[true,false,null]\}\}") or return
    println(json_keys(d) or [])
    println(encode_json(d) or "")
    println(json_length(d) or 0)
    let big = parse_json("[1e400, 1.5e-7, 1e5, -0]") or return
    for item in json_items(big) or [] {
        println(json_int(item))
        println(json_float(item))
    }
}
'''

DUPLICATE = 'fn main() {\n    let d = parse_json("\\{\\"é\\":1,\\"é\\":2\\}") or return\n}\n'
TRUNCATED = 'fn main() {\n    let d = parse_json("[1,") or return\n}\n'
BAD_ESCAPE = 'fn main() {\n    let d = parse_json("\\"\\\\é\\"") or return\n}\n'


def _run(command: list[str], cwd: Path) -> tuple[str, str, int]:
    done = subprocess.run(command, cwd=cwd, capture_output=True, text=True, timeout=300)
    return done.stdout, done.stderr, done.returncode


@unittest.skipUnless(GO, "Go toolchain unavailable")
class NativeDataTests(unittest.TestCase):
    def both(self, source: str) -> tuple[str, str, int]:
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            (base / "main.ks").write_text(source, encoding="utf-8")
            interpreted = _run([sys.executable, "-m", "koschei", "run", "main.ks"], base)
            build = _run([sys.executable, "-m", "koschei", "build", "main.ks", "-o", "app"], base)
            self.assertEqual(build[2], 0, build[1])
            native = _run([str(base / "app")], base)
        self.assertEqual(native, interpreted)
        return interpreted

    def test_access_surface_matches_ks_run(self) -> None:
        stdout, _, code = self.both(SURFACE)
        self.assertEqual((stdout, code), (EXPECTED, 0))

    def test_key_order_and_numbers_match_ks_run(self) -> None:
        stdout, _, _ = self.both(ORDER)
        lines = stdout.splitlines()
        self.assertEqual(lines[0], '["z", "é", "a"]')
        self.assertEqual(lines[1], '{"a":{"q":[true,false,null]},"z":1,"é":2.5}')
        self.assertEqual(lines[3], "KS3709: json_int(): 1e400 is outside the Int range")
        self.assertEqual(lines[5], "KS3709: json_int(): 1.5e-7 is not an integer")

    def test_parse_errors_match_ks_run(self) -> None:
        for source, message in (
            (DUPLICATE, "KS3604 [byte 8]: duplicate JSON object key 'é'"),
            (TRUNCATED, "KS3605 [byte 3]: unexpected end of JSON input"),
            (BAD_ESCAPE, "KS3605 [byte 1]: invalid JSON escape \\é"),
        ):
            _, stderr, code = self.both(source)
            self.assertEqual(code, 1)
            self.assertIn(message, stderr)


def _documents(seed: int, count: int) -> list[str]:
    rng = random.Random(seed)
    noise = ['{', '}', '[', ']', ':', ',', '"', 'é', '\\', 'u', '0', '-', '.', 'e', ' ',
             '\n', "'", '\x01', ' ', '\U0001F600', '\\u00e7', '\\ud83d', '\\u00', '\\é']

    def value(depth: int = 0) -> str:
        roll = rng.random()
        if depth > 3 or roll < 0.3:
            return rng.choice(['1', '-2.50', '0', '1e3', '1e400', '"x"', '"é\\n"', 'true',
                               'null', '"a\'b"', '1.0E-3', '-0', '"\\u0001"', '"\U0001F600"'])
        if roll < 0.6:
            return '[' + ','.join(value(depth + 1) for _ in range(rng.randint(0, 3))) + ']'
        keys = rng.sample(['a', 'b', 'é', 'x y', "q'", '"', '\t', '😀'], rng.randint(0, 3))
        return '{' + ','.join(json.dumps(k, ensure_ascii=False) + ':' + value(depth + 1) for k in keys) + '}'

    documents = [value() for _ in range(count)]
    for _ in range(count):
        text = value()
        at = rng.randrange(len(text) + 1)
        documents.append(text[:at] + rng.choice(noise) + text[at:])
    return documents


@unittest.skipUnless(GO, "Go toolchain unavailable")
class GoPythonCoreTests(unittest.TestCase):
    def test_cores_agree_on_random_documents(self) -> None:
        harness = r'''
func main() {
	scanner := bufio.NewScanner(os.Stdin)
	scanner.Buffer(make([]byte, 1<<20), 1<<22)
	for scanner.Scan() {
		var source string
		if err := json.Unmarshal(scanner.Bytes(), &source); err != nil {
			panic(err)
		}
		line := ""
		if value, err := Decode(source, DefaultLimits); err != nil {
			line = "ERR " + err.Error()
		} else if text, err := Encode(value, DefaultLimits); err != nil {
			line = "ERR " + err.Error()
		} else {
			line = "OK " + text
		}
		encoded, _ := json.Marshal(line)
		fmt.Println(string(encoded))
	}
}
'''
        core = (ROOT / "native" / "datajson" / "json.go").read_text(encoding="utf-8")
        core = core.replace("package datajson", "package main", 1)
        core = core.replace("import (\n", 'import (\n\t"bufio"\n\t"encoding/json"\n\t"os"\n', 1)
        documents = _documents(20261118, 400)
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            (base / "main.go").write_text(core + harness, encoding="utf-8")
            (base / "go.mod").write_text("module corecheck\n\ngo 1.22\n", encoding="utf-8")
            build = subprocess.run(["go", "build", "-o", "core", "."], cwd=base, capture_output=True, text=True)
            self.assertEqual(build.returncode, 0, build.stderr)
            feed = "".join(json.dumps(text) + "\n" for text in documents)
            done = subprocess.run([str(base / "core")], input=feed.encode(), capture_output=True, check=True)
        answers = [json.loads(line) for line in done.stdout.decode().splitlines()]
        self.assertEqual(len(answers), len(documents))
        for text, answer in zip(documents, answers):
            try:
                expected = "OK " + encode(decode(text))
            except DataError as error:
                expected = "ERR " + str(error)
            self.assertEqual(answer, expected, repr(text))


if __name__ == "__main__":
    unittest.main()
