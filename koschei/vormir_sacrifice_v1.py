"""Koschei Vormir Sacrifice Law v1.

The original commitment API is retained for compatibility, but a commitment by
itself is not irreversible sacrifice. The Galaxy extension below binds Vormir to
Koschei's durable epoch tombstone and authority-free rebirth physics: the old
epoch must become durably dead before the successor epoch can be accepted.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
from typing import Iterable

from .native_sigil_epoch_tombstone_v1 import DurableEpochFence, EpochRecord
from .universe_rebirth_v1 import RebirthReceipt, require_rebirth_receipt
from .universe_state_machine_v1 import SigilState, UniverseState

_CTX = b"koschei.vormir-sacrifice/v1\x00"


class VormirSacrificeError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class SacrificeCommitmentV1:
    principal_digest: bytes
    artifact_digest: bytes
    surrendered_authority: str
    requested_authority: str
    prior_epoch: int
    next_epoch: int
    hardware_attestation_digest: bytes
    verifier_digest: bytes
    commitment_digest: bytes


def _d32(value: bytes, name: str) -> bytes:
    if not isinstance(value, bytes) or len(value) != 32:
        raise VormirSacrificeError(f"{name} must be exactly 32 bytes")
    return value


def commit_sacrifice_v1(*, principal_digest: bytes, artifact_digest: bytes,
    surrendered_authority: str, requested_authority: str, prior_epoch: int,
    next_epoch: int, hardware_attestation_digest: bytes,
    verifier_digest: bytes) -> SacrificeCommitmentV1:
    principal = _d32(principal_digest, "principal_digest")
    artifact = _d32(artifact_digest, "artifact_digest")
    attest = _d32(hardware_attestation_digest, "hardware_attestation_digest")
    verifier = _d32(verifier_digest, "verifier_digest")
    if not surrendered_authority or not requested_authority:
        raise VormirSacrificeError("authorities must be explicit")
    if surrendered_authority == requested_authority:
        raise VormirSacrificeError("sacrifice must attenuate a distinct authority")
    if prior_epoch < 0 or next_epoch != prior_epoch + 1:
        raise VormirSacrificeError("Vormir requires exactly one monotonic epoch transition")
    fields = (
        principal, artifact, surrendered_authority.encode("utf-8"),
        requested_authority.encode("utf-8"), str(prior_epoch).encode("ascii"),
        str(next_epoch).encode("ascii"), attest, verifier,
    )
    digest = hashlib.sha3_256(_CTX + b"\x00".join(fields)).digest()
    return SacrificeCommitmentV1(principal, artifact, surrendered_authority,
        requested_authority, prior_epoch, next_epoch, attest, verifier, digest)


def admits_vormir_root_v1(commitment: SacrificeCommitmentV1, *,
    revoked_authority: str, observed_epoch: int,
    observed_artifact_digest: bytes) -> bool:
    """Compatibility gate for the original commitment-only Vormir slice."""
    if not isinstance(commitment, SacrificeCommitmentV1):
        return False
    try:
        artifact = _d32(observed_artifact_digest, "observed_artifact_digest")
    except VormirSacrificeError:
        return False
    return (
        revoked_authority == commitment.surrendered_authority
        and observed_epoch == commitment.next_epoch
        and artifact == commitment.artifact_digest
    )


# ---------------------------------------------------------------------------
# Galaxy extension: irreversible epoch sacrifice
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class VormirEpochWitnessV1:
    domain_digest: bytes
    evidence_digest: bytes

    def __post_init__(self) -> None:
        _d32(self.domain_digest, "Vormir witness domain_digest")
        _d32(self.evidence_digest, "Vormir witness evidence_digest")


@dataclass(frozen=True, slots=True)
class VormirEpochSacrificeReceiptV1:
    activation_plan_digest: str
    sacrificed_epoch: int
    successor_epoch: int
    previous_state_digest: str
    fresh_state_digest: str
    rebirth_receipt_digest: str
    tombstone_record_digest: str
    witness_bindings: tuple[tuple[bytes, bytes], ...]
    sacrifice_digest: bytes
    version: int = 1

    def assert_sealed(self) -> None:
        if self.sacrificed_epoch < 1 or self.successor_epoch != self.sacrificed_epoch + 1:
            raise VormirSacrificeError("Vormir epoch sacrifice is not monotonic")
        if len(self.witness_bindings) < 2:
            raise VormirSacrificeError("Vormir requires at least two witness domains")
        domains = tuple(domain for domain, _ in self.witness_bindings)
        evidence = tuple(item for _, item in self.witness_bindings)
        if len(set(domains)) != len(domains):
            raise VormirSacrificeError("Vormir witness domains must be distinct")
        if len(set(evidence)) != len(evidence):
            raise VormirSacrificeError("Vormir witness evidence must be distinct")
        for domain, item in self.witness_bindings:
            _d32(domain, "Vormir witness domain")
            _d32(item, "Vormir witness evidence")
        expected = _epoch_sacrifice_digest(
            activation_plan_digest=self.activation_plan_digest,
            sacrificed_epoch=self.sacrificed_epoch,
            successor_epoch=self.successor_epoch,
            previous_state_digest=self.previous_state_digest,
            fresh_state_digest=self.fresh_state_digest,
            rebirth_receipt_digest=self.rebirth_receipt_digest,
            tombstone_record_digest=self.tombstone_record_digest,
            witness_bindings=self.witness_bindings,
        )
        if self.sacrifice_digest != expected:
            raise VormirSacrificeError("Vormir epoch sacrifice seal mismatch")


def _canonical_epoch_witnesses(
    witnesses: Iterable[VormirEpochWitnessV1],
) -> tuple[tuple[bytes, bytes], ...]:
    supplied = tuple(witnesses)
    if len(supplied) < 2:
        raise VormirSacrificeError("Vormir requires at least two witness domains")
    domains = [item.domain_digest for item in supplied]
    evidence = [item.evidence_digest for item in supplied]
    if len(set(domains)) != len(domains):
        raise VormirSacrificeError("Vormir witness domains must be distinct")
    if len(set(evidence)) != len(evidence):
        raise VormirSacrificeError("Vormir witness evidence must be distinct")
    return tuple(sorted((item.domain_digest, item.evidence_digest) for item in supplied))


def _epoch_sacrifice_digest(
    *,
    activation_plan_digest: str,
    sacrificed_epoch: int,
    successor_epoch: int,
    previous_state_digest: str,
    fresh_state_digest: str,
    rebirth_receipt_digest: str,
    tombstone_record_digest: str,
    witness_bindings: tuple[tuple[bytes, bytes], ...],
) -> bytes:
    h = hashlib.sha3_256(
        _CTX
        + b"epoch-sacrifice\x00"
        + activation_plan_digest.encode("ascii")
        + b"\x00"
        + str(sacrificed_epoch).encode("ascii")
        + b"\x00"
        + str(successor_epoch).encode("ascii")
        + b"\x00"
        + previous_state_digest.encode("ascii")
        + b"\x00"
        + fresh_state_digest.encode("ascii")
        + b"\x00"
        + rebirth_receipt_digest.encode("ascii")
        + b"\x00"
        + tombstone_record_digest.encode("ascii")
    )
    for domain, evidence in witness_bindings:
        h.update(b"\x00W\x00" + domain + evidence)
    return h.digest()


def commit_vormir_epoch_sacrifice_v1(
    previous: UniverseState,
    fresh: UniverseState,
    rebirth: RebirthReceipt,
    fence: DurableEpochFence,
    *,
    witnesses: Iterable[VormirEpochWitnessV1],
) -> VormirEpochSacrificeReceiptV1:
    """Durably kill the old epoch before accepting the staged successor epoch.

    The `fresh` state may be computed before the durable transition, but it must
    remain fully INACTIVE. It therefore carries no active sigil authority while
    the old epoch is still alive. The irreversible step is the atomic durable
    tombstone performed by `DurableEpochFence.advance_rebirth`.
    """

    try:
        require_rebirth_receipt(previous, fresh, rebirth)
    except ValueError as error:
        raise VormirSacrificeError(str(error)) from error
    if any(row.state is not SigilState.CONTAINED for row in previous.sigils):
        raise VormirSacrificeError("Vormir requires a fully contained sacrificed epoch")
    if any(row.state is not SigilState.INACTIVE for row in fresh.sigils):
        raise VormirSacrificeError("Vormir successor must be born inactive")

    witness_bindings = _canonical_epoch_witnesses(witnesses)
    try:
        record = fence.advance_rebirth(previous, fresh, rebirth)
    except ValueError as error:
        raise VormirSacrificeError(str(error)) from error

    if not fence.is_tombstoned(rebirth.activation_plan_digest, rebirth.previous_epoch):
        raise VormirSacrificeError("Vormir failed to durably tombstone the sacrificed epoch")
    if record.current_epoch != rebirth.next_epoch:
        raise VormirSacrificeError("Vormir durable successor epoch mismatch")

    result = VormirEpochSacrificeReceiptV1(
        activation_plan_digest=rebirth.activation_plan_digest,
        sacrificed_epoch=rebirth.previous_epoch,
        successor_epoch=rebirth.next_epoch,
        previous_state_digest=previous.digest,
        fresh_state_digest=fresh.digest,
        rebirth_receipt_digest=rebirth.digest,
        tombstone_record_digest=record.record_digest,
        witness_bindings=witness_bindings,
        sacrifice_digest=b"",
    )
    object.__setattr__(
        result,
        "sacrifice_digest",
        _epoch_sacrifice_digest(
            activation_plan_digest=result.activation_plan_digest,
            sacrificed_epoch=result.sacrificed_epoch,
            successor_epoch=result.successor_epoch,
            previous_state_digest=result.previous_state_digest,
            fresh_state_digest=result.fresh_state_digest,
            rebirth_receipt_digest=result.rebirth_receipt_digest,
            tombstone_record_digest=result.tombstone_record_digest,
            witness_bindings=result.witness_bindings,
        ),
    )
    result.assert_sealed()
    return result


def require_vormir_epoch_sacrifice_v1(
    previous: UniverseState,
    fresh: UniverseState,
    rebirth: RebirthReceipt,
    receipt: VormirEpochSacrificeReceiptV1,
    fence: DurableEpochFence,
) -> EpochRecord:
    """Prove that old reach is durably dead and the successor is the only head."""

    receipt.assert_sealed()
    try:
        require_rebirth_receipt(previous, fresh, rebirth)
    except ValueError as error:
        raise VormirSacrificeError(str(error)) from error
    if receipt.activation_plan_digest != rebirth.activation_plan_digest:
        raise VormirSacrificeError("Vormir receipt Universe plan mismatch")
    if receipt.sacrificed_epoch != rebirth.previous_epoch:
        raise VormirSacrificeError("Vormir receipt sacrificed epoch mismatch")
    if receipt.successor_epoch != rebirth.next_epoch:
        raise VormirSacrificeError("Vormir receipt successor epoch mismatch")
    if receipt.previous_state_digest != previous.digest:
        raise VormirSacrificeError("Vormir receipt previous state mismatch")
    if receipt.fresh_state_digest != fresh.digest:
        raise VormirSacrificeError("Vormir receipt fresh state mismatch")
    if receipt.rebirth_receipt_digest != rebirth.digest:
        raise VormirSacrificeError("Vormir receipt rebirth mismatch")
    if not fence.is_tombstoned(receipt.activation_plan_digest, receipt.sacrificed_epoch):
        raise VormirSacrificeError("Vormir sacrificed epoch is not durably dead")
    head = fence.current(receipt.activation_plan_digest)
    if head is None or head.current_epoch != receipt.successor_epoch:
        raise VormirSacrificeError("Vormir successor is not the durable current epoch")
    if head.record_digest != receipt.tombstone_record_digest:
        raise VormirSacrificeError("Vormir durable record mismatch")
    return head
