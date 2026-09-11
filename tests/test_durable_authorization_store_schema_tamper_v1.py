from __future__ import annotations

from pathlib import Path
import sqlite3
import tempfile
import unittest

from koschei.durable_authorization_store_v1 import (
    DurableAuthorizationStoreV1,
    DurableAuthorizationStoreV1Error,
)


class DurableAuthorizationStoreSchemaTamperV1Tests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.path = Path(self._tmp.name) / "authority.db"
        DurableAuthorizationStoreV1(self.path)

    def _execute_schema(self, statement: str) -> None:
        conn = sqlite3.connect(self.path)
        try:
            conn.execute(statement)
            conn.commit()
        finally:
            conn.close()

    def test_rejects_trigger_that_can_erase_execution_claims(self) -> None:
        self._execute_schema(
            "CREATE TRIGGER erase_claim_after_insert "
            "AFTER INSERT ON execution_claims BEGIN "
            "DELETE FROM execution_claims WHERE permit_digest = NEW.permit_digest; "
            "END"
        )
        with self.assertRaisesRegex(
            DurableAuthorizationStoreV1Error,
            "unsupported executable schema object",
        ):
            DurableAuthorizationStoreV1(self.path)

    def test_rejects_unexpected_view_in_authority_database(self) -> None:
        self._execute_schema(
            "CREATE VIEW leaked_heads AS "
            "SELECT subject, state_digest FROM authorization_heads"
        )
        with self.assertRaisesRegex(
            DurableAuthorizationStoreV1Error,
            "unsupported executable schema object",
        ):
            DurableAuthorizationStoreV1(self.path)


if __name__ == "__main__":
    unittest.main()
