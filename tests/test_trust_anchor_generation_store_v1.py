import sqlite3
import pytest
from koschei.attestation_verifier_abi_v1 import seal_attestation_verifier_abi_v1
from koschei.trust_anchor_admission_v1 import seal_trust_anchor_manifest_v1,admit_attestation_verifier_from_trust_anchor_v1
from koschei.trust_anchor_generation_store_v1 import SqliteTrustAnchorGenerationStoreV1,TrustAnchorGenerationStoreV1Error

def setup():
    artifact=b"attestation-verifier-v1"; abi=seal_attestation_verifier_abi_v1(provider_id="generic-tee",evidence_format_id="quote-v1",schema_version="v1",verifier_artifact_bytes=artifact); root_key=b"r"*32; runtime_key=b"a"*32; store_key=b"s"*32
    def manifest(generation,roots=("root-a",)):
        return seal_trust_anchor_manifest_v1(anchor_id="offline-root",generation=generation,abi=abi,allowed_trust_root_ids=roots,valid_from_epoch=10,expires_before_epoch=100,root_signing_key=root_key)
    return locals()
def test_generation_survives_process_restart(tmp_path):
    x=setup(); path=tmp_path/"trust.db"; m1=x['manifest'](1)
    with SqliteTrustAnchorGenerationStoreV1(path,generation_store_key=x['store_key']) as store:
        admit_attestation_verifier_from_trust_anchor_v1(manifest=m1,abi=x['abi'],verifier_artifact_bytes=x['artifact'],current_epoch=11,root_signing_key=x['root_key'],runtime_admission_key=x['runtime_key'],generation_state=store)
        assert store.highest_generation("offline-root")==1
    with SqliteTrustAnchorGenerationStoreV1(path,generation_store_key=x['store_key']) as reopened:
        reopened.assert_current(m1); assert reopened.highest_generation("offline-root")==1
def test_newer_generation_persists_and_old_generation_rejects_after_restart(tmp_path):
    x=setup(); path=tmp_path/"trust.db"; m1=x['manifest'](1); m2=x['manifest'](2)
    with SqliteTrustAnchorGenerationStoreV1(path,generation_store_key=x['store_key']) as store:
        store.observe(m1,root_signing_key=x['root_key'],abi=x['abi'],current_epoch=11); store.observe(m2,root_signing_key=x['root_key'],abi=x['abi'],current_epoch=11)
    with SqliteTrustAnchorGenerationStoreV1(path,generation_store_key=x['store_key']) as reopened:
        assert reopened.highest_generation("offline-root")==2
        with pytest.raises(TrustAnchorGenerationStoreV1Error,match="current observed generation"): reopened.assert_current(m1)
        reopened.assert_current(m2)
def test_same_generation_different_manifest_is_equivocation(tmp_path):
    x=setup(); path=tmp_path/"trust.db"; m1=x['manifest'](1); conflict=x['manifest'](1,("root-a","root-b"))
    with SqliteTrustAnchorGenerationStoreV1(path,generation_store_key=x['store_key']) as store:
        store.observe(m1,root_signing_key=x['root_key'],abi=x['abi'],current_epoch=11)
        with pytest.raises(TrustAnchorGenerationStoreV1Error,match="equivocation"): store.observe(conflict,root_signing_key=x['root_key'],abi=x['abi'],current_epoch=11)
def test_authenticated_history_detects_database_tamper(tmp_path):
    x=setup(); path=tmp_path/"trust.db"; m1=x['manifest'](1)
    with SqliteTrustAnchorGenerationStoreV1(path,generation_store_key=x['store_key']) as store: store.observe(m1,root_signing_key=x['root_key'],abi=x['abi'],current_epoch=11)
    db=sqlite3.connect(path); db.execute("UPDATE trust_anchor_generation_history SET manifest_digest=? WHERE anchor_id=?",("0"*64,"offline-root")); db.commit(); db.close()
    with SqliteTrustAnchorGenerationStoreV1(path,generation_store_key=x['store_key']) as reopened:
        with pytest.raises(TrustAnchorGenerationStoreV1Error,match="authentication failed"): reopened.highest_generation("offline-root")
def test_authenticated_head_detects_valid_prefix_tail_deletion(tmp_path):
    x=setup(); path=tmp_path/"trust.db"; m1=x['manifest'](1); m2=x['manifest'](2)
    with SqliteTrustAnchorGenerationStoreV1(path,generation_store_key=x['store_key']) as store:
        store.observe(m1,root_signing_key=x['root_key'],abi=x['abi'],current_epoch=11); store.observe(m2,root_signing_key=x['root_key'],abi=x['abi'],current_epoch=11)
    db=sqlite3.connect(path); db.execute("DELETE FROM trust_anchor_generation_history WHERE anchor_id=? AND revision=2",("offline-root",)); db.commit(); db.close()
    with SqliteTrustAnchorGenerationStoreV1(path,generation_store_key=x['store_key']) as reopened:
        with pytest.raises(TrustAnchorGenerationStoreV1Error,match="tail differs from authenticated head"): reopened.highest_generation("offline-root")
def test_missing_authenticated_head_fails_closed_when_history_remains(tmp_path):
    x=setup(); path=tmp_path/"trust.db"; m1=x['manifest'](1)
    with SqliteTrustAnchorGenerationStoreV1(path,generation_store_key=x['store_key']) as store: store.observe(m1,root_signing_key=x['root_key'],abi=x['abi'],current_epoch=11)
    db=sqlite3.connect(path); db.execute("DELETE FROM trust_anchor_generation_heads WHERE anchor_id=?",("offline-root",)); db.commit(); db.close()
    with SqliteTrustAnchorGenerationStoreV1(path,generation_store_key=x['store_key']) as reopened:
        with pytest.raises(TrustAnchorGenerationStoreV1Error,match="authenticated head is missing"): reopened.highest_generation("offline-root")
def test_wrong_store_key_rejects_authenticated_history(tmp_path):
    x=setup(); path=tmp_path/"trust.db"; m1=x['manifest'](1)
    with SqliteTrustAnchorGenerationStoreV1(path,generation_store_key=x['store_key']) as store: store.observe(m1,root_signing_key=x['root_key'],abi=x['abi'],current_epoch=11)
    with SqliteTrustAnchorGenerationStoreV1(path,generation_store_key=b"x"*32) as reopened:
        with pytest.raises(TrustAnchorGenerationStoreV1Error,match="authentication failed"): reopened.highest_generation("offline-root")
