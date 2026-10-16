"""Executable P0.1 proof: a deliberately restricted Koschei pure fixture to WASI."""
from __future__ import annotations

import os
import pathlib
import shutil
import subprocess
import tempfile
import unittest

from koschei.codegen_go import CodegenError, generate_go_wasi_pure
from koschei.parser import parse
from koschei.semantic import check
from tests.test_p0_wasi_import_inventory import _imports, _unexpected_authority

ROOT = pathlib.Path(__file__).resolve().parents[1]


class WasiPureBackendTests(unittest.TestCase):
    def test_hello_fixture_emits_go_without_native_capability_runtime(self):
        program = parse((ROOT / "examples/hello.ks").read_text(encoding="utf-8"))
        check(program)
        source = generate_go_wasi_pure(program)
        self.assertIn('fmt.Println("Koschei")', source)
        self.assertIn("fmt.Println(1)", source)
        self.assertNotIn("syscall", source)
        self.assertNotIn("ksNewSystemCaps", source)

    def test_host_capability_expression_fails_closed(self):
        program = parse("fn main() { println(system) }")
        with self.assertRaises(CodegenError):
            generate_go_wasi_pure(program)

    @unittest.skipUnless(shutil.which("go"), "Go toolchain unavailable")
    def test_hello_cross_compiles_to_real_wasm(self):
        program = parse((ROOT / "examples/hello.ks").read_text(encoding="utf-8"))
        check(program)
        with tempfile.TemporaryDirectory(prefix="koschei-pure-wasi-") as tmp:
            root = pathlib.Path(tmp)
            (root / "main.go").write_text(generate_go_wasi_pure(program), encoding="utf-8")
            (root / "go.mod").write_text("module koscheipurewasi\\n\\ngo 1.21\\n", encoding="utf-8")
            wasm = root / "hello.wasm"
            env = dict(os.environ, GOOS="wasip1", GOARCH="wasm", CGO_ENABLED="0")
            build = subprocess.run(
                ["go", "build", "-o", str(wasm), "."], cwd=root,
                env=env, capture_output=True, text=True, timeout=240,
            )
            self.assertEqual(build.returncode, 0, build.stderr)
            data = wasm.read_bytes()
            self.assertTrue(data.startswith(bytes((0, 97, 115, 109, 1, 0, 0, 0))))
            imports = _imports(data)
            print("P0_PURE_WASI_REAL_BINARY_IMPORTS", imports)
            self.assertEqual(_unexpected_authority(imports), ())
            self.assertNotIn(("wasi_snapshot_preview1", "path_open"), imports)


if __name__ == "__main__":
    unittest.main()
