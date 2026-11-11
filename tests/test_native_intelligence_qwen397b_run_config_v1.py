from dataclasses import replace
from pathlib import Path
import tempfile
import unittest

from koschei.native_intelligence_holdout_v1 import build_native_intelligence_holdout_v1
from koschei.native_intelligence_qwen397b_base_spec_v1 import CANONICAL_QWEN397B_REVISION_V1
from koschei.native_intelligence_qwen397b_preflight_v1 import seal_qwen397b_preflight_v1
from koschei.native_intelligence_qwen397b_profile_v1 import (
    OFFICIAL_ARCHITECTURE,
    OFFICIAL_EXPERTS,
    OFFICIAL_EXPERTS_PER_TOKEN,
    OFFICIAL_MAX_POSITION_EMBEDDINGS,
    OFFICIAL_TEXT_HIDDEN_SIZE,
    OFFICIAL_TEXT_LAYERS,
    canonical_qwen397b_koschei_profile_v1,
)
from koschei.native_intelligence_qwen397b_run_config_v1 import (
    Qwen397BRunConfigError,
    seal_qwen397b_run_config_v1,
)
from koschei.native_intelligence_qwen397b_token_profile_v1 import (
    FORMATTING_VERSION_V1,
    seal_qwen397b_token_profile_v1,
)
from koschei.native_intelligence_training_balance_v1 import build_balanced_native_training_corpus_v1
from koschei.native_intelligence_training_export_v1 import write_native_training_export_v1
from koschei.native_intelligence_v1 import CANONICAL_BASE_MODEL_V1
from koschei.native_model_curriculum_v2 import build_native_model_curriculum_v2


class Qwen397BRunConfigV1Tests(unittest.TestCase):
    def setUp(self):
        curriculum = build_native_model_curriculum_v2(
            source_commit="a" * 40,
            parent_curriculum_digest="b" * 64,
        )
        holdout = build_native_intelligence_holdout_v1(curriculum)
        corpus = build_balanced_native_training_corpus_v1(holdout, variants_per_family=1)
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.manifest = write_native_training_export_v1(
            holdout, corpus, Path(self.temp.name) / "release"
        )
        self.profile = canonical_qwen397b_koschei_profile_v1()
        self.preflight = seal_qwen397b_preflight_v1(
            repo_id=CANONICAL_BASE_MODEL_V1,
            requested_revision=CANONICAL_QWEN397B_REVISION_V1,
            resolved_revision=CANONICAL_QWEN397B_REVISION_V1,
            shard_count=94,
            weight_bytes=807_000_000_000,
            safetensors_index_sha256="a" * 64,
            architecture=OFFICIAL_ARCHITECTURE,
            text_hidden_size=OFFICIAL_TEXT_HIDDEN_SIZE,
            text_layers=OFFICIAL_TEXT_LAYERS,
            experts=OFFICIAL_EXPERTS,
            experts_per_token=OFFICIAL_EXPERTS_PER_TOKEN,
            native_context=OFFICIAL_MAX_POSITION_EMBEDDINGS,
        )
        counts = {row.split: row.example_count for row in self.manifest.files}
        self.token_profile = seal_qwen397b_token_profile_v1(
            self.manifest,
            self.profile,
            tokenizer_revision=CANONICAL_QWEN397B_REVISION_V1,
            formatting_version=FORMATTING_VERSION_V1,
            train_examples=counts["train"],
            validation_examples=counts["validation"],
            train_tokens=counts["train"] * 150,
            validation_tokens=counts["validation"] * 150,
            max_train_tokens=500,
            max_validation_tokens=500,
            train_truncated_examples=0,
            validation_truncated_examples=0,
        )

    def test_run_config_binds_all_first_run_evidence(self):
        config = seal_qwen397b_run_config_v1(
            self.profile, self.preflight, self.token_profile, self.manifest
        )
        config.assert_for(self.profile, self.preflight, self.token_profile, self.manifest)
        self.assertEqual(config.profile_digest, self.profile.digest)
        self.assertEqual(config.base_preflight_digest, self.preflight.digest)
        self.assertEqual(config.token_profile_digest, self.token_profile.digest)
        self.assertEqual(config.training_export_digest, self.manifest.digest)
        self.assertFalse(config.authority)

    def test_foreign_token_profile_or_preflight_fails_closed(self):
        config = seal_qwen397b_run_config_v1(
            self.profile, self.preflight, self.token_profile, self.manifest
        )
        forged_token = replace(self.token_profile, digest="b" * 64)
        with self.assertRaises(Qwen397BRunConfigError):
            config.assert_for(self.profile, self.preflight, forged_token, self.manifest)

        forged_preflight = replace(self.preflight, digest="c" * 64)
        with self.assertRaises(Qwen397BRunConfigError):
            config.assert_for(self.profile, forged_preflight, self.token_profile, self.manifest)

    def test_run_config_cannot_carry_authority_or_static_profile_substitute(self):
        config = seal_qwen397b_run_config_v1(
            self.profile, self.preflight, self.token_profile, self.manifest
        )
        with self.assertRaises(Qwen397BRunConfigError):
            replace(config, authority=True).assert_for(
                self.profile, self.preflight, self.token_profile, self.manifest
            )
        self.assertNotEqual(config.digest, self.profile.digest)


if __name__ == "__main__":
    unittest.main()
