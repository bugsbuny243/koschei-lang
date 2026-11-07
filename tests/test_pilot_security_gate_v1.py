"""Customer ZIP security pilot: executed evidence, honest non-production scope."""
from __future__ import annotations

import hashlib
from pathlib import Path
import stat
import tempfile
import unittest
import zipfile

from tools.pilot_security_gate_v1 import (
    PilotGateError, REQUIRED, SCHEMA, main, pilot_checks, verify_archive,
)
from tools.polar_bundle_v1 import build_bundle


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


class PilotSecurityGateTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.temp = tempfile.TemporaryDirectory(prefix="koschei-launch-gate-tests-")
        cls.root = Path(cls.temp.name)
        cls.bundle = build_bundle(cls.root)
        cls.sha256 = sha(cls.bundle.read_bytes())

    @classmethod
    def tearDownClass(cls) -> None:
        cls.temp.cleanup()

    def test_official_bundle_runs_its_own_deny_and_manifest_examples(self) -> None:
        result = pilot_checks(self.bundle, self.sha256)
        self.assertEqual(result["schema"], SCHEMA)
        self.assertEqual(result["artifact_sha256"], self.sha256)
        self.assertTrue(result["pilot_checks_passed"], result["checks"])
        self.assertFalse(result["approved_for_production"])
        self.assertGreaterEqual(len(result["checks"]), 6)
        self.assertTrue(all(item["passed"] for item in result["checks"]))
        self.assertIn("developer credential theft prevented", result["not_proved"])

    def test_hash_mismatch_is_refused_even_for_valid_zip(self) -> None:
        with self.assertRaisesRegex(PilotGateError, "digest differs"):
            verify_archive(self.bundle, "0" * 64)
        output = self.root / "untrusted.json"
        code = main([
            "--bundle", str(self.bundle), "--expected-sha256", "0" * 64,
            "--output", str(output),
        ])
        self.assertEqual(code, 2)
        self.assertFalse(output.exists())

    def test_expected_hash_must_be_canonical(self) -> None:
        with self.assertRaisesRegex(PilotGateError, "64 lowercase"):
            verify_archive(self.bundle, self.sha256.upper())
        with self.assertRaisesRegex(PilotGateError, "64 lowercase"):
            verify_archive(self.bundle, "bad")

    def test_zip_traversal_rejected_even_with_matching_hash(self) -> None:
        attack = self.root / "traversal.zip"
        with zipfile.ZipFile(attack, "w") as z:
            z.writestr("koschei-lang-0.10.0/../escape.txt", b"attack")
        with self.assertRaisesRegex(PilotGateError, "unsafe ZIP member"):
            verify_archive(attack, sha(attack.read_bytes()))

    def test_zip_symlink_rejected_even_with_matching_hash(self) -> None:
        attack = self.root / "symlink.zip"
        symlink = zipfile.ZipInfo("koschei-lang-0.10.0/README.md")
        symlink.create_system = 3
        symlink.external_attr = (stat.S_IFLNK | 0o777) << 16
        with zipfile.ZipFile(attack, "w") as z:
            z.writestr(symlink, "../../secrets")
        with self.assertRaisesRegex(PilotGateError, "unsafe ZIP member"):
            verify_archive(attack, sha(attack.read_bytes()))

    def test_zip_missing_required_product_file_is_refused(self) -> None:
        candidate = self.root / "incomplete.zip"
        with zipfile.ZipFile(candidate, "w") as z:
            z.writestr("koschei-lang-0.10.0/README.md", "incomplete")
        with self.assertRaisesRegex(PilotGateError, "missing required"):
            verify_archive(candidate, sha(candidate.read_bytes()))
        self.assertTrue({"LICENSE", "examples/supply_chain/main.ks"} <= REQUIRED)


if __name__ == "__main__":
    unittest.main()
