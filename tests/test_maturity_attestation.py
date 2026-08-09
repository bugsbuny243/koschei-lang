from __future__ import annotations

import hashlib
import json
import shutil
import tempfile
import unittest
import zipfile
from pathlib import Path

from koschei.cli_entry import main
from koschei.maturity import evaluate_maturity, load_maturity_evidence
from koschei.maturity_attestation import (
    MaturityAttestationError,
    build_attested_maturity_evidence,
    write_attested_maturity_evidence,
)
from koschei.release_proof import ReleaseProof


def _digest(value: object) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
    ).hexdigest()


def _proof() -> ReleaseProof:
    payload = {
        "schema_version": "koschei.release-proof.v1",
        "state": "verified_reproducible_release_candidate",
        "authority": "release_candidate_evidence_only",
        "module_lock_digest": "1" * 64,
        "mir_version": "koschei.mir.v5",
        "mir_fingerprint": "2" * 64,
        "compiler_version": "0.10.0",
        "backend": "go",
        "backend_toolchain": "go version go1.25.0 linux/amd64",
        "release_manifest_digest": "3" * 64,
        "witness_manifest_digest": "4" * 64,
        "release_artifact_sha256": "5" * 64,
        "witness_artifact_sha256": "5" * 64,
        "reproducibility_report_digest": "6" * 64,
        "shared_input_digest": "7" * 64,
        "byte_reproducible": True,
        "owner_approval_required": True,
        "automatic_publish_allowed": False,
        "package_registry_write_allowed": False,
        "production_integration_allowed": False,
    }
    return ReleaseProof(
        state=str(payload["state"]),
        authority=str(payload["authority"]),
        module_lock_digest=str(payload["module_lock_digest"]),
        mir_version=str(payload["mir_version"]),
        mir_fingerprint=str(payload["mir_fingerprint"]),
        compiler_version=str(payload["compiler_version"]),
        backend=str(payload["backend"]),
        backend_toolchain=str(payload["backend_toolchain"]),
        release_manifest_digest=str(payload["release_manifest_digest"]),
        witness_manifest_digest=str(payload["witness_manifest_digest"]),
        release_artifact_sha256=str(payload["release_artifact_sha256"]),
        witness_artifact_sha256=str(payload["witness_artifact_sha256"]),
        reproducibility_report_digest=str(payload["reproducibility_report_digest"]),
        shared_input_digest=str(payload["shared_input_digest"]),
        byte_reproducible=True,
        owner_approval_required=True,
        automatic_publish_allowed=False,
        package_registry_write_allowed=False,
        production_integration_allowed=False,
        proof_digest=_digest(payload),
    )


def _base(path: Path) -> Path:
    checks = {
        "compiler_tests": True,
        "repository_truth": True,
        "capability_security": True,
        "syntax_stability": True,
        "type_system_stability": True,
        "real_programs": True,
    }
    path.write_text(
        json.dumps({"schema_version": "koschei.maturity-evidence.v1", "checks": checks}),
        encoding="utf-8",
    )
    return path


def _ci_artifact(
    path: Path,
    *,
    include_supply_chain: bool = True,
    include_parity: bool = True,
    parity_cases: int = 7,
    include_fuzz: bool = True,
    fuzz_cases: int = 16,
    fuzz_seed: int = 20260809,
) -> Path:
    supply_chain = (
        "  PASS  examples/supply_chain/main.ks — correctly rejected with KS2401\n"
        if include_supply_chain
        else ""
    )
    parity = (
        f"  PASS  interpreter/native parity: {parity_cases} cases — "
        f"PARITY SHA256: {'9' * 64}\n\n"
        if include_parity
        else ""
    )
    fuzz = (
        f"  PASS  differential fuzz: {fuzz_cases} cases seed {fuzz_seed} — "
        f"FUZZ SHA256: {'a' * 64} — CORPUS SHA256: {'b' * 64}\n\n"
        if include_fuzz
        else ""
    )
    report = (
        "Koschei verify — Koschei 0.10.0\n\n"
        "==> Test suite\n"
        f"  PASS  Ran 600 tests — ARTIFACT SHA256: {'8' * 64}\n\n"
        "==> Sealed MIR\n"
        "  PASS  check and backend input share one sealed MIR fingerprint\n\n"
        "==> Interpreter/native parity\n"
        f"{parity}"
        "==> Differential fuzzing\n"
        f"{fuzz}"
        "==> Examples\n"
        "  PASS  examples/capability.ks\n"
        f"{supply_chain}\n"
        "==> Summary\n"
        "  1 warning(s), no failures.\n"
    )
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("verify-report.txt", report)
    return path


class MaturityAttestationTests(unittest.TestCase):
    def test_v1_cannot_self_assert_protected_checks(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "evidence.json"
            path.write_text(
                json.dumps(
                    {
                        "schema_version": "koschei.maturity-evidence.v1",
                        "checks": {
                            "package_integrity": True,
                            "reproducible_builds": True,
                            "interpreter_native_parity": True,
                            "fuzzing": True,
                        },
                    }
                ),
                encoding="utf-8",
            )
            with self.assertRaisesRegex(ValueError, "protected maturity checks"):
                load_maturity_evidence(path)

    def test_attested_json_alone_cannot_satisfy_reference_trust(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            base = load_maturity_evidence(_base(root / "base.json"))
            ci_zip = _ci_artifact(root / "truth.zip")
            payload = build_attested_maturity_evidence(
                base,
                _proof(),
                ci_artifact_path=ci_zip,
                ci_head_sha="a" * 40,
            )
            output = root / "attested.json"
            write_attested_maturity_evidence(payload, output)
            evidence = load_maturity_evidence(output)
            report = evaluate_maturity(evidence, "reference")

            self.assertEqual(evidence.schema_version, "koschei.maturity-evidence.v5")
            self.assertTrue(evidence.checks["interpreter_native_parity"])
            self.assertTrue(evidence.checks["fuzzing"])
            self.assertTrue(evidence.checks["package_integrity"])
            self.assertTrue(evidence.checks["reproducible_builds"])
            self.assertEqual(payload["ci_test_count"], 600)
            self.assertEqual(payload["ci_warning_count"], 1)
            self.assertEqual(payload["ci_parity_case_count"], 7)
            self.assertEqual(payload["ci_parity_evidence_sha256"], "9" * 64)
            self.assertEqual(payload["ci_fuzz_case_count"], 16)
            self.assertEqual(payload["ci_fuzz_seed"], 20260809)
            self.assertEqual(payload["ci_fuzz_evidence_sha256"], "a" * 64)
            self.assertEqual(payload["ci_fuzz_corpus_sha256"], "b" * 64)
            self.assertTrue(payload["ci_repository_truth_observed"])
            self.assertTrue(payload["ci_sealed_mir_observed"])
            self.assertTrue(payload["ci_capability_security_observed"])
            self.assertTrue(payload["ci_interpreter_native_parity_observed"])
            self.assertTrue(payload["ci_differential_fuzzing_observed"])
            self.assertFalse(report.ready)
            self.assertIn("compiler_tests", report.missing_checks)
            self.assertIn("interpreter_native_parity", report.missing_checks)
            self.assertIn("package_integrity", report.missing_checks)
            self.assertFalse(report.as_dict()["production_integration_allowed"])

    def test_ci_artifact_without_supply_chain_rejection_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            base = load_maturity_evidence(_base(root / "base.json"))
            ci_zip = _ci_artifact(root / "truth.zip", include_supply_chain=False)
            with self.assertRaisesRegex(MaturityAttestationError, "supply-chain"):
                build_attested_maturity_evidence(
                    base,
                    _proof(),
                    ci_artifact_path=ci_zip,
                    ci_head_sha="b" * 40,
                )

    def test_ci_artifact_without_sufficient_parity_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            base = load_maturity_evidence(_base(root / "base.json"))
            for kwargs in ({"include_parity": False}, {"parity_cases": 4}):
                ci_zip = _ci_artifact(root / f"truth-parity-{len(kwargs)}.zip", **kwargs)
                with self.assertRaisesRegex(MaturityAttestationError, "parity cases"):
                    build_attested_maturity_evidence(
                        base,
                        _proof(),
                        ci_artifact_path=ci_zip,
                        ci_head_sha="b" * 40,
                    )

    def test_ci_artifact_without_sufficient_fuzzing_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            base = load_maturity_evidence(_base(root / "base.json"))
            for kwargs in ({"include_fuzz": False}, {"fuzz_cases": 15}):
                ci_zip = _ci_artifact(root / f"truth-fuzz-{len(kwargs)}.zip", **kwargs)
                with self.assertRaisesRegex(MaturityAttestationError, "fuzz cases"):
                    build_attested_maturity_evidence(
                        base,
                        _proof(),
                        ci_artifact_path=ci_zip,
                        ci_head_sha="b" * 40,
                    )

    def test_attestation_tamper_and_overwrite_fail_closed(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            base = load_maturity_evidence(_base(root / "base.json"))
            payload = build_attested_maturity_evidence(
                base,
                _proof(),
                ci_artifact_path=_ci_artifact(root / "truth.zip"),
                ci_head_sha="c" * 40,
            )
            output = root / "attested.json"
            write_attested_maturity_evidence(payload, output)
            with self.assertRaises(MaturityAttestationError):
                write_attested_maturity_evidence(payload, output)

            changed = json.loads(output.read_text(encoding="utf-8"))
            changed["ci_fuzz_case_count"] = 999
            output.write_text(json.dumps(changed), encoding="utf-8")
            with self.assertRaises(ValueError):
                load_maturity_evidence(output)

    @unittest.skipUnless(shutil.which("go"), "Go is required for native build tests")
    def test_cli_attests_real_release_proof_chain(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "main.ks"
            lockfile = root / "koschei.lock.json"
            artifact = root / "app"
            manifest = root / "app.build.json"
            witness_dir = root / "witness"
            witness_dir.mkdir()
            witness_artifact = witness_dir / "app"
            report = root / "reproducibility.json"
            proof = root / "release-proof.json"
            attested = root / "maturity.attested.json"
            base = _base(root / "base.json")
            ci_zip = _ci_artifact(root / "truth.zip")
            source.write_text("fn main() {\n    return\n}\n", encoding="utf-8")

            self.assertEqual(main(["lock", "create", str(source), "--output", str(lockfile)]), 0)
            self.assertEqual(
                main(
                    [
                        "build",
                        str(source),
                        "--locked",
                        "--lockfile",
                        str(lockfile),
                        "--output",
                        str(artifact),
                        "--build-manifest",
                        str(manifest),
                    ]
                ),
                0,
            )
            shutil.copyfile(artifact, witness_artifact)
            compare_inputs = [
                "--left-source",
                str(source),
                "--left-artifact",
                str(artifact),
                "--left-manifest",
                str(manifest),
                "--left-lockfile",
                str(lockfile),
                "--right-source",
                str(source),
                "--right-artifact",
                str(witness_artifact),
                "--right-manifest",
                str(manifest),
                "--right-lockfile",
                str(lockfile),
            ]
            self.assertEqual(
                main(["build-compare", *compare_inputs, "--output", str(report)]),
                0,
            )
            release_inputs = [
                "--release-source",
                str(source),
                "--release-artifact",
                str(artifact),
                "--release-manifest",
                str(manifest),
                "--release-lockfile",
                str(lockfile),
                "--witness-source",
                str(source),
                "--witness-artifact",
                str(witness_artifact),
                "--witness-manifest",
                str(manifest),
                "--witness-lockfile",
                str(lockfile),
                "--report",
                str(report),
            ]
            self.assertEqual(
                main(["release-proof", "create", *release_inputs, "--output", str(proof)]),
                0,
            )
            attest_inputs = [
                "--base-evidence",
                str(base),
                *release_inputs,
                "--proof",
                str(proof),
                "--ci-artifact",
                str(ci_zip),
                "--ci-head-sha",
                "d" * 40,
            ]
            self.assertEqual(
                main(["maturity-attest", "create", *attest_inputs, "--output", str(attested)]),
                0,
            )
            self.assertEqual(
                main(
                    [
                        "maturity-attest",
                        "verify",
                        *attest_inputs,
                        "--attested-evidence",
                        str(attested),
                        "--target",
                        "reference",
                    ]
                ),
                0,
            )
            self.assertEqual(
                main(["maturity", "--evidence", str(attested), "--target", "reference"]),
                2,
            )


if __name__ == "__main__":
    unittest.main()
