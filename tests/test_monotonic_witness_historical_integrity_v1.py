from dataclasses import replace
import importlib.util
from pathlib import Path
import pytest

from koschei.monotonic_witness_evidence_v1 import MonotonicWitnessEvidenceBundleV1
from koschei.provider_native_historical_integrity_v1 import ProviderNativeHistoricalIntegrityV1Error,assert_provider_native_historical_integrity_v1
from koschei.provider_native_verifier_v1 import verify_provider_native_response_v1


def _load(name,filename):
    path=Path(__file__).with_name(filename); spec=importlib.util.spec_from_file_location(name,path); module=importlib.util.module_from_spec(spec); assert spec.loader is not None; spec.loader.exec_module(module); return module


def _chain():
    provider=_load("provider_fixture_hist","test_provider_native_verifier_v1.py"); witness=_load("witness_fixture_hist","test_monotonic_witness_v1.py")
    x=provider.admitted(); txid,effect_receipt,effect_envelope=provider.effect_chain()
    wa=witness._witness(anchor_id=x['manifest_a'].anchor_id,generation=x['manifest_a'].generation,manifest_digest=x['manifest_a'].manifest_digest,suffix="hist-a")
    wb=witness._witness(anchor_id=x['manifest_b'].anchor_id,generation=x['manifest_b'].generation,manifest_digest=x['manifest_b'].manifest_digest,suffix="hist-b")
    state_a=witness._confirmed(x['generation_state_a'],wa); state_b=witness._confirmed(x['generation_state_b'],wb)
    kwargs=provider.provider_kwargs(x,txid,effect_receipt,effect_envelope); kwargs['builder_a_generation_state']=state_a; kwargs['builder_b_generation_state']=state_b
    native=verify_provider_native_response_v1(**kwargs,verifier=provider.verifier_for(txid))
    bundle_a=MonotonicWitnessEvidenceBundleV1(wa['receipt'],wa['abi'],wa['artifact'],wa['raw'],wa['challenge']); bundle_b=MonotonicWitnessEvidenceBundleV1(wb['receipt'],wb['abi'],wb['artifact'],wb['raw'],wb['challenge'])
    return locals()


def _validate(c,**overrides):
    x=c['x']; k=c['kwargs']
    params=dict(receipt=c['native'],provider_native_verifier_key=k['provider_native_verifier_key'],adapter_abi=k['adapter_abi'],runtime_admission=k['runtime_admission'],reproducible_admission=k['reproducible_admission'],reproducibility_receipt=k['reproducibility_receipt'],reproducibility_key=k['reproducibility_key'],provenance=k['provenance'],verifier_artifact_bytes=k['verifier_artifact_bytes'],build_provenance_key=k['build_provenance_key'],runtime_admission_key=k['runtime_admission_key'],reproducible_admission_key=k['reproducible_admission_key'],effect_envelope=c['effect_envelope'],effect_receipt=c['effect_receipt'],effect_result_bytes=c['txid'],raw_response_bytes=k['raw_response_bytes'],builder_a_witness_evidence=c['bundle_a'],builder_b_witness_evidence=c['bundle_b'],builder_a_witness_verifier_key=c['wa']['key'],builder_b_witness_verifier_key=c['wb']['key'])
    params.update(overrides); assert_provider_native_historical_integrity_v1(**params)


def test_witnessed_provider_receipt_has_historical_integrity_without_current_liveness():
    c=_chain(); _validate(c)


def test_witnessed_historical_validation_requires_archived_witness_evidence():
    c=_chain()
    with pytest.raises(ProviderNativeHistoricalIntegrityV1Error,match="builder A witness evidence is required"):
        _validate(c,builder_a_witness_evidence=None,builder_a_witness_verifier_key=None)


def test_witnessed_historical_validation_rejects_raw_witness_rebinding():
    c=_chain(); bad=replace(c['bundle_a'],raw_response_bytes=b"different-witness-response")
    with pytest.raises(ValueError,match="raw response mismatch"):
        _validate(c,builder_a_witness_evidence=bad)
