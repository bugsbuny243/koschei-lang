"""P0.1 evidence: compiled host symbols of the public ``ks build`` projection.

Each fixture goes through the sealed-MIR projection that ``ks build`` uses
(``mir_go_native``), is built with ``CGO_ENABLED=0`` and inspected with
``go tool nm``. Absence is asserted per authority domain: a binary may only
carry the host symbols its domains need.

Absent symbols are not a sandbox proof. They show that no code for that
operation was linked into the program binary. The native broker that serves
disk and environment requests runs as a separate process and is measured
only as far as the program binary that launches it.
"""
from __future__ import annotations

import contextlib
import io
import os
import pathlib
import shutil
import subprocess
import tempfile
import unittest

from koschei import cli as _cli
from koschei.mir import require_mir
from koschei.mir_go_native import generate_go_mir_native
from koschei.modules import check_graph


GO = shutil.which("go")
ROOT = pathlib.Path(__file__).resolve().parents[1]

WATCHED = (
    "syscall.Openat",
    "syscall.Close",
    "syscall.Socket",
    "syscall.Socketpair",
    "syscall.Connect",
    "syscall.Bind",
    "syscall.Listen",
    "syscall.Renameat",
    "syscall.Unlinkat",
    "os.NewFile",
    "os.LookupEnv",
    "os.Remove",
    "os.OpenFile",
    "os.ReadFile",
    "os.StartProcess",
    "os/exec.Command",
    "io.ReadAll",
    "net.Dial",
    "net/http.NewRequest",
    "time.Now",
    "crypto/rand.Read",
)

NETWORK = frozenset(
    {
        "syscall.Socket",
        "syscall.Connect",
        "syscall.Bind",
        "syscall.Listen",
        "net.Dial",
        "net/http.NewRequest",
    }
)
FILESYSTEM = frozenset(
    {
        "syscall.Openat",
        "syscall.Renameat",
        "syscall.Unlinkat",
        "os.Remove",
        "os.OpenFile",
        "os.ReadFile",
    }
)
PROCESS = frozenset({"os.StartProcess", "os/exec.Command"})
ENVIRONMENT = frozenset({"os.LookupEnv"})

CLOCK_SOURCE = """fn main(caps: SystemCaps) {
    let clock = caps.clock.allow(1)
    println(clock.now_ms() > 0)
}
"""


@unittest.skipUnless(GO, "Go unavailable: native artifact measurement not run")
class HostSymbolEvidenceTests(unittest.TestCase):
    _cache: dict[str, frozenset[str]] = {}

    def _present(self, label: str, path: pathlib.Path) -> frozenset[str]:
        if label in self._cache:
            return self._cache[label]
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            graph = _cli.open_graph(str(path))
            check_graph(graph)
            mir = require_mir(graph)
        generated = generate_go_mir_native(mir)
        with tempfile.TemporaryDirectory(prefix="koschei-p0-host-") as tmp:
            work = pathlib.Path(tmp)
            (work / "main.go").write_text(generated, encoding="utf-8")
            (work / "go.mod").write_text("module koscheihostsurface\n\ngo 1.21\n", encoding="utf-8")
            binary = work / "program"
            version = subprocess.run([GO, "version"], capture_output=True, text=True, timeout=30)
            self.assertEqual(version.returncode, 0, version.stderr)
            built = subprocess.run(
                [GO, "build", "-trimpath", "-o", str(binary), "."],
                cwd=work,
                env=dict(os.environ, CGO_ENABLED="0"),
                capture_output=True,
                text=True,
                timeout=300,
            )
            self.assertEqual(built.returncode, 0, built.stderr)
            nm = subprocess.run(
                [GO, "tool", "nm", str(binary)], capture_output=True, text=True, timeout=120
            )
            self.assertEqual(nm.returncode, 0, nm.stderr)
            symbols = [
                line.split(maxsplit=2)[-1]
                for line in nm.stdout.splitlines()
                if len(line.split(maxsplit=2)) == 3
            ]
            self.assertTrue(symbols, "go tool nm returned no symbols")
            present = frozenset(
                name
                for name in WATCHED
                if any(symbol == name or symbol.startswith(name + ".") for symbol in symbols)
            )
            absent = tuple(name for name in WATCHED if name not in present)
            print(
                "P0_HOST_SYMBOL_RECEIPT "
                f"go={version.stdout.strip()!r} "
                f"fixture={label!r} size={binary.stat().st_size} "
                f"present={tuple(sorted(present))!r} absent={absent!r}"
            )
        self._cache[label] = present
        return present

    def _example(self, name: str) -> frozenset[str]:
        return self._present(f"examples/{name}.ks", ROOT / "examples" / f"{name}.ks")

    def test_pure_program_links_no_network_filesystem_process_or_environment(self) -> None:
        present = self._example("hello")
        for family in (NETWORK, FILESYSTEM, PROCESS, ENVIRONMENT):
            self.assertEqual(present & family, frozenset())
        self.assertNotIn("time.Now", present)
        self.assertNotIn("crypto/rand.Read", present)

    def test_clock_program_adds_only_the_clock(self) -> None:
        with tempfile.TemporaryDirectory(prefix="koschei-p0-clock-") as tmp:
            path = pathlib.Path(tmp) / "main.ks"
            path.write_text(CLOCK_SOURCE, encoding="utf-8")
            clock = self._present("inline:clock", path)
        pure = self._example("hello")
        self.assertEqual(clock - pure, frozenset({"time.Now"}))

    def test_broker_program_links_no_network(self) -> None:
        # runtime_demo uses only the environment, through the native broker.
        present = self._example("runtime_demo")
        self.assertEqual(present & NETWORK, frozenset())
        self.assertEqual(present & ENVIRONMENT, frozenset(),
                         "environment is read by the broker, not the program binary")
        # The broker is a separate process, so its launcher is linked.
        self.assertEqual(present & PROCESS, PROCESS)
        print(f"P0_HOST_SYMBOL_DELTA fixture='examples/runtime_demo.ks' "
              f"added={tuple(sorted(present - self._example('hello')))!r}")

    def test_network_program_links_network(self) -> None:
        present = self._example("capability")
        self.assertTrue(NETWORK - {"net.Dial", "net/http.NewRequest"} <= present)
        print(f"P0_HOST_SYMBOL_DELTA fixture='examples/capability.ks' "
              f"added={tuple(sorted(present - self._example('hello')))!r}")


if __name__ == "__main__":
    unittest.main()
