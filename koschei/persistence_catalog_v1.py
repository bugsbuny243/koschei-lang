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
                    "Interpreter and Linux native-Go exact-object authority implementations "
                    "exist, but reserved operations keep backend flags false until real parity "
                    "gates execute and the operation is explicitly promoted."
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
                    "Interpreter and Linux native-Go loads are descriptor-anchored and hard "
                    "byte-bounded. The v1 deadline is checked around syscalls but cannot "
                    "preempt a blocking kernel filesystem call, so deadline is not promoted "
                    "as an enforced budget."
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
                    "Interpreter and Linux native-Go commits use same-directory temp write, "
                    "full-write loop, file fsync, descriptor-relative atomic replace and "
                    "directory fsync. Post-replace durability uncertainty is KS3423. Real CI "
                    "and syscall-preemptive deadline semantics are still required for promotion."
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
