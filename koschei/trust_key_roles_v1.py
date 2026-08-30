"""Exact key-role separation invariant for Koschei Lang bootstrap trust boundaries v1."""
from __future__ import annotations

class TrustKeyRolesV1Error(ValueError): pass

def assert_distinct_trust_keys_v1(**roles:bytes)->None:
    if len(roles)<2: return
    seen:dict[bytes,str]={}
    for role,key in roles.items():
        if not isinstance(role,str) or not role.strip(): raise TrustKeyRolesV1Error("trust key role name cannot be empty")
        if not isinstance(key,bytes) or len(key)<32: raise TrustKeyRolesV1Error(f"{role} must contain at least 32 bytes")
        prior=seen.get(key)
        if prior is not None: raise TrustKeyRolesV1Error(f"trust key roles must be distinct: {prior} equals {role}")
        seen[key]=role
