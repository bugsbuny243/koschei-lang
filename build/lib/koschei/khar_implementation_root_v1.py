"""Externally witnessed Koschei Khar implementation-root binding v1.

Canonical Khar identifies the laws, but software cannot prove its own executing
bytes trustworthy by hashing itself.  This module therefore defines the
software side of an external measurement boundary: an implementation
measurement is bound to one canonical Khar, one Veyra, one native-MIR product
and one execution epoch, then independently witnessed by distinct failure roots.

The witness keys are deliberately not stored here.  They must be supplied by an
external deployment anchor (for example a measured host, isolated verifier, or
other independently protected root).  Passing caller-controlled keys provides
no physical trust; this module makes that boundary explicit rather than hiding
it behind a boolean such as ``trusted=True``.

This layer grants no authority.  A verified implementation root only proves
that the configured independent witnesses agreed on the exact implementation
measurement.  Critical effects must still pass the normal Galaxy laws.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import hmac
import string
from typing import Mapping

from .khar_constitution_v1 import CANONICAL_KHAR_DIGEST_V1

_CTX = b"koschei.khar-implementation-root/v1\x00"
_HEX = frozenset(string.hexdigits.lower())
MIN_INDEPENDENT_WITNESSES_V1 = 2


class KharImplementationRootError(ValueError):
    pass


def _require_digest(value: str, label: str) -> str:
    if not isinstance(value, str) or len(value) != 64:
        raise KharImplementationRootError(f"{label} must be a 64-character digest")
    lowered = value.lower()
    if any(ch not in _HEX for ch in lowered):
        raise KharImplementationRootError(f"{label} must be hexadecimal")
    if lowered == "0" * 64:
        raise KharImplementationRootError(f"{label} cannot be the zero digest")
    return lowered


def _require_commit(value: str) -> str:
    if not isinstance(value, str) or len(value) != 40:
        raise KharImplementationRootError("ci_head_sha must be a 40-character Git commit SHA")
    lowered = value.lower()
    if any(ch not in _HEX for ch in lowered):
        raise KharImplementationRootError("ci_head_sha must be hexadecimal")
    return lowered


def _require_epoch(value: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise KharImplementationRootError("implementation epoch must be a non-negative integer")
    return value


def _require_label(value: str, label: str) -> str:
    if not isinstance(value, str) or not value or len(value) > 128 or "\x00" in value:
        raise KharImplementationRootError(
            f"{label} must be 1..128 characters of non-NUL text"
        )
    return value


def _require_key(value: bytes) -> bytes:
    if not isinstance(value, bytes) or len(value) < 32:
        raise KharImplementationRootError("witness key must contain at least 256 bits")
    return value


def _hash_rows(kind: bytes, rows: tuple[str, ...]) -> str:
    return hashlib.sha256(
        _CTX + kind + b"\x00" + "\n".join(rows).encode("utf-8")
    ).hexdigest()


def _witness_mac(
    *,
    key: bytes,
    witness_id: str,
    failure_root: str,
    measurement_digest: str,
) -> str:
    message = (
        _CTX
        + b"witness\x00"
        + witness_id.encode("utf-8")
        + b"\x00"
        + failure_root.encode("utf-8")
        + b"\x00"
        + measurement_digest.encode("ascii")
    )
    return "hmac-sha256:" + hmac.new(key, message, hashlib.sha256).hexdigest()


@dataclass(frozen=True, slots=True)
class KharImplementationMeasurementV1:
    khar_digest: str
    veyra_digest: str
    native_mir_fingerprint: str
    epoch: int
    compiler_sha256: str
    runtime_sha256: str
    native_build_manifest_digest: str
    release_proof_digest: str
    maturity_attestation_digest: str
    ci_head_sha: str
    digest: str
    version: int = 1

    def assert_sealed(self) -> None:
        if self.version != 1:
            raise KharImplementationRootError("unsupported implementation measurement version")
        khar = _require_digest(self.khar_digest, "khar_digest")
        if khar != CANONICAL_KHAR_DIGEST_V1:
            raise KharImplementationRootError(
                "implementation measurement is not bound to canonical Khar v1"
            )
        veyra = _require_digest(self.veyra_digest, "veyra_digest")
        mir = _require_digest(self.native_mir_fingerprint, "native_mir_fingerprint")
        epoch = _require_epoch(self.epoch)
        compiler = _require_digest(self.compiler_sha256, "compiler_sha256")
        runtime = _require_digest(self.runtime_sha256, "runtime_sha256")
        build = _require_digest(
            self.native_build_manifest_digest,
            "native_build_manifest_digest",
        )
        release = _require_digest(self.release_proof_digest, "release_proof_digest")
        maturity = _require_digest(
            self.maturity_attestation_digest,
            "maturity_attestation_digest",
        )
        head = _require_commit(self.ci_head_sha)
        expected = _hash_rows(
            b"measurement",
            (
                f"khar={khar}",
                f"veyra={veyra}",
                f"mir={mir}",
                f"epoch={epoch}",
                f"compiler={compiler}",
                f"runtime={runtime}",
                f"build-manifest={build}",
                f"release-proof={release}",
                f"maturity-attestation={maturity}",
                f"ci-head={head}",
            ),
        )
        if self.digest != expected:
            raise KharImplementationRootError("implementation measurement seal mismatch")


def build_khar_implementation_measurement(
    *,
    veyra_digest: str,
    native_mir_fingerprint: str,
    epoch: int,
    compiler_sha256: str,
    runtime_sha256: str,
    native_build_manifest_digest: str,
    release_proof_digest: str,
    maturity_attestation_digest: str,
    ci_head_sha: str,
) -> KharImplementationMeasurementV1:
    """Build the exact claim that independent roots must witness.

    The build/release/maturity digests are intended to come from the repository's
    already-verified native-build, release-proof and maturity-attestation paths.
    This function binds those identities; it does not replace their verifiers.
    """

    result = KharImplementationMeasurementV1(
        khar_digest=CANONICAL_KHAR_DIGEST_V1,
        veyra_digest=_require_digest(veyra_digest, "veyra_digest"),
        native_mir_fingerprint=_require_digest(
            native_mir_fingerprint,
            "native_mir_fingerprint",
        ),
        epoch=_require_epoch(epoch),
        compiler_sha256=_require_digest(compiler_sha256, "compiler_sha256"),
        runtime_sha256=_require_digest(runtime_sha256, "runtime_sha256"),
        native_build_manifest_digest=_require_digest(
            native_build_manifest_digest,
            "native_build_manifest_digest",
        ),
        release_proof_digest=_require_digest(release_proof_digest, "release_proof_digest"),
        maturity_attestation_digest=_require_digest(
            maturity_attestation_digest,
            "maturity_attestation_digest",
        ),
        ci_head_sha=_require_commit(ci_head_sha),
        digest="",
    )
    object.__setattr__(
        result,
        "digest",
        _hash_rows(
            b"measurement",
            (
                f"khar={result.khar_digest}",
                f"veyra={result.veyra_digest}",
                f"mir={result.native_mir_fingerprint}",
                f"epoch={result.epoch}",
                f"compiler={result.compiler_sha256}",
                f"runtime={result.runtime_sha256}",
                f"build-manifest={result.native_build_manifest_digest}",
                f"release-proof={result.release_proof_digest}",
                f"maturity-attestation={result.maturity_attestation_digest}",
                f"ci-head={result.ci_head_sha}",
            ),
        ),
    )
    result.assert_sealed()
    return result


@dataclass(frozen=True, slots=True)
class KharImplementationWitnessV1:
    witness_id: str
    failure_root: str
    measurement_digest: str
    mac: str
    version: int = 1

    def assert_for(self, measurement: KharImplementationMeasurementV1, key: bytes) -> None:
        if self.version != 1:
            raise KharImplementationRootError("unsupported implementation witness version")
        measurement.assert_sealed()
        witness_id = _require_label(self.witness_id, "witness_id")
        failure_root = _require_label(self.failure_root, "failure_root")
        if self.measurement_digest != measurement.digest:
            raise KharImplementationRootError("witness belongs to a different measurement")
        if not isinstance(self.mac, str) or not self.mac.startswith("hmac-sha256:"):
            raise KharImplementationRootError("implementation witness MAC is malformed")
        digest = self.mac[12:]
        if len(digest) != 64 or any(ch not in _HEX for ch in digest.lower()):
            raise KharImplementationRootError("implementation witness MAC is malformed")
        expected = _witness_mac(
            key=_require_key(key),
            witness_id=witness_id,
            failure_root=failure_root,
            measurement_digest=measurement.digest,
        )
        if not hmac.compare_digest(expected, self.mac.lower()):
            raise KharImplementationRootError("implementation witness MAC is invalid")


def seal_khar_implementation_witness(
    measurement: KharImplementationMeasurementV1,
    *,
    witness_id: str,
    failure_root: str,
    key: bytes,
) -> KharImplementationWitnessV1:
    """Seal one external witness claim for the exact implementation measurement."""

    measurement.assert_sealed()
    wid = _require_label(witness_id, "witness_id")
    root = _require_label(failure_root, "failure_root")
    secret = _require_key(key)
    result = KharImplementationWitnessV1(
        witness_id=wid,
        failure_root=root,
        measurement_digest=measurement.digest,
        mac=_witness_mac(
            key=secret,
            witness_id=wid,
            failure_root=root,
            measurement_digest=measurement.digest,
        ),
    )
    result.assert_for(measurement, secret)
    return result


@dataclass(frozen=True, slots=True)
class VerifiedKharImplementationRootV1:
    khar_digest: str
    veyra_digest: str
    native_mir_fingerprint: str
    epoch: int
    measurement_digest: str
    witness_ids: tuple[str, ...]
    failure_roots: tuple[str, ...]
    authority: bool
    digest: str
    version: int = 1

    def assert_sealed(self) -> None:
        if self.version != 1:
            raise KharImplementationRootError("unsupported verified implementation-root version")
        if self.authority is not False:
            raise KharImplementationRootError("implementation-root evidence cannot grant authority")
        khar = _require_digest(self.khar_digest, "khar_digest")
        if khar != CANONICAL_KHAR_DIGEST_V1:
            raise KharImplementationRootError("verified implementation root is not canonical Khar v1")
        veyra = _require_digest(self.veyra_digest, "veyra_digest")
        mir = _require_digest(self.native_mir_fingerprint, "native_mir_fingerprint")
        epoch = _require_epoch(self.epoch)
        measurement = _require_digest(self.measurement_digest, "measurement_digest")
        if len(self.witness_ids) < MIN_INDEPENDENT_WITNESSES_V1:
            raise KharImplementationRootError("implementation root has too few witnesses")
        if len(set(self.witness_ids)) != len(self.witness_ids):
            raise KharImplementationRootError("implementation root repeats a witness")
        if len(self.failure_roots) < MIN_INDEPENDENT_WITNESSES_V1:
            raise KharImplementationRootError("implementation root has too few failure roots")
        if len(set(self.failure_roots)) != len(self.failure_roots):
            raise KharImplementationRootError("implementation root repeats a failure root")
        witnesses = tuple(_require_label(value, "witness_id") for value in self.witness_ids)
        roots = tuple(_require_label(value, "failure_root") for value in self.failure_roots)
        if witnesses != tuple(sorted(witnesses)) or roots != tuple(sorted(roots)):
            raise KharImplementationRootError("implementation root witness sets are not canonical")
        expected = _hash_rows(
            b"verified-root",
            (
                f"khar={khar}",
                f"veyra={veyra}",
                f"mir={mir}",
                f"epoch={epoch}",
                f"measurement={measurement}",
                "witnesses=" + ",".join(witnesses),
                "failure-roots=" + ",".join(roots),
                "authority=false",
            ),
        )
        if self.digest != expected:
            raise KharImplementationRootError("verified implementation-root seal mismatch")

    def assert_for(
        self,
        *,
        veyra_digest: str,
        native_mir_fingerprint: str,
        epoch: int,
    ) -> None:
        self.assert_sealed()
        if self.veyra_digest != _require_digest(veyra_digest, "veyra_digest"):
            raise KharImplementationRootError("implementation root belongs to a different Veyra")
        if self.native_mir_fingerprint != _require_digest(
            native_mir_fingerprint,
            "native_mir_fingerprint",
        ):
            raise KharImplementationRootError(
                "implementation root belongs to a different native MIR product"
            )
        if self.epoch != _require_epoch(epoch):
            raise KharImplementationRootError("implementation root belongs to a different epoch")


def verify_khar_implementation_root(
    measurement: KharImplementationMeasurementV1,
    witnesses: tuple[KharImplementationWitnessV1, ...],
    *,
    witness_keys: Mapping[str, bytes],
) -> VerifiedKharImplementationRootV1:
    """Verify independent external witnesses and mint authority-free root evidence.

    ``witness_keys`` is part of the external trust boundary.  It must come from
    outside caller-controlled Koschei program state.  The verifier rejects the
    whole set when any supplied witness is malformed or invalid; there is no
    best-effort partial acceptance.
    """

    measurement.assert_sealed()
    if not isinstance(witness_keys, Mapping):
        raise KharImplementationRootError("witness_keys must be a mapping")
    if len(witnesses) < MIN_INDEPENDENT_WITNESSES_V1:
        raise KharImplementationRootError(
            f"at least {MIN_INDEPENDENT_WITNESSES_V1} independent witnesses are required"
        )

    witness_ids: list[str] = []
    failure_roots: list[str] = []
    for witness in witnesses:
        if not isinstance(witness, KharImplementationWitnessV1):
            raise KharImplementationRootError("invalid implementation witness")
        if witness.witness_id in witness_ids:
            raise KharImplementationRootError("duplicate implementation witness id")
        if witness.failure_root in failure_roots:
            raise KharImplementationRootError(
                "implementation witnesses must use independent failure roots"
            )
        try:
            key = witness_keys[witness.witness_id]
        except KeyError as error:
            raise KharImplementationRootError(
                f"missing external key for implementation witness {witness.witness_id!r}"
            ) from error
        witness.assert_for(measurement, key)
        witness_ids.append(witness.witness_id)
        failure_roots.append(witness.failure_root)

    ids = tuple(sorted(witness_ids))
    roots = tuple(sorted(failure_roots))
    result = VerifiedKharImplementationRootV1(
        khar_digest=measurement.khar_digest,
        veyra_digest=measurement.veyra_digest,
        native_mir_fingerprint=measurement.native_mir_fingerprint,
        epoch=measurement.epoch,
        measurement_digest=measurement.digest,
        witness_ids=ids,
        failure_roots=roots,
        authority=False,
        digest="",
    )
    object.__setattr__(
        result,
        "digest",
        _hash_rows(
            b"verified-root",
            (
                f"khar={result.khar_digest}",
                f"veyra={result.veyra_digest}",
                f"mir={result.native_mir_fingerprint}",
                f"epoch={result.epoch}",
                f"measurement={result.measurement_digest}",
                "witnesses=" + ",".join(result.witness_ids),
                "failure-roots=" + ",".join(result.failure_roots),
                "authority=false",
            ),
        ),
    )
    result.assert_sealed()
    return result
