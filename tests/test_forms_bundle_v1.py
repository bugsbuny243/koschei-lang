"""The Koschei Forms download is complete and byte-for-byte reproducible."""
from __future__ import annotations

from pathlib import Path
import tempfile
import unittest
import zipfile

from tools.forms_bundle_v1 import FILES, VERSION, build


class FormsBundleTests(unittest.TestCase):
    def test_contents_and_reproducibility(self) -> None:
        with tempfile.TemporaryDirectory() as first, tempfile.TemporaryDirectory() as second:
            a = build(Path(first))
            b = build(Path(second))
            self.assertEqual(a.read_bytes(), b.read_bytes())
            with zipfile.ZipFile(a) as archive:
                names = archive.namelist()
                self.assertEqual(names, [f"koschei-forms-{VERSION}/{name}" for name in FILES])
                license_text = archive.read(f"koschei-forms-{VERSION}/LICENSE.md").decode()
                self.assertIn("Koschei Forms License 1.0", license_text)
                self.assertIn("Koschei Forms Lisansı 1.0", license_text)


if __name__ == "__main__":
    unittest.main()
