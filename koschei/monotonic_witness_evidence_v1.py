"""Archival evidence bundle for a monotonic-witness receipt v1.

The bundle contains public/provenance inputs needed to recheck the receipt seal later.
The verifier HMAC key is deliberately not stored inside the bundle.
"""
from __future__ import annotations
from dataclasses import dataclass
from .monotonic_witness_v1 import MonotonicWitnessAbiV1,MonotonicWitnessReceiptV1

@dataclass(frozen=True,slots=True)
class MonotonicWitnessEvidenceBundleV1:
    receipt:MonotonicWitnessReceiptV1
    abi:MonotonicWitnessAbiV1
    verifier_artifact_bytes:bytes
    raw_response_bytes:bytes
    challenge_bytes:bytes
    def assert_integrity(self,*,witness_verifier_key:bytes)->None:
        self.receipt.assert_integrity(abi=self.abi,verifier_artifact_bytes=self.verifier_artifact_bytes,raw_response_bytes=self.raw_response_bytes,challenge_bytes=self.challenge_bytes,witness_verifier_key=witness_verifier_key)
