from dataclasses import replace
import hashlib

import pytest

from koschei.library_proof_envelope_v1 import make_receipt
from koschei.native_sigil_library_bridge_v1 import expand_native_sigil_mir
from koschei.native_sigil_mir_v1 import lower_native_sigils
from koschei.native_sigil_proof_pipeline_v1 import seal_native_sigil_proof
from koschei.parser import parse
from koschei.provider_adapter_abi_v1 import seal_provider_adapter_abi_v1
from koschei.verified_ir_build_input_v1 import derive_verified_ir_build_input_v1
from koschei.verifier_build_provenance_v1 import (
    attest_verifier_build_from_verified_ir_v1,
    measure_verifier_artifact_v1,
)
from koschei.verifier_reproducible_admission_v1 import (
    VerifierReproducibleAdmissionV1Error,
    admit_reproducible_verifier_artifact_v1,
)
from koschei.verifier_reproducible_build_v1 import (
    VerifierReproducibleBuildV1Error,
    attest_builder_observation_v1,
    seal_reproducible_build_receipt_v1,
)

SOURCE = """ka treasury;\nvor withdrawal;\nshi evidence;\nthal recovery;\nnur visibility;\n"""


def h(tag):
    return hashlib.sha256(tag.encode()).hexdigest()


def verified_world():
    mir = lower_native_sigils(parse(SOURCE))
    plan = expand_native_sigil_mir(mir).library_plan
    receipts = [make_receipt(
        activation_step_id=s.activation_step_id,
        obligation=s.obligation,
        subsystem=s.subsystem,
        proof_kind=s.proof_kind,
        evidence_digest=hashlib.sha256(s.binding_digest.encode()).hexdigest(),
        success=True,
    ) for s in plan.steps]
    proof = seal_native_sigil_proof(mir, receipts)
    verified = derive_verified_ir_build_input_v1(mir=mir, proof=proof)
    return mir, proof, verified


def chain():
    mir, proof, verified = verified_world()
    artifact = b"deterministic-verifier-artifact-v1"
    akey, bkey, rkey = b"A"*32, b"B"*32, b"R"*32
    bk, rk, gak = b"P"*32, b"L"*32, b"G"*32
    obs_a = attest_builder_observation_v1(
        builder_id="builder-a", builder_key=akey, verified_input=verified,
        mir=mir, proof=proof, artifact_bytes=artifact,
        toolchain_digest=h("toolchain-v1"), build_profile="release-reproducible",
    )
    obs_b = attest_builder_observation_v1(
        builder_id="builder-b", builder_key=bkey, verified_input=verified,
        mir=mir, proof=proof, artifact_bytes=artifact,
        toolchain_digest=h("toolchain-v1"), build_profile="release-reproducible",
    )
    repro = seal_reproducible_build_receipt_v1(
        reproducibility_key=rkey, builder_a_key=akey, builder_b_key=bkey,
        builder_a=obs_a, builder_b=obs_b, verified_input=verified,
        mir=mir, proof=proof, artifact_bytes=artifact,
    )
    provenance = attest_verifier_build_from_verified_ir_v1(
        verified_input=verified, mir=mir, proof=proof, artifact_bytes=artifact,
        toolchain_digest=h("toolchain-v1"), build_profile="release-reproducible",
        build_provenance_key=bk,
    )
    abi = seal_provider_adapter_abi_v1(
        provider_id="pi", adapter_id="pi-verifier", schema_id="pi-payment",
        schema_version="v1", verifier_implementation_digest=measure_verifier_artifact_v1(artifact),
    )
    base, gated = admit_reproducible_verifier_artifact_v1(
        reproducible_admission_key=gak, runtime_admission_key=rk,
        build_provenance_key=bk, reproducibility_key=rkey,
        builder_a_key=akey, builder_b_key=bkey, reproducibility_receipt=repro,
        builder_a=obs_a, builder_b=obs_b, verified_input=verified,
        mir=mir, proof=proof, provenance=provenance,
        artifact_bytes=artifact, adapter_abi=abi,
    )
    return locals()


def test_two_independent_builders_gate_runtime_admission():
    x = chain()
    assert x["repro"].reproducible is True
    assert x["repro"].artifact_digest == x["base"].artifact_digest
    assert x["gated"].reproducibility_receipt_digest == x["repro"].receipt_digest
    assert x["gated"].authority is False


def test_same_builder_identity_cannot_count_twice():
    mir, proof, verified = verified_world()
    artifact = b"artifact"
    key = b"A"*32
    obs_a = attest_builder_observation_v1(
        builder_id="same", builder_key=key, verified_input=verified,
        mir=mir, proof=proof, artifact_bytes=artifact,
        toolchain_digest=h("t"), build_profile="release",
    )
    obs_b = attest_builder_observation_v1(
        builder_id="same", builder_key=b"B"*32, verified_input=verified,
        mir=mir, proof=proof, artifact_bytes=artifact,
        toolchain_digest=h("t"), build_profile="release",
    )
    with pytest.raises(VerifierReproducibleBuildV1Error, match="distinct builder"):
        seal_reproducible_build_receipt_v1(
            reproducibility_key=b"R"*32, builder_a_key=key, builder_b_key=b"B"*32,
            builder_a=obs_a, builder_b=obs_b, verified_input=verified,
            mir=mir, proof=proof, artifact_bytes=artifact,
        )


def test_different_builder_artifact_cannot_form_reproducibility_receipt():
    mir, proof, verified = verified_world()
    obs_a = attest_builder_observation_v1(
        builder_id="a", builder_key=b"A"*32, verified_input=verified,
        mir=mir, proof=proof, artifact_bytes=b"artifact-a",
        toolchain_digest=h("t"), build_profile="release",
    )
    obs_b = attest_builder_observation_v1(
        builder_id="b", builder_key=b"B"*32, verified_input=verified,
        mir=mir, proof=proof, artifact_bytes=b"artifact-b",
        toolchain_digest=h("t"), build_profile="release",
    )
    with pytest.raises(VerifierReproducibleBuildV1Error):
        seal_reproducible_build_receipt_v1(
            reproducibility_key=b"R"*32, builder_a_key=b"A"*32, builder_b_key=b"B"*32,
            builder_a=obs_a, builder_b=obs_b, verified_input=verified,
            mir=mir, proof=proof, artifact_bytes=b"artifact-a",
        )


def test_reproducible_admission_tampering_is_rejected():
    x = chain()
    forged = replace(x["gated"], reproducibility_receipt_digest=h("forged"))
    with pytest.raises(VerifierReproducibleAdmissionV1Error):
        forged.assert_authenticated(
            reproducible_admission_key=x["gak"],
            base_admission=x["base"], adapter_abi=x["abi"],
        )
