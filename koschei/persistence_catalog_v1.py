"""Truthful stdlib catalog overlay for exact-object persistence v1."""

from __future__ import annotations

from . import stdlib_catalog as _catalog

_INSTALLED = False


def install_persistence_catalog_v1() -> None:
    global _INSTALLED
    if _INSTALLED:
        return

    family = _catalog.Family(
        name="persist",
        status="partial",
        target="v1",
        purpose=(
            "Exact-object persistent state with bounded payloads, descriptor anchoring, "
            "atomic replacement and explicit durability-state errors."
        ),
        operations=(
            _catalog.Operation(
                name="allow",
                status="reserved",
                capability="PersistRoot",
                security_sensitive=True,
                note=(
                    "An interpreter authority implementation exists, but catalog backend flags "
                    "remain false until the operation is promoted through executed parity gates."
                ),
            ),
            _catalog.Operation(
                name="load",
                status="reserved",
                capability="PersistCaps",
                required_budgets=("bytes", "deadline"),
                enforced_budgets=("bytes",),
                security_sensitive=True,
                note=(
                    "Interpreter load is descriptor-anchored and hard byte-bounded. The v1 "
                    "deadline is checked around syscalls but cannot preempt a blocking kernel "
                    "filesystem call, and native parity is not yet promoted."
                ),
            ),
            _catalog.Operation(
                name="commit",
                status="reserved",
                capability="PersistCaps",
                required_budgets=("bytes", "deadline"),
                enforced_budgets=("bytes",),
                security_sensitive=True,
                note=(
                    "Interpreter commit uses same-directory temp write, full-write loop, file "
                    "fsync, atomic replace and directory fsync. Post-replace durability "
                    "uncertainty is KS3423. Deadline preemption/native parity are not claimed."
                ),
            ),
        ),
    )

    if any(item.name == "persist" for item in _catalog.CATALOG):
        _catalog.CATALOG = tuple(
            family if item.name == "persist" else item for item in _catalog.CATALOG
        )
    else:
        _catalog.CATALOG = (*_catalog.CATALOG, family)
    _catalog.validate_catalog(_catalog.CATALOG)
    _INSTALLED = True
