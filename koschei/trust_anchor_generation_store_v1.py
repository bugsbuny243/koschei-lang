"""Durable local monotonic trust-anchor generation store for Koschei Lang v1.

SQLite provides transactional persistence across process restart. Each per-anchor history
row is HMAC-chained under a dedicated store key so ordinary database tampering is
fail-closed. This is NOT hardware rollback-resistant: restoring an older valid database
snapshot can also restore an older valid HMAC chain.
"""
from __future__ import annotations
import hashlib,hmac,sqlite3
from pathlib import Path
from .attestation_verifier_abi_v1 import AttestationVerifierAbiV1
from .trust_anchor_admission_v1 import TrustAnchorAdmissionV1Error,TrustAnchorManifestV1

_CTX=b"koschei.trust-anchor-generation-store/v1\x00"
class TrustAnchorGenerationStoreV1Error(TrustAnchorAdmissionV1Error): pass

def _key(v:bytes)->bytes:
    if not isinstance(v,bytes) or len(v)<32: raise TrustAnchorGenerationStoreV1Error("generation_store_key must contain at least 32 bytes")
    return v
def _text(v:str,label:str)->str:
    if not isinstance(v,str) or not v.strip(): raise TrustAnchorGenerationStoreV1Error(f"{label} cannot be empty")
    return v.strip()
def _generation(v:int)->int:
    if not isinstance(v,int) or isinstance(v,bool) or v<0: raise TrustAnchorGenerationStoreV1Error("generation must be a non-negative integer")
    return v
def _mac(key:bytes,*,anchor_id:str,revision:int,generation:int,manifest_digest:str,previous_mac:str)->str:
    payload=_CTX+"\n".join((f"anchor={anchor_id}",f"revision={revision}",f"generation={generation}",f"manifest={manifest_digest}",f"previous={previous_mac}")).encode()
    return hmac.new(key,payload,hashlib.sha256).hexdigest()

class SqliteTrustAnchorGenerationStoreV1:
    """Transactional persistent state with the same observe/assert-current surface as V1 memory state."""
    def __init__(self,path:str|Path,*,generation_store_key:bytes)->None:
        self._key=_key(generation_store_key); self._path=str(path)
        self._db=sqlite3.connect(self._path,isolation_level=None)
        self._db.execute("PRAGMA journal_mode=WAL")
        self._db.execute("PRAGMA synchronous=FULL")
        self._db.execute("CREATE TABLE IF NOT EXISTS trust_anchor_generation_history (anchor_id TEXT NOT NULL, revision INTEGER NOT NULL, generation INTEGER NOT NULL, manifest_digest TEXT NOT NULL, previous_mac TEXT NOT NULL, record_mac TEXT NOT NULL, PRIMARY KEY(anchor_id,revision))")
    def close(self)->None: self._db.close()
    def __enter__(self): return self
    def __exit__(self,exc_type,exc,tb): self.close()
    def _chain(self,anchor_id:str):
        anchor=_text(anchor_id,"anchor_id"); rows=self._db.execute("SELECT revision,generation,manifest_digest,previous_mac,record_mac FROM trust_anchor_generation_history WHERE anchor_id=? ORDER BY revision ASC",(anchor,)).fetchall(); previous=""
        for revision,generation,manifest_digest,previous_mac,record_mac in rows:
            if previous_mac!=previous: raise TrustAnchorGenerationStoreV1Error("trust-anchor generation history chain is broken")
            expected=_mac(self._key,anchor_id=anchor,revision=int(revision),generation=_generation(int(generation)),manifest_digest=_text(manifest_digest,"manifest_digest"),previous_mac=previous)
            if not hmac.compare_digest(record_mac,expected): raise TrustAnchorGenerationStoreV1Error("trust-anchor generation history authentication failed")
            previous=record_mac
        return rows
    def observe(self,manifest:TrustAnchorManifestV1,*,root_signing_key:bytes,abi:AttestationVerifierAbiV1,current_epoch:int)->None:
        manifest.assert_authenticated(root_signing_key=root_signing_key,abi=abi,current_epoch=current_epoch)
        anchor=_text(manifest.anchor_id,"anchor_id"); generation=_generation(manifest.generation); digest=_text(manifest.manifest_digest,"manifest_digest")
        self._db.execute("BEGIN IMMEDIATE")
        try:
            rows=self._chain(anchor)
            if rows:
                revision,prior_generation,prior_digest,_,prior_mac=rows[-1]; prior_generation=int(prior_generation)
                if generation<prior_generation: raise TrustAnchorGenerationStoreV1Error("trust-anchor manifest generation rollback detected")
                if generation==prior_generation and digest!=prior_digest: raise TrustAnchorGenerationStoreV1Error("trust-anchor manifest generation equivocation detected")
                if generation==prior_generation:
                    self._db.execute("COMMIT"); return
                next_revision=int(revision)+1; previous_mac=prior_mac
            else:
                next_revision=1; previous_mac=""
            record_mac=_mac(self._key,anchor_id=anchor,revision=next_revision,generation=generation,manifest_digest=digest,previous_mac=previous_mac)
            self._db.execute("INSERT INTO trust_anchor_generation_history(anchor_id,revision,generation,manifest_digest,previous_mac,record_mac) VALUES(?,?,?,?,?,?)",(anchor,next_revision,generation,digest,previous_mac,record_mac))
            self._db.execute("COMMIT")
        except Exception:
            if self._db.in_transaction: self._db.execute("ROLLBACK")
            raise
    def assert_current_binding(self,*,anchor_id:str,generation:int,manifest_digest:str)->None:
        anchor=_text(anchor_id,"anchor_id"); gen=_generation(generation); digest=_text(manifest_digest,"manifest_digest"); rows=self._chain(anchor)
        if not rows: raise TrustAnchorGenerationStoreV1Error("trust-anchor generation store has not observed this anchor")
        _,current_generation,current_digest,_,_=rows[-1]
        if gen!=int(current_generation) or digest!=current_digest: raise TrustAnchorGenerationStoreV1Error("trust-anchor binding is not the current observed generation")
    def assert_current(self,manifest:TrustAnchorManifestV1)->None:
        self.assert_current_binding(anchor_id=manifest.anchor_id,generation=manifest.generation,manifest_digest=manifest.manifest_digest)
    def highest_generation(self,anchor_id:str)->int|None:
        rows=self._chain(anchor_id); return None if not rows else int(rows[-1][1])
