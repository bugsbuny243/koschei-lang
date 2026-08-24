"""Khar six-axis failure-root independence proof v1.

A six-axis Sathra is not sufficiently independent merely because its six witness
digests differ. Six logical witnesses can still be aliases for one hidden trust
root. This module makes the failure roots explicit and seals one distinct root
and one distinct attestation domain to every Khar axis.

This is an enforceable identity-separation contract, not a magical claim that two
physical systems are independent because their digests differ. Physical failure-
root attestation remains an external evidence problem; Koschei refuses to accept
that evidence if any root or attestation domain is reused across axes.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import string
from typing import Iterable

from .khar_sathra_v1 import KHAR_AXES, Sathra

_CTX = b"koschei.khar-failure-independence/v1\x00"
_HEX = frozenset(string.hexdigits.lower())


class KharFailureIndependenceError(ValueError):
    pass


def _require_digest(value: str, label: str) -> str:
    if not isinstance(value, str) or len(value) != 64:
        raise KharFailureIndependenceError(f"{label} must be a 64-character digest")
    value = value.lower()
    if any(ch not in _HEX for ch in value) or value == "0" * 64:
        raise KharFailureIndependenceError(f"{label} must be a non-zero hexadecimal digest")
    return value


@dataclass(frozen=True, slots=True)
class AxisFailureRootAttestation:
    axis: str
    axis_witness_digest: str
    failure_root_digest: str
    attestation_domain_digest: str
    evidence_digest: str

    def __post_init__(self) -> None:
        if self.axis not in KHAR_AXES:
            raise KharFailureIndependenceError(f"unknown Khar axis: {self.axis!r}")
        _require_digest(self.axis_witness_digest, "axis_witness_digest")
        root = _require_digest(self.failure_root_digest, "failure_root_digest")
        domain = _require_digest(self.attestation_domain_digest, "attestation_domain_digest")
        _require_digest(self.evidence_digest, "evidence_digest")
        if root == domain:
            raise KharFailureIndependenceError(
                "an axis failure root cannot self-attest as its own trust domain"
            )


@dataclass(frozen=True, slots=True)
class FailureIndependentSathra:
    sathra_digest: str
    roots: tuple[tuple[str, str, str, str], ...]
    digest: str
    version: int = 1

    def assert_sealed(self, sathra: Sathra) -> None:
        sathra.assert_sealed()
        if self.sathra_digest != sathra.digest:
            raise KharFailureIndependenceError("failure-independence proof Sathra mismatch")
        if tuple(row[0] for row in self.roots) != KHAR_AXES:
            raise KharFailureIndependenceError("failure-independence axes are incomplete or unordered")

        witness_by_axis = dict(sathra.axis_witnesses)
        root_digests = []
        attestation_domains = []
        evidence_digests = []
        for axis, witness, root, domain_and_evidence in self.roots:
            # The fourth field packs `domain:evidence` only inside the immutable
            # proof representation; split and validate both before trusting it.
            try:
                domain, evidence = domain_and_evidence.split(":", 1)
            except ValueError as error:
                raise KharFailureIndependenceError("invalid root attestation binding") from error
            if witness_by_axis.get(axis) != witness:
                raise KharFailureIndependenceError(
                    f"failure-root proof does not bind the Sathra witness for axis {axis}"
                )
            _require_digest(witness, "axis_witness_digest")
            root_digests.append(_require_digest(root, "failure_root_digest"))
            attestation_domains.append(_require_digest(domain, "attestation_domain_digest"))
            evidence_digests.append(_require_digest(evidence, "evidence_digest"))
            if root == domain:
                raise KharFailureIndependenceError("failure root cannot self-attest")

        if len(set(root_digests)) != len(KHAR_AXES):
            raise KharFailureIndependenceError(
                "six Khar axes must have six distinct failure roots"
            )
        if len(set(attestation_domains)) != len(KHAR_AXES):
            raise KharFailureIndependenceError(
                "six Khar axes must have six distinct attestation domains"
            )
        if len(set(evidence_digests)) != len(KHAR_AXES):
            raise KharFailureIndependenceError(
                "six Khar axes must have six distinct independence evidence records"
            )
        if set(root_digests) & set(attestation_domains):
            raise KharFailureIndependenceError(
                "an axis failure root cannot serve as another axis attestation domain"
            )

        expected = _proof_digest(self.sathra_digest, self.roots)
        if self.digest != expected:
            raise KharFailureIndependenceError("failure-independence proof seal mismatch")


def _proof_digest(sathra_digest: str, roots: tuple[tuple[str, str, str, str], ...]) -> str:
    rows = [f"sathra={sathra_digest}"]
    rows.extend(
        f"axis={axis}|witness={witness}|root={root}|attestation={domain_evidence}"
        for axis, witness, root, domain_evidence in roots
    )
    return hashlib.sha256(_CTX + "\n".join(rows).encode("utf-8")).hexdigest()


def seal_failure_independent_sathra(
    sathra: Sathra,
    attestations: Iterable[AxisFailureRootAttestation],
) -> FailureIndependentSathra:
    """Require all six Sathra axes to originate from distinct declared roots."""

    sathra.assert_sealed()
    supplied = tuple(attestations)
    if len(supplied) != len(KHAR_AXES):
        raise KharFailureIndependenceError(
            "failure independence requires exactly six axis root attestations"
        )
    by_axis: dict[str, AxisFailureRootAttestation] = {}
    for item in supplied:
        if item.axis in by_axis:
            raise KharFailureIndependenceError(
                f"duplicate failure-root attestation for axis {item.axis}"
            )
        by_axis[item.axis] = item
    missing = tuple(axis for axis in KHAR_AXES if axis not in by_axis)
    if missing:
        raise KharFailureIndependenceError(
            "missing failure-root attestations: " + ", ".join(missing)
        )

    witness_by_axis = dict(sathra.axis_witnesses)
    rows = []
    for axis in KHAR_AXES:
        item = by_axis[axis]
        if witness_by_axis.get(axis) != item.axis_witness_digest:
            raise KharFailureIndependenceError(
                f"failure-root attestation does not match Sathra axis {axis}"
            )
        rows.append(
            (
                axis,
                item.axis_witness_digest,
                item.failure_root_digest,
                item.attestation_domain_digest + ":" + item.evidence_digest,
            )
        )
    frozen = tuple(rows)
    result = FailureIndependentSathra(
        sathra_digest=sathra.digest,
        roots=frozen,
        digest=_proof_digest(sathra.digest, frozen),
    )
    result.assert_sealed(sathra)
    return result


def require_failure_independent_sathra(
    sathra: Sathra,
    proof: FailureIndependentSathra,
) -> None:
    proof.assert_sealed(sathra)
