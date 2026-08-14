from __future__ import annotations

import unittest

from koschei.decoy_measurement_v1 import measure_unauthorized_probes
from koschei.read_authorization_v1 import issue_read_grant

OID = "0123456789abcdef0123456789abcdef"
AUTH_KEY = b"a" * 32
DECEPTION_KEY = b"d" * 32
SECRET = b"fn vault_secret() -> Int { return 424242; }\n"

class DecoyMeasurementWave3Tests(unittest.TestCase):
    def stale_grant(self):
        return issue_read_grant(project_id="p-01", object_id=OID, not_before_epoch=1, expires_after_epoch=1, nonce="wave3-stale-nonce-0001", authorization_key=AUTH_KEY)

    def test_ten_thousand_unauthorized_probes_never_read_canonical(self):
        metrics = measure_unauthorized_probes(project_id="p-01", object_id=OID, start_epoch=100, probes=10_000, stale_grant=self.stale_grant(), deception_key=DECEPTION_KEY, authorization_key=AUTH_KEY, canonical_reader=lambda _: SECRET)
        self.assertEqual(metrics.canonical_reader_calls, 0)
        self.assertEqual(metrics.probes, 10_000)
        self.assertGreater(metrics.unique_ratio, 0.999)
        self.assertGreater(metrics.min_size, 100)
        self.assertGreaterEqual(metrics.max_size, metrics.min_size)

    def test_observable_size_band_is_bounded_for_current_generator(self):
        metrics = measure_unauthorized_probes(project_id="p-01", object_id=OID, start_epoch=200, probes=1_000, stale_grant=self.stale_grant(), deception_key=DECEPTION_KEY, authorization_key=AUTH_KEY, canonical_reader=lambda _: SECRET)
        self.assertLess(metrics.max_size - metrics.min_size, 128)

    def test_timing_metrics_are_reported_without_claiming_constant_time(self):
        metrics = measure_unauthorized_probes(project_id="p-01", object_id=OID, start_epoch=500, probes=250, stale_grant=self.stale_grant(), deception_key=DECEPTION_KEY, authorization_key=AUTH_KEY, canonical_reader=lambda _: SECRET)
        self.assertGreater(metrics.median_ns, 0)
        self.assertGreaterEqual(metrics.p95_ns, metrics.median_ns)

if __name__ == "__main__":
    unittest.main()
