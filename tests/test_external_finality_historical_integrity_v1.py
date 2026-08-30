from dataclasses import replace
import importlib.util
from pathlib import Path
import pytest
from koschei.external_finality_historical_integrity_v1 import ExternalFinalityHistoricalIntegrityV1Error,assert_external_finality_historical_integrity_v1,assert_historical_finalized_v1
from koschei.trust_anchor_admission_v1 import seal_trust_anchor_manifest_v1


def _fixture_module():
    path=Path(__file__).with_name("test_external_finality_proof_envelope_v1.py")
    spec=importlib.util.spec_from_file_location("_koschei_finality_fixture_v1",path)
    module=importlib.util.module_from_spec(spec); assert spec.loader is not None; spec.loader.exec_module(module); return module


def _historical_kwargs(x,envelope=None):
    return dict(envelope=envelope or x['finality'],effect_envelope=x['effect_envelope'],effect_receipt=x['effect_receipt'],effect_result_bytes=x['effect_result'],raw_provider_response_bytes=x['raw_pi_response'],adapter_abi=x['adapter_abi'],provenance=x['provenance'],runtime_admission=x['runtime_admission'],reproducible_admission=x['reproducible_admission'],reproducibility_receipt=x['repro'],reproducibility_key=x['repro_key'],verifier_artifact_bytes=x['verifier_artifact'],build_provenance_key=x['bk'],runtime_admission_key=x['ak'],reproducible_admission_key=x['gate_key'],native_receipt=x['native_receipt'],base=x['base'],grant=x['grant'],evidence=x['evidence'],mir=x['mir'],request=x['request'],proof=x['proof'],bound=x['bound'],basis=x['basis'],decision=x['decision'],permit=x['permit'],consumption=x['consumption'],verdict=x['verdict'],attestation=x['attestation'],decision_key=x['dk'],runtime_key=x['rk'],effect_key=x['ek'],provider_native_verifier_key=x['nk'],provider_verifier_key=x['vk'],finality_key=x['fk'])


def test_generation_advance_breaks_current_validity_but_not_historical_integrity():
    fixture=_fixture_module(); x=fixture.chain()
    assert_external_finality_historical_integrity_v1(**_historical_kwargs(x)); assert_historical_finalized_v1(x['finality'])
    newer=seal_trust_anchor_manifest_v1(anchor_id=x['manifest_a'].anchor_id,generation=2,abi=x['attabi_a'],allowed_trust_root_ids=("root-a",),valid_from_epoch=70,expires_before_epoch=90,root_signing_key=x['root_key_a'])
    x['generation_state_a'].observe(newer,root_signing_key=x['root_key_a'],abi=x['attabi_a'],current_epoch=71)
    with pytest.raises(ValueError,match="current observed generation"): fixture.validate(x)
    assert_external_finality_historical_integrity_v1(**_historical_kwargs(x)); assert_historical_finalized_v1(x['finality'])


def test_historical_integrity_still_rejects_proof_tampering():
    fixture=_fixture_module(); x=fixture.chain(); forged=replace(x['finality'],provider_proof_digest="0"*64)
    with pytest.raises(ExternalFinalityHistoricalIntegrityV1Error): assert_external_finality_historical_integrity_v1(**_historical_kwargs(x,forged))


def test_historical_integrity_does_not_authorize_new_execution():
    fixture=_fixture_module(); x=fixture.chain(); newer=seal_trust_anchor_manifest_v1(anchor_id=x['manifest_a'].anchor_id,generation=2,abi=x['attabi_a'],allowed_trust_root_ids=("root-a",),valid_from_epoch=70,expires_before_epoch=90,root_signing_key=x['root_key_a']); x['generation_state_a'].observe(newer,root_signing_key=x['root_key_a'],abi=x['attabi_a'],current_epoch=71)
    assert_external_finality_historical_integrity_v1(**_historical_kwargs(x))
    with pytest.raises(ValueError,match="current observed generation"): fixture.validate(x)
