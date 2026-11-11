import unittest

from koschei.fabric_case_adapter_v1 import build_lang_fabric_projection_v1


class FabricCaseAdapterV1Tests(unittest.TestCase):
    def _projection(self, **overrides):
        values = {
            "principal": "user:fixture",
            "caller": "agent:readonly",
            "scope": ("report:read",),
            "authority_state": "AUTHORIZED",
            "policy_version": "policy-v1",
            "runtime_version": "runtime-v1",
            "revocation_epoch": 4,
            "isolation_state": "UNVERIFIED",
            "max_calls": 4,
            "max_duration_ms": 1000,
            "max_data_bytes": 4096,
            "native_schema": "koschei.authority-receipt.v1",
            "native_ref": "fixture://authority/1",
            "native_digest_sha256": "a" * 64,
        }
        values.update(overrides)
        return build_lang_fabric_projection_v1(**values)

    def test_projection_keeps_lang_as_authority_owner(self):
        projection = self._projection()
        self.assertEqual(projection.authority["authorityOwner"], "koschei-lang")
        self.assertEqual(projection.runtime["runtimeOwner"], "koschei-lang")
        self.assertEqual(projection.authority["scope"], ["report:read"])
        self.assertEqual(projection.native_binding["owner"], "koschei-lang")

    def test_adapter_does_not_silently_upgrade_isolation(self):
        projection = self._projection(isolation_state="UNVERIFIED")
        self.assertEqual(projection.runtime["isolationState"], "UNVERIFIED")

    def test_empty_or_duplicate_scope_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "scope"):
            self._projection(scope=())
        with self.assertRaisesRegex(ValueError, "unique"):
            self._projection(scope=("report:read", "report:read"))

    def test_invalid_digest_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "SHA-256"):
            self._projection(native_digest_sha256="not-a-digest")

    def test_negative_budget_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "max_calls"):
            self._projection(max_calls=-1)

    def test_unknown_authority_state_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "authority state"):
            self._projection(authority_state="TRUST_ME")


if __name__ == "__main__":
    unittest.main()
