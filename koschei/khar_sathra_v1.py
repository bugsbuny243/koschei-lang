"""Koschei Khar six-axis concurrence physics v1.

This module encodes one constitutional rule of the Koschei Universe: a critical
result is not accumulated from partial power. Six independent axes must agree on
one living event in one Aevra, one Veyra, one epoch, and one reality. Five axes
are not partial success; they are no Sathra at all.

The axis names are native Koschei terms rather than third-party universe names:

- khor: locus / isolation
- sei: intent / control direction
- rha: executable reality
- vaal: effect force
- teyr: temporal epoch
- esh: continuity / living identity

This layer does not manufacture evidence. It only seals already-produced axis
witnesses into a Sathra when the Khar concurrence law is satisfied.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
from typing import Iterable

_CTX = b"koschei.khar-sathra/v1\x00"
KHAR_AXES = ("khor", "sei", "rha", "vaal", "teyr", "esh")
_KHAR_AXIS_SET = frozenset(KHAR_AXES)


class KharSathraError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class AxisWitness:
    axis: str
    aevra_digest: str
    veyra_digest: str
    event_digest: str
    reality_digest: str
    epoch: int
    witness_digest: str

    def __post_init__(self) -> None:
        if self.axis not in _KHAR_AXIS_SET:
            raise KharSathraError(f"unknown Khar axis: {self.axis!r}")
        if self.epoch < 0:
            raise KharSathraError("Khar axis witness epoch cannot be negative")
        for label, value in (
            ("aevra", self.aevra_digest),
            ("veyra", self.veyra_digest),
            ("event", self.event_digest),
            ("reality", self.reality_digest),
            ("witness", self.witness_digest),
        ):
            if not value:
                raise KharSathraError(f"Khar axis witness requires {label} digest")


@dataclass(frozen=True, slots=True)
class Sathra:
    aevra_digest: str
    veyra_digest: str
    event_digest: str
    reality_digest: str
    epoch: int
    axis_witnesses: tuple[tuple[str, str], ...]
    digest: str
    version: int = 1

    def assert_sealed(self) -> None:
        if tuple(axis for axis, _ in self.axis_witnesses) != KHAR_AXES:
            raise KharSathraError("Sathra axis set or canonical order is invalid")
        witness_digests = tuple(digest for _, digest in self.axis_witnesses)
        if len(set(witness_digests)) != len(KHAR_AXES):
            raise KharSathraError("Sathra requires six independent axis witnesses")
        expected = _sathra_digest(
            aevra_digest=self.aevra_digest,
            veyra_digest=self.veyra_digest,
            event_digest=self.event_digest,
            reality_digest=self.reality_digest,
            epoch=self.epoch,
            axis_witnesses=self.axis_witnesses,
        )
        if self.digest != expected:
            raise KharSathraError("Sathra seal mismatch")


def _sathra_digest(
    *,
    aevra_digest: str,
    veyra_digest: str,
    event_digest: str,
    reality_digest: str,
    epoch: int,
    axis_witnesses: tuple[tuple[str, str], ...],
) -> str:
    rows = (
        f"aevra={aevra_digest}",
        f"veyra={veyra_digest}",
        f"event={event_digest}",
        f"reality={reality_digest}",
        f"epoch={epoch}",
        *(f"axis={axis}:{digest}" for axis, digest in axis_witnesses),
    )
    return hashlib.sha256(_CTX + "\n".join(rows).encode("utf-8")).hexdigest()


def _require_same_binding(witnesses: tuple[AxisWitness, ...]) -> None:
    first = witnesses[0]
    bindings = (
        ("Aevra", lambda item: item.aevra_digest),
        ("Veyra", lambda item: item.veyra_digest),
        ("event", lambda item: item.event_digest),
        ("reality", lambda item: item.reality_digest),
        ("epoch", lambda item: item.epoch),
    )
    for label, accessor in bindings:
        expected = accessor(first)
        if any(accessor(item) != expected for item in witnesses[1:]):
            raise KharSathraError(
                f"six Khar axes do not belong to the same {label} binding"
            )


def seal_sathra(witnesses: Iterable[AxisWitness]) -> Sathra:
    """Seal exactly one witness from every Khar axis into one critical event.

    There is intentionally no partial-result type. Missing, duplicated, reused,
    cross-event, cross-Veyra, cross-reality, or cross-epoch witnesses fail closed.
    """

    supplied = tuple(witnesses)
    if len(supplied) != len(KHAR_AXES):
        raise KharSathraError(
            "Sathra requires exactly six Khar axes; partial concurrence is zero"
        )

    by_axis: dict[str, AxisWitness] = {}
    for witness in supplied:
        if witness.axis in by_axis:
            raise KharSathraError(f"duplicate Khar axis witness: {witness.axis}")
        by_axis[witness.axis] = witness

    missing = tuple(axis for axis in KHAR_AXES if axis not in by_axis)
    if missing:
        raise KharSathraError(
            "Sathra missing Khar axes: " + ", ".join(missing)
        )

    ordered = tuple(by_axis[axis] for axis in KHAR_AXES)
    if len({item.witness_digest for item in ordered}) != len(KHAR_AXES):
        raise KharSathraError(
            "one witness cannot satisfy more than one Khar axis"
        )
    _require_same_binding(ordered)

    first = ordered[0]
    axis_witnesses = tuple((item.axis, item.witness_digest) for item in ordered)
    result = Sathra(
        aevra_digest=first.aevra_digest,
        veyra_digest=first.veyra_digest,
        event_digest=first.event_digest,
        reality_digest=first.reality_digest,
        epoch=first.epoch,
        axis_witnesses=axis_witnesses,
        digest="",
    )
    object.__setattr__(
        result,
        "digest",
        _sathra_digest(
            aevra_digest=result.aevra_digest,
            veyra_digest=result.veyra_digest,
            event_digest=result.event_digest,
            reality_digest=result.reality_digest,
            epoch=result.epoch,
            axis_witnesses=result.axis_witnesses,
        ),
    )
    result.assert_sealed()
    return result
