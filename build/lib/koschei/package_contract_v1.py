"""Koschei Secure Package Contract v1.

A package is inert metadata until admitted. Import/install never grants ambient
filesystem, network, process, secret, signing or persistence authority.
"""
from __future__ import annotations
from dataclasses import dataclass
import hashlib

_CTX=b"koschei.package-contract/v1\x00"
_ALLOWED_EFFECTS=frozenset({"compute","decode","encode","disk","network","process","secret","sign","persist","device","ffi"})

class PackageContractError(ValueError): pass

def _d32(v: bytes,name: str)->bytes:
    if not isinstance(v,bytes) or len(v)!=32: raise PackageContractError(f"{name} must be exactly 32 bytes")
    return v

@dataclass(frozen=True,slots=True)
class PackageManifestV1:
    name:str
    version:str
    artifact_digest:bytes
    provenance_digest:bytes
    dependency_digests:tuple[bytes,...]
    declared_effects:frozenset[str]
    exact_targets:tuple[str,...]
    resource_budget_digest:bytes
    manifest_digest:bytes
    ambient_authority:bool=False

def build_package_manifest_v1(*,name:str,version:str,artifact_digest:bytes,
    provenance_digest:bytes,dependency_digests:tuple[bytes,...]=(),
    declared_effects:frozenset[str]=frozenset(),exact_targets:tuple[str,...]=(),
    resource_budget_digest:bytes)->PackageManifestV1:
    if not name or not version: raise PackageContractError("package name/version required")
    artifact=_d32(artifact_digest,"artifact_digest"); provenance=_d32(provenance_digest,"provenance_digest")
    budget=_d32(resource_budget_digest,"resource_budget_digest")
    deps=tuple(sorted({_d32(d,"dependency_digest") for d in dependency_digests}))
    if not declared_effects.issubset(_ALLOWED_EFFECTS): raise PackageContractError("unknown effect")
    powerful=declared_effects & frozenset({"disk","network","process","secret","sign","persist","device","ffi"})
    if powerful and not exact_targets: raise PackageContractError("authority-bearing package effects require exact targets")
    targets=tuple(sorted(set(exact_targets)))
    h=hashlib.sha3_256(_CTX)
    for part in (name.encode(),version.encode(),artifact,provenance,budget): h.update(part+b"\x00")
    for d in deps: h.update(b"D"+d)
    for e in sorted(declared_effects): h.update(b"E"+e.encode()+b"\x00")
    for t in targets: h.update(b"T"+t.encode()+b"\x00")
    return PackageManifestV1(name,version,artifact,provenance,deps,frozenset(declared_effects),targets,budget,h.digest(),False)

def import_grants_authority_v1(manifest:PackageManifestV1)->bool:
    """Installing/importing metadata alone never grants executable authority."""
    return False
