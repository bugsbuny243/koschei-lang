"""Oracle-backed Koschei native-intelligence curriculum v2.

The older model curriculum teaches the legacy/general language and capability
surface.  This v2 curriculum is the first deterministic dataset slice for the
merged Koschei Lang native-intelligence plane.  Labels come from real parser,
typed-semantics, sealed-MIR and Khar/Sathra code paths rather than handwritten
claims about what Koschei is supposed to do.

V2 intentionally starts small.  A tiny verified curriculum is preferable to a
large synthetic corpus whose labels drift away from executable language physics.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
import json
import string
from typing import Callable

from .khar_sathra_v1 import AxisWitness, KHAR_AXES, seal_sathra
from .native_sigil_mir_v1 import lower_native_sigils
from .native_sigil_semantics_v1 import check_native_sigils
from .parser import Parser

SCHEMA_VERSION = "koschei.native-intelligence-curriculum.v2"
GENERATOR_VERSION = "koschei-native-intelligence-oracle/v2"
SOURCE_REPOSITORY = "bugsbuny243/koschei-lang"
STAGES = ("N0", "N1", "N2", "N3", "N4", "N5", "N6")
OUTCOMES = ("ACCEPTED", "REJECTED")
_CTX = b"koschei.native-model-curriculum/v2\x00"
_HEX = frozenset(string.hexdigits.lower())


class NativeModelCurriculumError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class NativeCurriculumCaseV2:
    case_id: str
    stage: str
    family: str
    task: str
    input_text: str
    outcome: str
    oracle: str
    oracle_digest: str
    target_text: str
    law_ids: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class NativeModelCurriculumV2:
    schema_version: str
    generator_version: str
    source_repository: str
    source_commit: str
    parent_curriculum_digest: str
    case_count: int
    stage_counts: dict[str, int]
    accepted_count: int
    rejected_count: int
    curriculum_sha256: str
    cases: tuple[NativeCurriculumCaseV2, ...]

    def to_dict(self) -> dict[str, object]:
        return json.loads(_canonical_json(asdict(self)))


def _canonical_json(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _digest(kind: str, payload: object) -> str:
    return hashlib.sha256(
        _CTX + kind.encode("ascii") + b"\x00" + _canonical_json(payload).encode("utf-8")
    ).hexdigest()


def _require_hex(value: str, length: int, label: str) -> str:
    if not isinstance(value, str) or len(value) != length:
        raise NativeModelCurriculumError(f"{label} must be {length} hexadecimal characters")
    lowered = value.lower()
    if any(ch not in _HEX for ch in lowered) or lowered == "0" * length:
        raise NativeModelCurriculumError(f"{label} must be a non-zero hexadecimal value")
    return lowered


def _accepted_native_source(
    case_id: str,
    *,
    source: str,
    task: str,
    laws: tuple[str, ...],
) -> NativeCurriculumCaseV2:
    program = Parser.from_source(source).parse()
    semantic = check_native_sigils(program)
    mir = lower_native_sigils(program, semantic)
    target = {
        "decision": "ACCEPTED",
        "sigils": [item.sigil for item in semantic.declarations],
        "domains": [item.semantic_domain for item in semantic.declarations],
        "universe_plan_digest": semantic.universe_plan_digest,
        "typed_semantic_digest": semantic.digest,
        "native_mir_fingerprint": mir.fingerprint,
        "authority_may_exist_only_where_declared": True,
    }
    return NativeCurriculumCaseV2(
        case_id=case_id,
        stage="N0",
        family="native-language:compiler-oracle",
        task=task,
        input_text=source,
        outcome="ACCEPTED",
        oracle="parser->native-semantics->sealed-mir",
        oracle_digest=_digest("native-accepted", target),
        target_text=_canonical_json(target),
        law_ids=laws,
    )


def _rejected_native_source(
    case_id: str,
    *,
    source: str,
    task: str,
    expected_fragment: str,
    laws: tuple[str, ...],
) -> NativeCurriculumCaseV2:
    try:
        program = Parser.from_source(source).parse()
        semantic = check_native_sigils(program)
        lower_native_sigils(program, semantic)
    except ValueError as error:
        message = str(error)
        if expected_fragment not in message:
            raise NativeModelCurriculumError(
                f"native oracle drift for {case_id}: expected {expected_fragment!r}, got {message!r}"
            ) from error
        target = {"decision": "REJECTED", "reason": message}
        return NativeCurriculumCaseV2(
            case_id=case_id,
            stage="N0",
            family="native-language:compiler-oracle",
            task=task,
            input_text=source,
            outcome="REJECTED",
            oracle="parser->native-semantics->sealed-mir",
            oracle_digest=_digest("native-rejected", target),
            target_text=_canonical_json(target),
            law_ids=laws,
        )
    raise NativeModelCurriculumError(f"native oracle drift for {case_id}: invalid case was accepted")


def _axis_witnesses(*, veyra: str = "veyra-a") -> tuple[AxisWitness, ...]:
    return tuple(
        AxisWitness(
            axis=axis,
            aevra_digest="aevra-a",
            veyra_digest=veyra,
            event_digest="event-a",
            reality_digest="reality-a",
            epoch=7,
            witness_digest=f"witness-{axis}",
        )
        for axis in KHAR_AXES
    )


def _accepted_sathra_case() -> NativeCurriculumCaseV2:
    witnesses = _axis_witnesses()
    sathra = seal_sathra(witnesses)
    target = {
        "decision": "ACCEPTED",
        "result": "SATHRA",
        "axis_count": 6,
        "partial_authority": 0,
        "sathra_digest": sathra.digest,
    }
    return NativeCurriculumCaseV2(
        case_id="n2-six-of-six-same-event",
        stage="N2",
        family="khar:six-axis-concurrence",
        task="Recognize that exactly six independent Khar axes bound to one event may form Sathra.",
        input_text=_canonical_json([asdict(item) for item in witnesses]),
        outcome="ACCEPTED",
        oracle="khar_sathra_v1.seal_sathra",
        oracle_digest=_digest("sathra-accepted", target),
        target_text=_canonical_json(target),
        law_ids=("khar-six-axis-concurrence", "sathra-one-event"),
    )


def _rejected_sathra_case(
    case_id: str,
    *,
    witnesses: tuple[AxisWitness, ...],
    task: str,
    expected_fragment: str,
    laws: tuple[str, ...],
) -> NativeCurriculumCaseV2:
    try:
        seal_sathra(witnesses)
    except ValueError as error:
        message = str(error)
        if expected_fragment not in message:
            raise NativeModelCurriculumError(
                f"Sathra oracle drift for {case_id}: expected {expected_fragment!r}, got {message!r}"
            ) from error
        target = {
            "decision": "REJECTED",
            "result": "ZERO",
            "reason": message,
            "partial_authority": 0,
        }
        return NativeCurriculumCaseV2(
            case_id=case_id,
            stage="N2",
            family="khar:six-axis-concurrence",
            task=task,
            input_text=_canonical_json([asdict(item) for item in witnesses]),
            outcome="REJECTED",
            oracle="khar_sathra_v1.seal_sathra",
            oracle_digest=_digest("sathra-rejected", target),
            target_text=_canonical_json(target),
            law_ids=laws,
        )
    raise NativeModelCurriculumError(f"Sathra oracle drift for {case_id}: invalid case was accepted")


def _materialize_cases() -> tuple[NativeCurriculumCaseV2, ...]:
    canonical_source = (
        "ka treasury;\n"
        "vor withdrawal;\n"
        "shi evidence;\n"
        "thal recovery;\n"
        "nur visibility;\n"
    )
    full = _axis_witnesses()
    cross_veyra = list(full)
    cross_veyra[-1] = AxisWitness(
        axis=cross_veyra[-1].axis,
        aevra_digest=cross_veyra[-1].aevra_digest,
        veyra_digest="veyra-b",
        event_digest=cross_veyra[-1].event_digest,
        reality_digest=cross_veyra[-1].reality_digest,
        epoch=cross_veyra[-1].epoch,
        witness_digest=cross_veyra[-1].witness_digest,
    )
    reused = list(full)
    reused[-1] = AxisWitness(
        axis=reused[-1].axis,
        aevra_digest=reused[-1].aevra_digest,
        veyra_digest=reused[-1].veyra_digest,
        event_digest=reused[-1].event_digest,
        reality_digest=reused[-1].reality_digest,
        epoch=reused[-1].epoch,
        witness_digest=reused[0].witness_digest,
    )
    return (
        _accepted_native_source(
            "n0-five-native-sigils",
            source=canonical_source,
            task="Compile the five native Koschei semantic roots into typed semantics and sealed MIR.",
            laws=("native-sigils-are-semantic-roots", "ka-genesis-first"),
        ),
        _rejected_native_source(
            "n0-ka-not-first",
            source="vor withdrawal;\nka treasury;\n",
            task="Reject a multi-sigil Universe that places ka after another semantic root.",
            expected_fragment="ka is the genesis boundary and must be first",
            laws=("ka-genesis-first",),
        ),
        _rejected_native_source(
            "n0-duplicate-sigil",
            source="ka first;\nvor one;\nvor two;\n",
            task="Reject repeated sigil roots instead of interpreting repetition as more authority.",
            expected_fragment="duplicate sigils are not canonical",
            laws=("no-authority-by-repetition",),
        ),
        _accepted_sathra_case(),
        _rejected_sathra_case(
            "n2-five-of-six-is-zero",
            witnesses=full[:-1],
            task="Reject five of six Khar axes as zero critical authority, not partial success.",
            expected_fragment="exactly six Khar axes; partial concurrence is zero",
            laws=("five-of-six-is-zero",),
        ),
        _rejected_sathra_case(
            "n2-cross-veyra-fragments-are-zero",
            witnesses=tuple(cross_veyra),
            task="Reject six witnesses assembled across different customer Veyras.",
            expected_fragment="same Veyra binding",
            laws=("same-veyra-concurrence", "cross-customer-non-transfer"),
        ),
        _rejected_sathra_case(
            "n2-one-witness-cannot-be-two-axes",
            witnesses=tuple(reused),
            task="Reject reusing one witness digest to satisfy two Khar axes.",
            expected_fragment="one witness cannot satisfy more than one Khar axis",
            laws=("axis-independence", "six-distinct-witnesses"),
        ),
    )


def build_native_model_curriculum_v2(
    *,
    source_commit: str,
    parent_curriculum_digest: str,
) -> NativeModelCurriculumV2:
    """Build the deterministic N0/N2 first slice from executable Koschei oracles."""

    source = _require_hex(source_commit, 40, "source_commit")
    parent = _require_hex(parent_curriculum_digest, 64, "parent_curriculum_digest")
    cases = _materialize_cases()
    stage_counts = {stage: 0 for stage in STAGES}
    accepted = 0
    rejected = 0
    for case in cases:
        if case.stage not in STAGES:
            raise NativeModelCurriculumError(f"unsupported native curriculum stage: {case.stage}")
        if case.outcome not in OUTCOMES:
            raise NativeModelCurriculumError(f"unsupported native curriculum outcome: {case.outcome}")
        stage_counts[case.stage] += 1
        accepted += case.outcome == "ACCEPTED"
        rejected += case.outcome == "REJECTED"

    payload = {
        "schema_version": SCHEMA_VERSION,
        "generator_version": GENERATOR_VERSION,
        "source_repository": SOURCE_REPOSITORY,
        "source_commit": source,
        "parent_curriculum_digest": parent,
        "case_count": len(cases),
        "stage_counts": stage_counts,
        "accepted_count": accepted,
        "rejected_count": rejected,
        "cases": [asdict(case) for case in cases],
    }
    curriculum_digest = hashlib.sha256(_canonical_json(payload).encode("utf-8")).hexdigest()
    return NativeModelCurriculumV2(
        schema_version=SCHEMA_VERSION,
        generator_version=GENERATOR_VERSION,
        source_repository=SOURCE_REPOSITORY,
        source_commit=source,
        parent_curriculum_digest=parent,
        case_count=len(cases),
        stage_counts=stage_counts,
        accepted_count=accepted,
        rejected_count=rejected,
        curriculum_sha256=curriculum_digest,
        cases=cases,
    )
