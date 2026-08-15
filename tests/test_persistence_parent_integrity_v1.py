from __future__ import annotations

import os
from pathlib import Path
import stat
import tempfile
import unittest

from koschei.interpreter import KsError, KsUnit, PersistCaps, SystemCaps


@unittest.skipUnless(os.name == "posix", "persistence parent mode contract is POSIX-specific")
class PersistenceParentIntegrityV1Tests(unittest.TestCase):
    def token(self, target: Path) -> PersistCaps:
        value = SystemCaps().persist.allow(str(target), 4096, 2000)
        self.assertIsInstance(value, PersistCaps)
        return value

    def test_group_world_writable_non_sticky_parent_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            parent = Path(temporary) / "shared"
            parent.mkdir(mode=0o700)
            os.chmod(parent, 0o777)
            target = parent / "state.txt"
            target.write_text("old", encoding="utf-8")
            token = self.token(target)

            result = token.commit("new")
            self.assertIsInstance(result, KsError)
            self.assertIn("KS3420", result.message)
            self.assertIn("group/world-writable", result.message)
            self.assertEqual(target.read_text(encoding="utf-8"), "old")

    def test_sticky_shared_parent_is_not_rejected_by_mode_guard(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            parent = Path(temporary) / "sticky"
            parent.mkdir(mode=0o700)
            os.chmod(parent, 0o1777)
            mode = parent.stat().st_mode
            if not (mode & stat.S_ISVTX):
                self.skipTest("filesystem did not preserve sticky bit")

            target = parent / "state.txt"
            token = self.token(target)
            result = token.commit("allowed")
            self.assertIs(result, KsUnit)
            self.assertEqual(target.read_text(encoding="utf-8"), "allowed")

    def test_parent_permission_widening_after_token_creation_is_detected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            parent = Path(temporary) / "state-dir"
            parent.mkdir(mode=0o700)
            target = parent / "state.txt"
            target.write_text("old", encoding="utf-8")
            token = self.token(target)

            os.chmod(parent, 0o777)
            result = token.commit("new")
            self.assertIsInstance(result, KsError)
            self.assertIn("KS3420", result.message)
            self.assertEqual(target.read_text(encoding="utf-8"), "old")


if __name__ == "__main__":
    unittest.main()
