from __future__ import annotations

import unittest

from koschei.decoy_view_broker_v1 import (
    DecoyViewError,
    read_source_view,
    require_canonical_build_view,
)


OID_A = "0123456789abcdef0123456789abcdef"
OID_B = "fedcba9876543210fedcba9876543210"
KEY = b"z" * 32
SECRET_A = b"fn custody_root() -> Int { return 700001; }\n"
SECRET_B = b"fn settlement_root() -> Int { return 800002; }\n"


class DecoyAttackSimulationV1Tests(unittest.TestCase):
    def test_repeated_unauthorized_probing_never_reads_canonical(self):
        calls: list[str] = []

        def canonical_reader(object_id: str) -> bytes:
            calls.append(object_id)
            return SECRET_A

        digests = set()
        for _ in range(1000):
            view = read_source_view(
                project_id="p-attack",
                object_id=OID_A,
                epoch=900,
                authorized=False,
                canonical_reader=canonical_reader,
                deception_key=KEY,
            )
            digests.add(view.view_digest)
            self.assertEqual(view.provenance, "decoy")
            self.assertFalse(view.deployable)

        self.assertEqual(calls, [])
        self.assertEqual(len(digests), 1, "same epoch must stay coherent under repeated probing")

    def test_stale_dump_does_not_match_next_epoch(self):
        stale = read_source_view(
            project_id="p-attack",
            object_id=OID_A,
            epoch=900,
            authorized=False,
            canonical_reader=lambda _: SECRET_A,
            deception_key=KEY,
        )
        current = read_source_view(
            project_id="p-attack",
            object_id=OID_A,
            epoch=901,
            authorized=False,
            canonical_reader=lambda _: SECRET_A,
            deception_key=KEY,
        )
        self.assertNotEqual(stale.view_digest, current.view_digest)
        self.assertNotEqual(stale.content, current.content)

    def test_cross_object_correlation_does_not_collapse_to_same_view(self):
        first = read_source_view(
            project_id="p-attack",
            object_id=OID_A,
            epoch=902,
            authorized=False,
            canonical_reader=lambda _: SECRET_A,
            deception_key=KEY,
        )
        second = read_source_view(
            project_id="p-attack",
            object_id=OID_B,
            epoch=902,
            authorized=False,
            canonical_reader=lambda _: SECRET_B,
            deception_key=KEY,
        )
        self.assertNotEqual(first.view_digest, second.view_digest)
        self.assertNotEqual(first.content, second.content)
        self.assertNotIn(b"custody_root", first.content + second.content)
        self.assertNotIn(b"settlement_root", first.content + second.content)
        self.assertNotIn(b"700001", first.content + second.content)
        self.assertNotIn(b"800002", first.content + second.content)

    def test_decoy_replay_cannot_be_promoted_to_canonical_build(self):
        captured = read_source_view(
            project_id="p-attack",
            object_id=OID_A,
            epoch=903,
            authorized=False,
            canonical_reader=lambda _: SECRET_A,
            deception_key=KEY,
        )
        with self.assertRaises(DecoyViewError):
            require_canonical_build_view(captured)

    def test_many_epochs_never_expose_known_canonical_markers(self):
        calls: list[str] = []

        def canonical_reader(object_id: str) -> bytes:
            calls.append(object_id)
            return SECRET_A

        seen = set()
        for epoch in range(1000, 1100):
            view = read_source_view(
                project_id="p-attack",
                object_id=OID_A,
                epoch=epoch,
                authorized=False,
                canonical_reader=canonical_reader,
                deception_key=KEY,
            )
            seen.add(view.view_digest)
            self.assertNotIn(b"custody_root", view.content)
            self.assertNotIn(b"700001", view.content)
        self.assertEqual(calls, [])
        self.assertEqual(len(seen), 100, "each tested epoch should produce a distinct decoy view")


if __name__ == "__main__":
    unittest.main()
