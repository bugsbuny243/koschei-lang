import json
from pathlib import Path
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
        self.assertEqual(component.legacyInterfaces, "preserve")
        self.assertEqual(component.defaultMode, "observe")

    def test_contract_does_not_overclaim_blocked_toolchain(self):
        capabilities = {item.id: item for item in fabric_component_v1().capabilities}
        self.assertEqual(capabilities["language-toolchain"].status, "experimental")
        self.assertEqual(capabilities["language-toolchain"].evidenceState, "blocked")
        self.assertIn("LANG-01", capabilities["language-toolchain"].workPackages)
        self.assertEqual(capabilities["authorization-transition-ir"].evidenceState, "partial")
        self.assertEqual(capabilities["web4-policy-agent-profile"].status, "experimental")
        self.assertEqual(capabilities["web5-identity-data-profile"].status, "planned")

    def test_legacy_capability_id_is_explicit_alias_not_second_authority_surface(self):
        capabilities = {item.id: item for item in fabric_component_v1().capabilities}
        legacy = capabilities["web4-web6-policy-and-agent-profile"]
        self.assertEqual(legacy.compatibilityAliasFor, "web4-policy-agent-profile")
        self.assertEqual(legacy.backend, "adapter")
        self.assertEqual(legacy.evidenceState, "research")

    def test_provider_canonical_capabilities_match_operator_manifest(self):
        manifest = json.loads(Path("fabric/component.json").read_text(encoding="utf-8"))
        component = fabric_component_v1()
        provider = {item.id: item for item in component.capabilities}

        self.assertEqual(component.schemaVersion, manifest["schemaVersion"])
        self.assertEqual(component.component, manifest["component"])
        self.assertEqual(component.repository, manifest["repository"])
        self.assertEqual(component.role, manifest["role"])
        self.assertEqual(component.preserveExisting, manifest["preserveExisting"])
        self.assertEqual(component.defaultMode, manifest["defaultMode"])
        self.assertEqual(component.breakingChangesAllowed, manifest["compatibility"]["breakingChangesAllowed"])
        self.assertEqual(component.crossProjectAccess, manifest["compatibility"]["crossProjectAccess"])
        self.assertEqual(component.legacyInterfaces, manifest["compatibility"]["legacyInterfaces"])

        for expected in manifest["capabilities"]:
            actual = provider[expected["id"]]
            self.assertEqual(actual.domain, expected["domain"])
            self.assertEqual(actual.status, expected["status"])
            self.assertEqual(actual.evidenceState, expected["evidenceState"])
            self.assertEqual(actual.workPackages, tuple(expected["workPackages"]))
            self.assertEqual(actual.backend, expected["backend"])
            self.assertEqual(actual.frontend, expected["frontend"])
            self.assertEqual(actual.telemetry, expected["telemetry"])
            self.assertEqual(actual.notes, expected["notes"])

    def test_payload_is_json_serializable_shape(self):
        payload = fabric_component_payload_v1()
        self.assertEqual(payload["schemaVersion"], "1.0")
        self.assertEqual(payload["component"], "koschei-lang")
        encoded = json.dumps(payload, sort_keys=True)
        self.assertIn("authorization-transition-ir", encoded)
        self.assertIn("LANG-01", encoded)

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
            legacyInterfaces=safe.legacyInterfaces,
        )
        with self.assertRaisesRegex(ValueError, "preserve existing"):
            require_safe_fabric_contract_v1(unsafe)


if __name__ == "__main__":
    unittest.main()
