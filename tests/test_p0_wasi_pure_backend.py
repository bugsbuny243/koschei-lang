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

    def test_pure_arithmetic_and_string_concatenation(self):
        program = parse('fn main() { let n = 2 + 3 * 4 println(n) let s = "Kos" + "chei" println(s) }')
        source = generate_go_wasi_pure(program)
        self.assertIn("fmt.Println(14)", source)
        self.assertIn('fmt.Println("Koschei")', source)

    def test_unsupported_dynamic_host_access_is_rejected(self):
        program = parse('fn main() { let x = system println(x) }')
        with self.assertRaises(CodegenError):
            generate_go_wasi_pure(program)

    @unittest.skipUnless(shutil.which("go"), "Go toolchain unavailable")
    def test_hello_cross_compiles_to_real_wasm(self):
        program = parse((ROOT / "examples/hello.ks").read_text(encoding="utf-8"))
        check(program)
        with tempfile.TemporaryDirectory(prefix="koschei-pure-wasi-") as tmp:
            root = pathlib.Path(tmp)
            (root / "main.go").write_text(generate_go_wasi_pure(program), encoding="utf-8")
            (root / "go.mod").write_text("module koscheipurewasi\n\ngo 1.21\n", encoding="utf-8")
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
            residual = tuple(sorted(member for module, member in imports
                                    if member in {"fd_prestat_get", "fd_prestat_dir_name",
                                                  "environ_get", "environ_sizes_get"}))
            print("P0_PURE_WASI_STARTUP_RESIDUAL", residual)
            self.assertIn("fd_prestat_get", residual)
            # Import presence alone does not prove access to a preopened directory.
            self.assertEqual(_unexpected_authority(imports), ())
            self.assertNotIn(("wasi_snapshot_preview1", "path_open"), imports)
            # Execute under Wasmtime with no directory preopens or guest env.
            # Python's wasmtime package is pinned by the CI acquisition recipe.
            import wasmtime
            stdout_path = root / "wasm.stdout"
            stderr_path = root / "wasm.stderr"
            engine = wasmtime.Engine()
            module = wasmtime.Module.from_file(engine, str(wasm))
            linker = wasmtime.Linker(engine)
            linker.define_wasi()
            store = wasmtime.Store(engine)
            wasi = wasmtime.WasiConfig()
            wasi.argv = ["hello.wasm"]
            wasi.stdout_file = str(stdout_path)
            wasi.stderr_file = str(stderr_path)
            store.set_wasi(wasi)
            instance = linker.instantiate(store, module)
            try:
                instance.exports(store)["_start"](store)
            except wasmtime.ExitTrap as exit_trap:
                self.assertEqual(exit_trap.code, 0)
            actual_stdout = stdout_path.read_text(encoding="utf-8")
            actual_stderr = stderr_path.read_text(encoding="utf-8")
            self.assertEqual(actual_stdout, "Koschei\n1\n")
            self.assertEqual(actual_stderr, "")
            print("P0_PURE_WASI_EXECUTION_PARITY stdout=", repr(actual_stdout))


if __name__ == "__main__":
    unittest.main()
