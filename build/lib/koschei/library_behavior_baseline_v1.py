"""Koschei Library Behavior Baseline v1.

Turns library observations into a deterministic behavioral baseline suitable for
Sentinel prediction. The baseline is descriptive, never authoritative: it records
what a third-party artifact normally does, then detects deviations before those
deviations can be treated as ordinary behavior.

Core laws:
- a baseline cannot grant effects;
- newly observed effects are authority deltas, not auto-learning events;
- target expansion is explicit and evidence-producing;
- resource drift is measured against bounded learned ceilings;
- artifact/revision/epoch changes invalidate baseline reuse.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
from typing import Iterable

from .library_boundary_v1 import (
    LibraryObservationV1,
    LibraryPrecursorFactV1,
    ResourceBudgetV1,
)

_CONTEXT = b"koschei.library-behavior-baseline/v1\x00"
_MAX_EFFECTS = 32
_MAX_TARGETS_PER_EFFECT = 256


class LibraryBehaviorBaselineError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class EffectBaselineV1:
    effect: str
    targets: frozenset[bytes]
    cpu_ceiling: int
    memory_ceiling: int
    input_ceiling: int
    nesting_ceiling: int


@dataclass(frozen=True, slots=True)
class LibraryBehaviorBaselineV1:
    artifact_digest: bytes
    revision_digest: bytes
    epoch: int
    effects: tuple[EffectBaselineV1, ...]
    baseline_digest: bytes


@dataclass(frozen=True, slots=True)
class LibraryBehaviorDeltaV1:
    kind: str
    effect: str
    observation_digest: bytes
    baseline_digest: bytes
    delta_digest: bytes


@dataclass(frozen=True, slots=True)
class LibraryBehaviorAssessmentV1:
    conforming: bool
    delta: LibraryBehaviorDeltaV1 | None
    precursor: LibraryPrecursorFactV1 | None


def _fail(message: str) -> None:
    raise LibraryBehaviorBaselineError(message)


def _d32(value: bytes, label: str) -> bytes:
    if not isinstance(value, bytes) or len(value) != 32:
        _fail(f"{label} must be exactly 32 bytes")
    return value


def _obs_digest(obs: LibraryObservationV1) -> bytes:
    if not isinstance(obs, LibraryObservationV1):
        _fail("canonical LibraryObservationV1 required")
    target = obs.target_digest or (b"\x00" * 32)
    payload = b"\x00".join((
        obs.artifact_digest,
        obs.effect.encode("ascii"),
        obs.cpu_units.to_bytes(8, "big"),
        obs.memory_bytes.to_bytes(8, "big"),
        obs.input_bytes.to_bytes(8, "big"),
        obs.nesting.to_bytes(4, "big"),
        target,
    ))
    return hashlib.sha3_256(_CONTEXT + b"observation\x00" + payload).digest()


def _effect_digest(item: EffectBaselineV1) -> bytes:
    payload = [
        item.effect.encode("ascii"),
        item.cpu_ceiling.to_bytes(8, "big"),
        item.memory_ceiling.to_bytes(8, "big"),
        item.input_ceiling.to_bytes(8, "big"),
        item.nesting_ceiling.to_bytes(4, "big"),
    ]
    payload.extend(sorted(item.targets))
    return hashlib.sha3_256(_CONTEXT + b"effect\x00" + b"\x00".join(payload)).digest()


def derive_library_behavior_baseline_v1(*, artifact_digest: bytes,
    revision_digest: bytes, epoch: int, observations: Iterable[LibraryObservationV1],
    hard_budget: ResourceBudgetV1) -> LibraryBehaviorBaselineV1:
    artifact = _d32(artifact_digest, "artifact digest")
    revision = _d32(revision_digest, "revision digest")
    if not isinstance(epoch, int) or isinstance(epoch, bool) or epoch < 1:
        _fail("epoch must be positive")
    if not isinstance(hard_budget, ResourceBudgetV1):
        _fail("canonical hard budget required")

    grouped: dict[str, list[LibraryObservationV1]] = {}
    count = 0
    for obs in observations:
        if not isinstance(obs, LibraryObservationV1):
            _fail("baseline observations must be canonical")
        if obs.artifact_digest != artifact:
            _fail("baseline cannot mix artifact identities")
        grouped.setdefault(obs.effect, []).append(obs)
        count += 1
    if count == 0:
        _fail("baseline requires at least one observation")
    if len(grouped) > _MAX_EFFECTS:
        _fail("baseline effect cardinality exceeds v1 bound")

    effects: list[EffectBaselineV1] = []
    for effect in sorted(grouped):
        rows = grouped[effect]
        targets = frozenset(r.target_digest for r in rows if r.target_digest is not None)
        if len(targets) > _MAX_TARGETS_PER_EFFECT:
            _fail("baseline target cardinality exceeds v1 bound")
        cpu = max(r.cpu_units for r in rows)
        memory = max(r.memory_bytes for r in rows)
        input_bytes = max(r.input_bytes for r in rows)
        nesting = max(r.nesting for r in rows)
        if cpu > hard_budget.cpu_units or memory > hard_budget.memory_bytes:
            _fail("baseline observation exceeds hard resource budget")
        if input_bytes > hard_budget.input_bytes or nesting > hard_budget.nesting:
            _fail("baseline observation exceeds hard parser budget")
        effects.append(EffectBaselineV1(effect, targets, cpu, memory, input_bytes, nesting))

    payload = [artifact, revision, epoch.to_bytes(8, "big")]
    payload.extend(_effect_digest(item) for item in effects)
    digest = hashlib.sha3_256(_CONTEXT + b"baseline\x00" + b"\x00".join(payload)).digest()
    return LibraryBehaviorBaselineV1(artifact, revision, epoch, tuple(effects), digest)


def assess_library_behavior_v1(baseline: LibraryBehaviorBaselineV1,
    observation: LibraryObservationV1) -> LibraryBehaviorAssessmentV1:
    if not isinstance(baseline, LibraryBehaviorBaselineV1):
        _fail("canonical LibraryBehaviorBaselineV1 required")
    if not isinstance(observation, LibraryObservationV1):
        _fail("canonical LibraryObservationV1 required")
    obs_digest = _obs_digest(observation)
    if observation.artifact_digest != baseline.artifact_digest:
        kind = "artifact-identity-drift"
    else:
        by_effect = {item.effect: item for item in baseline.effects}
        item = by_effect.get(observation.effect)
        if item is None:
            kind = "new-effect"
        elif observation.target_digest is not None and observation.target_digest not in item.targets:
            kind = "target-expansion"
        elif observation.cpu_units > item.cpu_ceiling:
            kind = "cpu-drift"
        elif observation.memory_bytes > item.memory_ceiling:
            kind = "memory-drift"
        elif observation.input_bytes > item.input_ceiling:
            kind = "input-drift"
        elif observation.nesting > item.nesting_ceiling:
            kind = "nesting-drift"
        else:
            return LibraryBehaviorAssessmentV1(True, None, None)

    payload = b"\x00".join((baseline.baseline_digest, obs_digest,
        observation.effect.encode("ascii"), kind.encode("ascii")))
    delta_digest = hashlib.sha3_256(_CONTEXT + b"delta\x00" + payload).digest()
    delta = LibraryBehaviorDeltaV1(kind, observation.effect, obs_digest,
        baseline.baseline_digest, delta_digest)
    precursor = LibraryPrecursorFactV1(observation.artifact_digest,
        observation.effect, f"behavior-{kind}", obs_digest)
    return LibraryBehaviorAssessmentV1(False, delta, precursor)
