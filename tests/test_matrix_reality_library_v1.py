"""The Koschei `matrix_reality` library module agrees with the Python one.

`koschei/core_library/matrix_reality.ks` ports `koschei/matrix_reality_v1.py`:
Matrix birth, Hara birth and Matrix/Hara admission, each with its seal check.
Seals are SHA-256 over the Python byte layout, so the hex values must be
identical, and every refusal must give the Python message. Veyra and Aevra
are sealed by the host in both: the Python side gets stand-ins whose seal
check passes, the Koschei side a `MatrixHost`. The generated program runs
under `ks run` and as a `ks build` binary.
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

from koschei.matrix_reality_v1 import (
    HaraIdentity,
    MatrixAdmission,
    MatrixIdentity,
    MatrixRealityError,
    admit_matrix_hara,
    birth_hara,
    birth_matrix,
)

GO = shutil.which("go")


def _host(veyra: str, veyra_epoch: int, aevra: str, aevra_epoch: int, mir: str):
    veyra_value = SimpleNamespace(digest=veyra, birth_epoch=veyra_epoch, assert_sealed=lambda: None)
    aevra_value = SimpleNamespace(digest=aevra, birth_epoch=aevra_epoch, assert_sealed=lambda *_: None)
    return veyra_value, aevra_value, SimpleNamespace(fingerprint=mir)


def _digest(rng: random.Random) -> str:
    roll = rng.random()
    if roll < 0.03:
        return "0" * 64
    if roll < 0.06:
        return "ab" * 31
    if roll < 0.09:
        return "g" + "a" * 63
    text = "".join(rng.choice("0123456789abcdef") for _ in range(64))
    return text.upper() if roll < 0.2 else text


def _ks(text: str) -> str:
    return '"' + text + '"'


def _matrix(value: MatrixIdentity) -> str:
    return (
        f"MatrixIdentity {{ veyra_digest: {_ks(value.veyra_digest)}, instance_digest: {_ks(value.instance_digest)}, "
        f"reality_commitment_digest: {_ks(value.reality_commitment_digest)}, birth_epoch: {value.birth_epoch}, "
        f"digest: {_ks(value.digest)} }}"
    )


def _hara(value: HaraIdentity) -> str:
    return (
        f"HaraIdentity {{ matrix_digest: {_ks(value.matrix_digest)}, aevra_digest: {_ks(value.aevra_digest)}, "
        f"horizon_commitment_digest: {_ks(value.horizon_commitment_digest)}, epoch: {value.epoch}, "
        f"digest: {_ks(value.digest)} }}"
    )


def _cases(seed: int, count: int) -> tuple[str, list[str]]:
    rng = random.Random(seed)
    body: list[str] = []
    calls: list[str] = []
    expected: list[str] = []
    for index in range(count):
        veyra = "".join(rng.choice("0123456789abcdef") for _ in range(64))
        aevra = "".join(rng.choice("0123456789abcdef") for _ in range(64))
        mir = "mir-" + str(rng.randrange(1000))
        veyra_epoch, aevra_epoch = rng.choice([0, 3]), rng.choice([0, 2, 6])
        host = f"MatrixHost {{ veyra_digest: {_ks(veyra)}, veyra_birth_epoch: {veyra_epoch}, aevra_digest: {_ks(aevra)}, aevra_birth_epoch: {aevra_epoch}, mir_fingerprint: {_ks(mir)} }}"
        v, a, m = _host(veyra, veyra_epoch, aevra, aevra_epoch, mir)
        instance, reality, horizon, evidence = (_digest(rng) for _ in range(4))
        matrix_epoch = veyra_epoch + rng.choice([-1, 0, 1, 2, 2])
        hara_epoch = max(matrix_epoch, aevra_epoch) + rng.choice([-1, 0, 1, 1, 3])
        body.append(f"fn case{index}() {{")
        body.append(f"    let h{index} = {host}")
        call = f"matrix_reality.birth_matrix(h{index}, {_ks(instance)}, {_ks(reality)}, {matrix_epoch})"
        body.append(f"    show_matrix({call})")
        body.append(f"    let m{index} = {call} or {{")
        body.append("        return")
        body.append("    }")
        calls.append(f"    case{index}()")
        try:
            matrix = birth_matrix(v, instance_digest=instance, reality_commitment_digest=reality, birth_epoch=matrix_epoch)
        except MatrixRealityError as error:
            expected.append(f"error {error}")
            body.append("}")
            continue
        expected.append(matrix.digest)
        body.append(f"    show_hara(matrix_reality.birth_hara(m{index}, h{index}, {_ks(horizon)}, {hara_epoch}))")
        try:
            hara = birth_hara(matrix, v, a, m, horizon_commitment_digest=horizon, epoch=hara_epoch)
        except MatrixRealityError as error:
            expected.append(f"error {error}")
            body.append("}")
            continue
        expected.append(hara.digest)
        body.append(f"    let a{index} = {_hara(hara)}")
        body.append(f"    show_admission(matrix_reality.admit(m{index}, a{index}, h{index}, {_ks(evidence)}), m{index}, a{index}, h{index})")
        body.append("}")
        try:
            admission = admit_matrix_hara(matrix, hara, v, a, m, evidence_digest=evidence)
        except MatrixRealityError as error:
            expected.append(f"error {error}")
            continue
        expected.extend([admission.digest, "true"])

    source = "\n".join([
        "import matrix_reality",
        "",
        "fn show_matrix(result: Result<MatrixIdentity, Error>) {",
        "    match result {",
        "        Ok(matrix) => println(matrix.digest),",
        '        Err(error) => println("error {error}"),',
        "    }",
        "}",
        "",
        "fn show_hara(result: Result<HaraIdentity, Error>) {",
        "    match result {",
        "        Ok(hara) => println(hara.digest),",
        '        Err(error) => println("error {error}"),',
        "    }",
        "}",
        "",
        "fn show_admission(result: Result<MatrixAdmission, Error>, matrix: MatrixIdentity, hara: HaraIdentity, host: MatrixHost) {",
        "    match result {",
        "        Ok(admission) => {",
        "            println(admission.digest)",
        "            println(matrix_reality.is_admitted(admission, matrix, hara, host))",
        "        },",
        '        Err(error) => println("error {error}"),',
        "    }",
        "}",
        "",
        *body,
        "",
        "fn main() {",
        *calls,
        "}",
        "",
    ])
    return source, expected


def _tamper_expectations() -> list[str]:
    veyra, aevra = "1" * 64, "2" * 64
    v, a, m = _host(veyra, 1, aevra, 1, "mir-a")
    matrix = birth_matrix(v, instance_digest="3" * 64, reality_commitment_digest="4" * 64, birth_epoch=2)
    hara = birth_hara(matrix, v, a, m, horizon_commitment_digest="5" * 64, epoch=3)
    admission = admit_matrix_hara(matrix, hara, v, a, m, evidence_digest="6" * 64)
    out = []
    for check in (
        lambda: MatrixIdentity(matrix.veyra_digest, matrix.instance_digest, matrix.reality_commitment_digest, 9, matrix.digest).assert_sealed(v),
        lambda: matrix.assert_sealed(SimpleNamespace(digest="9" * 64, birth_epoch=1, assert_sealed=lambda: None)),
        lambda: HaraIdentity(hara.matrix_digest, "7" * 64, hara.horizon_commitment_digest, hara.epoch, hara.digest).assert_sealed(matrix, v, a, m),
        lambda: admission.assert_sealed(matrix, hara, v, a, SimpleNamespace(fingerprint="mir-b")),
        lambda: MatrixAdmission(*[admission.matrix_digest, admission.hara_digest, admission.aevra_digest, admission.veyra_digest, admission.native_mir_fingerprint, admission.epoch, "8" * 64, admission.digest]).assert_sealed(matrix, hara, v, a, m),
    ):
        try:
            check()
            out.append("")
        except MatrixRealityError as error:
            out.append(str(error))
    return out


TAMPER = r'''
import matrix_reality

fn main() {
    let host = MatrixHost { veyra_digest: "1111111111111111111111111111111111111111111111111111111111111111", veyra_birth_epoch: 1, aevra_digest: "2222222222222222222222222222222222222222222222222222222222222222", aevra_birth_epoch: 1, mir_fingerprint: "mir-a" }
    let m = matrix_reality.birth_matrix(host, "3333333333333333333333333333333333333333333333333333333333333333", "4444444444444444444444444444444444444444444444444444444444444444", 2) or return
    let h = matrix_reality.birth_hara(m, host, "5555555555555555555555555555555555555555555555555555555555555555", 3) or return
    let a = matrix_reality.admit(m, h, host, "6666666666666666666666666666666666666666666666666666666666666666") or return
    let reborn = MatrixIdentity { veyra_digest: m.veyra_digest, instance_digest: m.instance_digest, reality_commitment_digest: m.reality_commitment_digest, birth_epoch: 9, digest: m.digest }
    println(matrix_reality.matrix_problem(reborn, host))
    let other = MatrixHost { veyra_digest: "9999999999999999999999999999999999999999999999999999999999999999", veyra_birth_epoch: 1, aevra_digest: host.aevra_digest, aevra_birth_epoch: 1, mir_fingerprint: "mir-a" }
    println(matrix_reality.matrix_problem(m, other))
    let stolen = HaraIdentity { matrix_digest: h.matrix_digest, aevra_digest: "7777777777777777777777777777777777777777777777777777777777777777", horizon_commitment_digest: h.horizon_commitment_digest, epoch: h.epoch, digest: h.digest }
    println(matrix_reality.hara_problem(stolen, m, host))
    let changed = MatrixHost { veyra_digest: host.veyra_digest, veyra_birth_epoch: 1, aevra_digest: host.aevra_digest, aevra_birth_epoch: 1, mir_fingerprint: "mir-b" }
    println(matrix_reality.admission_problem(a, m, h, changed))
    let forged = MatrixAdmission { matrix_digest: a.matrix_digest, hara_digest: a.hara_digest, aevra_digest: a.aevra_digest, veyra_digest: a.veyra_digest, native_mir_fingerprint: a.native_mir_fingerprint, epoch: a.epoch, evidence_digest: "8888888888888888888888888888888888888888888888888888888888888888", digest: a.digest }
    println(matrix_reality.admission_problem(forged, m, h, host))
}
'''


def _run(command: list[str], cwd: Path) -> tuple[str, str, int]:
    done = subprocess.run(command, cwd=cwd, capture_output=True, text=True, timeout=600)
    return done.stdout, done.stderr, done.returncode


class MatrixRealityLibraryTests(unittest.TestCase):
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

    def test_random_births_and_admissions_match_python(self) -> None:
        source, expected = _cases(20261119, 40)
        self.assertEqual(self.execute(source).splitlines(), expected)

    def test_tampered_records_give_the_python_reason(self) -> None:
        self.assertEqual(self.execute(TAMPER).splitlines(), _tamper_expectations())


if __name__ == "__main__":
    unittest.main()
