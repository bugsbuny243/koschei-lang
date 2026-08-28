import importlib.util
from pathlib import Path
import pytest

from koschei.monotonic_witness_v1 import (
    MonotonicWitnessVerificationResultV1,
    MonotonicWitnessV1Error,
    WitnessConfirmedGenerationStateV1,
    seal_monotonic_witness_abi_v1,
    verify_monotonic_witness_response_v1,
)
from koschei.provider_native_verifier_v1 import verify_provider_native_response_v1
from koschei.trust_anchor_admission_v1 import seal_trust_anchor_manifest_v1
from koschei.trust_anchor_generation_store_v1 import SqliteTrustAnchorGenerationStoreV1


def _provider_fixture_module():
    path=Path(__file__).with_name("test_provider_native_verifier_v1.py")
    spec=importlib.util.spec_from_file_location("koschei_provider_native_fixture",path)
    module=importlib.util.module_from_spec(spec); assert spec.loader is not None; spec.loader.exec_module(module); return module


def _witness(*,anchor_id,generation,manifest_digest,counter=100,current_epoch=71,suffix="a"):
    artifact=("external-monotonic-witness-verifier-"+suffix).encode(); raw=("signed-witness-response-"+suffix).encode(); challenge=("runtime-challenge-"+suffix).encode(); key=(suffix.encode()*32)[:32]
    abi=seal_monotonic_witness_abi_v1(provider_id="external-transparency-witness",protocol_id="opaque-checkpoint",schema_version="v1",verifier_artifact_bytes=artifact)
    receipt=verify_monotonic_witness_response_v1(abi=abi,verifier_artifact_bytes=artifact,raw_response_bytes=raw,expected_anchor_id=anchor_id,challenge_bytes=challenge,current_epoch=current_epoch,verifier=lambda response,expected_challenge:MonotonicWitnessVerificationResultV1(anchor_id,generation,manifest_digest,counter,current_epoch,current_epoch+5,expected_challenge,b"provider-proof:"+response),witness_verifier_key=key)
    return dict(receipt=receipt,abi=abi,artifact=artifact,raw=raw,challenge=challenge,key=key,current_epoch=current_epoch)


def _confirmed(local_state,w):
    return WitnessConfirmedGenerationStateV1(local_state=local_state,witness_receipt=w['receipt'],abi=w['abi'],verifier_artifact_bytes=w['artifact'],raw_response_bytes=w['raw'],challenge_bytes=w['challenge'],witness_verifier_key=w['key'],current_epoch=w['current_epoch'])


def test_sqlite_snapshot_rollback_is_detected_by_newer_external_witness(tmp_path):
    fixture=_provider_fixture_module(); x=fixture.admitted(); store_key=b"s"*32; db=tmp_path/"generation.db"
    with SqliteTrustAnchorGenerationStoreV1(db,generation_store_key=store_key) as store:
        store.observe(x['manifest_a'],root_signing_key=x['root_key_a'],abi=x['attabi_a'],current_epoch=71)
        newer=seal_trust_anchor_manifest_v1(anchor_id=x['manifest_a'].anchor_id,generation=2,abi=x['attabi_a'],allowed_trust_root_ids=("root-a",),valid_from_epoch=70,expires_before_epoch=90,root_signing_key=x['root_key_a'])
        witness=_witness(anchor_id=newer.anchor_id,generation=newer.generation,manifest_digest=newer.manifest_digest,suffix="snapshot")
        confirmed=_confirmed(store,witness)
        with pytest.raises(MonotonicWitnessV1Error,match="differs from external monotonic witness"):
            confirmed.assert_current_binding(anchor_id=x['manifest_a'].anchor_id,generation=x['manifest_a'].generation,manifest_digest=x['manifest_a'].manifest_digest)


def test_provider_native_receipt_binds_both_live_witness_receipts():
    fixture=_provider_fixture_module(); x=fixture.admitted(); txid,effect_receipt,effect_envelope=fixture.effect_chain(); calls=[]
    wa=_witness(anchor_id=x['manifest_a'].anchor_id,generation=x['manifest_a'].generation,manifest_digest=x['manifest_a'].manifest_digest,suffix="a")
    wb=_witness(anchor_id=x['manifest_b'].anchor_id,generation=x['manifest_b'].generation,manifest_digest=x['manifest_b'].manifest_digest,suffix="b")
    state_a=_confirmed(x['generation_state_a'],wa); state_b=_confirmed(x['generation_state_b'],wb)
    kwargs=fixture.provider_kwargs(x,txid,effect_receipt,effect_envelope); kwargs['builder_a_generation_state']=state_a; kwargs['builder_b_generation_state']=state_b
    native=verify_provider_native_response_v1(**kwargs,verifier=lambda raw:calls.append(1) or fixture.verifier_for(txid)(raw))
    assert calls==[1]
    assert native.builder_a_monotonic_witness_receipt_digest==wa['receipt'].receipt_digest
    assert native.builder_b_monotonic_witness_receipt_digest==wb['receipt'].receipt_digest
    native.assert_authenticated(provider_native_verifier_key=kwargs['provider_native_verifier_key'],adapter_abi=kwargs['adapter_abi'],runtime_admission=kwargs['runtime_admission'],reproducible_admission=kwargs['reproducible_admission'],reproducibility_receipt=kwargs['reproducibility_receipt'],reproducibility_key=kwargs['reproducibility_key'],builder_a_generation_state=state_a,builder_b_generation_state=state_b,provenance=kwargs['provenance'],verifier_artifact_bytes=kwargs['verifier_artifact_bytes'],build_provenance_key=kwargs['build_provenance_key'],runtime_admission_key=kwargs['runtime_admission_key'],reproducible_admission_key=kwargs['reproducible_admission_key'],effect_envelope=effect_envelope,effect_receipt=effect_receipt,effect_result_bytes=txid,raw_response_bytes=kwargs['raw_response_bytes'])


def test_stale_external_witness_rejects_before_provider_callback():
    fixture=_provider_fixture_module(); x=fixture.admitted(); txid,effect_receipt,effect_envelope=fixture.effect_chain(); calls=[]
    newer=seal_trust_anchor_manifest_v1(anchor_id=x['manifest_a'].anchor_id,generation=2,abi=x['attabi_a'],allowed_trust_root_ids=("root-a",),valid_from_epoch=70,expires_before_epoch=90,root_signing_key=x['root_key_a'])
    wa=_witness(anchor_id=newer.anchor_id,generation=newer.generation,manifest_digest=newer.manifest_digest,suffix="newer-a")
    wb=_witness(anchor_id=x['manifest_b'].anchor_id,generation=x['manifest_b'].generation,manifest_digest=x['manifest_b'].manifest_digest,suffix="current-b")
    kwargs=fixture.provider_kwargs(x,txid,effect_receipt,effect_envelope); kwargs['builder_a_generation_state']=_confirmed(x['generation_state_a'],wa); kwargs['builder_b_generation_state']=_confirmed(x['generation_state_b'],wb)
    with pytest.raises(MonotonicWitnessV1Error,match="differs from external monotonic witness"):
        verify_provider_native_response_v1(**kwargs,verifier=lambda raw:calls.append(1) or fixture.verifier_for(txid)(raw))
    assert calls==[]


def test_mixed_witnessed_and_local_builder_states_fail_closed_before_callback():
    fixture=_provider_fixture_module(); x=fixture.admitted(); txid,effect_receipt,effect_envelope=fixture.effect_chain(); calls=[]
    wa=_witness(anchor_id=x['manifest_a'].anchor_id,generation=x['manifest_a'].generation,manifest_digest=x['manifest_a'].manifest_digest,suffix="mixed")
    kwargs=fixture.provider_kwargs(x,txid,effect_receipt,effect_envelope); kwargs['builder_a_generation_state']=_confirmed(x['generation_state_a'],wa)
    with pytest.raises(ValueError,match="both builder generation states"):
        verify_provider_native_response_v1(**kwargs,verifier=lambda raw:calls.append(1) or fixture.verifier_for(txid)(raw))
    assert calls==[]


def test_witness_artifact_challenge_and_raw_response_are_bound():
    w=_witness(anchor_id="anchor-a",generation=7,manifest_digest="manifest-7",suffix="binding")
    with pytest.raises(MonotonicWitnessV1Error,match="raw response mismatch"):
        w['receipt'].assert_integrity(abi=w['abi'],verifier_artifact_bytes=w['artifact'],raw_response_bytes=b"different-response",challenge_bytes=w['challenge'],witness_verifier_key=w['key'])
    with pytest.raises(MonotonicWitnessV1Error,match="challenge mismatch"):
        w['receipt'].assert_integrity(abi=w['abi'],verifier_artifact_bytes=w['artifact'],raw_response_bytes=w['raw'],challenge_bytes=b"different-challenge",witness_verifier_key=w['key'])
