import json
import unittest

from koschei.fabric_contract_v1 import (
    FabricComponentV1,
    fabric_component_payload_v1,
    fabric_component_v1,
    require_safe_fabric_contract_v1,
)


class FabricContractV1Tests(unittest.TestCase):
    def test_contract_preserves_existing_lang(self):
        component = require_safe_fabric_contract_v1()
        self.assertTrue(component.preserveExisting)
        self.assertFalse(component.breakingChangesAllowed)
        self.assertEqual(component.crossProjectAccess, "contract-only")
        self.assertEqual(component.defaultMode, "observe")

    def test_contract_tracks_web4_and_web5_without_overclaiming(self):
        capabilities = {item.id: item for item in fabric_component_v1().capabilities}
        self.assertEqual(capabilities["language-toolchain"].status, "stable")
        self.assertEqual(capabilities["language-toolchain"].backend, "existing")
        self.assertEqual(capabilities["web4-web6-policy-and-agent-profile"].status, "experimental")
        self.assertEqual(capabilities["web4-web6-policy-and-agent-profile"].backend, "adapter")
        self.assertEqual(capabilities["web5-identity-data-profile"].status, "planned")
        self.assertEqual(capabilities["web5-identity-data-profile"].backend, "planned")

    def test_payload_is_json_serializable_shape(self):
        payload = fabric_component_payload_v1()
        self.assertEqual(payload["schemaVersion"], "1.0")
        self.assertEqual(payload["component"], "koschei-lang")
        encoded = json.dumps(payload, sort_keys=True)
        self.assertIn("web5-identity-data-profile", encoded)

    def test_unsafe_contract_is_rejected(self):
        safe = fabric_component_v1()
        unsafe = FabricComponentV1(
            schemaVersion=safe.schemaVersion,
            component=safe.component,
            repository=safe.repository,
            role=safe.role,
            preserveExisting=False,
            defaultMode=safe.defaultMode,
            breakingChangesAllowed=safe.breakingChangesAllowed,
            crossProjectAccess=safe.crossProjectAccess,
            capabilities=safe.capabilities,
        )
        with self.assertRaisesRegex(ValueError, "preserve existing"):
            require_safe_fabric_contract_v1(unsafe)


if __name__ == "__main__":
    unittest.main()
