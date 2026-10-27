"""The Bytes type (G1.3): one meaning in every executor and in binaries."""
from __future__ import annotations

from contextlib import redirect_stderr, redirect_stdout
import hashlib
import io
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

from koschei import runtime_budget
from koschei.canonical_mir_budget_runtime_v1 import _run_budgeted_canonical_mir
from koschei.cli_entry import main as cli_main
from koschei.modules import check_graph, load_graph
from koschei.runtime_budget import BudgetedInterpreter, RuntimeBudget
from koschei.semantic import SemanticError

GO = shutil.which("go")

SURFACE = """
import secure

fn describe(data: Bytes) -> String {
    return "{data.length()}:{data.hex()}"
}

fn main() {
    let data = "héllo".to_bytes()
    println(data)
    println(describe(data))
    println(data.get(1) or -1)
    println(data.get(6))
    println(data.get(-1))
    let head = data.slice(0, 2) or data
    println(head)
    println(data.slice(3, 2))
    println(data.slice(0, 7))
    println(data.to_text() or "?")
    let raw = bytes_from_hex("00fF") or data
    println(raw)
    println(raw.to_text())
    println(bytes_from_hex("0"))
    println(bytes_from_hex(" 00"))
    println(bytes_from_hex("zz"))
    println(head + raw)
    println(head == "hé".to_bytes())
    println(raw < head)
    println([raw, head])
    println(sha3_256_bytes("abc".to_bytes()) or "?")
    println(secure.hash_bytes(raw) or "?")
    let empty = bytes_from_hex("") or data
    println("{empty.length()} [{empty.to_text() or "?"}]")
}
"""

EXPECTED = "\n".join([
    "Bytes(68c3a96c6c6f)",
    "6:68c3a96c6c6f",
    "195",
    "KS3460: Bytes.get() indeksi aralık dışında: 6 (uzunluk 6).",
    "KS3460: Bytes.get() indeksi aralık dışında: -1 (uzunluk 6).",
    "Bytes(68c3)",
    "KS3460: Bytes.slice() aralığı geçersiz: 3..2 (uzunluk 6).",
    "KS3460: Bytes.slice() aralığı geçersiz: 0..7 (uzunluk 6).",
    "héllo",
    "Bytes(00ff)",
    "KS3430: Bytes geçerli UTF-8 metin değil.",
    "KS3461: bytes_from_hex() çift uzunlukta bir hex metni bekler.",
    "KS3461: bytes_from_hex() çift uzunlukta bir hex metni bekler.",
    "KS3461: bytes_from_hex() çift uzunlukta bir hex metni bekler.",
    "Bytes(68c300ff)",
    "false",
    "true",
    "[Bytes(00ff), Bytes(68c3)]",
    hashlib.sha3_256(b"abc").hexdigest(),
    "sha3-256:" + hashlib.sha3_256(b"\x00\xff").hexdigest(),
    "0 []",
]) + "\n"

CAPABILITIES = """
fn main(caps: SystemCaps) {
    let input = caps.input.allow(8)
    let data = input.read_bytes() or "?".to_bytes()
    println(data)
    let random = caps.random.allow(16)
    let fresh = random.bytes(16) or data
    println(fresh.length())
    println(random.bytes(1))
    println(random.bytes(0))
}
"""


class BytesTests(unittest.TestCase):
    maxDiff = None

    def write(self, source: str) -> Path:
        temporary = tempfile.TemporaryDirectory(prefix="koschei-bytes-")
        self.addCleanup(temporary.cleanup)
        path = Path(temporary.name) / "main.ks"
        path.write_text(source, encoding="utf-8")
        return path

    def ks_run(self, path: Path, data: bytes = b"") -> str:
        stdout = io.StringIO()
        stream = io.TextIOWrapper(io.BytesIO(data), encoding="utf-8")
        with mock.patch.object(sys, "stdin", stream), redirect_stdout(stdout), redirect_stderr(io.StringIO()) as errors:
            self.assertEqual(cli_main(["run", str(path)]), 0, errors.getvalue())
        return stdout.getvalue()

    def native(self, path: Path, data: bytes = b"") -> str | None:
        if GO is None:
            return None
        binary = path.parent / "app"
        with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()) as errors:
            self.assertEqual(cli_main(["build", str(path), "-o", str(binary)]), 0, errors.getvalue())
        completed = subprocess.run([str(binary)], input=data, capture_output=True, timeout=60, check=False)
        self.assertEqual(completed.returncode, 0, completed.stderr)
        return completed.stdout.decode("utf-8")

    def check_error(self, source: str) -> str:
        graph = load_graph(self.write(source))
        with self.assertRaises(SemanticError) as caught:
            check_graph(graph)
        return caught.exception.code

    def test_every_executor_agrees(self) -> None:
        path = self.write(SURFACE)
        self.assertEqual(self.ks_run(path), EXPECTED)
        graph = load_graph(path)
        check_graph(graph)
        mir = graph.mir
        root = mir.root_module
        checked = io.StringIO()
        with redirect_stdout(checked):
            BudgetedInterpreter(
                root.program, [], namespaces=mir.namespaces(), imports=dict(root.imports),
                enums=mir.enums(), module_imports=mir.module_imports(), structs=mir.structs(),
                budget=runtime_budget.RuntimeBudget(),
            ).execute_main()
        self.assertEqual(checked.getvalue(), EXPECTED)
        canonical = io.StringIO()
        with redirect_stdout(canonical):
            _run_budgeted_canonical_mir(mir, [], RuntimeBudget())
        self.assertEqual(canonical.getvalue(), EXPECTED)
        native = self.native(path)
        if native is not None:
            self.assertEqual(native, EXPECTED)

    def test_binary_sources(self) -> None:
        path = self.write(CAPABILITIES)
        for data in (b"\x00\xff\xfe", b"123456789"):
            outputs = [self.ks_run(path, data), self.native(path, data)]
            for output in outputs:
                if output is None:
                    continue
                lines = output.splitlines()
                if data == b"123456789":
                    self.assertEqual(lines[0], "Bytes(3f)")
                else:
                    self.assertEqual(lines[0], "Bytes(00fffe)")
                self.assertEqual(lines[1], "16")
                self.assertEqual(
                    lines[2],
                    "KS3450: Rastgele sayı bütçesi tükendi: bu yetki en fazla 16 bayt üretebilir.",
                )
                self.assertEqual(
                    lines[3], "KS3451: random.bytes() bayt sayısı 1..1024 aralığında olmalıdır."
                )

    def test_disk_reads_bytes_inside_its_scope(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "blob.bin").write_bytes(b"\x00\xffhi")
            (root / "link.bin").symlink_to(root / "blob.bin")
            source = (
                "fn main(caps: SystemCaps) {\n"
                f'    let disk = caps.disk.allow_read_only("{root}/")\n'
                f'    println(disk.read_bytes("{root}/blob.bin"))\n'
                f'    println(disk.read_bytes("{root}/link.bin"))\n'
                '    println(disk.read_bytes("/etc/hostname"))\n}\n'
            )
            lines = self.ks_run(self.write(source)).splitlines()
        self.assertEqual(lines[0], "Bytes(00ff6869)")
        self.assertIn("KS3405", lines[1])
        self.assertTrue(lines[2].startswith("KS3402"))

    def test_bytes_respect_the_value_budget(self) -> None:
        source = (
            "fn main(caps: SystemCaps) {\n    let input = caps.input.allow(16777216)\n"
            '    let block = input.read_bytes() or "".to_bytes()\n'
            '    let joined = block + "x".to_bytes()\n    println(joined)\n}\n'
        )
        path = self.write(source)
        message = "KS3502: Bellek bütçesi aşıldı: bir Bytes en fazla 16777216 bayt olabilir.\n"
        data = b"\x00" * (1 << 24)
        self.assertEqual(self.ks_run(path, data), message)
        native = self.native(path, data)
        if native is not None:
            self.assertEqual(native, message)

    def test_hex_respects_the_string_budget(self) -> None:
        source = (
            "fn main(caps: SystemCaps) {\n    let input = caps.input.allow(16777216)\n"
            '    let block = input.read_bytes() or "".to_bytes()\n'
            "    println(block.hex())\n}\n"
        )
        path = self.write(source)
        message = "KS3502: Bellek bütçesi aşıldı: bir String en fazla 16777216 bayt UTF-8 olabilir.\n"
        data = b"\x00" * ((1 << 23) + 1)
        self.assertEqual(self.ks_run(path, data), message)
        native = self.native(path, data)
        if native is not None:
            self.assertEqual(native, message)

    def test_the_checker_keeps_bytes_and_text_apart(self) -> None:
        cases = {
            'fn main() {\n    let x = "a".to_bytes() + "b"\n}\n': "KS1306",
            'fn main() {\n    let x = "a".to_bytes() - "b".to_bytes()\n}\n': "KS1306",
            'fn main() {\n    let x = "a".to_bytes().split(",")\n}\n': "KS1306",
            'fn main() {\n    let x = "a".to_bytes().get("0")\n}\n': "KS1301",
            'fn main() {\n    let x = "a".to_bytes(1)\n}\n': "KS1301",
            'fn main() {\n    let x = bytes_from_hex(5)\n}\n': "KS1301",
            'fn main() {\n    let x = sha3_256_bytes("text")\n}\n': "KS1301",
        }
        for source, code in cases.items():
            with self.subTest(source):
                self.assertEqual(self.check_error(source), code)


if __name__ == "__main__":
    unittest.main()
