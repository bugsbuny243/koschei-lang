"""Clock and random capabilities (G3).

Values differ from run to run, so the tests compare what must not differ:
shapes, bounds, rounding, budgets and Error values, in `ks run` and in the
MIR-Go binary.
"""
from __future__ import annotations

from contextlib import redirect_stderr, redirect_stdout
import io
from pathlib import Path
import shutil
import subprocess
import tempfile
import time
import unittest

from koschei.capability_effect_contract_v1 import (
    CLOCK_READ,
    POWER_DOMAIN_DATA,
    RANDOM_READ,
    require_capability_method_same_power_domain,
)
from koschei.cli_entry import main as cli_main
from koschei.mir_go_native import generate_go_mir_native, inspect_mir_go_support
from koschei.modules import check_graph, load_graph
from koschei.semantic import SemanticError

GO = shutil.which("go")

# Prints only facts that hold on every run.
FACTS = """
fn spend(random: RandomCaps) -> Int {
    let mut ok = 0
    let a = random.hex(8) or ""
    if a.length() == 16 {
        ok = ok + 1
    }
    let b = random.hex(8) or ""
    if b.length() == 16 {
        ok = ok + 1
    }
    let token = random.hex(1) or "budget"
    println(token)
    let die = random.below(6) or 99
    println(die)
    println(random.hex(0))
    println(random.below(0))
    return ok
}

fn main(caps: SystemCaps) {
    let clock = caps.clock.allow(1000)
    let now = clock.now_ms()
    println(now % 1000 == 0)
    println(now > 1700000000000)
    let first = clock.monotonic_ms()
    let second = clock.monotonic_ms()
    println(second >= first)
    println(spend(caps.random.allow(16)))
    let small = caps.random.allow(16)
    let n = small.below(6) or 99
    println(n >= 0 && n < 6)
    let m = small.below(1) or 99
    println(m)
    println(small.below(6))
    println(small.hex(1025))
}
"""

EXPECTED = [
    "true",
    "true",
    "true",
    "budget",
    "99",
    "KS3451: random.hex() bayt sayısı 1..1024 aralığında olmalıdır.",
    "KS3451: random.below() üst sınırı en az 1 olmalıdır.",
    "2",
    "true",
    "0",
    "KS3450: Rastgele sayı bütçesi tükendi: bu yetki en fazla 16 bayt üretebilir.",
    "KS3451: random.hex() bayt sayısı 1..1024 aralığında olmalıdır.",
]

SAMPLES = """
fn main(caps: SystemCaps) {
    let clock = caps.clock.allow(1)
    println(clock.now_ms())
    let random = caps.random.allow(1048576)
    let mut i = 0
    while i < 200 {
        println(random.below(10) or 99)
        i = i + 1
    }
    println(random.hex(32) or "")
}
"""


class ClockRandomTests(unittest.TestCase):
    def write(self, source: str) -> Path:
        temporary = tempfile.TemporaryDirectory(prefix="koschei-clock-random-")
        self.addCleanup(temporary.cleanup)
        path = Path(temporary.name) / "main.ks"
        path.write_text(source, encoding="utf-8")
        return path

    def ks_run(self, path: Path) -> list[str]:
        stdout = io.StringIO()
        with redirect_stdout(stdout), redirect_stderr(io.StringIO()) as errors:
            self.assertEqual(cli_main(["run", str(path)]), 0, errors.getvalue())
        return stdout.getvalue().splitlines()

    def native(self, path: Path) -> list[str]:
        binary = path.parent / "app"
        with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()) as errors:
            self.assertEqual(cli_main(["build", str(path), "-o", str(binary)]), 0, errors.getvalue())
        completed = subprocess.run([str(binary)], capture_output=True, timeout=60, check=False)
        self.assertEqual(completed.returncode, 0, completed.stderr)
        return completed.stdout.decode("utf-8").splitlines()

    def check_error(self, source: str) -> str:
        graph = load_graph(self.write(source))
        with self.assertRaises(SemanticError) as caught:
            check_graph(graph)
        return caught.exception.code

    def test_the_checker_bounds_both_domains(self) -> None:
        cases = {
            "let n = 5\n    let c = caps.clock.allow(n)": "KS2440",
            "let c = caps.clock.allow(0)": "KS2441",
            "let c = caps.clock.allow(86400001)": "KS2441",
            "let t = caps.clock.now_ms()": "KS2402",
            "let r = caps.random.allow()": "KS2450",
            "let r = caps.random.allow(1048577)": "KS2451",
            "let r = caps.random.allow(8)\n    let x = r.hex()": "KS1301",
            'let r = caps.random.allow(8)\n    let x = r.hex("8")': "KS1301",
            "let r = caps.random.allow(8)\n    let wider = r.allow(9)": "KS2403",
            "let c = caps.clock.allow(5)\n    let x = c.sleep(5)": "KS2404",
        }
        for body, code in cases.items():
            with self.subTest(body):
                self.assertEqual(
                    self.check_error(f"fn main(caps: SystemCaps) {{\n    {body}\n}}\n"), code
                )

    def test_reading_time_or_randomness_is_an_effect(self) -> None:
        source = (
            "pure fn stamp(clock: ClockCaps) -> Int {\n    return clock.now_ms()\n}\n\n"
            "fn main(caps: SystemCaps) {\n    println(stamp(caps.clock.allow(1000)))\n}\n"
        )
        self.assertEqual(self.check_error(source), "KS3940")
        for capability, method, effect in (
            ("ClockCaps", "now_ms", CLOCK_READ),
            ("RandomCaps", "below", RANDOM_READ),
        ):
            self.assertEqual(
                require_capability_method_same_power_domain(capability, method),
                (effect, POWER_DOMAIN_DATA),
            )

    def test_the_manifest_shows_resolution_and_budget(self) -> None:
        stdout = io.StringIO()
        with redirect_stdout(stdout), redirect_stderr(io.StringIO()):
            self.assertEqual(cli_main(["caps", str(self.write(FACTS))]), 0)
        manifest = stdout.getvalue()
        self.assertIn("SAAT:", manifest)
        self.assertIn("resolution_ms=1000", manifest)
        self.assertIn("RASTGELE SAYI:", manifest)
        self.assertIn("bytes=16", manifest)

    def test_ks_run_keeps_every_rule(self) -> None:
        self.assertEqual(self.ks_run(self.write(FACTS)), EXPECTED)

    def test_samples_are_in_range(self) -> None:
        before = time.time_ns() // 1_000_000
        lines = self.ks_run(self.write(SAMPLES))
        after = time.time_ns() // 1_000_000
        self.assert_samples(lines, before, after)

    def assert_samples(self, lines: list[str], before: int, after: int) -> None:
        self.assertTrue(before <= int(lines[0]) <= after)
        draws = [int(item) for item in lines[1:201]]
        self.assertTrue(all(0 <= item < 10 for item in draws))
        self.assertGreater(len(set(draws)), 5)
        token = lines[201]
        self.assertEqual(len(token), 64)
        self.assertTrue(set(token) <= set("0123456789abcdef"))

    @unittest.skipIf(GO is None, "Go toolchain is not installed")
    def test_the_native_binary_keeps_every_rule(self) -> None:
        self.assertEqual(self.native(self.write(FACTS)), EXPECTED)

    @unittest.skipIf(GO is None, "Go toolchain is not installed")
    def test_native_samples_are_in_range(self) -> None:
        path = self.write(SAMPLES)
        binary = path.parent / "app"
        with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
            self.assertEqual(cli_main(["build", str(path), "-o", str(binary)]), 0)
        before = time.time_ns() // 1_000_000
        completed = subprocess.run([str(binary)], capture_output=True, timeout=60, check=True)
        after = time.time_ns() // 1_000_000
        self.assert_samples(completed.stdout.decode().splitlines(), before, after)

    def test_each_runtime_is_emitted_only_when_used(self) -> None:
        clock_only = (
            "fn main(caps: SystemCaps) {\n    let c = caps.clock.allow(10)\n"
            "    println(c.now_ms() > 0)\n}\n"
        )
        graph = load_graph(self.write(clock_only))
        check_graph(graph)
        self.assertTrue(inspect_mir_go_support(graph.mir).supported)
        source = generate_go_mir_native(graph.mir)
        self.assertIn('"time"', source)
        self.assertNotIn('"crypto/rand"', source)
        self.assertNotIn("_ksInputReadText", source)


if __name__ == "__main__":
    unittest.main()
