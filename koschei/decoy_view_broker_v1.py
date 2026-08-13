"""Koschei protected read broker v1.

Unauthorized or unverified reads never touch canonical source bytes. They receive
an epoch-scoped synthetic decoy view derived from independent deception material.
Canonical build/sign/deploy paths must reject every decoy view by provenance.
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


CanonicalReader = Callable[[str], bytes]


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


def _token(key: bytes, label: bytes, project_id: str, object_id: str, epoch: int, n: int = 12) -> str:
    message = (
        b"koschei/decoy-view/v1\x00"
        + label
        + b"\x00"
        + project_id.encode("utf-8")
        + b"\x00"
        + object_id.encode("ascii")
        + b"\x00"
        + str(epoch).encode("ascii")
    )
    digest = hmac.new(key, message, hashlib.sha256).digest()[:n]
    return base64.b32encode(digest).decode("ascii").rstrip("=").lower()


def generate_decoy_source(
    *,
    project_id: str,
    object_id: str,
    epoch: int,
    deception_key: bytes,
) -> bytes:
    """Generate a coherent synthetic Koschei-shaped object without canonical input.

    v1 is deliberately deterministic and model-free so leakage and rotation can be
    measured before a generative model is connected. A later model may replace the
    content generator, but it must preserve this no-canonical-read boundary.
    """

    if not isinstance(project_id, str) or not project_id:
        raise DecoyViewError("project_id must be non-empty text")
    oid = _require_object_id(object_id)
    ep = _require_epoch(epoch)
    key = _require_key(deception_key)

    namespace = "n_" + _token(key, b"namespace", project_id, oid, ep, 8)
    fn_a = "f_" + _token(key, b"fn-a", project_id, oid, ep, 7)
    fn_b = "f_" + _token(key, b"fn-b", project_id, oid, ep, 7)
    marker = _token(key, b"marker", project_id, oid, ep, 10)

    # Synthetic source intentionally contains no canonical source bytes, names,
    # hashes, policy values, secrets, paths, or dependency metadata.
    text = (
        f"namespace {namespace} {{\n"
        f"  struct R_{marker[:8]} {{ value: Int }}\n\n"
        f"  fn {fn_a}(seed: Int) -> Int {{\n"
        f"    let x: Int = seed * 3 + {ep % 97};\n"
        f"    return x;\n"
        f"  }}\n\n"
        f"  fn {fn_b}(seed: Int) -> Int {{\n"
        f"    let y: Int = {fn_a}(seed) + {int(marker[:2], 36) % 31};\n"
        f"    return y;\n"
        f"  }}\n"
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
) -> SourceView:
    """Return canonical bytes only for an admitted read; otherwise return decoy.

    The unauthorized branch never invokes canonical_reader. This is the primary
    v1 non-leakage invariant and is covered by tests.
    """

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
            project_id=project_id,
            object_id=oid,
            epoch=ep,
            deception_key=deception_key,
        )
        provenance = "decoy"
        deployable = False

    digest = "sha256:" + hashlib.sha256(content).hexdigest()
    return SourceView(
        object_id=oid,
        epoch=ep,
        provenance=provenance,
        deployable=deployable,
        content=content,
        view_digest=digest,
    )


def require_canonical_build_view(view: SourceView) -> None:
    """Fail closed if a decoy/untrusted view reaches build/sign/deploy input."""

    if not isinstance(view, SourceView):
        raise DecoyViewError("invalid source view")
    if view.provenance != "canonical" or view.deployable is not True:
        raise DecoyViewError("decoy/non-canonical source view cannot enter build/sign/deploy")
