"""Canonical Koschei Galaxy identity physics v1.

Veyra is a customer-Galaxy identity commitment, not a topology map. Aevra is a
canonical living program-entity identity bound to one Veyra and one compiler
product. Neither object grants authority and neither contains the Galaxy graph.

This module deliberately makes `copy(bytes) != birth(Aevra)` concrete: a visible
source copy is insufficient to establish Aevra identity because birth is also
bound to a Veyra, compiler-produced native MIR and explicit birth evidence.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import string

from .native_sigil_mir_v1 import NativeSigilMir

_CTX = b"koschei.galaxy-identity/v1\x00"
_HEX = frozenset(string.hexdigits.lower())


class GalaxyIdentityError(ValueError):
    pass


def _require_digest(value: str, label: str) -> str:
    if not isinstance(value, str) or len(value) != 64:
        raise GalaxyIdentityError(f"{label} must be a 64-character digest")
    lowered = value.lower()
    if any(ch not in _HEX for ch in lowered):
        raise GalaxyIdentityError(f"{label} must be hexadecimal")
    if lowered == "0" * 64:
        raise GalaxyIdentityError(f"{label} cannot be the zero digest")
    return lowered


def _hash_rows(kind: bytes, rows: tuple[str, ...]) -> str:
    return hashlib.sha256(_CTX + kind + b"\x00" + "\n".join(rows).encode("utf-8")).hexdigest()


@dataclass(frozen=True, slots=True)
class VeyraIdentity:
    profile_digest: str
    genesis_digest: str
    constitution_digest: str
    instance_digest: str
    birth_epoch: int
    digest: str
    version: int = 1

    def assert_sealed(self) -> None:
        profile = _require_digest(self.profile_digest, "profile_digest")
        genesis = _require_digest(self.genesis_digest, "genesis_digest")
        constitution = _require_digest(self.constitution_digest, "constitution_digest")
        instance = _require_digest(self.instance_digest, "instance_digest")
        if not isinstance(self.birth_epoch, int) or self.birth_epoch < 0:
            raise GalaxyIdentityError("Veyra birth_epoch must be non-negative")
        expected = _hash_rows(
            b"veyra",
            (
                f"profile={profile}",
                f"genesis={genesis}",
                f"constitution={constitution}",
                f"instance={instance}",
                f"epoch={self.birth_epoch}",
            ),
        )
        if self.digest != expected:
            raise GalaxyIdentityError("Veyra identity seal mismatch")


@dataclass(frozen=True, slots=True)
class AevraIdentity:
    veyra_digest: str
    native_mir_fingerprint: str
    sigil: str
    semantic_subject_digest: str
    birth_evidence_digest: str
    birth_epoch: int
    digest: str
    version: int = 1

    def assert_sealed(self, veyra: VeyraIdentity, mir: NativeSigilMir) -> None:
        veyra.assert_sealed()
        mir.assert_sealed()
        if self.veyra_digest != veyra.digest:
            raise GalaxyIdentityError("Aevra belongs to a different Veyra")
        if self.native_mir_fingerprint != mir.fingerprint:
            raise GalaxyIdentityError("Aevra belongs to a different compiler product")
        if not isinstance(self.birth_epoch, int) or self.birth_epoch < veyra.birth_epoch:
            raise GalaxyIdentityError("Aevra cannot predate its Veyra")
        _require_digest(self.semantic_subject_digest, "semantic_subject_digest")
        _require_digest(self.birth_evidence_digest, "birth_evidence_digest")
        matching = [item for item in mir.bindings if item.sigil == self.sigil]
        if not matching:
            raise GalaxyIdentityError("Aevra sigil is absent from native MIR")
        subject_digests = {
            hashlib.sha256(item.subject.encode("utf-8")).hexdigest() for item in matching
        }
        if self.semantic_subject_digest not in subject_digests:
            raise GalaxyIdentityError("Aevra semantic subject is absent from native MIR")
        expected = _hash_rows(
            b"aevra",
            (
                f"veyra={self.veyra_digest}",
                f"mir={self.native_mir_fingerprint}",
                f"sigil={self.sigil}",
                f"subject={self.semantic_subject_digest}",
                f"birth-evidence={self.birth_evidence_digest}",
                f"epoch={self.birth_epoch}",
            ),
        )
        if self.digest != expected:
            raise GalaxyIdentityError("Aevra identity seal mismatch")


def birth_veyra(
    *,
    profile_digest: str,
    genesis_digest: str,
    constitution_digest: str,
    instance_digest: str,
    birth_epoch: int,
) -> VeyraIdentity:
    profile = _require_digest(profile_digest, "profile_digest")
    genesis = _require_digest(genesis_digest, "genesis_digest")
    constitution = _require_digest(constitution_digest, "constitution_digest")
    instance = _require_digest(instance_digest, "instance_digest")
    if not isinstance(birth_epoch, int) or birth_epoch < 0:
        raise GalaxyIdentityError("Veyra birth_epoch must be non-negative")
    result = VeyraIdentity(
        profile_digest=profile,
        genesis_digest=genesis,
        constitution_digest=constitution,
        instance_digest=instance,
        birth_epoch=birth_epoch,
        digest="",
    )
    object.__setattr__(
        result,
        "digest",
        _hash_rows(
            b"veyra",
            (
                f"profile={profile}",
                f"genesis={genesis}",
                f"constitution={constitution}",
                f"instance={instance}",
                f"epoch={birth_epoch}",
            ),
        ),
    )
    result.assert_sealed()
    return result


def birth_aevra(
    veyra: VeyraIdentity,
    mir: NativeSigilMir,
    *,
    sigil: str,
    subject: str,
    birth_evidence_digest: str,
    birth_epoch: int,
) -> AevraIdentity:
    veyra.assert_sealed()
    mir.assert_sealed()
    if not isinstance(subject, str) or not subject:
        raise GalaxyIdentityError("Aevra subject cannot be empty")
    if not any(item.sigil == sigil and item.subject == subject for item in mir.bindings):
        raise GalaxyIdentityError("Aevra birth must name a canonical native MIR binding")
    if not isinstance(birth_epoch, int) or birth_epoch < veyra.birth_epoch:
        raise GalaxyIdentityError("Aevra cannot predate its Veyra")
    evidence = _require_digest(birth_evidence_digest, "birth_evidence_digest")
    subject_digest = hashlib.sha256(subject.encode("utf-8")).hexdigest()
    result = AevraIdentity(
        veyra_digest=veyra.digest,
        native_mir_fingerprint=mir.fingerprint,
        sigil=sigil,
        semantic_subject_digest=subject_digest,
        birth_evidence_digest=evidence,
        birth_epoch=birth_epoch,
        digest="",
    )
    object.__setattr__(
        result,
        "digest",
        _hash_rows(
            b"aevra",
            (
                f"veyra={result.veyra_digest}",
                f"mir={result.native_mir_fingerprint}",
                f"sigil={result.sigil}",
                f"subject={result.semantic_subject_digest}",
                f"birth-evidence={result.birth_evidence_digest}",
                f"epoch={result.birth_epoch}",
            ),
        ),
    )
    result.assert_sealed(veyra, mir)
    return result
