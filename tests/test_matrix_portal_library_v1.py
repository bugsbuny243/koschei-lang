"""Matrix portal: Koschei native/interpreter parity and Python policy comparison.

Both implementations refuse same Reality, invalid payload/target, empty effect,
negative epoch and changed transit identity. Digests deliberately use different
byte encodings; matching hex values are NOT expected and aren't forged here.
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
from koschei.matrix_portal_transit_v1 import (
    MatrixPortalTransitError, create_portal_transit_proof_v1,
    portal_matches_reality_v1,
)
from koschei.wanda_reality_integrity_v1 import commit_reality_v1


def d(tag: str) -> str:
    return "sha3-256:" + hashlib.sha3_256(tag.encode()).hexdigest()


def oracle() -> list[str]:
    source = commit_reality_v1(
        reality_id="AEGIS", epoch=4,
        state_digest=b"s" * 32, authority_digest=b"a" * 32)
    destination = commit_reality_v1(
        reality_id="FORGE", epoch=9,
        state_digest=b"d" * 32, authority_digest=b"b" * 32)
    changed = commit_reality_v1(
        reality_id="AEGIS", epoch=4,
        state_digest=b"x" * 32, authority_digest=b"a" * 32)
    proof = create_portal_transit_proof_v1(
        source=source, destination=destination,
        payload_digest=b"p" * 32, effect="compile",
        target_digest=b"t" * 32, epoch=11)
    values = [
        portal_matches_reality_v1(proof, source=source, destination=destination,
            payload_digest=b"p" * 32, effect="compile", target_digest=b"t" * 32, epoch=11),
        portal_matches_reality_v1(proof, source=changed, destination=destination,
            payload_digest=b"p" * 32, effect="compile", target_digest=b"t" * 32, epoch=11),
        portal_matches_reality_v1(proof, source=source, destination=destination,
            payload_digest=b"z" * 32, effect="compile", target_digest=b"t" * 32, epoch=11),
        portal_matches_reality_v1(proof, source=source, destination=destination,
            payload_digest=b"p" * 32, effect="send", target_digest=b"t" * 32, epoch=11),
        portal_matches_reality_v1(proof, source=source, destination=destination,
            payload_digest=b"p" * 32, effect="compile", target_digest=b"z" * 32, epoch=11),
        portal_matches_reality_v1(proof, source=source, destination=destination,
            payload_digest=b"p" * 32, effect="compile", target_digest=b"t" * 32, epoch=12),
    ]
    for args in [
        dict(source=source, destination=source, payload_digest=b"p" * 32,
             effect="compile", target_digest=b"t" * 32, epoch=11),
        dict(source=source, destination=destination, payload_digest=b"p" * 31,
             effect="compile", target_digest=b"t" * 32, epoch=11),
        dict(source=source, destination=destination, payload_digest=b"p" * 32,
             effect="", target_digest=b"t" * 32, epoch=11),
        dict(source=source, destination=destination, payload_digest=b"p" * 32,
             effect="compile", target_digest=b"t" * 32, epoch=-1),
    ]:
        try:
            create_portal_transit_proof_v1(**args)
        except MatrixPortalTransitError:
            values.append(False)
        else:
            values.append(True)
    return [str(value).lower() for value in values]


class MatrixPortalLibraryTests(unittest.TestCase):
    def run_program(self, program: str, *, native: bool = False) -> list[str]:
        with tempfile.TemporaryDirectory(prefix="koschei-matrix-portal-") as directory:
            path = Path(directory) / "main.ks"
            path.write_text(program, encoding="utf-8")
            errors, stdout = io.StringIO(), io.StringIO()
            with redirect_stdout(stdout), redirect_stderr(errors):
                code = cli_main(["run", "--max-steps", "3000000", str(path)])
            self.assertEqual(code, 0, errors.getvalue())
            if native and shutil.which("go"):
                binary = Path(directory) / "portal"
                with redirect_stdout(io.StringIO()), redirect_stderr(errors):
                    self.assertEqual(
                        cli_main(["build", str(path), "-o", str(binary)]), 0,
                        errors.getvalue())
                completed = subprocess.run(
                    [str(binary)], capture_output=True, timeout=90, check=False)
                self.assertEqual(completed.returncode, 0, completed.stderr.decode())
                self.assertEqual(completed.stdout.decode(), stdout.getvalue())
            return stdout.getvalue().splitlines()

    def test_portal_matches_python_guard_decisions_and_native_output(self) -> None:
        source = """
import secure
import wanda
import matrix_portal

fn allowed(value: Result<PortalTransitProposal, Error>) -> Bool {
    return match value {
        Ok(_) => true,
        Err(_) => false,
    }
}
fn main() {
    let ss = secure.hash("source-state") or return
    let sa = secure.hash("source-authority") or return
    let ds = secure.hash("destination-state") or return
    let da = secure.hash("destination-authority") or return
    let source = wanda.commit("AEGIS", 4, ss, sa, secure.zero_digest()) or return
    let destination = wanda.commit("FORGE", 9, ds, da, secure.zero_digest()) or return
    let changed_state = secure.hash("changed-source") or return
    let changed = wanda.commit("AEGIS", 4, changed_state, sa, secure.zero_digest()) or return
    let payload = secure.hash("payload") or return
    let target = secure.hash("target") or return
    let other_payload = secure.hash("other-payload") or return
    let other_target = secure.hash("other-target") or return
    let proof = matrix_portal.propose(source, destination, payload, "compile", target, 11) or return
    println(matrix_portal.matches(proof, source, destination, payload, "compile", target, 11))
    println(matrix_portal.matches(proof, changed, destination, payload, "compile", target, 11))
    println(matrix_portal.matches(proof, source, destination, other_payload, "compile", target, 11))
    println(matrix_portal.matches(proof, source, destination, payload, "send", target, 11))
    println(matrix_portal.matches(proof, source, destination, payload, "compile", other_target, 11))
    println(matrix_portal.matches(proof, source, destination, payload, "compile", target, 12))
    println(allowed(matrix_portal.propose(source, source, payload, "compile", target, 11)))
    println(allowed(matrix_portal.propose(source, destination, "bad-digest", "compile", target, 11)))
    println(allowed(matrix_portal.propose(source, destination, payload, "", target, 11)))
    println(allowed(matrix_portal.propose(source, destination, payload, "compile", target, -1)))
}
"""
        self.assertEqual(self.run_program(source, native=True), oracle())

    def test_forged_proof_and_noncanonical_wanda_commitments_fail_closed(self) -> None:
        source = """
import secure
import wanda
import matrix_portal

fn accepted(value: Result<PortalTransitProposal, Error>) -> Bool {
    return match value {
        Ok(_) => true,
        Err(_) => false,
    }
}
fn main() {
    let ss = secure.hash("source-state") or return
    let sa = secure.hash("source-authority") or return
    let ds = secure.hash("destination-state") or return
    let da = secure.hash("destination-authority") or return
    let payload = secure.hash("payload") or return
    let target = secure.hash("target") or return
    let source = wanda.commit("AEGIS", 4, ss, sa, secure.zero_digest()) or return
    let destination = wanda.commit("FORGE", 9, ds, da, secure.zero_digest()) or return
    let proof = matrix_portal.propose(source, destination, payload, "compile", target, 11) or return
    let mut fake_proof = proof
    fake_proof.effect = "send"
    println(matrix_portal.matches(fake_proof, source, destination, payload, "compile", target, 11))
    let mut forged_digest = proof
    forged_digest.transit_digest = secure.hash("forged") or return
    println(matrix_portal.matches(forged_digest, source, destination, payload, "compile", target, 11))
    let mut forged_source = source
    forged_source.epoch = 17
    println(accepted(matrix_portal.propose(forged_source, destination, payload, "compile", target, 11)))
    println(matrix_portal.matches(proof, forged_source, destination, payload, "compile", target, 11))
    let mut forged_dest = destination
    let other_state = secure.hash("other-state") or return
    forged_dest.state_digest = other_state
    println(accepted(matrix_portal.propose(source, forged_dest, payload, "compile", target, 11)))
    println(matrix_portal.matches(proof, source, forged_dest, payload, "compile", target, 11))
    println(accepted(matrix_portal.propose(source, destination, payload, "compile", target, 11)))
}
"""
        self.assertEqual(self.run_program(source), [
            "false", "false", "false", "false", "false", "false", "true"
        ])


if __name__ == "__main__":
    unittest.main()
