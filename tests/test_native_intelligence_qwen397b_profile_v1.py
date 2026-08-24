from dataclasses import replace
import unittest

from koschei.native_intelligence_qwen397b_profile_v1 import (
    CANONICAL_LORA_TARGETS_V1,
    OFFICIAL_EXPERTS,
    OFFICIAL_EXPERTS_PER_TOKEN,
    OFFICIAL_MAX_POSITION_EMBEDDINGS,
    OFFICIAL_TEXT_LAYERS,
    Qwen397BProfileError,
    canonical_qwen397b_koschei_profile_v1,
)
from koschei.native_intelligence_v1 import CANONICAL_BASE_MODEL_V1


class Qwen397BKoscheiProfileV1Tests(unittest.TestCase):
    def test_profile_records_canonical_architecture_and_conservative_adapter_surface(self):
        profile = canonical_qwen397b_koschei_profile_v1()
        profile.assert_sealed()

        self.assertEqual(profile.base_model_id, CANONICAL_BASE_MODEL_V1)
        self.assertEqual(profile.text_layers, OFFICIAL_TEXT_LAYERS)
        self.assertEqual(profile.experts, OFFICIAL_EXPERTS)
        self.assertEqual(profile.experts_per_token, OFFICIAL_EXPERTS_PER_TOKEN)
        self.assertEqual(profile.native_context, OFFICIAL_MAX_POSITION_EMBEDDINGS)
        self.assertTrue(profile.freeze_vision)
        self.assertTrue(profile.freeze_router)
        self.assertTrue(profile.freeze_experts)
        self.assertEqual(profile.target_modules, CANONICAL_LORA_TARGETS_V1)
        self.assertFalse(profile.authority)

    def test_profile_is_deterministic(self):
        self.assertEqual(
            canonical_qwen397b_koschei_profile_v1(),
            canonical_qwen397b_koschei_profile_v1(),
        )

    def test_router_expert_or_vision_unfreeze_is_not_canonical_first_run(self):
        profile = canonical_qwen397b_koschei_profile_v1()
        for field in ("freeze_vision", "freeze_router", "freeze_experts"):
            forged = replace(profile, **{field: False})
            with self.assertRaisesRegex(
                Qwen397BProfileError,
                "must freeze vision, router and expert weights",
            ):
                forged.assert_sealed()

    def test_target_surface_or_sequence_drift_fails_closed(self):
        profile = canonical_qwen397b_koschei_profile_v1()
        with self.assertRaises(Qwen397BProfileError):
            replace(profile, target_modules=("self_attn.q_proj",)).assert_sealed()
        with self.assertRaises(Qwen397BProfileError):
            replace(profile, max_sequence_length=8192).assert_sealed()


if __name__ == "__main__":
    unittest.main()
