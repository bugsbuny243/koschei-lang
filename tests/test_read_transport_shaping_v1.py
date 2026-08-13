from __future__ import annotations

import unittest

from koschei.read_transport_shaping_v1 import ReadTransportError, read_shaped_source


OID = "0123456789abcdef0123456789abcdef"
OTHER_OID = "fedcba9876543210fedcba9876543210"
DECEPTION_KEY = b"d" * 32
SHAPING_KEY = b"s" * 32
CANONICAL = b"fn crown() -> Int { return 123456; }\n"


class FakeTime:
    def __init__(self):
        self.now = 1_000_000
        self.sleeps: list[float] = []

    def clock(self) -> int:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.sleeps.append(seconds)
        self.now += int(seconds * 1_000_000_000)


class ReadTransportShapingV1Tests(unittest.TestCase):
    def test_canonical_and_decoy_share_fixed_transport_bucket(self):
        canonical = read_shaped_source(
            project_id="p-shape", object_id=OID, epoch=10, authorized=True,
            canonical_reader=lambda _: CANONICAL,
            deception_key=DECEPTION_KEY, shaping_key=SHAPING_KEY,
            bucket_bytes=1024,
        )
        decoy = read_shaped_source(
            project_id="p-shape", object_id=OID, epoch=10, authorized=False,
            canonical_reader=lambda _: (_ for _ in ()).throw(AssertionError("must not read canonical")),
            deception_key=DECEPTION_KEY, shaping_key=SHAPING_KEY,
            bucket_bytes=1024,
        )
        self.assertEqual(len(canonical.transport), 1024)
        self.assertEqual(len(decoy.transport), 1024)
        self.assertEqual(canonical.provenance, "canonical")
        self.assertEqual(decoy.provenance, "decoy")

    def test_unauthorized_shaped_read_never_touches_canonical_reader(self):
        calls: list[str] = []
        response = read_shaped_source(
            project_id="p-shape", object_id=OID, epoch=11, authorized=False,
            canonical_reader=lambda oid: calls.append(oid) or CANONICAL,
            deception_key=DECEPTION_KEY, shaping_key=SHAPING_KEY,
            bucket_bytes=2048,
        )
        self.assertEqual(calls, [])
        self.assertFalse(response.deployable)
        self.assertEqual(response.provenance, "decoy")
        self.assertNotIn(b"123456", response.transport)

    def test_oversized_canonical_fails_closed_instead_of_changing_bucket(self):
        with self.assertRaises(ReadTransportError):
            read_shaped_source(
                project_id="p-shape", object_id=OID, epoch=12, authorized=True,
                canonical_reader=lambda _: b"x" * 513,
                deception_key=DECEPTION_KEY, shaping_key=SHAPING_KEY,
                bucket_bytes=512,
            )

    def test_timing_floor_uses_injected_clock_and_sleeper(self):
        fake = FakeTime()
        response = read_shaped_source(
            project_id="p-shape", object_id=OID, epoch=13, authorized=False,
            canonical_reader=lambda _: CANONICAL,
            deception_key=DECEPTION_KEY, shaping_key=SHAPING_KEY,
            bucket_bytes=1024,
            target_floor_ns=5_000_000,
            clock_ns=fake.clock,
            sleeper=fake.sleep,
        )
        self.assertTrue(response.floor_met)
        self.assertGreaterEqual(response.elapsed_ns, 5_000_000)
        self.assertEqual(len(fake.sleeps), 1)

    def test_padding_changes_across_epoch_and_object(self):
        one = read_shaped_source(
            project_id="p-shape", object_id=OID, epoch=20, authorized=False,
            canonical_reader=lambda _: CANONICAL,
            deception_key=DECEPTION_KEY, shaping_key=SHAPING_KEY,
            bucket_bytes=1024,
        )
        next_epoch = read_shaped_source(
            project_id="p-shape", object_id=OID, epoch=21, authorized=False,
            canonical_reader=lambda _: CANONICAL,
            deception_key=DECEPTION_KEY, shaping_key=SHAPING_KEY,
            bucket_bytes=1024,
        )
        other_object = read_shaped_source(
            project_id="p-shape", object_id=OTHER_OID, epoch=20, authorized=False,
            canonical_reader=lambda _: CANONICAL,
            deception_key=DECEPTION_KEY, shaping_key=SHAPING_KEY,
            bucket_bytes=1024,
        )
        self.assertNotEqual(one.transport_digest, next_epoch.transport_digest)
        self.assertNotEqual(one.transport_digest, other_object.transport_digest)

    def test_weak_shaping_key_fails_closed(self):
        with self.assertRaises(ReadTransportError):
            read_shaped_source(
                project_id="p-shape", object_id=OID, epoch=30, authorized=False,
                canonical_reader=lambda _: CANONICAL,
                deception_key=DECEPTION_KEY, shaping_key=b"short",
                bucket_bytes=1024,
            )


if __name__ == "__main__":
    unittest.main()
