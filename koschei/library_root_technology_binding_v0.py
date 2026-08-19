"""Bind Koschei Library roots to the technology core, fail-closed.

A semantic root is not activatable merely because its corpus commitments exist.
It must also be cryptographically bound to a concrete TechnologyBindingV0.
This keeps 'meaning without enforcement' from becoming a valid root state.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import hmac

from .library_nucleus_v0 import (
    ActivationTicketV0,
    PrivateRootRecordV0,
    activate_root_v0,
    verify_activation_ticket_v0,
)
from .library_technology_core_v0 import TechnologyBindingV0

_CTX=b"koschei.library-root-tech-binding/v0\x00"

class RootTechnologyBindingError(ValueError): pass

@dataclass(frozen=True, slots=True)
class RootTechnologyBindingV0:
    root_id: str
    generation: int
    technology_digest: bytes
    root_binding_digest: bytes
    authority: bool=False

@dataclass(frozen=True, slots=True)
class TechnologyBoundActivationV0:
    root_ticket: ActivationTicketV0
    technology_digest: bytes
    activation_digest: bytes
    authority: bool=False

def _d32(v:bytes,name:str)->bytes:
    if not isinstance(v,bytes) or len(v)!=32:
        raise RootTechnologyBindingError(f"{name} must be exactly 32 bytes")
    return v

def bind_root_to_technology_v0(*,record:PrivateRootRecordV0,technology:TechnologyBindingV0)->RootTechnologyBindingV0:
    if not isinstance(record,PrivateRootRecordV0):
        raise RootTechnologyBindingError("private root record required")
    if not isinstance(technology,TechnologyBindingV0) or technology.authority:
        raise RootTechnologyBindingError("authority-free technology binding required")
    p=record.public
    material=(
        _CTX+p.root_id.encode("utf-8")+b"\x00"+p.generation.to_bytes(8,"big")
        +p.semantic_commitment+p.policy_commitment+p.composition_commitment
        +record.corpus_digest+record.adversarial_digest+record.invariant_digest
        +_d32(technology.binding_digest,"technology.binding_digest")
    )
    digest=hashlib.sha3_256(material).digest()
    return RootTechnologyBindingV0(p.root_id,p.generation,technology.binding_digest,digest,False)

def activate_bound_root_v0(*,record:PrivateRootRecordV0,technology:TechnologyBindingV0,binding:RootTechnologyBindingV0,context_digest:bytes,nonce_digest:bytes,activation_key:bytes)->TechnologyBoundActivationV0:
    expected=bind_root_to_technology_v0(record=record,technology=technology)
    if not isinstance(binding,RootTechnologyBindingV0) or binding.authority:
        raise RootTechnologyBindingError("root technology binding required")
    if binding.root_id!=expected.root_id or binding.generation!=expected.generation:
        raise RootTechnologyBindingError("root identity/generation mismatch")
    if not hmac.compare_digest(binding.technology_digest,expected.technology_digest) or not hmac.compare_digest(binding.root_binding_digest,expected.root_binding_digest):
        raise RootTechnologyBindingError("technology binding mismatch")
    root_ticket=activate_root_v0(record=record,context_digest=context_digest,nonce_digest=nonce_digest,activation_key=activation_key)
    mac=hmac.new(activation_key,_CTX+b"activate\x00"+root_ticket.ticket_digest+binding.root_binding_digest+technology.binding_digest,hashlib.sha3_256).digest()
    return TechnologyBoundActivationV0(root_ticket,technology.binding_digest,mac,False)

def verify_bound_activation_v0(*,record:PrivateRootRecordV0,technology:TechnologyBindingV0,binding:RootTechnologyBindingV0,ticket:TechnologyBoundActivationV0,activation_key:bytes)->bool:
    if not isinstance(ticket,TechnologyBoundActivationV0) or ticket.authority:
        return False
    try:
        expected_binding=bind_root_to_technology_v0(record=record,technology=technology)
    except RootTechnologyBindingError:
        return False
    if not isinstance(binding,RootTechnologyBindingV0) or binding.authority:
        return False
    if binding!=expected_binding:
        return False
    if not verify_activation_ticket_v0(record=record,ticket=ticket.root_ticket,activation_key=activation_key):
        return False
    if not hmac.compare_digest(ticket.technology_digest,technology.binding_digest):
        return False
    expected=hmac.new(activation_key,_CTX+b"activate\x00"+ticket.root_ticket.ticket_digest+binding.root_binding_digest+technology.binding_digest,hashlib.sha3_256).digest()
    return hmac.compare_digest(ticket.activation_digest,expected)
