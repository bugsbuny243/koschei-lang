"""Koschei protected read broker v1.

Unauthorized or unverified reads never touch canonical source bytes. They receive
an epoch-scoped synthetic decoy view derived from independent deception material.
Canonical build/sign/deploy paths must reject every decoy or unattested view.
"""

from __future__ import annotations

from dataclasses import dataclass
import base64
import hashlib
import hmac
from typing import Callable


class DecoyViewError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class SourceView:
    object_id: str
    epoch: int
    provenance: str
    deployable: bool
    content: bytes
    view_digest: str
    project_id: str = ""
    canonical_attestation: str = ""


CanonicalReader = Callable[[str], bytes]


def _require_project_id(project_id: str) -> str:
    if not isinstance(project_id, str) or not project_id:
        raise DecoyViewError("project_id must be non-empty text")
    if "\x00" in project_id:
        raise DecoyViewError("project_id cannot contain NUL")
    return project_id


def _require_object_id(object_id: str) -> str:
    if not isinstance(object_id, str):
        raise DecoyViewError("object_id must be text")
    oid = object_id.lower()
    if len(oid) < 32 or any(ch not in "0123456789abcdef" for ch in oid):
        raise DecoyViewError("object_id must be >=128-bit hexadecimal")
    return oid


def _require_epoch(epoch: int) -> int:
    if not isinstance(epoch, int) or isinstance(epoch, bool) or epoch < 0:
        raise DecoyViewError("epoch must be a non-negative integer")
    return epoch


def _require_key(key: bytes) -> bytes:
    if not isinstance(key, bytes) or len(key) < 32:
        raise DecoyViewError("deception_key must contain at least 256 bits")
    return key


def _require_canonical_view_key(key: bytes | None) -> bytes:
    if not isinstance(key, bytes) or len(key) < 32:
        raise DecoyViewError("canonical_view_key must contain at least 256 bits")
    return key


def _require_digest(value: str) -> str:
    if not isinstance(value, str) or not value.startswith("sha256:"):
        raise DecoyViewError("source view digest must be sha256 text")
    digest = value[7:]
    if len(digest) != 64 or any(ch not in "0123456789abcdef" for ch in digest):
        raise DecoyViewError("source view digest is malformed")
    return value


def _require_attestation(value: str) -> str:
    if not isinstance(value, str) or not value.startswith("hmac-sha256:"):
        raise DecoyViewError("canonical source view attestation is missing or malformed")
    digest = value[12:]
    if len(digest) != 64 or any(ch not in "0123456789abcdef" for ch in digest):
        raise DecoyViewError("canonical source view attestation is malformed")
    return value


def _frame(value: bytes) -> bytes:
    return len(value).to_bytes(8, "big") + value


def _canonical_attestation(
    *,
    key: bytes,
    project_id: str,
    object_id: str,
    epoch: int,
    content_digest: str,
    deployable: bool,
) -> str:
    message = (
        b"koschei/canonical-source-view/v1\x00"
        + _frame(project_id.encode("utf-8"))
        + _frame(object_id.encode("ascii"))
        + _frame(str(epoch).encode("ascii"))
        + _frame(content_digest.encode("ascii"))
        + (b"\x01" if deployable else b"\x00")
    )
    return "hmac-sha256:" + hmac.new(key, message, hashlib.sha256).hexdigest()


def _token(key: bytes, label: bytes, project_id: str, object_id: str, epoch: int, n: int = 12) -> str:
    message = (
        b"koschei/decoy-view/v1\x00" + label + b"\x00"
        + project_id.encode("utf-8") + b"\x00"
        + object_id.encode("ascii") + b"\x00"
        + str(epoch).encode("ascii")
    )
    digest = hmac.new(key, message, hashlib.sha256).digest()[:n]
    return base64.b32encode(digest).decode("ascii").rstrip("=").lower()


def generate_decoy_source(*, project_id: str, object_id: str, epoch: int, deception_key: bytes) -> bytes:
    """Generate synthetic Koschei source without reading canonical content.

    The visible source shape is size-invariant across object/session/epoch inputs:
    both numeric literals intentionally remain in a two-decimal-digit domain.
    Identity/content still rotate through keyed function names and marker-derived
    values, but a passive observer does not get a one-byte classifier from the
    decimal width of those values.
    """
    project = _require_project_id(project_id)
    oid = _require_object_id(object_id)
    ep = _require_epoch(epoch)
    key = _require_key(deception_key)

    fn_a = "f_" + _token(key, b"fn-a", project, oid, ep, 7)
    fn_b = "f_" + _token(key, b"fn-b", project, oid, ep, 7)
    marker = _token(key, b"marker", project, oid, ep, 10)

    # Keep both decimal literals in [10, 96] / [10, 30] so their textual width
    # is always exactly two bytes. This removes a source-length side channel
    # without making the synthetic program static.
    epoch_term = (ep % 87) + 10
    delta = (int(marker[:2], 36) % 21) + 10

    text = (
        f"fn {fn_a}(seed: Int) -> Int {{\n"
        f"    let x: Int = seed * 3 + {epoch_term};\n"
        f"    return x;\n"
        f"}}\n\n"
        f"fn {fn_b}(seed: Int) -> Int {{\n"
        f"    let y: Int = {fn_a}(seed) + {delta};\n"
        f"    return y;\n"
        f"}}\n"
    )
    return text.encode("utf-8")


def read_source_view(
    *,
    project_id: str,
    object_id: str,
    epoch: int,
    authorized: bool,
    canonical_reader: CanonicalReader,
    deception_key: bytes,
    canonical_view_key: bytes | None = None,
) -> SourceView:
    """Return canonical bytes only for admitted reads; otherwise an isolated decoy.

    ``canonical_view_key`` is intentionally optional for ordinary authorized
    developer reads. A canonical view can enter build/sign/deploy only when the
    trusted caller supplies this separate key and the build gate verifies the
    resulting HMAC attestation.
    """
    project = _require_project_id(project_id)
    oid = _require_object_id(object_id)
    ep = _require_epoch(epoch)
    if not callable(canonical_reader):
        raise DecoyViewError("canonical_reader must be callable")

    if authorized:
        content = canonical_reader(oid)
        if not isinstance(content, bytes):
            raise DecoyViewError("canonical_reader must return bytes")
        provenance = "canonical"
        deployable = True
    else:
        content = generate_decoy_source(
            project_id=project,
            object_id=oid,
            epoch=ep,
            deception_key=deception_key,
        )
        provenance = "decoy"
        deployable = False

    digest = "sha256:" + hashlib.sha256(content).hexdigest()
    attestation = ""
    if authorized and canonical_view_key is not None:
        key = _require_canonical_view_key(canonical_view_key)
        attestation = _canonical_attestation(
            key=key,
            project_id=project,
            object_id=oid,
            epoch=ep,
            content_digest=digest,
            deployable=deployable,
        )

    return SourceView(
        object_id=oid,
        epoch=ep,
        provenance=provenance,
        deployable=deployable,
        content=content,
        view_digest=digest,
        project_id=project,
        canonical_attestation=attestation,
    )


def require_canonical_build_view(
    view: SourceView,
    *,
    canonical_view_key: bytes | None = None,
) -> None:
    """Fail closed unless a canonical view carries a valid build attestation."""
    if not isinstance(view, SourceView):
        raise DecoyViewError("invalid source view")
    if view.provenance != "canonical" or view.deployable is not True:
        raise DecoyViewError("decoy/non-canonical source view cannot enter build/sign/deploy")

    key = _require_canonical_view_key(canonical_view_key)
    project = _require_project_id(view.project_id)
    oid = _require_object_id(view.object_id)
    ep = _require_epoch(view.epoch)
    if not isinstance(view.content, bytes):
        raise DecoyViewError("canonical source content must be bytes")

    claimed_digest = _require_digest(view.view_digest)
    digest = "sha256:" + hashlib.sha256(view.content).hexdigest()
    if not hmac.compare_digest(digest, claimed_digest):
        raise DecoyViewError("canonical source view digest mismatch")

    claimed_attestation = _require_attestation(view.canonical_attestation)
    expected = _canonical_attestation(
        key=key,
        project_id=project,
        object_id=oid,
        epoch=ep,
        content_digest=digest,
        deployable=view.deployable,
    )
    if not hmac.compare_digest(expected, claimed_attestation):
        raise DecoyViewError("canonical source view attestation is invalid")
