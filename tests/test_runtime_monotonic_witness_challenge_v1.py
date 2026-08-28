from dataclasses import replace
import pytest

from koschei.monotonic_witness_runtime_v1 import verify_monotonic_witness_with_runtime_challenge_v1
from koschei.monotonic_witness_v1 import MonotonicWitnessVerificationResultV1,seal_monotonic_witness_abi_v1
from koschei.runtime_monotonic_witness_challenge_v1 import RuntimeMonotonicWitnessChallengeV1Error,issue_runtime_monotonic_witness_challenge_v1


def _world():
    anchor="offline-root-a"; artifact=b"external-witness-verifier-v1"; raw=b"signed-witness-response-v1"; verifier_key=b"v"*32; challenge_key=b"c"*32
    abi=seal_monotonic_witness_abi_v1(provider_id="external-witness",protocol_id="opaque-checkpoint",schema_version="v1",verifier_artifact_bytes=artifact)
    challenge=issue_runtime_monotonic_witness_challenge_v1(anchor_id=anchor,current_epoch=71,ttl_epochs=2,witness_challenge_key=challenge_key)
    return locals()


def test_runtime_issued_challenge_drives_witness_verifier():
    x=_world(); calls=[]
    receipt=verify_monotonic_witness_with_runtime_challenge_v1(abi=x['abi'],verifier_artifact_bytes=x['artifact'],raw_response_bytes=x['raw'],expected_anchor_id=x['anchor'],runtime_challenge=x['challenge'],current_epoch=71,verifier=lambda raw,challenge:calls.append((raw,challenge)) or MonotonicWitnessVerificationResultV1(x['anchor'],7,"manifest-7",99,71,73,challenge,b"proof:"+raw),witness_verifier_key=x['verifier_key'],witness_challenge_key=x['challenge_key'])
    assert calls==[(x['raw'],x['challenge'].challenge_bytes)]
    assert receipt.challenge_digest


def test_expired_runtime_challenge_rejects_before_witness_callback():
    x=_world(); calls=[]
    with pytest.raises(RuntimeMonotonicWitnessChallengeV1Error,match="not live"):
        verify_monotonic_witness_with_runtime_challenge_v1(abi=x['abi'],verifier_artifact_bytes=x['artifact'],raw_response_bytes=x['raw'],expected_anchor_id=x['anchor'],runtime_challenge=x['challenge'],current_epoch=73,verifier=lambda raw,challenge:calls.append(1) or MonotonicWitnessVerificationResultV1(x['anchor'],7,"manifest-7",99,71,74,challenge,b"proof"),witness_verifier_key=x['verifier_key'],witness_challenge_key=x['challenge_key'])
    assert calls==[]


def test_forged_runtime_challenge_bytes_fail_authentication_before_callback():
    x=_world(); calls=[]; forged=replace(x['challenge'],challenge_bytes=b"z"*32)
    with pytest.raises(RuntimeMonotonicWitnessChallengeV1Error,match="bytes do not match"):
        verify_monotonic_witness_with_runtime_challenge_v1(abi=x['abi'],verifier_artifact_bytes=x['artifact'],raw_response_bytes=x['raw'],expected_anchor_id=x['anchor'],runtime_challenge=forged,current_epoch=71,verifier=lambda raw,challenge:calls.append(1) or MonotonicWitnessVerificationResultV1(x['anchor'],7,"manifest-7",99,71,73,challenge,b"proof"),witness_verifier_key=x['verifier_key'],witness_challenge_key=x['challenge_key'])
    assert calls==[]


def test_runtime_challenge_is_anchor_scoped():
    x=_world(); calls=[]
    with pytest.raises(RuntimeMonotonicWitnessChallengeV1Error,match="anchor mismatch"):
        verify_monotonic_witness_with_runtime_challenge_v1(abi=x['abi'],verifier_artifact_bytes=x['artifact'],raw_response_bytes=x['raw'],expected_anchor_id="offline-root-b",runtime_challenge=x['challenge'],current_epoch=71,verifier=lambda raw,challenge:calls.append(1) or MonotonicWitnessVerificationResultV1("offline-root-b",7,"manifest-7",99,71,73,challenge,b"proof"),witness_verifier_key=x['verifier_key'],witness_challenge_key=x['challenge_key'])
    assert calls==[]
