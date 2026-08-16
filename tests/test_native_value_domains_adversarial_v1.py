from __future__ import annotations

from dataclasses import replace
from pathlib import Path
import tempfile
import unicodedata
import unittest

from koschei.native_value_domains_v1 import (
    GLYPHS,
    NativeValueDomainError,
    check_native_value_domains,
)
from koschei.object_space_value_domains_v1 import (
    ObjectSpaceValueDomainError,
    decode_native_value_domain_graph,
    encode_native_value_domain_graph_secret,
)
from koschei.object_space_v1 import create_object_space_project
from koschei.temporal_access_v1 import TemporalAccessPolicy
from tests.test_object_space_adversarial_v1 import TestOnlyProvider


class NativeValueDomainsAdversarialV1Tests(unittest.TestCase):
    def test_numeric_operation_refuses_truth_coercion(self) -> None:
        with self.assertRaisesRegex(NativeValueDomainError, "requires whole/whole"):
            check_native_value_domains(
                "witness flag truth yes\n"
                "witness one 1\n"
                "witness bad sum flag one\n"
                "resolve bad\n"
            )

    def test_same_refuses_cross_domain_equality_coercion(self) -> None:
        with self.assertRaisesRegex(NativeValueDomainError, "identical value domains"):
            check_native_value_domains(
                "witness flag truth yes\n"
                "witness one 1\n"
                "witness bad same flag one\n"
                "resolve bad\n"
            )

    def test_merge_refuses_textual_coercion(self) -> None:
        with self.assertRaisesRegex(NativeValueDomainError, "requires glyphs/glyphs"):
            check_native_value_domains(
                "witness text glyphs 1 x\n"
                "witness one 1\n"
                "witness bad merge text one\n"
                "resolve bad\n"
            )

    def test_nfd_source_alias_is_rejected(self) -> None:
        source = "witness text glyphs 6 cafe\u0301\nresolve text\n"
        self.assertNotEqual(source, unicodedata.normalize("NFC", source))
        with self.assertRaisesRegex(NativeValueDomainError, "Unicode NFC canonical"):
            check_native_value_domains(source)

    def test_glyph_byte_length_alias_and_mismatch_are_rejected(self) -> None:
        with self.assertRaisesRegex(NativeValueDomainError, "leading-zero alias"):
            check_native_value_domains(
                "witness text glyphs 01 x\n"
                "resolve text\n"
            )
        with self.assertRaisesRegex(NativeValueDomainError, "payload is 2 bytes"):
            check_native_value_domains(
                "witness text glyphs 1 é\n"
                "resolve text\n"
            )

    def test_merge_result_is_nfc_even_when_composition_crosses_operand_boundary(self) -> None:
        checked = check_native_value_domains(
            "witness base glyphs 1 e\n"
            "witness mark glyphs 2 \u0301\n"
            "witness joined merge base mark\n"
            "resolve joined\n"
        )
        self.assertEqual(checked.value.domain, GLYPHS)
        self.assertEqual(checked.value.value, "é")
        self.assertEqual(checked.value.value, unicodedata.normalize("NFC", checked.value.value))

    def test_bidi_override_control_is_rejected_from_glyph_source(self) -> None:
        source = "witness text glyphs 5 a\u202eb\nresolve text\n"
        with self.assertRaisesRegex(NativeValueDomainError, "bidirectional control"):
            check_native_value_domains(source)

    def test_value_domain_frontend_identity_tamper_fails_closed(self) -> None:
        provider = TestOnlyProvider()
        temporal_key = bytes(range(1, 65))
        policy = TemporalAccessPolicy(period_seconds=30)
        now = 1_800_000_000
        project_id = bytes.fromhex("a1" * 16)
        root_id = bytes.fromhex("a2" * 16)
        payload = b"witness answer 42\nresolve answer\n"
        objects = {root_id: payload}
        secret = encode_native_value_domain_graph_secret(
            project_id=project_id,
            root_object_id=root_id,
            objects=objects,
        )
        with tempfile.TemporaryDirectory() as temporary:
            project, _ = create_object_space_project(
                Path(temporary) / "space",
                provider=provider,
                temporal_key=temporal_key,
                objects=objects,
                root_object_id=root_id,
                graph_secret=secret,
                temporal_policy=policy,
                now=now,
                project_id=project_id,
            )
            forged = bytearray(project.graph_secret)
            forged[-1] ^= 1
            with self.assertRaisesRegex(ObjectSpaceValueDomainError, "frontend identity mismatch"):
                decode_native_value_domain_graph(
                    replace(project, graph_secret=bytes(forged))
                )

    def test_value_domain_digest_tamper_fails_against_k0_authority(self) -> None:
        provider = TestOnlyProvider()
        temporal_key = bytes(range(1, 65))
        policy = TemporalAccessPolicy(period_seconds=30)
        now = 1_800_000_000
        project_id = bytes.fromhex("b1" * 16)
        root_id = bytes.fromhex("b2" * 16)
        payload = b"witness answer 42\nresolve answer\n"
        objects = {root_id: payload}
        secret = encode_native_value_domain_graph_secret(
            project_id=project_id,
            root_object_id=root_id,
            objects=objects,
        )
        with tempfile.TemporaryDirectory() as temporary:
            project, _ = create_object_space_project(
                Path(temporary) / "space",
                provider=provider,
                temporal_key=temporal_key,
                objects=objects,
                root_object_id=root_id,
                graph_secret=secret,
                temporal_policy=policy,
                now=now,
                project_id=project_id,
            )
            forged = bytearray(project.graph_secret)
            # Header layout ends with digest(32) + frontend(32). Flip digest only.
            forged[-33] ^= 1
            with self.assertRaisesRegex(ObjectSpaceValueDomainError, "digest differs from sealed k0 authority"):
                decode_native_value_domain_graph(
                    replace(project, graph_secret=bytes(forged))
                )


if __name__ == "__main__":
    unittest.main()
