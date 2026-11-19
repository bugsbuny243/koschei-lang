"""The Koschei `galaxy_identity` module agrees with the Python one.

`koschei/core_library/galaxy_identity.ks` ports
`koschei/galaxy_identity_v1.py`: Veyra and Aevra birth and seal checks, with
byte-identical SHA-256 seals and the same refusal messages. The native MIR is
sealed by the compiler in both: the Python side gets a stand-in whose seal
check passes, the Koschei side a `GalaxyMir`. The full chain (Veyra, Aevra,
then `matrix_reality`'s Matrix, Hara and admission through `matrix_host`) is
checked too, under `ks run` and as a `ks build` binary.
"""
from __future__ import annotations

import random
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace
import unittest

from koschei.galaxy_identity_v1 import (
    AevraIdentity,
    GalaxyIdentityError,
    VeyraIdentity,
    birth_aevra,
    birth_veyra,
)
from koschei.matrix_reality_v1 import admit_matrix_hara, birth_hara, birth_matrix

GO = shutil.which("go")
SIGILS = [("⟁", "payments.settle"), ("⧉", "ledger.read"), ("⟁", "payments.refund"), ("◈", "ağ.yaz")]


def _mir(fingerprint: str, bindings: list[tuple[str, str]]):
    return SimpleNamespace(
        fingerprint=fingerprint,
        bindings=tuple(SimpleNamespace(sigil=s, subject=t) for s, t in bindings),
        assert_sealed=lambda: None,
    )


def _ks_mir(fingerprint: str, bindings: list[tuple[str, str]]) -> str:
    items = ", ".join(f'GalaxyBinding {{ sigil: "{s}", subject: "{t}" }}' for s, t in bindings)
    return f'GalaxyMir {{ fingerprint: "{fingerprint}", bindings: [{items}] }}'


def _digest(rng: random.Random) -> str:
    roll = rng.random()
    if roll < 0.03:
        return "0" * 64
    if roll < 0.05:
        return "ab" * 31
    if roll < 0.07:
        return "g" + "a" * 63
    text = "".join(rng.choice("0123456789abcdef") for _ in range(64))
    return text.upper() if roll < 0.2 else text


def _cases(seed: int, count: int) -> tuple[str, list[str]]:
    rng = random.Random(seed)
    functions: list[str] = []
    calls: list[str] = []
    expected: list[str] = []
    for index in range(count):
        digests = [_digest(rng) for _ in range(4)]
        veyra_epoch = rng.choice([-1, 0, 2, 2, 5])
        mir = _mir(f"mir-{index}", SIGILS)
        sigil, subject = rng.choice(SIGILS + [("⟁", "ledger.read"), ("◈", "")])
        aevra_epoch = veyra_epoch + rng.choice([-1, 0, 1, 1, 2])
        evidence = _digest(rng)
        matrix_epoch = aevra_epoch + rng.choice([0, 1])
        hara_epoch = matrix_epoch + rng.choice([0, 1])
        instance, reality, horizon, admission_evidence = (_digest(rng) for _ in range(4))
        lines = [f"fn case{index}() {{"]
        lines.append(f'    let veyra = galaxy_identity.birth_veyra("{digests[0]}", "{digests[1]}", "{digests[2]}", "{digests[3]}", {veyra_epoch}) or {{')
        lines.append('        println("veyra refused")')
        lines.append("        return")
        lines.append("    }")
        lines.append("    println(veyra.digest)")
        lines.append(f"    let mir = {_ks_mir(f'mir-{index}', SIGILS)}")
        lines.append(f'    show_aevra(galaxy_identity.birth_aevra(veyra, mir, "{sigil}", "{subject}", "{evidence}", {aevra_epoch}), veyra, mir)')
        lines.append(f'    let aevra = galaxy_identity.birth_aevra(veyra, mir, "{sigil}", "{subject}", "{evidence}", {aevra_epoch}) or {{')
        lines.append("        return")
        lines.append("    }")
        lines.append("    let host = galaxy_identity.matrix_host(veyra, aevra, mir) or {")
        lines.append("        return")
        lines.append("    }")
        lines.append(f'    let matrix = matrix_reality.birth_matrix(host, "{instance}", "{reality}", {matrix_epoch}) or {{')
        lines.append('        println("matrix refused")')
        lines.append("        return")
        lines.append("    }")
        lines.append(f'    let hara = matrix_reality.birth_hara(matrix, host, "{horizon}", {hara_epoch}) or {{')
        lines.append('        println("hara refused")')
        lines.append("        return")
        lines.append("    }")
        lines.append(f'    let admission = matrix_reality.admit(matrix, hara, host, "{admission_evidence}") or {{')
        lines.append('        println("admission refused")')
        lines.append("        return")
        lines.append("    }")
        lines.append("    println(admission.digest)")
        lines.append("}")
        functions.extend(lines)
        calls.append(f"    case{index}()")

        try:
            veyra = birth_veyra(profile_digest=digests[0], genesis_digest=digests[1],
                                constitution_digest=digests[2], instance_digest=digests[3],
                                birth_epoch=veyra_epoch)
        except GalaxyIdentityError:
            expected.append("veyra refused")
            continue
        expected.append(veyra.digest)
        try:
            aevra = birth_aevra(veyra, mir, sigil=sigil, subject=subject,
                                birth_evidence_digest=evidence, birth_epoch=aevra_epoch)
        except GalaxyIdentityError as error:
            expected.append(f"error {error}")
            continue
        expected.extend([aevra.digest, "ok"])
        for step in ("matrix", "hara", "admission"):
            try:
                if step == "matrix":
                    matrix = birth_matrix(veyra, instance_digest=instance, reality_commitment_digest=reality, birth_epoch=matrix_epoch)
                elif step == "hara":
                    hara = birth_hara(matrix, veyra, aevra, mir, horizon_commitment_digest=horizon, epoch=hara_epoch)
                else:
                    admission = admit_matrix_hara(matrix, hara, veyra, aevra, mir, evidence_digest=admission_evidence)
                    expected.append(admission.digest)
            except Exception:
                expected.append(f"{step} refused")
                break

    source = "\n".join([
        "import galaxy_identity",
        "import matrix_reality",
        "",
        "fn show_aevra(result: Result<AevraIdentity, Error>, veyra: VeyraIdentity, mir: GalaxyMir) {",
        "    match result {",
        "        Ok(aevra) => {",
        "            println(aevra.digest)",
        '            let problem = galaxy_identity.aevra_problem(aevra, veyra, mir)',
        '            if problem == "" {',
        '                println("ok")',
        "            } else {",
        "                println(problem)",
        "            }",
        "        },",
        '        Err(error) => println("error {error}"),',
        "    }",
        "}",
        "",
        *functions,
        "",
        "fn main() {",
        *calls,
        "}",
        "",
    ])
    return source, expected


def _tamper_expectations() -> list[str]:
    veyra = birth_veyra(profile_digest="1" * 64, genesis_digest="2" * 64, constitution_digest="3" * 64, instance_digest="4" * 64, birth_epoch=1)
    mir = _mir("mir-a", SIGILS)
    aevra = birth_aevra(veyra, mir, sigil="⟁", subject="payments.settle", birth_evidence_digest="5" * 64, birth_epoch=2)
    out = []
    for check in (
        lambda: VeyraIdentity(veyra.profile_digest, veyra.genesis_digest, veyra.constitution_digest, veyra.instance_digest, 9, veyra.digest).assert_sealed(),
        lambda: aevra.assert_sealed(veyra, _mir("mir-b", SIGILS)),
        lambda: aevra.assert_sealed(veyra, _mir("mir-a", [("⧉", "ledger.read")])),
        lambda: aevra.assert_sealed(veyra, _mir("mir-a", [("⟁", "payments.refund")])),
        lambda: AevraIdentity(aevra.veyra_digest, aevra.native_mir_fingerprint, aevra.sigil, aevra.semantic_subject_digest, "6" * 64, aevra.birth_epoch, aevra.digest).assert_sealed(veyra, mir),
    ):
        try:
            check()
            out.append("")
        except GalaxyIdentityError as error:
            out.append(str(error))
    return out


TAMPER = r'''
import galaxy_identity

fn main() {
    let veyra = galaxy_identity.birth_veyra("1111111111111111111111111111111111111111111111111111111111111111", "2222222222222222222222222222222222222222222222222222222222222222", "3333333333333333333333333333333333333333333333333333333333333333", "4444444444444444444444444444444444444444444444444444444444444444", 1) or return
    let settle = GalaxyBinding { sigil: "⟁", subject: "payments.settle" }
    let read = GalaxyBinding { sigil: "⧉", subject: "ledger.read" }
    let refund = GalaxyBinding { sigil: "⟁", subject: "payments.refund" }
    let write = GalaxyBinding { sigil: "◈", subject: "ağ.yaz" }
    let mir = GalaxyMir { fingerprint: "mir-a", bindings: [settle, read, refund, write] }
    let aevra = galaxy_identity.birth_aevra(veyra, mir, "⟁", "payments.settle", "5555555555555555555555555555555555555555555555555555555555555555", 2) or return
    let reborn = VeyraIdentity { profile_digest: veyra.profile_digest, genesis_digest: veyra.genesis_digest, constitution_digest: veyra.constitution_digest, instance_digest: veyra.instance_digest, birth_epoch: 9, digest: veyra.digest }
    println(galaxy_identity.veyra_problem(reborn))
    println(galaxy_identity.aevra_problem(aevra, veyra, GalaxyMir { fingerprint: "mir-b", bindings: mir.bindings }))
    println(galaxy_identity.aevra_problem(aevra, veyra, GalaxyMir { fingerprint: "mir-a", bindings: [read] }))
    println(galaxy_identity.aevra_problem(aevra, veyra, GalaxyMir { fingerprint: "mir-a", bindings: [refund] }))
    let forged = AevraIdentity { veyra_digest: aevra.veyra_digest, native_mir_fingerprint: aevra.native_mir_fingerprint, sigil: aevra.sigil, semantic_subject_digest: aevra.semantic_subject_digest, birth_evidence_digest: "6666666666666666666666666666666666666666666666666666666666666666", birth_epoch: aevra.birth_epoch, digest: aevra.digest }
    println(galaxy_identity.aevra_problem(forged, veyra, mir))
}
'''


def _run(command: list[str], cwd: Path) -> tuple[str, str, int]:
    done = subprocess.run(command, cwd=cwd, capture_output=True, text=True, timeout=600)
    return done.stdout, done.stderr, done.returncode


class GalaxyIdentityLibraryTests(unittest.TestCase):
    def execute(self, source: str) -> str:
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            (base / "main.ks").write_text(source, encoding="utf-8")
            interpreted = _run([sys.executable, "-m", "koschei", "run", "--max-steps", "50000000", "main.ks"], base)
            self.assertEqual(interpreted[2], 0, interpreted[1])
            if GO:
                compiled = _run([sys.executable, "-m", "koschei", "build", "main.ks", "-o", "app"], base)
                self.assertEqual(compiled[2], 0, compiled[1])
                self.assertEqual(_run([str(base / "app")], base), interpreted)
        return interpreted[0]

    def test_random_chains_match_python(self) -> None:
        source, expected = _cases(20261119, 30)
        self.assertEqual(self.execute(source).splitlines(), expected)

    def test_tampered_identities_give_the_python_reason(self) -> None:
        self.assertEqual(self.execute(TAMPER).splitlines(), _tamper_expectations())


if __name__ == "__main__":
    unittest.main()
