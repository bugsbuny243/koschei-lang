from dataclasses import replace
import unittest

from koschei.native_intelligence_qwen397b_preflight_v1 import (
    EXPECTED_WEIGHT_SHARDS_V1,
    Qwen397BPreflightError,
    seal_qwen397b_preflight_v1,
)
from koschei.native_intelligence_qwen397b_profile_v1 import (
    OFFICIAL_ARCHITECTURE,
    OFFICIAL_EXPERTS,
    OFFICIAL_EXPERTS_PER_TOKEN,
    OFFICIAL_MAX_POSITION_EMBEDDINGS,
    OFFICIAL_TEXT_HIDDEN_SIZE,
    OFFICIAL_TEXT_LAYERS,
)
from koschei.native_intelligence_qwen397b_training_plan_v1 import CANONICAL_QWEN397B_REVISION_V1
from koschei.native_intelligence_v1 import CANONICAL_BASE_MODEL_V1


def preflight():
    return seal_qwen397b_preflight_v1(
        repo_id=CANONICAL_BASE_MODEL_V1,
        requested_revision=CANONICAL_QWEN397B_REVISION_V1,
        resolved_revision=CANONICAL_QWEN397B_REVISION_V1,
        shard_count=EXPECTED_WEIGHT_SHARDS_V1,
        weight_bytes=807_000_000_000,
        safetensors_index_sha256="a" * 64,
        architecture=OFFICIAL_ARCHITECTURE,
        text_hidden_size=OFFICIAL_TEXT_HIDDEN_SIZE,
        text_layers=OFFICIAL_TEXT_LAYERS,
        experts=OFFICIAL_EXPERTS,
        experts_per_token=OFFICIAL_EXPERTS_PER_TOKEN,
        native_context=OFFICIAL_MAX_POSITION_EMBEDDINGS,
    )


class Qwen397BPreflightV1Tests(unittest.TestCase):
    def test_preflight_seals_resolved_base_artifact_identity(self):
        evidence = preflight()
        evidence.assert_sealed()
        self.assertEqual(evidence.shard_count, 94)
        self.assertEqual(evidence.resolved_revision, CANONICAL_QWEN397B_REVISION_V1)
        self.assertEqual(len(evidence.weights_identity_digest), 64)
        self.assertFalse(evidence.authority)

    def test_missing_shard_or_incomplete_weight_observation_fails_closed(self):
        evidence = preflight()
        with self.assertRaisesRegex(Qwen397BPreflightError, "shard count mismatch"):
            replace(evidence, shard_count=93).assert_sealed()
        with self.assertRaisesRegex(Qwen397BPreflightError, "weight-byte observation is incomplete"):
            replace(evidence, weight_bytes=100_000_000_000).assert_sealed()

    def test_revision_or_architecture_drift_fails_closed(self):
        evidence = preflight()
        with self.assertRaises(Qwen397BPreflightError):
            replace(evidence, resolved_revision="b" * 40).assert_sealed()
        with self.assertRaises(Qwen397BPreflightError):
            replace(evidence, experts=511).assert_sealed()

    def test_preflight_does_not_claim_full_weight_byte_hash(self):
        evidence = preflight()
        self.assertNotEqual(evidence.weights_identity_digest, evidence.safetensors_index_sha256)
        self.assertNotEqual(evidence.digest, evidence.weights_identity_digest)


if __name__ == "__main__":
    unittest.main()
