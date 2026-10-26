"""Fail-closed runtime boundary for compiler-owned MIR variant identities.

This module does not select match arms and carries no authority.  It only
interprets an already sealed canonical ``Owner::Variant`` fact against Koschei's
canonical ``EnumValue`` runtime representation.  Source-visible arm text alone
is never accepted as identity.
"""
from __future__ import annotations

from .interpreter import EnumValue, _NO_PAYLOAD


class MirVariantRuntimeError(ValueError):
    pass


def split_canonical_variant_v1(canonical_variant: str) -> tuple[str, str]:
    """Parse one exact compiler-owned ``Owner::Variant`` identity."""

    if not isinstance(canonical_variant, str) or not canonical_variant:
        raise MirVariantRuntimeError("canonical variant identity must be non-empty")
    if canonical_variant.count("::") != 1:
        raise MirVariantRuntimeError("canonical variant identity must be Owner::Variant")
    owner, variant = canonical_variant.split("::", 1)
    if not owner or not variant:
        raise MirVariantRuntimeError("canonical variant owner and name must be non-empty")
    return owner, variant


def variant_is_v1(value: object, canonical_variant: str) -> bool:
    """Compare runtime value with one compiler-selected canonical identity."""

    owner, variant = split_canonical_variant_v1(canonical_variant)
    if not isinstance(value, EnumValue):
        raise MirVariantRuntimeError("MIR variant comparison requires EnumValue")
    return value.enum_name == owner and value.variant == variant


def variant_payload_v1(value: object, canonical_variant: str) -> object:
    """Extract payload only when the exact canonical variant currently matches."""

    if not variant_is_v1(value, canonical_variant):
        raise MirVariantRuntimeError("payload extraction variant proof mismatch")
    assert isinstance(value, EnumValue)
    if value.payload is _NO_PAYLOAD:
        raise MirVariantRuntimeError("canonical variant carries no payload")
    return value.payload
