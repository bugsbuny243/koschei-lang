"""Koschei Library nucleus v0.

This is the first brick of the hidden semantic/runtime library that Koschei Lang
will consume later. It deliberately contains no React/DOM/HTML/CSS/JS model and
no public copy of the private corpus. Public callers see only opaque handles and
verifiable commitments; private semantic material stays outside distributable
packages.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import hmac

_CTX = b"koschei.library-nucleus/v0\x00"

class LibraryNucleusError(ValueError):
    pass


def _d32(value: bytes, name: str) -> bytes:
    if not isinstance(value, bytes) or len(value) != 32:
        raise LibraryNucleusError(f"{name} must be exactly 32 bytes")
    return value


@dataclass(frozen=True, slots=True)
class PublicRootHandleV0:
    """The only identity a distributed client needs to name a Koschei root."""
    root_id: str
    generation: int
    semantic_commitment: bytes
    policy_commitment: bytes
    composition_commitment: bytes
    authority: bool = False


@dataclass(frozen=True, slots=True)
class PrivateRootRecordV0:
    """Server-side metadata. corpus_locator is never serialized to public clients."""
    public: PublicRootHandleV0
    corpus_locator: str
    corpus_digest: bytes
    adversarial_digest: bytes
    invariant_digest: bytes


@dataclass(frozen=True, slots=True)
class ActivationTicketV0:
    root_id: str
    generation: int
    context_digest: bytes
    nonce_digest: bytes
    ticket_digest: bytes
    authority: bool = False


def make_public_root_handle_v0(*, root_id: str, generation: int,
    semantic_commitment: bytes, policy_commitment: bytes,
    composition_commitment: bytes) -> PublicRootHandleV0:
    if not isinstance(root_id, str) or not root_id or len(root_id) > 64:
        raise LibraryNucleusError("invalid root identity")
    if not isinstance(generation, int) or generation < 1:
        raise LibraryNucleusError("generation must be positive")
    return PublicRootHandleV0(
        root_id,
        generation,
        _d32(semantic_commitment, "semantic_commitment"),
        _d32(policy_commitment, "policy_commitment"),
        _d32(composition_commitment, "composition_commitment"),
        False,
    )


def bind_private_root_v0(*, public: PublicRootHandleV0, corpus_locator: str,
    corpus_digest: bytes, adversarial_digest: bytes,
    invariant_digest: bytes) -> PrivateRootRecordV0:
    if not isinstance(public, PublicRootHandleV0) or public.authority:
        raise LibraryNucleusError("authority-free public handle required")
    if not isinstance(corpus_locator, str) or not corpus_locator:
        raise LibraryNucleusError("private corpus locator required")
    # Intentionally no API exists here to export corpus_locator or corpus bytes.
    return PrivateRootRecordV0(
        public,
        corpus_locator,
        _d32(corpus_digest, "corpus_digest"),
        _d32(adversarial_digest, "adversarial_digest"),
        _d32(invariant_digest, "invariant_digest"),
    )


def activate_root_v0(*, record: PrivateRootRecordV0, context_digest: bytes,
    nonce_digest: bytes, activation_key: bytes) -> ActivationTicketV0:
    if not isinstance(record, PrivateRootRecordV0):
        raise LibraryNucleusError("private root record required")
    context_digest = _d32(context_digest, "context_digest")
    nonce_digest = _d32(nonce_digest, "nonce_digest")
    if not isinstance(activation_key, bytes) or len(activation_key) < 32:
        raise LibraryNucleusError("activation key must be at least 256 bits")
    p = record.public
    material = (
        _CTX + p.root_id.encode("utf-8") + b"\x00"
        + p.generation.to_bytes(8, "big")
        + p.semantic_commitment + p.policy_commitment + p.composition_commitment
        + record.corpus_digest + record.adversarial_digest + record.invariant_digest
        + context_digest + nonce_digest
    )
    ticket_digest = hmac.new(activation_key, material, hashlib.sha3_256).digest()
    return ActivationTicketV0(
        p.root_id, p.generation, context_digest, nonce_digest, ticket_digest, False
    )


def verify_activation_ticket_v0(*, record: PrivateRootRecordV0,
    ticket: ActivationTicketV0, activation_key: bytes) -> bool:
    if not isinstance(ticket, ActivationTicketV0) or ticket.authority:
        return False
    try:
        expected = activate_root_v0(
            record=record,
            context_digest=ticket.context_digest,
            nonce_digest=ticket.nonce_digest,
            activation_key=activation_key,
        )
    except LibraryNucleusError:
        return False
    return (
        ticket.root_id == expected.root_id
        and ticket.generation == expected.generation
        and hmac.compare_digest(ticket.ticket_digest, expected.ticket_digest)
    )
