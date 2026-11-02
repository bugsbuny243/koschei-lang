"""Matrix horizon's pure Koschei decision gate against the durable Python rule.

The .ks module deliberately does NOT implement durable SQLite state, issuer
authentication or atomic tombstones. This test only compares the shared
cross-Matrix identity/epoch eligibility rules, plus .ks integrity checks.
"""
from __future__ import annotations

from contextlib import redirect_stderr, redirect_stdout
import hashlib
import io
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

from koschei.cli_entry import main as cli_main
from koschei.matrix_horizon_fence_v1 import DurableMatrixHorizonFence, MatrixHorizonFenceError
from koschei.matrix_reality_v1 import MatrixAdmission


def h(tag: str) -> str:
    return "sha3-256:" + hashlib.sha3_256(tag.encode()).hexdigest()


def record_digest(parts: list[str]) -> str:
    context = "koschei.matrix.horizon.proposal/v1"
    text = f"koschei.secure.digest/v1\n{len(context)}:{context}"
    for part in parts:
        text += f"\n{len(part)}:{part}"
    return h(text)


def admission(v: str, a: str, matrix: str, hara: str, epoch: int) -> MatrixAdmission:
    # Synthetic admissions for isolating the fence's *transition* checks.
    # The independent higher-level MatrixAdmission seal is out of scope.
    return MatrixAdmission(matrix, hara, a, v, h("mir"), epoch,
                           h("evidence"), h("admission"), 1)


def python_allows(old: MatrixAdmission, new: MatrixAdmission) -> bool:
    with DurableMatrixHorizonFence(":memory:") as fence:
        fence.initialize(old, cause_digest=h("genesis"))
        try:
            fence.advance(old, new, cause_digest=h("move"))
            return True
        except MatrixHorizonFenceError:
            return False


def decision_source(v: str, a: str, matrix: str, hara: str,
                    candidates: list[tuple[str, str, str, str, int]]) -> str:
    lines = [
        "import matrix_horizon",
        "fn outcome(value: Result<MatrixHorizonProposal, Error>) -> String {",
        "    return match value {",
        '        Ok(_) => "allow",',
        '        Err(_) => "deny",',
        "    }",
        "}",
        "fn main() {",
        f'    let current = matrix_horizon.genesis("{v}", "{a}", "{matrix}", "{hara}", 7, "{h("genesis")}") or return',
        '    println("canonical {matrix_horizon.is_canonical(current)}")',
        '    println("digest {current.record_digest}")',
    ]
    for n, (next_v, next_a, next_matrix, next_hara, epoch) in enumerate(candidates):
        lines.append(
            f'    println("case{n} {{outcome(matrix_horizon.propose_transition(current, '
            f'"{next_v}", "{next_a}", "{next_matrix}", "{next_hara}", '
            f'{epoch}, "{h("move")}"))}}")'
        )
    lines += ["}", ""]
    return "\n".join(lines)


class MatrixHorizonLibraryTests(unittest.TestCase):
    def run_case(self, source: str, *, native: bool = False) -> tuple[list[str], str]:
        with tempfile.TemporaryDirectory(prefix="matrix-horizon-lib-") as dirname:
            path = Path(dirname) / "main.ks"
            path.write_text(source, encoding="utf-8")
            stream, errors = io.StringIO(), io.StringIO()
            with redirect_stdout(stream), redirect_stderr(errors):
                code = cli_main(["run", "--max-steps", "1000000", str(path)])
            self.assertEqual(code, 0, errors.getvalue())
            output = stream.getvalue()
            if native and shutil.which("go"):
                binary = Path(dirname) / "matrix-horizon"
                with redirect_stdout(io.StringIO()), redirect_stderr(errors):
                    self.assertEqual(cli_main(["build", str(path), "-o", str(binary)]), 0,
                                     errors.getvalue())
                built = subprocess.run([str(binary)], capture_output=True, timeout=60,
                                       check=False)
                self.assertEqual(built.returncode, 0, built.stderr.decode())
                self.assertEqual(built.stdout.decode(), output)
            return output.splitlines(), errors.getvalue()

    def test_cross_matrix_policy_matches_durable_python_guard_and_native(self) -> None:
        v, a, matrix, hara = (h(x) for x in ("veyra", "aevra", "matrix-one", "hara-one"))
        other_matrix, other_hara = h("matrix-two"), h("hara-two")
        candidates = [
            (v, a, other_matrix, other_hara, 8),  # accept
            (v, a, matrix, other_hara, 8),  # same Matrix
            (v, a, other_matrix, hara, 8),  # same Hara
            (v, a, other_matrix, other_hara, 7),  # replay epoch
            (v, a, other_matrix, other_hara, 9),  # skipped epoch
            (h("wrong-veyra"), a, other_matrix, other_hara, 8),
            (v, h("wrong-aevra"), other_matrix, other_hara, 8),
            (v, a, other_matrix, other_hara, -1),
        ]
        old = admission(v, a, matrix, hara, 7)
        # Genesis deliberately uses the conventional all-zero previous hash.
        expected = ["canonical true", "digest " + record_digest(
            [v, a, matrix, hara, "7", "sha3-256:" + "0" * 64, h("genesis")]
        )]
        expected.extend(
            f"case{i} {'allow' if python_allows(old, admission(nv, na, nm, nh, epoch)) else 'deny'}"
            for i, (nv, na, nm, nh, epoch) in enumerate(candidates)
        )
        got, _ = self.run_case(decision_source(v, a, matrix, hara, candidates), native=True)
        self.assertEqual(got, expected)

    def test_forged_snapshot_and_malformed_digests_are_denied(self) -> None:
        v, a, m, hara = (h(x) for x in ("v", "a", "m", "h"))
        next_m, next_h = h("next-matrix"), h("next-hara")
        script = f"""
import matrix_horizon

fn decision(value: Result<MatrixHorizonProposal, Error>) -> String {{
    return match value {{
        Ok(_) => "allow",
        Err(_) => "deny",
    }}
}}
fn main() {{
    let first = matrix_horizon.genesis("{v}", "{a}", "{m}", "{hara}", 7, "{h("cause")}") or return
    let next = matrix_horizon.propose_transition(first, "{v}", "{a}", "{next_m}", "{next_h}", 8, "{h("next-cause")}") or return
    println("{{matrix_horizon.is_canonical(first)}} {{matrix_horizon.is_canonical(next)}}")
    println("{{matrix_horizon.matches_snapshot(next, "{v}", "{a}", "{next_m}", "{next_h}", 8)}}")
    println("{{matrix_horizon.matches_snapshot(next, "{v}", "{a}", "{m}", "{next_h}", 8)}}")
    let mut forged = next
    forged.epoch = 99
    println("{{matrix_horizon.is_canonical(forged)}} {{matrix_horizon.matches_snapshot(forged, "{v}", "{a}", "{next_m}", "{next_h}", 99)}}")
    println(decision(matrix_horizon.propose_transition(forged, "{v}", "{a}", "{m}", "{hara}", 100, "{h("next-cause")}")))
    println(decision(matrix_horizon.propose_transition(next, "{v}", "{a}", "{m}", "{hara}", 9, "{h("next-cause")}")))
    println(decision(matrix_horizon.genesis("not-a-digest", "{a}", "{m}", "{hara}", 7, "{h("cause")}")))
    println(decision(matrix_horizon.genesis("{v}", "{a}", "{m}", "{hara}", -1, "{h("cause")}")))
    println(decision(matrix_horizon.genesis("{v}", "{a}", "{m}", "{hara}", 7, "sha3-256:{"0" * 64}")))
}}
"""
        got, _ = self.run_case(script)
        self.assertEqual(got, [
            "true true", "true", "false", "false false",
            "deny", "deny", "deny", "deny", "deny",
        ])


if __name__ == "__main__":
    unittest.main()
