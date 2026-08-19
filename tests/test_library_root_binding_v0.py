import hashlib

from koschei.library_nucleus_v0 import make_public_root_handle_v0, bind_private_root_v0
from koschei.library_technology_core_v0 import AlgorithmSuiteV0, ProvenanceV0, ExecutionBudgetV0, TrustClass, IsolationClass, bind_technology_core_v0
from koschei.library_root_technology_binding_v0 import bind_root_to_technology_v0


def d(value: str) -> bytes:
    return hashlib.sha3_256(value.encode()).digest()


def test_root_binding_changes_with_technology():
    public = make_public_root_handle_v0(root_id="ka", generation=1, semantic_commitment=d("s"), policy_commitment=d("p"), composition_commitment=d("c"))
    record = bind_private_root_v0(public=public, corpus_locator="private://ka/v1", corpus_digest=d("corpus"), adversarial_digest=d("adv"), invariant_digest=d("inv"))
    common = dict(algorithms=AlgorithmSuiteV0("x25519", "ml-kem-768", "ed25519", "ml-dsa-65"), trust=TrustClass.VERIFIED, isolation=IsolationClass.SANDBOX, budget=ExecutionBudgetV0(1000000, 67108864, 8388608, 1500))
    first = bind_technology_core_v0(provenance=ProvenanceV0(d("src"), d("build-a"), d("tool"), d("policy")), **common)
    second = bind_technology_core_v0(provenance=ProvenanceV0(d("src"), d("build-b"), d("tool"), d("policy")), **common)
    a = bind_root_to_technology_v0(record=record, technology=first)
    b = bind_root_to_technology_v0(record=record, technology=second)
    assert a.root_binding_digest != b.root_binding_digest
    assert a.authority is False
    assert b.authority is False
