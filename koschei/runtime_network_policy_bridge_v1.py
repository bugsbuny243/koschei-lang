"""Bind bootstrap runtime network policy to Koschei's canonical contract.

The interpreter still exposes ``ALLOWED_NET_SCHEMES`` for its URL-origin helper,
but it must not own the value.  At every validated boot this bridge replaces the
bootstrap value with the canonical immutable policy object.
"""
from __future__ import annotations

from types import ModuleType

from .capability_effect_contract_v1 import NET_ORIGIN_SCHEMES


class RuntimeNetworkPolicyError(RuntimeError):
    pass


def bind_canonical_network_policy(runtime: ModuleType) -> None:
    if not hasattr(runtime, "ALLOWED_NET_SCHEMES"):
        raise RuntimeNetworkPolicyError("runtime network policy surface is missing")
    runtime.ALLOWED_NET_SCHEMES = NET_ORIGIN_SCHEMES


def require_canonical_network_policy(runtime: ModuleType) -> None:
    if getattr(runtime, "ALLOWED_NET_SCHEMES", None) is not NET_ORIGIN_SCHEMES:
        raise RuntimeNetworkPolicyError(
            "runtime network policy is not bound to canonical contract object"
        )
