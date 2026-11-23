"""Ed25519 (RFC 8032, section 5.1) without third-party dependencies.

This follows the RFC's own Python reference implementation (section 6),
which the RFC places in the public domain, with the checks a verifier must
make spelled out:

- public keys and the ``R`` half of a signature must decode to curve points
  from canonical encodings (``y < p``; no "negative zero" x);
- ``S`` must be below the group order ``L`` (no malleable signatures);
- public keys of small order are refused (a key like the identity point
  "verifies" a trivial signature for every message; OpenSSL accepts that,
  this module does not);
- the check is the cofactorless equation ``[S]B == R + [k]A``, the same one
  OpenSSL and libsodium use.

Verification handles public data only. Signing handles a secret seed and is
not constant-time; it is meant for ``ks pkg keygen`` / ``ks pkg sign`` on the
publisher's own machine, never for a server. ``tests/test_ed25519_v1.py``
checks this module against the RFC's test vectors and, when the
``cryptography`` package is installed, against OpenSSL on random keys,
messages and corrupted signatures.
"""

from __future__ import annotations

import hashlib
import secrets

P = 2**255 - 19
L = 2**252 + 27742317777372353535851937790883648493
D = (-121665 * pow(121666, P - 2, P)) % P
SQRT_M1 = pow(2, (P - 1) // 4, P)

Point = tuple[int, int, int, int]  # extended coordinates (X, Y, Z, T)


def _sha512(data: bytes) -> bytes:
    return hashlib.sha512(data).digest()


def _sha512_mod_l(data: bytes) -> int:
    return int.from_bytes(_sha512(data), "little") % L


def _add(a: Point, b: Point) -> Point:
    x1, y1, z1, t1 = a
    x2, y2, z2, t2 = b
    aa = (y1 - x1) * (y2 - x2) % P
    bb = (y1 + x1) * (y2 + x2) % P
    cc = t1 * 2 * D * t2 % P
    dd = z1 * 2 * z2 % P
    e, f, g, h = bb - aa, dd - cc, dd + cc, bb + aa
    return (e * f % P, g * h % P, f * g % P, e * h % P)


def _mul(scalar: int, point: Point) -> Point:
    result: Point = (0, 1, 1, 0)
    while scalar > 0:
        if scalar & 1:
            result = _add(result, point)
        point = _add(point, point)
        scalar >>= 1
    return result


def _equal(a: Point, b: Point) -> bool:
    x1, y1, z1, _ = a
    x2, y2, z2, _ = b
    return (x1 * z2 - x2 * z1) % P == 0 and (y1 * z2 - y2 * z1) % P == 0


def _recover_x(y: int, sign: int) -> int | None:
    if y >= P:
        return None
    x2 = (y * y - 1) * pow(D * y * y + 1, P - 2, P) % P
    if x2 == 0:
        return None if sign else 0
    x = pow(x2, (P + 3) // 8, P)
    if (x * x - x2) % P != 0:
        x = x * SQRT_M1 % P
    if (x * x - x2) % P != 0:
        return None
    if (x & 1) != sign:
        x = P - x
    return x


_GY = 4 * pow(5, P - 2, P) % P
_GX = _recover_x(_GY, 0)
assert _GX is not None
BASE: Point = (_GX, _GY, 1, _GX * _GY % P)


def _compress(point: Point) -> bytes:
    x, y, z, _ = point
    inverse = pow(z, P - 2, P)
    x, y = x * inverse % P, y * inverse % P
    return int.to_bytes(y | ((x & 1) << 255), 32, "little")


def _decompress(data: bytes) -> Point | None:
    if len(data) != 32:
        return None
    y = int.from_bytes(data, "little")
    sign = y >> 255
    y &= (1 << 255) - 1
    x = _recover_x(y, sign)
    if x is None:
        return None
    return (x, y, 1, x * y % P)


def _expand(seed: bytes) -> tuple[int, bytes]:
    if len(seed) != 32:
        raise ValueError("an Ed25519 secret seed is 32 bytes")
    digest = _sha512(seed)
    scalar = int.from_bytes(digest[:32], "little")
    scalar &= (1 << 254) - 8
    scalar |= 1 << 254
    return scalar, digest[32:]


def new_seed() -> bytes:
    return secrets.token_bytes(32)


def public_key(seed: bytes) -> bytes:
    scalar, _ = _expand(seed)
    return _compress(_mul(scalar, BASE))


def sign(seed: bytes, message: bytes) -> bytes:
    scalar, prefix = _expand(seed)
    public = _compress(_mul(scalar, BASE))
    r = _sha512_mod_l(prefix + message)
    big_r = _compress(_mul(r, BASE))
    k = _sha512_mod_l(big_r + public + message)
    s = (r + k * scalar) % L
    return big_r + int.to_bytes(s, 32, "little")


def verify(public: bytes, message: bytes, signature: bytes) -> bool:
    if len(public) != 32 or len(signature) != 64:
        return False
    a = _decompress(public)
    if a is None or _equal(_mul(8, a), (0, 1, 1, 0)):
        return False
    big_r = _decompress(signature[:32])
    if big_r is None:
        return False
    s = int.from_bytes(signature[32:], "little")
    if s >= L:
        return False
    k = _sha512_mod_l(signature[:32] + public + message)
    return _equal(_mul(s, BASE), _add(big_r, _mul(k, a)))
