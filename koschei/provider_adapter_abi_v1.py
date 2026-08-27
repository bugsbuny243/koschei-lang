"""Deterministic provider-adapter ABI identity for Koschei Lang v1.

This contract identifies *which verifier implementation contract* is authorized to
interpret one provider response schema.  It is provenance, not execution authority.
Provider SDK/network code remains outside Lang core.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import string

_CTX = b"koschei.provider-adapter-abi/v1\x00"
_HEX = frozenset(string.hexdigits.lower())


class ProviderAdapterAbiV1Error(ValueError):
    pass


def _text(value: str, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ProviderAdapterAbiV1Error(f"{label} cannot be empty")
    return value.strip()


def _digest(value: str, label: str) -> str:
    if not isinstance(value, str) or len(value) != 64:
        raise ProviderAdapterAbiV1Error(f"{label} must be a 64-character digest")
    lowered = value.lower()
    if any(ch not in _HEX for ch in lowered) or lowered == "0" * 64:
        raise ProviderAdapterAbiV1Error(f"{label} must be a non-zero hexadecimal digest")
    return lowered


def _payload(*, provider_id: str, adapter_id: str, schema_id: str,
             schema_version: str, verifier_implementation_digest: str) -> bytes:
    rows = (
        f"provider={provider_id}",
        f"adapter={adapter_id}",
        f"schema={schema_id}",
        f"schema_version={schema_version}",
        f"verifier_implementation={verifier_implementation_digest}",
        "authority=0",
    )
    return _CTX + "\n".join(rows).encode("utf-8")


@dataclass(frozen=True, slots=True)
class ProviderAdapterAbiV1:
    provider_id: str
    adapter_id: str
    schema_id: str
    schema_version: str
    verifier_implementation_digest: str
    abi_digest: str
    authority: bool = False
    version: int = 1

    def assert_sealed(self) -> None:
        if self.authority:
            raise ProviderAdapterAbiV1Error("provider adapter ABI cannot carry ambient authority")
        provider = _text(self.provider_id, "provider_id")
        adapter = _text(self.adapter_id, "adapter_id")
        schema = _text(self.schema_id, "schema_id")
        schema_version = _text(self.schema_version, "schema_version")
        implementation = _digest(self.verifier_implementation_digest, "verifier_implementation_digest")
        expected = hashlib.sha256(_payload(
            provider_id=provider,
            adapter_id=adapter,
            schema_id=schema,
            schema_version=schema_version,
            verifier_implementation_digest=implementation,
        )).hexdigest()
        if self.abi_digest != expected:
            raise ProviderAdapterAbiV1Error("provider adapter ABI seal mismatch")


def seal_provider_adapter_abi_v1(*, provider_id: str, adapter_id: str,
                                 schema_id: str, schema_version: str,
                                 verifier_implementation_digest: str) -> ProviderAdapterAbiV1:
    result = ProviderAdapterAbiV1(
        provider_id=_text(provider_id, "provider_id"),
        adapter_id=_text(adapter_id, "adapter_id"),
        schema_id=_text(schema_id, "schema_id"),
        schema_version=_text(schema_version, "schema_version"),
        verifier_implementation_digest=_digest(
            verifier_implementation_digest, "verifier_implementation_digest"
        ),
        abi_digest="",
    )
    object.__setattr__(result, "abi_digest", hashlib.sha256(_payload(
        provider_id=result.provider_id,
        adapter_id=result.adapter_id,
        schema_id=result.schema_id,
        schema_version=result.schema_version,
        verifier_implementation_digest=result.verifier_implementation_digest,
    )).hexdigest())
    result.assert_sealed()
    return result
