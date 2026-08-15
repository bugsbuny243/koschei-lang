from __future__ import annotations

import os
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import patch

from koschei.interpreter import KsError, PersistCaps, SystemCaps
from koschei.parser import parse
from koschei.semantic import SemanticError, check


class PersistenceExactObjectIntegrityV1Tests(unittest.TestCase):
    def token(self, target: Path) -> PersistCaps:
        value = SystemCaps().persist.allow(str(target), 4096, 2000)
        self.assertIsInstance(value, PersistCaps)
        return value

    def test_policy_rejects_lexical_aliases_instead_of_silent_rewrite(self) -> None:
        aliases = (
            "/tmp/koschei-state/../state.txt",
            "/tmp//koschei-state.txt",
            "/tmp/koschei-state.txt ",
            " /tmp/koschei-state.txt",
        )
        for path in aliases:
            with self.subTest(path=path):
                program = parse(
                    "fn main(caps: SystemCaps) { "
                    f'let state = caps.persist.allow("{path}", 4096, 2000) '
                    "}"
                )
                with self.assertRaisesRegex(SemanticError, "KS2421"):
                    check(program)

    @unittest.skipUnless(hasattr(os, "link"), "hard links are unavailable")
    def test_hard_link_alias_is_rejected_for_load_and_commit(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            secret = root / "secret.txt"
            secret.write_text("secret", encoding="utf-8")
            target = root / "state.txt"
            os.link(secret, target)
            self.assertGreater(secret.stat().st_nlink, 1)

            token = self.token(target)
            loaded = token.load()
            self.assertIsInstance(loaded, KsError)
            self.assertIn("KS3420", loaded.message)
            self.assertIn("hard-link", loaded.message)

            committed = token.commit("replacement")
            self.assertIsInstance(committed, KsError)
            self.assertIn("KS3420", committed.message)
            self.assertEqual(secret.read_text(encoding="utf-8"), "secret")
            self.assertEqual(target.read_text(encoding="utf-8"), "secret")

    @unittest.skipUnless(hasattr(os, "mkfifo") and hasattr(os, "O_NONBLOCK"), "FIFO defense requires POSIX nonblocking open")
    def test_load_open_is_nonblocking_even_if_shape_check_is_raced_to_fifo(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            target = Path(temporary) / "state"
            target.write_text("old", encoding="utf-8")
            token = self.token(target)
            target.unlink()
            os.mkfifo(target, 0o600)

            with patch(
                "koschei.bounded_persistence_v1._safe_target_shape",
                return_value=None,
            ):
                started = time.monotonic()
                result = token.load()
                elapsed = time.monotonic() - started

            self.assertIsInstance(result, KsError)
            self.assertIn("KS3420", result.message)
            self.assertIn("regular file", result.message)
            self.assertLess(elapsed, 1.0)


if __name__ == "__main__":
    unittest.main()
