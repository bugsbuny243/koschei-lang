"""Active Lang-only release profile for the native model curriculum.

The underlying executable oracle implementation remains the compatible v2
curriculum format. This profile removes the cancelled Sentinel-merge semantics
from active releases, rejects legacy merged curricula at the training boundary,
and requires additional executable N3/N4 Matrix/Nur hardening cases.
"""
from __future__ import annotations

from dataclasses import replace
import hashlib
import json
from pathlib import Path

from .native_model_curriculum_lang_hardening_v1 import (
    LangCurriculumHardeningError,
    augment_lang_curriculum_v1,
    verify_lang_hardening_cases_v1,
)
from .native_model_curriculum_v2 import (
    NativeCurriculumCaseV2,
    NativeModelCurriculumError,
    NativeModelCurriculumV2,
    build_native_model_curriculum_v2,
    load_native_model_curriculum_v2,
    verify_native_model_curriculum_v2,
    write_native_model_curriculum_v2,
)

ACTIVE_PROFILE = "koschei-lang.native-curriculum-profile.v1"
N6_FAMILY = "lang-defensive-reasoning:current-evidence"
_FORBIDDEN_ACTIVE_FRAGMENTS = (
    "sentinel",
    "historical-security-material",
    "historical or new security material",
    "merged koschei",
    "merged architecture",
)


class LangNativeCurriculumError(NativeModelCurriculumError):
    pass


def _canonical_json(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _rewrite_n6_case(case: NativeCurriculumCaseV2) -> NativeCurriculumCaseV2:
    if case.stage != "N6":
        return case

    if case.case_id == "n6-security-evidence-passes-native-adversarial-gate":
        return replace(
            case,
            family=N6_FAMILY,
            task=(
                "Admit Lang defensive-reasoning evidence only after every current "
                "Lang adversarial suite and anti-shrink minimum passes."
            ),
            law_ids=(
                "lang-defensive-reasoning-requires-current-evidence",
                "security-evidence-before-promotion",
                "native-hard-gates-first",
            ),
        )

    if case.case_id == "n6-missing-security-suite-fails-closed":
        return replace(
            case,
            family=N6_FAMILY,
            task=(
                "Reject Lang defensive-reasoning evidence when any required native "
                "adversarial evidence suite is absent."
            ),
            law_ids=(
                "lang-defensive-reasoning-requires-current-evidence",
                "missing-evidence-is-not-evidence",
            ),
        )

    if case.case_id == "n6-security-suite-shrink-is-rejected":
        return replace(
            case,
            family=N6_FAMILY,
            task=(
                "Reject Lang defensive-reasoning evidence whose suite claims success "
                "while executing fewer attacks than the sealed minimum."
            ),
            law_ids=(
                "attack-suite-shrink-fails-closed",
                "security-evidence-before-promotion",
                "lang-defensive-reasoning-requires-current-evidence",
            ),
        )

    raise LangNativeCurriculumError(f"unknown N6 case in active Lang profile: {case.case_id}")


def _reseal(curriculum: NativeModelCurriculumV2) -> NativeModelCurriculumV2:
    cases = tuple(_rewrite_n6_case(case) for case in curriculum.cases)
    provisional = replace(curriculum, cases=cases, curriculum_sha256="0" * 64)
    payload = provisional.to_dict()
    payload.pop("curriculum_sha256", None)
    digest = hashlib.sha256(_canonical_json(payload).encode("utf-8")).hexdigest()
    return replace(provisional, curriculum_sha256=digest)


def verify_lang_native_model_curriculum_v1(
    curriculum: NativeModelCurriculumV2 | dict[str, object],
) -> NativeModelCurriculumV2:
    """Verify structural seals plus active Lang separation and N3/N4 hardening."""

    verified = verify_native_model_curriculum_v2(curriculum)
    serialized = _canonical_json(verified.to_dict()).lower()
    for fragment in _FORBIDDEN_ACTIVE_FRAGMENTS:
        if fragment in serialized:
            raise LangNativeCurriculumError(
                f"active Lang curriculum contains cancelled Sentinel-merge semantics: {fragment}"
            )

    n6 = tuple(case for case in verified.cases if case.stage == "N6")
    if len(n6) != 3:
        raise LangNativeCurriculumError("active Lang curriculum requires exactly three N6 evidence cases")
    if any(case.family != N6_FAMILY for case in n6):
        raise LangNativeCurriculumError("active N6 curriculum must be Lang defensive reasoning")
    if any("historical" in law.lower() for case in n6 for law in case.law_ids):
        raise LangNativeCurriculumError("active N6 law cannot inherit historical project trust")
    try:
        verify_lang_hardening_cases_v1(verified)
    except LangCurriculumHardeningError as error:
        raise LangNativeCurriculumError(str(error)) from error
    return verified


def build_lang_native_model_curriculum_v1(
    *,
    source_commit: str,
    parent_curriculum_digest: str,
) -> NativeModelCurriculumV2:
    """Build the active Lang-only curriculum without changing oracle compatibility."""

    legacy_shape = build_native_model_curriculum_v2(
        source_commit=source_commit,
        parent_curriculum_digest=parent_curriculum_digest,
    )
    active_profile = _reseal(legacy_shape)
    hardened = augment_lang_curriculum_v1(active_profile)
    return verify_lang_native_model_curriculum_v1(hardened)


def load_lang_native_model_curriculum_v1(path: str | Path) -> NativeModelCurriculumV2:
    return verify_lang_native_model_curriculum_v1(load_native_model_curriculum_v2(path))


def write_lang_native_model_curriculum_v1(
    curriculum: NativeModelCurriculumV2,
    output: str | Path,
) -> None:
    write_native_model_curriculum_v2(verify_lang_native_model_curriculum_v1(curriculum), output)
