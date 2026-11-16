"""Executable P0.1 proof: the public MIR-Go projection compiled to WASI.

Every fixture goes through the same sealed-MIR projection ``ks build`` uses
(``mir_go_native``), is compiled for ``GOOS=wasip1`` and for the host, and both
artifacts must agree on stdout, stderr and exit code. The WASI module runs
under Wasmtime with no directory preopens, no guest environment and a single
argv entry. An import outside the exact reviewed set fails the test.

This measures the import surface of a pure program. It is not a sandbox proof:
the host runtime and the Go startup imports remain part of the trust base.
"""
from __future__ import annotations

import contextlib
import gzip
import io
import os
import pathlib
import shutil
import subprocess
import tempfile
import unittest

from koschei import cli as _cli
from koschei.mir import require_mir
from koschei.mir_go_native import (
    MirGoUnsupported,
    generate_go_mir_native,
    generate_go_mir_wasi_pure,
)
from koschei.modules import check_graph
from tests.test_p0_wasi_import_inventory import _imports, _unexpected_authority

ROOT = pathlib.Path(__file__).resolve().parents[1]
GO = shutil.which("go")

# Pure fixtures: no authority domain reaches the generated runtime.
PURE_FIXTURES = (
    "app",
    "control_flow",
    "hello",
    "holders",
    "maps",
    "mir_cfg_project",
    "resource_contracts",
    "runtime_budget",
    "v08_types",
)

# Exact WASI import set of a pure MIR-Go module built with Go 1.24. Any other
# import, including a new one introduced by a toolchain upgrade, must be
# reviewed here before the test passes again.
REVIEWED_PURE_IMPORTS = frozenset(
    {
        "args_get",
        "args_sizes_get",
        "clock_time_get",
        "environ_get",
        "environ_sizes_get",
        "fd_close",
        "fd_fdstat_get",
        "fd_fdstat_set_flags",
        "fd_prestat_dir_name",
        "fd_prestat_get",
        "fd_write",
        "poll_oneoff",
        "proc_exit",
        "random_get",
        "sched_yield",
    }
)
# Go runtime startup probes these even for a pure program. They are residual
# host authority that the runner must starve (no preopens, empty environment).
STARTUP_RESIDUAL = frozenset(
    {"environ_get", "environ_sizes_get", "fd_prestat_get", "fd_prestat_dir_name"}
)
FORBIDDEN_PREFIXES = ("path_", "sock_")
FORBIDDEN_MEMBERS = frozenset({"fd_read", "fd_readdir", "fd_pread", "fd_pwrite"})

CAPABILITY_SOURCE = """fn main(caps: SystemCaps) {
    let clock = caps.clock.allow(1)
    println(clock.now_ms() > 0)
}
"""


def _sealed_mir(path: pathlib.Path):
    with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
        graph = _cli.open_graph(str(path))
        check_graph(graph)
        return require_mir(graph)


def _go_build(work: pathlib.Path, output: str, **target: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [GO, "build", "-trimpath", "-buildvcs=false", "-ldflags=-buildid=", "-o", output, "."],
        cwd=work,
        env=dict(os.environ, CGO_ENABLED="0", **target),
        capture_output=True,
        text=True,
        timeout=300,
    )


def _run_wasi(wasm: pathlib.Path, work: pathlib.Path) -> tuple[int, str, str]:
    import wasmtime

    stdout_path = work / "wasi.stdout"
    stderr_path = work / "wasi.stderr"
    engine = wasmtime.Engine()
    module = wasmtime.Module.from_file(engine, str(wasm))
    linker = wasmtime.Linker(engine)
    linker.define_wasi()
    store = wasmtime.Store(engine)
    wasi = wasmtime.WasiConfig()
    wasi.argv = ["guest.wasm"]
    wasi.stdout_file = str(stdout_path)
    wasi.stderr_file = str(stderr_path)
    # No preopened directory, no guest environment, no socket configuration.
    store.set_wasi(wasi)
    code = 0
    try:
        linker.instantiate(store, module).exports(store)["_start"](store)
    except wasmtime.ExitTrap as exit_trap:
        code = exit_trap.code
    return (
        code,
        stdout_path.read_text(encoding="utf-8"),
        stderr_path.read_text(encoding="utf-8"),
    )


class WasiPureGateTests(unittest.TestCase):
    """Source-level gate; needs no Go toolchain."""

    def test_pure_projection_is_the_public_mir_go_projection(self) -> None:
        mir = _sealed_mir(ROOT / "examples/hello.ks")
        self.assertEqual(generate_go_mir_wasi_pure(mir), generate_go_mir_native(mir))

    def test_pure_projection_names_no_host_effect_package(self) -> None:
        source = generate_go_mir_wasi_pure(_sealed_mir(ROOT / "examples/hello.ks"))
        for package in ('"syscall"', '"net"', '"net/http"', '"os/exec"', '"io"', '"time"'):
            self.assertNotIn(package, source)

    def test_authority_domain_is_refused(self) -> None:
        with tempfile.TemporaryDirectory(prefix="koschei-wasi-gate-") as tmp:
            path = pathlib.Path(tmp) / "main.ks"
            path.write_text(CAPABILITY_SOURCE, encoding="utf-8")
            mir = _sealed_mir(path)
            # The native projection admits the clock domain...
            self.assertIn('"time"', generate_go_mir_native(mir))
            # ...the WASI pure target must refuse it instead of emitting it.
            with self.assertRaises(MirGoUnsupported) as refused:
                generate_go_mir_wasi_pure(mir)
            self.assertIn("clock", str(refused.exception))

    def test_broker_domains_are_refused(self) -> None:
        for fixture in ("capability", "runtime_demo", "mir_effects_project", "showcase"):
            with self.subTest(fixture=fixture):
                mir = _sealed_mir(ROOT / "examples" / f"{fixture}.ks")
                with self.assertRaises(MirGoUnsupported):
                    generate_go_mir_wasi_pure(mir)

    def test_wasi_runtime_resource_limits(self) -> None:
        """Wasmtime fuel and memory ceilings are enforced by the host."""
        import wasmtime

        config = wasmtime.Config()
        config.consume_fuel = True
        engine = wasmtime.Engine(config)
        module = wasmtime.Module(engine, '(module (func (export "spin") (loop br 0)))')
        store = wasmtime.Store(engine)
        store.set_fuel(10000)
        instance = wasmtime.Instance(store, module, [])
        with self.assertRaises(wasmtime.Trap):
            instance.exports(store)["spin"](store)

        engine = wasmtime.Engine()
        module = wasmtime.Module(
            engine,
            '(module (memory (export "mem") 1)'
            ' (func (export "grow") (result i32) i32.const 2 memory.grow))',
        )
        store = wasmtime.Store(engine)
        store.set_limits(memory_size=65536)
        instance = wasmtime.Instance(store, module, [])
        self.assertEqual(instance.exports(store)["grow"](store), -1)


@unittest.skipUnless(GO, "Go toolchain unavailable: WASI artifact measurement not run")
class WasiPureArtifactTests(unittest.TestCase):
    def test_pure_fixtures_compile_run_and_match_native(self) -> None:
        passed = 0
        observed: set[str] = set()
        sizes: list[tuple[str, int, int]] = []
        for fixture in PURE_FIXTURES:
            with self.subTest(fixture=fixture), tempfile.TemporaryDirectory(
                prefix="koschei-pure-wasi-"
            ) as tmp:
                work = pathlib.Path(tmp)
                mir = _sealed_mir(ROOT / "examples" / f"{fixture}.ks")
                (work / "main.go").write_text(generate_go_mir_wasi_pure(mir), encoding="utf-8")
                (work / "go.mod").write_text("module koscheipurewasi\n\ngo 1.21\n", encoding="utf-8")

                native = _go_build(work, "native")
                self.assertEqual(native.returncode, 0, native.stderr)
                wasi = _go_build(work, "guest.wasm", GOOS="wasip1", GOARCH="wasm")
                self.assertEqual(wasi.returncode, 0, wasi.stderr)

                data = (work / "guest.wasm").read_bytes()
                self.assertTrue(data.startswith(b"\x00asm\x01\x00\x00\x00"))
                imports = _imports(data)
                self.assertTrue(imports, "module must expose an inspectable import section")
                self.assertEqual({module for module, _ in imports}, {"wasi_snapshot_preview1"})
                members = {member for _, member in imports}
                self.assertEqual(
                    sorted(members - REVIEWED_PURE_IMPORTS), [],
                    "unreviewed WASI import in a pure module",
                )
                for member in members:
                    self.assertFalse(member.startswith(FORBIDDEN_PREFIXES), member)
                    self.assertNotIn(member, FORBIDDEN_MEMBERS)
                self.assertEqual(_unexpected_authority(imports), ())
                observed |= members

                expected = subprocess.run(
                    [str(work / "native")], capture_output=True, text=True,
                    stdin=subprocess.DEVNULL, env={}, timeout=60,
                )
                code, stdout, stderr = _run_wasi(work / "guest.wasm", work)
                self.assertEqual(stdout, expected.stdout)
                self.assertEqual(stderr, expected.stderr)
                self.assertEqual(code, expected.returncode)
                sizes.append((fixture, len(data), len(gzip.compress(data))))
                passed += 1

        print(f"P0_WASI_PARITY fixtures={len(PURE_FIXTURES)} passed={passed}")
        print(f"P0_WASI_IMPORTS {tuple(sorted(observed))!r}")
        print(f"P0_WASI_STARTUP_RESIDUAL {tuple(sorted(observed & STARTUP_RESIDUAL))!r}")
        print(f"P0_WASI_SIZES {tuple(sizes)!r}")
        self.assertEqual(passed, len(PURE_FIXTURES))


if __name__ == "__main__":
    unittest.main()
