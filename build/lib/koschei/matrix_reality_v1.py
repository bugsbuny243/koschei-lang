"""Koschei Matrix/Hara execution-reality physics v1.

Matrix is a local execution reality inside one Veyra, not a global Galaxy map.
Hara is the Aevra-scoped horizon inside that Matrix. Two Aevras may share a
Matrix identity without sharing a Hara, knowledge surface, or critical reach.

This first slice binds Matrix/Hara admission to one Veyra, one Aevra, one native
MIR reality and one epoch. It grants no authority and exposes no topology graph.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import string

from .galaxy_identity_v1 import AevraIdentity, VeyraIdentity
from .native_sigil_mir_v1 import NativeSigilMir

_CTX = b"koschei.matrix-reality/v1\x00"
_HEX = frozenset(string.hexdigits.lower())


class MatrixRealityError(ValueError):
    pass


def _digest64(value: str, label: str) -> str:
    if not isinstance(value, str) or len(value) != 64:
        raise MatrixRealityError(f"{label} must be a 64-character digest")
    value = value.lower()
    if any(ch not in _HEX for ch in value) or value == "0" * 64:
        raise MatrixRealityError(f"{label} must be a non-zero hexadecimal digest")
    return value


def _hash(kind: bytes, rows: tuple[str, ...]) -> str:
    return hashlib.sha256(_CTX + kind + b"\x00" + "\n".join(rows).encode("utf-8")).hexdigest()


@dataclass(frozen=True, slots=True)
class MatrixIdentity:
    veyra_digest: str
    instance_digest: str
    reality_commitment_digest: str
    birth_epoch: int
    digest: str
    version: int = 1

    def assert_sealed(self, veyra: VeyraIdentity) -> None:
        veyra.assert_sealed()
        if self.veyra_digest != veyra.digest:
            raise MatrixRealityError("Matrix belongs to a different Veyra")
        _digest64(self.instance_digest, "Matrix instance_digest")
        _digest64(self.reality_commitment_digest, "Matrix reality_commitment_digest")
        if not isinstance(self.birth_epoch, int) or self.birth_epoch < veyra.birth_epoch:
            raise MatrixRealityError("Matrix cannot predate its Veyra")
        expected = _hash(
            b"matrix",
            (
                f"veyra={self.veyra_digest}",
                f"instance={self.instance_digest}",
                f"reality={self.reality_commitment_digest}",
                f"epoch={self.birth_epoch}",
            ),
        )
        if self.digest != expected:
            raise MatrixRealityError("Matrix identity seal mismatch")


@dataclass(frozen=True, slots=True)
class HaraIdentity:
    matrix_digest: str
    aevra_digest: str
    horizon_commitment_digest: str
    epoch: int
    digest: str
    version: int = 1

    def assert_sealed(
        self,
        matrix: MatrixIdentity,
        veyra: VeyraIdentity,
        aevra: AevraIdentity,
        mir: NativeSigilMir,
    ) -> None:
        matrix.assert_sealed(veyra)
        aevra.assert_sealed(veyra, mir)
        if self.matrix_digest != matrix.digest:
            raise MatrixRealityError("Hara belongs to a different Matrix")
        if self.aevra_digest != aevra.digest:
            raise MatrixRealityError("Hara belongs to a different Aevra")
        _digest64(self.horizon_commitment_digest, "Hara horizon_commitment_digest")
        if not isinstance(self.epoch, int) or self.epoch < max(matrix.birth_epoch, aevra.birth_epoch):
            raise MatrixRealityError("Hara cannot predate Matrix or Aevra")
        expected = _hash(
            b"hara",
            (
                f"matrix={self.matrix_digest}",
                f"aevra={self.aevra_digest}",
                f"horizon={self.horizon_commitment_digest}",
                f"epoch={self.epoch}",
            ),
        )
        if self.digest != expected:
            raise MatrixRealityError("Hara identity seal mismatch")


@dataclass(frozen=True, slots=True)
class MatrixAdmission:
    matrix_digest: str
    hara_digest: str
    aevra_digest: str
    veyra_digest: str
    native_mir_fingerprint: str
    epoch: int
    evidence_digest: str
    digest: str
    version: int = 1

    def assert_sealed(
        self,
        matrix: MatrixIdentity,
        hara: HaraIdentity,
        veyra: VeyraIdentity,
        aevra: AevraIdentity,
        mir: NativeSigilMir,
    ) -> None:
        matrix.assert_sealed(veyra)
        hara.assert_sealed(matrix, veyra, aevra, mir)
        if self.matrix_digest != matrix.digest:
            raise MatrixRealityError("Matrix admission matrix mismatch")
        if self.hara_digest != hara.digest:
            raise MatrixRealityError("Matrix admission Hara mismatch")
        if self.aevra_digest != aevra.digest:
            raise MatrixRealityError("Matrix admission Aevra mismatch")
        if self.veyra_digest != veyra.digest:
            raise MatrixRealityError("Matrix admission Veyra mismatch")
        if self.native_mir_fingerprint != mir.fingerprint:
            raise MatrixRealityError("Matrix admission executable reality mismatch")
        if self.epoch != hara.epoch:
            raise MatrixRealityError("Matrix admission epoch mismatch")
        _digest64(self.evidence_digest, "Matrix admission evidence_digest")
        expected = _hash(
            b"admission",
            (
                f"matrix={self.matrix_digest}",
                f"hara={self.hara_digest}",
                f"aevra={self.aevra_digest}",
                f"veyra={self.veyra_digest}",
                f"mir={self.native_mir_fingerprint}",
                f"epoch={self.epoch}",
                f"evidence={self.evidence_digest}",
            ),
        )
        if self.digest != expected:
            raise MatrixRealityError("Matrix admission seal mismatch")


def birth_matrix(
    veyra: VeyraIdentity,
    *,
    instance_digest: str,
    reality_commitment_digest: str,
    birth_epoch: int,
) -> MatrixIdentity:
    veyra.assert_sealed()
    instance = _digest64(instance_digest, "Matrix instance_digest")
    reality = _digest64(reality_commitment_digest, "Matrix reality_commitment_digest")
    if not isinstance(birth_epoch, int) or birth_epoch < veyra.birth_epoch:
        raise MatrixRealityError("Matrix cannot predate its Veyra")
    result = MatrixIdentity(veyra.digest, instance, reality, birth_epoch, "")
    object.__setattr__(
        result,
        "digest",
        _hash(
            b"matrix",
            (
                f"veyra={result.veyra_digest}",
                f"instance={result.instance_digest}",
                f"reality={result.reality_commitment_digest}",
                f"epoch={result.birth_epoch}",
            ),
        ),
    )
    result.assert_sealed(veyra)
    return result


def birth_hara(
    matrix: MatrixIdentity,
    veyra: VeyraIdentity,
    aevra: AevraIdentity,
    mir: NativeSigilMir,
    *,
    horizon_commitment_digest: str,
    epoch: int,
) -> HaraIdentity:
    matrix.assert_sealed(veyra)
    aevra.assert_sealed(veyra, mir)
    horizon = _digest64(horizon_commitment_digest, "Hara horizon_commitment_digest")
    if not isinstance(epoch, int) or epoch < max(matrix.birth_epoch, aevra.birth_epoch):
        raise MatrixRealityError("Hara cannot predate Matrix or Aevra")
    result = HaraIdentity(matrix.digest, aevra.digest, horizon, epoch, "")
    object.__setattr__(
        result,
        "digest",
        _hash(
            b"hara",
            (
                f"matrix={result.matrix_digest}",
                f"aevra={result.aevra_digest}",
                f"horizon={result.horizon_commitment_digest}",
                f"epoch={result.epoch}",
            ),
        ),
    )
    result.assert_sealed(matrix, veyra, aevra, mir)
    return result


def admit_matrix_hara(
    matrix: MatrixIdentity,
    hara: HaraIdentity,
    veyra: VeyraIdentity,
    aevra: AevraIdentity,
    mir: NativeSigilMir,
    *,
    evidence_digest: str,
) -> MatrixAdmission:
    matrix.assert_sealed(veyra)
    hara.assert_sealed(matrix, veyra, aevra, mir)
    evidence = _digest64(evidence_digest, "Matrix admission evidence_digest")
    result = MatrixAdmission(
        matrix.digest,
        hara.digest,
        aevra.digest,
        veyra.digest,
        mir.fingerprint,
        hara.epoch,
        evidence,
        "",
    )
    object.__setattr__(
        result,
        "digest",
        _hash(
            b"admission",
            (
                f"matrix={result.matrix_digest}",
                f"hara={result.hara_digest}",
                f"aevra={result.aevra_digest}",
                f"veyra={result.veyra_digest}",
                f"mir={result.native_mir_fingerprint}",
                f"epoch={result.epoch}",
                f"evidence={result.evidence_digest}",
            ),
        ),
    )
    result.assert_sealed(matrix, hara, veyra, aevra, mir)
    return result
