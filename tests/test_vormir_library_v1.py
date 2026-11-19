"""The Koschei `vormir` library module agrees with the Python guardian.

`koschei/core_library/vormir.ks` ports the pure part of
`koschei/vormir_sacrifice_v1.py`: the sacrifice commitment and its root gate,
witness canonicalization and the epoch-sacrifice seal. Unlike the earlier
Marvel modules, digests are raw 32-byte `Bytes` and every sealed digest is the
SHA3-256 of the Python byte layout, so the hex values must be identical. The
same generated program runs under `ks run` and as a `ks build` binary.
"""
from __future__ import annotations

import random
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
import unittest

from koschei.vormir_sacrifice_v1 import (
    VormirEpochWitnessV1,
    VormirSacrificeError,
    _canonical_epoch_witnesses,
    _epoch_sacrifice_digest,
    admits_vormir_root_v1,
    commit_sacrifice_v1,
)

GO = shutil.which("go")


def _hex(data: bytes) -> str:
    return f'bytes_from_hex("{data.hex()}") or "".to_bytes()'


def _digest(rng: random.Random) -> bytes:
    roll = rng.random()
    if roll < 0.02:
        return bytes(rng.randrange(256) for _ in range(rng.choice([0, 31, 33])))
    return bytes(rng.randrange(256) for _ in range(32))


def _cases(seed: int, count: int) -> tuple[str, list[str]]:
    rng = random.Random(seed)
    authorities = ["disk.write", "disk.read", "net", "", "ağ.yaz"]
    body: list[str] = []
    expected: list[str] = []
    for index in range(count):
        principal, artifact, attest, verifier = (_digest(rng) for _ in range(4))
        surrendered, requested = rng.sample(authorities[:3] + authorities[4:], 2)
        roll = rng.random()
        if roll < 0.05:
            surrendered = ""
        elif roll < 0.10:
            requested = surrendered
        prior = rng.choice([-1, 0, 4, 9, 4, 0])
        following = prior + (1 if rng.random() < 0.85 else rng.choice([0, 2]))
        body.append(
            f"    let c{index} = vormir.commit({_hex(principal)}, {_hex(artifact)}, "
            f'"{surrendered}", "{requested}", {prior}, {following}, {_hex(attest)}, {_hex(verifier)})'
        )
        body.append(f"    show_commit(c{index}, {_hex(artifact)}, \"{surrendered}\", {following})")
        try:
            commitment = commit_sacrifice_v1(
                principal_digest=principal, artifact_digest=artifact,
                surrendered_authority=surrendered, requested_authority=requested,
                prior_epoch=prior, next_epoch=following,
                hardware_attestation_digest=attest, verifier_digest=verifier,
            )
        except VormirSacrificeError as error:
            expected.append(f"error {error}")
            continue
        expected.append(commitment.commitment_digest.hex())
        expected.append(str(admits_vormir_root_v1(
            commitment, revoked_authority=surrendered, observed_epoch=following,
            observed_artifact_digest=artifact,
        )).lower())

    for index in range(count):
        size = rng.choice([0, 1, 2, 2, 3, 3, 4, 4, 4])
        domains = [_digest(rng) for _ in range(size)]
        evidence = [_digest(rng) for _ in range(size)]
        if size >= 2 and rng.random() < 0.08:
            domains[1] = domains[0]
        if size >= 2 and rng.random() < 0.08:
            evidence[1] = evidence[0]
        sacrificed = rng.choice([0, 1, 7, 7, 3])
        successor = sacrificed + (1 if rng.random() < 0.9 else 2)
        fields = ["plan-" + str(index), "prev", "fresh", "rebirth", "tomb"]
        witnesses = ", ".join(
            f"VormirWitness {{ domain_digest: {_hex(d)}, evidence_digest: {_hex(e)} }}"
            for d, e in zip(domains, evidence)
        )
        body.append(f"    let w{index}: List<VormirWitness> = [{witnesses}]")
        body.append(
            f'    show_seal(vormir.seal("{fields[0]}", {sacrificed}, {successor}, "{fields[1]}", '
            f'"{fields[2]}", "{fields[3]}", "{fields[4]}", w{index}))'
        )
        if sacrificed < 1 or successor != sacrificed + 1:
            expected.append("error Vormir epoch sacrifice is not monotonic")
            continue
        try:
            built = [VormirEpochWitnessV1(d, e) for d, e in zip(domains, evidence)]
            bindings = _canonical_epoch_witnesses(built)
        except VormirSacrificeError as error:
            expected.append(f"error {error}")
            continue
        expected.append(_epoch_sacrifice_digest(
            activation_plan_digest=fields[0], sacrificed_epoch=sacrificed,
            successor_epoch=successor, previous_state_digest=fields[1],
            fresh_state_digest=fields[2], rebirth_receipt_digest=fields[3],
            tombstone_record_digest=fields[4], witness_bindings=bindings,
        ).hex())
        expected.append("true")

    source = "\n".join([
        "import vormir",
        "",
        "fn show_commit(result: Result<VormirCommitment, Error>, artifact: Bytes, revoked: String, epoch: Int) {",
        "    match result {",
        "        Ok(commitment) => {",
        "            println(commitment.commitment_digest)",
        "            println(vormir.admits_root(commitment, revoked, epoch, artifact))",
        "        },",
        '        Err(error) => println("error {error}"),',
        "    }",
        "}",
        "",
        "fn show_seal(result: Result<VormirEpochReceipt, Error>) {",
        "    match result {",
        "        Ok(receipt) => {",
        "            println(receipt.sacrifice_digest)",
        "            println(vormir.is_sealed(receipt))",
        "        },",
        '        Err(error) => println("error {error}"),',
        "    }",
        "}",
        "",
        "fn main() {",
        *body,
        "}",
        "",
    ])
    return source, expected


TAMPER = r'''
import vormir

fn d(fill: String) -> Bytes {
    let mut text = ""
    let mut i = 0
    while i < 32 {
        text = text + fill
        i = i + 1
    }
    return bytes_from_hex(text) or "".to_bytes()
}

fn main() {
    let c = vormir.commit(d("01"), d("02"), "disk.write", "disk.read", 4, 5, d("03"), d("04")) or return
    println(vormir.admits_root(c, "disk.write", 5, d("02")))
    println(vormir.admits_root(c, "disk.read", 5, d("02")))
    println(vormir.admits_root(c, "disk.write", 6, d("02")))
    println(vormir.admits_root(c, "disk.write", 5, d("09")))
    let forged = VormirCommitment {
        principal_digest: c.principal_digest,
        artifact_digest: d("09"),
        surrendered_authority: c.surrendered_authority,
        requested_authority: c.requested_authority,
        prior_epoch: c.prior_epoch,
        next_epoch: c.next_epoch,
        hardware_attestation_digest: c.hardware_attestation_digest,
        verifier_digest: c.verifier_digest,
        commitment_digest: c.commitment_digest,
    }
    println(vormir.admits_root(forged, "disk.write", 5, d("09")))
    let w = [VormirWitness { domain_digest: d("bb"), evidence_digest: d("01") }, VormirWitness { domain_digest: d("aa"), evidence_digest: d("02") }]
    let r = vormir.seal("plan", 7, 8, "prev", "fresh", "rebirth", "tomb", w) or return
    let edited = VormirEpochReceipt {
        activation_plan_digest: r.activation_plan_digest,
        sacrificed_epoch: r.sacrificed_epoch,
        successor_epoch: 9,
        previous_state_digest: r.previous_state_digest,
        fresh_state_digest: r.fresh_state_digest,
        rebirth_receipt_digest: r.rebirth_receipt_digest,
        tombstone_record_digest: r.tombstone_record_digest,
        witnesses: r.witnesses,
        sacrifice_digest: r.sacrifice_digest,
    }
    println(vormir.seal_problem(edited))
    let swapped = VormirEpochReceipt {
        activation_plan_digest: "other-plan",
        sacrificed_epoch: r.sacrificed_epoch,
        successor_epoch: r.successor_epoch,
        previous_state_digest: r.previous_state_digest,
        fresh_state_digest: r.fresh_state_digest,
        rebirth_receipt_digest: r.rebirth_receipt_digest,
        tombstone_record_digest: r.tombstone_record_digest,
        witnesses: r.witnesses,
        sacrifice_digest: r.sacrifice_digest,
    }
    println(vormir.seal_problem(swapped))
}
'''


def _run(command: list[str], cwd: Path) -> tuple[str, str, int]:
    done = subprocess.run(command, cwd=cwd, capture_output=True, text=True, timeout=600)
    return done.stdout, done.stderr, done.returncode


class VormirLibraryTests(unittest.TestCase):
    def execute(self, source: str, build: bool) -> str:
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            (base / "main.ks").write_text(source, encoding="utf-8")
            interpreted = _run([sys.executable, "-m", "koschei", "run", "--max-steps", "50000000", "main.ks"], base)
            self.assertEqual(interpreted[2], 0, interpreted[1])
            if build:
                compiled = _run([sys.executable, "-m", "koschei", "build", "main.ks", "-o", "app"], base)
                self.assertEqual(compiled[2], 0, compiled[1])
                self.assertEqual(_run([str(base / "app")], base), interpreted)
        return interpreted[0]

    def test_random_commitments_and_seals_match_python(self) -> None:
        source, expected = _cases(20261119, 40)
        self.assertEqual(self.execute(source, build=bool(GO)).splitlines(), expected)

    def test_gates_refuse_tampering(self) -> None:
        lines = self.execute(TAMPER, build=bool(GO)).splitlines()
        self.assertEqual(lines[:5], ["true", "false", "false", "false", "false"])
        self.assertEqual(lines[5], "Vormir epoch sacrifice is not monotonic")
        self.assertEqual(lines[6], "Vormir epoch sacrifice seal mismatch")


if __name__ == "__main__":
    unittest.main()
