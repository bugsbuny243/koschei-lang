"""Koschei Library Boundary v1.

This module turns the threat-atlas laws into an executable containment contract for
third-party libraries, models, plugins, generated code and other imported
artifacts.

Core law: imported data/code receives ZERO ambient authority. Every effect is an
explicit, exact, artifact-bound grant. Observed behavior outside that envelope is
not merely logged: admission fails closed and produces a precursor fact suitable
for Sentinel/evidence processing.

This is intentionally generic. React, OpenSSL, PyTorch, npm packages, Web3 SDKs,
GPU/JIT backends and future quantum adapters can all be represented by the same
boundary without teaching the language their brand names.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
from typing import FrozenSet, Literal

Effect = Literal[
    "compute", "decode", "network", "persist", "process", "secret",
    "sign", "device", "ffi", "compile", "telemetry",
]

_ALLOWED_EFFECTS: FrozenSet[str] = frozenset({
    "compute", "decode", "network", "persist", "process", "secret",
    "sign", "device", "ffi", "compile", "telemetry",
})
_CONTEXT = b"koschei.library-boundary/v1\x00"
MAX_CPU_UNITS_V1 = 1_000_000
MAX_MEMORY_BYTES_V1 = 1 << 30
MAX_INPUT_BYTES_V1 = 1 << 30


class LibraryBoundaryError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class ResourceBudgetV1:
    cpu_units: int
    memory_bytes: int
    input_bytes: int
    nesting: int


@dataclass(frozen=True, slots=True)
class LibraryAuthorityEnvelopeV1:
    artifact_digest: bytes
    revision_digest: bytes
    effects: FrozenSet[str]
    budget: ResourceBudgetV1
    epoch: int
    envelope_digest: bytes

    def __repr__(self) -> str:
        return (
            "LibraryAuthorityEnvelopeV1(artifact=<committed>, revision=<committed>, "
            f"effects={sorted(self.effects)!r}, budget=<bounded>, epoch={self.epoch}, "
            "envelope=<committed>)"
        )


@dataclass(frozen=True, slots=True)
class LibraryObservationV1:
    artifact_digest: bytes
    effect: Effect
    cpu_units: int
    memory_bytes: int
    input_bytes: int
    nesting: int
    target_digest: bytes | None = None


@dataclass(frozen=True, slots=True)
class LibraryPrecursorFactV1:
    artifact_digest: bytes
    effect: str
    reason: str
    observation_digest: bytes


@dataclass(frozen=True, slots=True)
class LibraryAdmissionV1:
    admitted: bool
    observation_digest: bytes
    precursor: LibraryPrecursorFactV1 | None


def _fail(message: str) -> None:
    raise LibraryBoundaryError(message)


def _d32(value: bytes, label: str) -> bytes:
    if not isinstance(value, bytes) or len(value) != 32:
        _fail(f"{label} must be exactly 32 bytes")
    return value


def _nonnegative(value: int, label: str, maximum: int) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value < 0 or value > maximum:
        _fail(f"{label} outside canonical bound")
    return value


def make_resource_budget_v1(*, cpu_units: int, memory_bytes: int,
    input_bytes: int, nesting: int) -> ResourceBudgetV1:
    return ResourceBudgetV1(
        _nonnegative(cpu_units, "cpu_units", MAX_CPU_UNITS_V1),
        _nonnegative(memory_bytes, "memory_bytes", MAX_MEMORY_BYTES_V1),
        _nonnegative(input_bytes, "input_bytes", MAX_INPUT_BYTES_V1),
        _nonnegative(nesting, "nesting", 4096),
    )


def seal_library_authority_envelope_v1(*, artifact_digest: bytes,
    revision_digest: bytes, effects: FrozenSet[str], budget: ResourceBudgetV1,
    epoch: int) -> LibraryAuthorityEnvelopeV1:
    artifact = _d32(artifact_digest, "artifact digest")
    revision = _d32(revision_digest, "revision digest")
    if not isinstance(effects, frozenset) or not effects.issubset(_ALLOWED_EFFECTS):
        _fail("effects must be a canonical frozenset of known effect classes")
    if not isinstance(budget, ResourceBudgetV1):
        _fail("canonical resource budget required")
    if not isinstance(epoch, int) or isinstance(epoch, bool) or epoch < 1:
        _fail("epoch must be positive")
    # Empty effects is valid and is the zero-ambient default.
    effect_bytes = b",".join(sorted(e.encode("ascii") for e in effects))
    payload = b"\x00".join((
        artifact, revision, effect_bytes,
        budget.cpu_units.to_bytes(8, "big"),
        budget.memory_bytes.to_bytes(8, "big"),
        budget.input_bytes.to_bytes(8, "big"),
        budget.nesting.to_bytes(4, "big"),
        epoch.to_bytes(8, "big"),
    ))
    digest = hashlib.sha3_256(_CONTEXT + b"envelope\x00" + payload).digest()
    return LibraryAuthorityEnvelopeV1(artifact, revision, frozenset(effects), budget, epoch, digest)


def observe_library_effect_v1(*, artifact_digest: bytes, effect: Effect,
    cpu_units: int = 0, memory_bytes: int = 0, input_bytes: int = 0,
    nesting: int = 0, target_digest: bytes | None = None) -> LibraryObservationV1:
    artifact = _d32(artifact_digest, "artifact digest")
    if effect not in _ALLOWED_EFFECTS:
        _fail("unknown effect class")
    target = None if target_digest is None else _d32(target_digest, "target digest")
    return LibraryObservationV1(
        artifact, effect,
        _nonnegative(cpu_units, "cpu_units", MAX_CPU_UNITS_V1),
        _nonnegative(memory_bytes, "memory_bytes", MAX_MEMORY_BYTES_V1),
        _nonnegative(input_bytes, "input_bytes", MAX_INPUT_BYTES_V1),
        _nonnegative(nesting, "nesting", 4096),
        target,
    )


def _observation_digest(obs: LibraryObservationV1) -> bytes:
    target = obs.target_digest or (b"\x00" * 32)
    payload = b"\x00".join((
        obs.artifact_digest, obs.effect.encode("ascii"),
        obs.cpu_units.to_bytes(8, "big"), obs.memory_bytes.to_bytes(8, "big"),
        obs.input_bytes.to_bytes(8, "big"), obs.nesting.to_bytes(4, "big"), target,
    ))
    return hashlib.sha3_256(_CONTEXT + b"observation\x00" + payload).digest()


def _precursor(obs: LibraryObservationV1, reason: str, digest: bytes) -> LibraryAdmissionV1:
    fact = LibraryPrecursorFactV1(obs.artifact_digest, obs.effect, reason, digest)
    return LibraryAdmissionV1(False, digest, fact)


def admit_library_observation_v1(envelope: LibraryAuthorityEnvelopeV1,
    observation: LibraryObservationV1) -> LibraryAdmissionV1:
    if not isinstance(envelope, LibraryAuthorityEnvelopeV1):
        _fail("canonical library authority envelope required")
    if not isinstance(observation, LibraryObservationV1):
        _fail("canonical library observation required")
    digest = _observation_digest(observation)
    if observation.artifact_digest != envelope.artifact_digest:
        return _precursor(observation, "artifact-substitution", digest)
    if observation.effect not in envelope.effects:
        return _precursor(observation, "authority-expansion", digest)
    budget = envelope.budget
    if observation.cpu_units > budget.cpu_units:
        return _precursor(observation, "cpu-budget-exceeded", digest)
    if observation.memory_bytes > budget.memory_bytes:
        return _precursor(observation, "memory-budget-exceeded", digest)
    if observation.input_bytes > budget.input_bytes:
        return _precursor(observation, "input-budget-exceeded", digest)
    if observation.nesting > budget.nesting:
        return _precursor(observation, "nesting-budget-exceeded", digest)
    # Authority-bearing effects require an exact target commitment. This blocks a
    # broad 'network/process/sign' grant from becoming ambient authority.
    if observation.effect in {"network", "persist", "process", "secret", "sign", "device", "ffi"}:
        if observation.target_digest is None:
            return _precursor(observation, "missing-exact-target", digest)
    return LibraryAdmissionV1(True, digest, None)
