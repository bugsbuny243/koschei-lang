from dataclasses import replace
import hashlib

import pytest

from koschei.library_proof_envelope_v1 import make_receipt
from koschei.native_sigil_library_bridge_v1 import expand_native_sigil_mir
from koschei.native_sigil_mir_v1 import lower_native_sigils
from koschei.native_sigil_proof_pipeline_v1 import seal_native_sigil_proof
from koschei.parser import parse
from koschei.provider_adapter_abi_v1 import seal_provider_adapter_abi_v1
from koschei.toolchain_provenance_v1 import attest_toolchain_provenance_v1
from koschei.verified_ir_build_input_v1 import derive_verified_ir_build_input_v1
from koschei.verifier_build_provenance_v1 import attest_verifier_build_from_verified_ir_v1, measure_verifier_artifact_v1
from koschei.verifier_reproducible_admission_v1 import VerifierReproducibleAdmissionV1Error, admit_reproducible_verifier_artifact_v1
from koschei.verifier_reproducible_build_v1 import VerifierReproducibleBuildV1Error, attest_builder_observation_v1, seal_reproducible_build_receipt_v1

SOURCE = """ka treasury;\nvor withdrawal;\nshi evidence;\nthal recovery;\nnur visibility;\n"""


def verified_world():
    mir = lower_native_sigils(parse(SOURCE)); plan = expand_native_sigil_mir(mir).library_plan
    receipts = [make_receipt(activation_step_id=s.activation_step_id, obligation=s.obligation, subsystem=s.subsystem, proof_kind=s.proof_kind, evidence_digest=hashlib.sha256(s.binding_digest.encode()).hexdigest(), success=True) for s in plan.steps]
    proof = seal_native_sigil_proof(mir, receipts)
    return mir, proof, derive_verified_ir_build_input_v1(mir=mir, proof=proof)


def tc(version, byte):
    artifact = ("compiler-" + version).encode(); key = byte * 32
    receipt = attest_toolchain_provenance_v1(toolchain_id="koschei-compiler", toolchain_version=version, toolchain_artifact_bytes=artifact, build_profile="release", toolchain_signing_key=key)
    return receipt, artifact, key


def chain():
    mir, proof, verified = verified_world(); artifact = b"deterministic-verifier-artifact-v1"
    akey, bkey, rkey = b"A"*32, b"B"*32, b"R"*32; bk, rk, gak = b"P"*32, b"L"*32, b"G"*32
    tc_a, tc_a_bytes, tc_a_key = tc("a", b"x"); tc_b, tc_b_bytes, tc_b_key = tc("b", b"y")
    obs_a = attest_builder_observation_v1(builder_id="builder-a", builder_key=akey, verified_input=verified, mir=mir, proof=proof, toolchain=tc_a, toolchain_artifact_bytes=tc_a_bytes, toolchain_signing_key=tc_a_key, artifact_bytes=artifact, build_profile="release-reproducible")
    obs_b = attest_builder_observation_v1(builder_id="builder-b", builder_key=bkey, verified_input=verified, mir=mir, proof=proof, toolchain=tc_b, toolchain_artifact_bytes=tc_b_bytes, toolchain_signing_key=tc_b_key, artifact_bytes=artifact, build_profile="release-reproducible")
    repro = seal_reproducible_build_receipt_v1(reproducibility_key=rkey, builder_a_key=akey, builder_b_key=bkey, builder_a=obs_a, builder_b=obs_b, builder_a_toolchain=tc_a, builder_b_toolchain=tc_b, builder_a_toolchain_artifact_bytes=tc_a_bytes, builder_b_toolchain_artifact_bytes=tc_b_bytes, builder_a_toolchain_signing_key=tc_a_key, builder_b_toolchain_signing_key=tc_b_key, verified_input=verified, mir=mir, proof=proof, artifact_bytes=artifact)
    provenance = attest_verifier_build_from_verified_ir_v1(verified_input=verified, mir=mir, proof=proof, artifact_bytes=artifact, toolchain=tc_a, toolchain_artifact_bytes=tc_a_bytes, toolchain_signing_key=tc_a_key, build_profile="release-reproducible", build_provenance_key=bk)
    abi = seal_provider_adapter_abi_v1(provider_id="pi", adapter_id="pi-verifier", schema_id="pi-payment", schema_version="v1", verifier_implementation_digest=measure_verifier_artifact_v1(artifact))
    base, gated = admit_reproducible_verifier_artifact_v1(reproducible_admission_key=gak, runtime_admission_key=rk, build_provenance_key=bk, reproducibility_key=rkey, builder_a_key=akey, builder_b_key=bkey, reproducibility_receipt=repro, builder_a=obs_a, builder_b=obs_b, builder_a_toolchain=tc_a, builder_b_toolchain=tc_b, builder_a_toolchain_artifact_bytes=tc_a_bytes, builder_b_toolchain_artifact_bytes=tc_b_bytes, builder_a_toolchain_signing_key=tc_a_key, builder_b_toolchain_signing_key=tc_b_key, build_toolchain=tc_a, build_toolchain_artifact_bytes=tc_a_bytes, build_toolchain_signing_key=tc_a_key, verified_input=verified, mir=mir, proof=proof, provenance=provenance, artifact_bytes=artifact, adapter_abi=abi)
    return locals()


def test_two_independent_builders_gate_runtime_admission():
    x = chain(); assert x["repro"].reproducible is True; assert x["repro"].artifact_digest == x["base"].artifact_digest
    assert x["repro"].builder_a_toolchain_provenance_digest == x["tc_a"].provenance_digest
    assert x["repro"].builder_b_toolchain_provenance_digest == x["tc_b"].provenance_digest


def test_same_builder_identity_cannot_count_twice():
    x = chain()
    duplicate = replace(x["obs_b"], builder_id=x["obs_a"].builder_id)
    with pytest.raises(VerifierReproducibleBuildV1Error, match="distinct builder"):
        seal_reproducible_build_receipt_v1(reproducibility_key=x["rkey"], builder_a_key=x["akey"], builder_b_key=x["bkey"], builder_a=x["obs_a"], builder_b=duplicate, builder_a_toolchain=x["tc_a"], builder_b_toolchain=x["tc_b"], builder_a_toolchain_artifact_bytes=x["tc_a_bytes"], builder_b_toolchain_artifact_bytes=x["tc_b_bytes"], builder_a_toolchain_signing_key=x["tc_a_key"], builder_b_toolchain_signing_key=x["tc_b_key"], verified_input=x["verified"], mir=x["mir"], proof=x["proof"], artifact_bytes=x["artifact"])


def test_toolchain_rebinding_is_rejected():
    x = chain(); other, other_bytes, other_key = tc("other", b"z")
    with pytest.raises(VerifierReproducibleBuildV1Error, match="toolchain provenance mismatch"):
        x["obs_a"].assert_authenticated(builder_key=x["akey"], verified_input=x["verified"], mir=x["mir"], proof=x["proof"], toolchain=other, toolchain_artifact_bytes=other_bytes, toolchain_signing_key=other_key, artifact_bytes=x["artifact"])


def test_build_provenance_toolchain_must_appear_in_builder_observations():
    x = chain(); other, other_bytes, other_key = tc("third", b"z")
    foreign = attest_verifier_build_from_verified_ir_v1(verified_input=x["verified"], mir=x["mir"], proof=x["proof"], artifact_bytes=x["artifact"], toolchain=other, toolchain_artifact_bytes=other_bytes, toolchain_signing_key=other_key, build_profile="release-reproducible", build_provenance_key=x["bk"])
    with pytest.raises(VerifierReproducibleAdmissionV1Error, match="absent from reproducible builder observations"):
        admit_reproducible_verifier_artifact_v1(reproducible_admission_key=x["gak"], runtime_admission_key=x["rk"], build_provenance_key=x["bk"], reproducibility_key=x["rkey"], builder_a_key=x["akey"], builder_b_key=x["bkey"], reproducibility_receipt=x["repro"], builder_a=x["obs_a"], builder_b=x["obs_b"], builder_a_toolchain=x["tc_a"], builder_b_toolchain=x["tc_b"], builder_a_toolchain_artifact_bytes=x["tc_a_bytes"], builder_b_toolchain_artifact_bytes=x["tc_b_bytes"], builder_a_toolchain_signing_key=x["tc_a_key"], builder_b_toolchain_signing_key=x["tc_b_key"], build_toolchain=other, build_toolchain_artifact_bytes=other_bytes, build_toolchain_signing_key=other_key, verified_input=x["verified"], mir=x["mir"], proof=x["proof"], provenance=foreign, artifact_bytes=x["artifact"], adapter_abi=x["abi"])


def test_reproducible_admission_tampering_is_rejected():
    x = chain(); forged = replace(x["gated"], reproducibility_receipt_digest="0"*64)
    with pytest.raises(VerifierReproducibleAdmissionV1Error): forged.assert_authenticated(reproducible_admission_key=x["gak"], base_admission=x["base"], adapter_abi=x["abi"])
