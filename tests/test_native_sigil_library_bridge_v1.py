from __future__ import annotations

import dataclasses
import unittest

from koschei.native_sigil_library_bridge_v1 import (
    NativeSigilLibraryBridgeError,
    expand_native_sigil_mir,
)
from koschei.native_sigil_mir_v1 import lower_native_sigils
from koschei.parser import parse


class NativeSigilLibraryBridgeTests(unittest.TestCase):
    SOURCE = """
ka treasury;
vor withdrawal;
shi evidence;
thal recovery;
nur visibility;
"""

    def _mir(self):
        return lower_native_sigils(parse(self.SOURCE))

    def test_real_source_reaches_library_expansion(self) -> None:
        plan = expand_native_sigil_mir(self._mir())
        self.assertEqual(plan.library_plan.sigils, ("ka", "vor", "shi", "thal", "nur"))
        obligations = {step.obligation for step in plan.library_plan.steps}
        self.assertIn("derive-least-authority", obligations)
        self.assertIn("require-independent-evidence", obligations)
        self.assertIn("fence-stale-writers", obligations)
        self.assertIn("shrink-visibility-envelope", obligations)
        self.assertIn("seal-whole-universe-conservation-proof", obligations)

    def test_only_canonical_authority_binding_can_grant(self) -> None:
        plan = expand_native_sigil_mir(self._mir())
        authority_steps = [
            step for step in plan.library_plan.steps if step.obligation == "derive-least-authority"
        ]
        self.assertEqual(len(authority_steps), 1)
        self.assertEqual(authority_steps[0].subsystem, "library.authority_derivation")

    def test_bridge_is_deterministic(self) -> None:
        first = expand_native_sigil_mir(self._mir())
        second = expand_native_sigil_mir(self._mir())
        self.assertEqual(first.digest, second.digest)
        self.assertEqual(first.library_plan.digest, second.library_plan.digest)

    def test_tampered_mir_fails_before_library_expansion(self) -> None:
        mir = self._mir()
        tampered = dataclasses.replace(mir, universe_plan_digest="0" * 64)
        with self.assertRaises(Exception):
            expand_native_sigil_mir(tampered)

    def test_tampered_bridge_seal_is_rejected(self) -> None:
        plan = expand_native_sigil_mir(self._mir())
        tampered = dataclasses.replace(plan, digest="0" * 64)
        with self.assertRaises(NativeSigilLibraryBridgeError):
            tampered.assert_sealed()


if __name__ == "__main__":
    unittest.main()
