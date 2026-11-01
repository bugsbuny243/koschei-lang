"""Executable foundation gates for Web, read-only Web3, AI, and kernel policy.

Tests the actual Koschei parser/checker/interpreter and, when Go exists,
the compiler-produced native artifact. No runtime effects are granted.
"""
from __future__ import annotations

import io
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

from koschei.capabilities import analyze_graph
from koschei.cli_entry import main as ks_main
from koschei.core_library_v1 import CORE_LIBRARY_MODULES_V1, describe_core_library
from koschei.modules import check_graph, load_graph

ROOT = Path(__file__).resolve().parents[1]
SAMPLE = ROOT / "examples" / "platform_foundation_v1" / "main.ks"
NAMES = ("platform_ai", "platform_kernel", "platform_web", "platform_web3")
EXPECTED = (
    "web=health denied=DENY\n"
    "web3=block-number signed=DENY\n"
    "ai=local-model denied=DENY\n"
    "kernel-claimed=true forged=false\n"
)


def run_source(path: Path) -> tuple[int, str, str]:
    stdout = io.StringIO()
    stderr = io.StringIO()
    with redirect_stdout(stdout), redirect_stderr(stderr):
        code = ks_main(["run", str(path)])
    return code, stdout.getvalue(), stderr.getvalue()


class PlatformFoundationV1Tests(unittest.TestCase):
    def test_registry_exposes_four_pure_modules(self) -> None:
        self.assertTrue(set(NAMES) <= set(CORE_LIBRARY_MODULES_V1))
        descriptions = {mod.name: mod for mod in describe_core_library()}
        expected = {
            "platform_web": {"route_path", "admit", "body_within_budget"},
            "platform_web3": {"hex_digit", "quantity", "address", "admit_read"},
            "platform_ai": {"admit", "batch_allowed"},
            "platform_kernel": {"frame_in_pool", "claimed_frame", "disjoint"},
        }
        for name, functions in expected.items():
            self.assertEqual({f.name for f in descriptions[name].functions}, functions)

    def test_sample_has_no_ambient_authority(self) -> None:
        graph = load_graph(SAMPLE)
        check_graph(graph)
        self.assertFalse(analyze_graph(graph).has_any)

    def test_sample_interpreter_and_native_match(self) -> None:
        outcome = run_source(SAMPLE)
        self.assertEqual(outcome, (0, EXPECTED, ""))
        if shutil.which("go") is None:
            self.skipTest("Go toolchain not available for native parity")
        with tempfile.TemporaryDirectory(prefix="ks-platform-native-") as tmp:
            binary = Path(tmp) / "platform_foundation"
            stdout, stderr = io.StringIO(), io.StringIO()
            with redirect_stdout(stdout), redirect_stderr(stderr):
                code = ks_main(["build", str(SAMPLE), "-o", str(binary)])
            self.assertEqual(code, 0, stderr.getvalue())
            self.assertTrue(binary.is_file())
            run = subprocess.run([str(binary)], capture_output=True,
                                 check=False, timeout=120)
            self.assertEqual(
                (run.returncode, run.stdout.decode("utf-8"), run.stderr.decode("utf-8")),
                outcome,
            )

    def test_adversarial_boundaries_fail_closed(self) -> None:
        checks = [
            # Strict HTTP route handling. No percent encoding, query,
            # path traversal, non-ASCII, ambiguous slashes or wildcards.
            ('platform_web.route_path("/health")', True),
            ('platform_web.route_path("/")', True),
            ('platform_web.route_path("")', False),
            ('platform_web.route_path("health")', False),
            ('platform_web.route_path("//health")', False),
            ('platform_web.route_path("/v1//status")', False),
            ('platform_web.route_path("/v1/status/")', False),
            ('platform_web.route_path("/../admin")', False),
            ('platform_web.route_path("/%2e%2e/admin")', False),
            ('platform_web.route_path("/health?debug=1")', False),
            ('platform_web.route_path("/ç")', False),
            ('platform_web.body_within_budget(1024, 1024)', True),
            ('platform_web.body_within_budget(1025, 1024)', False),
            ('platform_web.body_within_budget(-1, 1024)', False),
            ('platform_web.body_within_budget(0, 0)', False),
            ('platform_web.body_within_budget(0, 1048577)', False),
            # Noncanonical quantities/addresses and dangerous RPC verbs.
            ('platform_web3.quantity("0x0")', True),
            ('platform_web3.quantity("0x1")', True),
            ('platform_web3.quantity("0x")', False),
            ('platform_web3.quantity("0x01")', False),
            ('platform_web3.quantity("0xAB")', False),
            ('platform_web3.quantity("0xgg")', False),
            ('platform_web3.quantity("1")', False),
            ('platform_web3.address("0x0000000000000000000000000000000000000001")', True),
            ('platform_web3.address("0x00000000000000000000000000000000000000GG")', False),
            # No implicit AI model selection, resource overflows or empty prompts.
            ('platform_ai.batch_allowed(3, 4)', True),
            ('platform_ai.batch_allowed(0, 4)', False),
            ('platform_ai.batch_allowed(1, 129)', False),
            # 4KiB physical page validation and duplicate claim rejection.
            ('platform_kernel.frame_in_pool(1048576, 16, 1052672)', True),
            ('platform_kernel.frame_in_pool(1048576, 16, 1052673)', False),
            ('platform_kernel.frame_in_pool(1048576, 16, 1114112)', False),
            ('platform_kernel.frame_in_pool(1048576, 0, 1048576)', False),
            ('platform_kernel.frame_in_pool(1048576, 513, 1048576)', False),
            ('platform_kernel.frame_in_pool(1073737728, 2, 1073737728)', False),
            ('platform_kernel.claimed_frame(1048576, 16, [1048576, 1052672], 1052672)', True),
            ('platform_kernel.claimed_frame(1048576, 16, [1048576, 1048576], 1048576)', False),
            ('platform_kernel.claimed_frame(1048576, 16, [1048576, 2000000], 1048576)', False),
            ('platform_kernel.disjoint(1048576, 2, 1056768, 1)', True),
            ('platform_kernel.disjoint(1048576, 2, 1052672, 1)', False),
        ]
        denial_checks = [
            ('platform_web.admit("GET", "/health")', "health"),
            ('platform_web.admit("POST", "/health")', "DENY"),
            ('platform_web.admit("GET", "/v1/jobs")', "DENY"),
            ('platform_web.admit("POST", "/v1/jobs")', "jobs-create"),
            ('platform_web3.admit_read("eth_chainId", "0x1", "")', "chain-id"),
            ('platform_web3.admit_read("eth_getBalance", "0x1", "0x0000000000000000000000000000000000000001")', "balance"),
            ('platform_web3.admit_read("eth_sendRawTransaction", "0x1", "")', "DENY"),
            ('platform_web3.admit_read("eth_blockNumber", "0x01", "")', "DENY"),
            ('platform_web3.admit_read("eth_getBalance", "0x1", "")', "DENY"),
            ('platform_ai.admit("model-v1", ["model-v1"], 4096, 4096, 512)', "model-v1"),
            ('platform_ai.admit("other", ["model-v1"], 10, 4096, 512)', "DENY"),
            ('platform_ai.admit("model-v1", ["model-v1"], 4097, 4096, 512)', "DENY"),
            ('platform_ai.admit("model-v1", ["model-v1"], 32, 4096, 8193)', "DENY"),
            ('platform_ai.admit("model-v1", ["model-v1"], 0, 4096, 32)', "DENY"),
        ]
        body = []
        for idx, (expression, value) in enumerate(checks):
            expected = "true" if value else "false"
            body.append(f'    if {expression} != {expected} {{ println("FAIL boolean {idx}") }}')
        for idx, (expression, value) in enumerate(denial_checks):
            body.append(f'    let admitted_{idx} = {expression} or "DENY"')
            body.append(f'    if admitted_{idx} != "{value}" {{ println("FAIL deny {idx}") }}')
        body.append('    println("PLATFORM-FOUNDATION/1 PASS")')
        program = (
            "import platform_web\nimport platform_web3\n"
            "import platform_ai\nimport platform_kernel\n"
            "fn main() {\n" + "\n".join(body) + "\n}\n"
        )
        with tempfile.TemporaryDirectory(prefix="ks-platform-negative-") as tmp:
            target = Path(tmp) / "main.ks"
            target.write_text(program, encoding="utf-8")
            graph = load_graph(target)
            check_graph(graph)
            self.assertFalse(analyze_graph(graph).has_any)
            self.assertEqual(run_source(target), (0, "PLATFORM-FOUNDATION/1 PASS\n", ""))


if __name__ == "__main__":
    unittest.main()
