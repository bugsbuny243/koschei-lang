from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
TOOL = ROOT / "tools" / "paddle_release_v1.py"

spec = importlib.util.spec_from_file_location("paddle_release_v1", TOOL)
assert spec and spec.loader
release = importlib.util.module_from_spec(spec)
spec.loader.exec_module(release)


@unittest.skipUnless(shutil.which("openssl"), "openssl required")
class PaddleProductionReleaseTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory(prefix="koschei-paddle-test-")
        self.root = Path(self.tmp.name)
        self.binary = self.root / "compiler.bin"
        self.binary.write_bytes(b"sealed-koschei-test-binary\n")
        self.version = "0.10.0"
        checks = {name: True for name in release.REQUIRED_SMOKE_CHECKS}
        self.smoke = self.root / "smoke.json"
        self.smoke.write_text(json.dumps({
            "schema": release.SMOKE_SCHEMA,
            "product": "koschei-lang",
            "channel": release.CHANNEL,
            "version": self.version,
            "binary": {
                "sha256": hashlib.sha256(self.binary.read_bytes()).hexdigest(),
                "size_bytes": self.binary.stat().st_size,
            },
            "checks": checks,
        }), encoding="utf-8")
        self.runtime = self.root / "runtime.json"
        self.runtime.write_text(json.dumps({
            "schema": release.RUNTIME_SCHEMA,
            "product": "koschei-lang",
            "platform": "linux-x86_64",
            "architecture": "x86_64",
            "os": "linux",
            "libc": "glibc",
            "minimum_libc_version": "2.34",
            "dynamic_dependencies": ["libc.so.6"],
        }), encoding="utf-8")
        self.readme = self.root / "README.txt"
        self.readme.write_text("customer readme\n", encoding="utf-8")
        self.license = self.root / "LICENSE.txt"
        self.license.write_text("customer license\n", encoding="utf-8")
        self.owner_private, self.owner_public = self._keypair("owner")

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def _keypair(self, name: str) -> tuple[Path, Path]:
        private = self.root / f"{name}-private.pem"
        public = self.root / f"{name}-public.pem"
        subprocess.run(["openssl", "genpkey", "-algorithm", "Ed25519", "-out", str(private)], check=True, capture_output=True)
        subprocess.run(["openssl", "pkey", "-in", str(private), "-pubout", "-out", str(public)], check=True, capture_output=True)
        return private, public

    def _assemble(self, name: str = "artifact") -> Path:
        target = self.root / name
        release.assemble(
            binary=self.binary,
            output=target,
            version=self.version,
            platform="linux-x86_64",
            source_commit="a" * 40,
            smoke_receipt=self.smoke,
            runtime_requirements=self.runtime,
            customer_readme=self.readme,
            license_notice=self.license,
        )
        return target

    def test_valid_external_trust_anchor_passes(self) -> None:
        artifact = self._assemble()
        release.sign(artifact, self.owner_private)
        self.assertEqual(release.verify(artifact, self.owner_public), [])

    def test_attacker_key_substitution_is_rejected(self) -> None:
        artifact = self._assemble()
        release.sign(artifact, self.owner_private)
        _, attacker_public = self._keypair("attacker")
        failures = release.verify(artifact, attacker_public)
        self.assertTrue(any("independently trusted public key" in item for item in failures))

    def test_binary_tamper_is_rejected(self) -> None:
        artifact = self._assemble()
        release.sign(artifact, self.owner_private)
        with (artifact / "ks").open("ab") as handle:
            handle.write(b"tamper")
        failures = release.verify(artifact, self.owner_public)
        self.assertIn("artifact SHA-256 mismatch", failures)

    def test_unsigned_staging_is_rejected(self) -> None:
        artifact = self._assemble()
        failures = release.verify(artifact, self.owner_public)
        self.assertTrue(any("not SIGNED" in item for item in failures))

    def test_testnet_marker_is_rejected(self) -> None:
        artifact = self._assemble()
        release.sign(artifact, self.owner_private)
        (artifact / "TESTNET-NOTICE.txt").write_text("testnet\n", encoding="utf-8")
        failures = release.verify(artifact, self.owner_public)
        self.assertTrue(any("forbidden Paddle production file" in item for item in failures))

    def test_missing_ks2401_smoke_evidence_blocks_assembly(self) -> None:
        data = json.loads(self.smoke.read_text(encoding="utf-8"))
        data["checks"]["ks2401_supply_chain_denial"] = False
        self.smoke.write_text(json.dumps(data), encoding="utf-8")
        with self.assertRaisesRegex(release.PaddleReleaseError, "ks2401_supply_chain_denial"):
            self._assemble()

    def test_runtime_requirements_are_digest_bound(self) -> None:
        artifact = self._assemble()
        release.sign(artifact, self.owner_private)
        path = artifact / release.RUNTIME_NAME
        data = json.loads(path.read_text(encoding="utf-8"))
        data["minimum_libc_version"] = "9.99"
        path.write_text(json.dumps(data), encoding="utf-8")
        failures = release.verify(artifact, self.owner_public)
        self.assertIn("runtime requirements digest mismatch", failures)


if __name__ == "__main__":
    unittest.main()
