"""Oracle-backed Koschei native-intelligence curriculum v2.

The older model curriculum teaches the legacy/general language and capability
surface. This v2 curriculum is the first deterministic dataset slice for the
merged Koschei Lang native-intelligence plane. Labels come from real parser,
typed-semantics, sealed-MIR and Khar/Sathra code paths rather than handwritten
claims about what Koschei is supposed to do.

V2 intentionally starts small. A tiny verified curriculum is preferable to a
large synthetic corpus whose labels drift away from executable language physics.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
import json
import os
from pathlib import Path
import string
import tempfile
from typing import Any

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


def _require_text(value: object, label: str) -> str:
    if not isinstance(value, str) or not value or "\x00" in value:
        raise NativeModelCurriculumError(f"{label} must be non-empty text")
    return value


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


def _payload_without_digest(curriculum: NativeModelCurriculumV2) -> dict[str, object]:
    return {
        "schema_version": curriculum.schema_version,
        "generator_version": curriculum.generator_version,
        "source_repository": curriculum.source_repository,
        "source_commit": curriculum.source_commit,
        "parent_curriculum_digest": curriculum.parent_curriculum_digest,
        "case_count": curriculum.case_count,
        "stage_counts": curriculum.stage_counts,
        "accepted_count": curriculum.accepted_count,
        "rejected_count": curriculum.rejected_count,
        "cases": [asdict(case) for case in curriculum.cases],
    }


def verify_native_model_curriculum_v2(
    value: NativeModelCurriculumV2 | dict[str, Any],
) -> NativeModelCurriculumV2:
    """Verify a released v2 curriculum without trusting its summary fields."""

    if isinstance(value, NativeModelCurriculumV2):
        curriculum = value
    else:
        if not isinstance(value, dict):
            raise NativeModelCurriculumError("native curriculum must be an object")
        raw_cases = value.get("cases")
        if not isinstance(raw_cases, list):
            raise NativeModelCurriculumError("native curriculum cases must be a list")
        cases: list[NativeCurriculumCaseV2] = []
        for raw in raw_cases:
            if not isinstance(raw, dict):
                raise NativeModelCurriculumError("native curriculum case must be an object")
            law_ids = raw.get("law_ids")
            if not isinstance(law_ids, list) or not all(isinstance(item, str) and item for item in law_ids):
                raise NativeModelCurriculumError("native curriculum law_ids must be non-empty strings")
            cases.append(
                NativeCurriculumCaseV2(
                    case_id=_require_text(raw.get("case_id"), "case_id"),
                    stage=_require_text(raw.get("stage"), "stage"),
                    family=_require_text(raw.get("family"), "family"),
                    task=_require_text(raw.get("task"), "task"),
                    input_text=_require_text(raw.get("input_text"), "input_text"),
                    outcome=_require_text(raw.get("outcome"), "outcome"),
                    oracle=_require_text(raw.get("oracle"), "oracle"),
                    oracle_digest=_require_hex(str(raw.get("oracle_digest", "")), 64, "oracle_digest"),
                    target_text=_require_text(raw.get("target_text"), "target_text"),
                    law_ids=tuple(law_ids),
                )
            )
        stage_counts = value.get("stage_counts")
        if not isinstance(stage_counts, dict):
            raise NativeModelCurriculumError("native curriculum stage_counts must be an object")
        curriculum = NativeModelCurriculumV2(
            schema_version=_require_text(value.get("schema_version"), "schema_version"),
            generator_version=_require_text(value.get("generator_version"), "generator_version"),
            source_repository=_require_text(value.get("source_repository"), "source_repository"),
            source_commit=_require_text(value.get("source_commit"), "source_commit"),
            parent_curriculum_digest=_require_text(
                value.get("parent_curriculum_digest"), "parent_curriculum_digest"
            ),
            case_count=int(value.get("case_count", -1)),
            stage_counts={str(k): int(v) for k, v in stage_counts.items()},
            accepted_count=int(value.get("accepted_count", -1)),
            rejected_count=int(value.get("rejected_count", -1)),
            curriculum_sha256=_require_text(value.get("curriculum_sha256"), "curriculum_sha256"),
            cases=tuple(cases),
        )

    if curriculum.schema_version != SCHEMA_VERSION:
        raise NativeModelCurriculumError("unsupported native curriculum schema")
    if curriculum.generator_version != GENERATOR_VERSION:
        raise NativeModelCurriculumError("unsupported native curriculum generator")
    if curriculum.source_repository != SOURCE_REPOSITORY:
        raise NativeModelCurriculumError("native curriculum source repository mismatch")
    _require_hex(curriculum.source_commit, 40, "source_commit")
    _require_hex(curriculum.parent_curriculum_digest, 64, "parent_curriculum_digest")
    _require_hex(curriculum.curriculum_sha256, 64, "curriculum_sha256")
    if not curriculum.cases:
        raise NativeModelCurriculumError("native curriculum must contain cases")

    ids: set[str] = set()
    stage_counts = {stage: 0 for stage in STAGES}
    accepted = 0
    rejected = 0
    for case in curriculum.cases:
        if not case.case_id or case.case_id in ids:
            raise NativeModelCurriculumError("native curriculum case IDs must be unique and non-empty")
        ids.add(case.case_id)
        if case.stage not in STAGES:
            raise NativeModelCurriculumError(f"unsupported native curriculum stage: {case.stage}")
        if case.outcome not in OUTCOMES:
            raise NativeModelCurriculumError(f"unsupported native curriculum outcome: {case.outcome}")
        _require_hex(case.oracle_digest, 64, f"oracle_digest:{case.case_id}")
        if not case.law_ids:
            raise NativeModelCurriculumError(f"native curriculum case has no law IDs: {case.case_id}")
        stage_counts[case.stage] += 1
        if case.outcome == "ACCEPTED":
            accepted += 1
        else:
            rejected += 1

    if curriculum.case_count != len(curriculum.cases):
        raise NativeModelCurriculumError("native curriculum case_count mismatch")
    if curriculum.stage_counts != stage_counts:
        raise NativeModelCurriculumError("native curriculum stage_counts mismatch")
    if curriculum.accepted_count != accepted or curriculum.rejected_count != rejected:
        raise NativeModelCurriculumError("native curriculum outcome counts mismatch")
    expected_digest = hashlib.sha256(
        _canonical_json(_payload_without_digest(curriculum)).encode("utf-8")
    ).hexdigest()
    if curriculum.curriculum_sha256 != expected_digest:
        raise NativeModelCurriculumError("native curriculum digest mismatch")
    return curriculum


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
        stage_counts[case.stage] += 1
        if case.outcome == "ACCEPTED":
            accepted += 1
        else:
            rejected += 1

    provisional = NativeModelCurriculumV2(
        schema_version=SCHEMA_VERSION,
        generator_version=GENERATOR_VERSION,
        source_repository=SOURCE_REPOSITORY,
        source_commit=source,
        parent_curriculum_digest=parent,
        case_count=len(cases),
        stage_counts=stage_counts,
        accepted_count=accepted,
        rejected_count=rejected,
        curriculum_sha256="0" * 64,
        cases=cases,
    )
    digest = hashlib.sha256(
        _canonical_json(_payload_without_digest(provisional)).encode("utf-8")
    ).hexdigest()
    result = NativeModelCurriculumV2(
        schema_version=provisional.schema_version,
        generator_version=provisional.generator_version,
        source_repository=provisional.source_repository,
        source_commit=provisional.source_commit,
        parent_curriculum_digest=provisional.parent_curriculum_digest,
        case_count=provisional.case_count,
        stage_counts=provisional.stage_counts,
        accepted_count=provisional.accepted_count,
        rejected_count=provisional.rejected_count,
        curriculum_sha256=digest,
        cases=provisional.cases,
    )
    return verify_native_model_curriculum_v2(result)


def write_native_model_curriculum_v2(
    curriculum: NativeModelCurriculumV2,
    output: str | Path,
) -> None:
    """Atomically write one verified curriculum release without overwriting."""

    verified = verify_native_model_curriculum_v2(curriculum)
    path = Path(output)
    if path.exists():
        raise FileExistsError(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=path.name + ".", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(verified.to_dict(), handle, ensure_ascii=False, sort_keys=True, indent=2)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    except BaseException:
        try:
            os.unlink(temporary)
        except FileNotFoundError:
            pass
        raise


def load_native_model_curriculum_v2(path: str | Path) -> NativeModelCurriculumV2:
    """Load and verify a curriculum release before it can enter training."""

    try:
        raw = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise NativeModelCurriculumError(f"cannot load native curriculum: {error}") from error
    return verify_native_model_curriculum_v2(raw)
