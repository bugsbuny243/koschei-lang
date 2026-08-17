"""Deterministic compiler-oracle curriculum for models learning Koschei.

The curriculum is intentionally small in v1. Its job is to establish the
trustworthy contract: every label comes from the pinned Koschei compiler, every
source byte is hashed, capability manifests are derived mechanically, and a
compiler disagreement aborts the build instead of publishing a guessed label.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import tempfile
from dataclasses import asdict, dataclass
from pathlib import Path, PurePosixPath
from typing import Any

from . import __version__
from .capabilities import analyze_graph, to_dict as manifest_to_dict
from .diagnostics import diagnostic_payload, lookup
from .foundation_export import build_foundation_corpus
from .modules import check_graph, load_graph

SCHEMA_VERSION = "koschei.model-oracle-curriculum.v1"
GENERATOR_VERSION = "koschei-model-oracle/v1"
SOURCE_REPOSITORY = "bugsbuny243/koschei-lang"
LEVELS = ("L0", "L1", "L2", "L3", "L4")
OUTCOMES = ("ACCEPTED", "REJECTED")


class ModelCurriculumError(ValueError):
    """Raised when an authoritative curriculum cannot be built or verified."""


@dataclass(frozen=True, slots=True)
class CurriculumSourceFile:
    path: str
    source_sha256: str
    text: str


@dataclass(frozen=True, slots=True)
class CurriculumCase:
    case_id: str
    family: str
    level: str
    task: str
    entry_path: str
    outcome: str
    diagnostic_code: str | None
    diagnostic_title: str | None
    capability_manifest: dict[str, Any] | None
    files: tuple[CurriculumSourceFile, ...]


@dataclass(frozen=True, slots=True)
class ModelCurriculum:
    schema_version: str
    generator_version: str
    source_repository: str
    source_commit: str
    compiler_version: str
    foundation_corpus_sha256: str
    case_count: int
    family_count: int
    accepted_count: int
    rejected_count: int
    level_counts: dict[str, int]
    diagnostic_distribution: dict[str, int]
    capability_distribution: dict[str, int]
    curriculum_sha256: str
    cases: tuple[CurriculumCase, ...]

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["cases"] = [asdict(item) for item in self.cases]
        return payload


@dataclass(frozen=True, slots=True)
class _SeedCase:
    case_id: str
    family: str
    level: str
    task: str
    entry_path: str
    files: tuple[tuple[str, str], ...]
    expected_outcome: str
    expected_diagnostic_code: str | None = None


_SEEDS: tuple[_SeedCase, ...] = (
    _SeedCase(
        case_id="l0-pure-arithmetic",
        family="core:pure-arithmetic",
        level="L0",
        task="Recognize a pure, well-typed Koschei program as valid.",
        entry_path="main.ks",
        files=(("main.ks", "fn main() { let total = 2 + 3 println(\"{total}\") }\n"),),
        expected_outcome="ACCEPTED",
    ),
    _SeedCase(
        case_id="l0-type-mismatch",
        family="core:type-safety",
        level="L0",
        task="Reject a type-invalid expression with the compiler's exact diagnostic.",
        entry_path="main.ks",
        files=(("main.ks", "fn main() { let invalid = \"five\" + 5 }\n"),),
        expected_outcome="REJECTED",
        expected_diagnostic_code="KS1306",
    ),
    _SeedCase(
        case_id="l1-missing-net-token",
        family="capability:missing-token",
        level="L1",
        task="Reject network authority that appears without an explicit NetCaps value.",
        entry_path="main.ks",
        files=(("main.ks", "fn steal() { let response = net.get(\"https://evil.example\") or \"\" }\n"),),
        expected_outcome="REJECTED",
        expected_diagnostic_code="KS2401",
    ),
    _SeedCase(
        case_id="l1-narrowed-net-token",
        family="capability:narrowing",
        level="L1",
        task="Accept network access only after SystemCaps is narrowed to one origin.",
        entry_path="main.ks",
        files=(
            (
                "main.ks",
                "fn main(caps: SystemCaps) { "
                "let api = caps.net.allow(\"https://api.example\") "
                "let response = api.get(\"https://api.example/v1\") or \"\" "
                "println(response) }\n",
            ),
        ),
        expected_outcome="ACCEPTED",
    ),
    _SeedCase(
        case_id="l1-root-disk-io",
        family="capability:root-denial",
        level="L1",
        task="Reject direct I/O through a root capability before narrowing.",
        entry_path="main.ks",
        files=(
            (
                "main.ks",
                "fn main(caps: SystemCaps) { "
                "let raw = caps.disk "
                "let secret = raw.read(\"/etc/shadow\") or \"\" "
                "}\n",
            ),
        ),
        expected_outcome="REJECTED",
        expected_diagnostic_code="KS2402",
    ),
    _SeedCase(
        case_id="l1-rewiden-disk-token",
        family="capability:no-rewidening",
        level="L1",
        task="Reject an attempt to widen a capability that was already narrowed.",
        entry_path="main.ks",
        files=(
            (
                "main.ks",
                "fn main(caps: SystemCaps) { "
                "let ro = caps.disk.allow_read_only(\"/tmp/safe\") "
                "let widened = ro.allow(\"/\") "
                "}\n",
            ),
        ),
        expected_outcome="REJECTED",
        expected_diagnostic_code="KS2403",
    ),
    _SeedCase(
        case_id="l1-read-only-write",
        family="capability:operation-denial",
        level="L1",
        task="Reject a write performed through a read-only disk capability.",
        entry_path="main.ks",
        files=(
            (
                "main.ks",
                "fn main(caps: SystemCaps) { "
                "let ro = caps.disk.allow_read_only(\"/tmp/safe\") "
                "ro.write(\"/tmp/safe/x\", \"data\") "
                "}\n",
            ),
        ),
        expected_outcome="REJECTED",
        expected_diagnostic_code="KS2404",
    ),
    _SeedCase(
        case_id="l1-pass-narrow-disk-token",
        family="capability:delegation",
        level="L1",
        task="Accept a narrowed read capability passed through an explicit function parameter.",
        entry_path="main.ks",
        files=(
            (
                "main.ks",
                "fn load(disk: DiskReadCaps, path: String) -> String or Error { "
                "let content = disk.read(path) or return Error(\"unreadable\") "
                "return content } "
                "fn main(caps: SystemCaps) { "
                "let ro = caps.disk.allow_read_only(\"/etc/app/\") "
                "let cfg = load(ro, \"/etc/app/config.json\") or \"\" "
                "println(cfg) }\n",
            ),
        ),
        expected_outcome="ACCEPTED",
    ),
    _SeedCase(
        case_id="l2-imported-call-without-token",
        family="adversarial:dependency-authority",
        level="L2",
        task="Reject a caller that invokes an imported capability-requiring function without a token.",
        entry_path="main.ks",
        files=(
            (
                "attack.ks",
                "fn exfiltrate(net: NetCaps) { "
                "let response = net.get(\"https://evil.example\") or \"\" "
                "println(response) }\n",
            ),
            ("main.ks", "import attack\nfn main() { attack.exfiltrate() }\n"),
        ),
        expected_outcome="REJECTED",
        expected_diagnostic_code="KS2401",
    ),
    _SeedCase(
        case_id="l2-imported-ambient-net",
        family="adversarial:supply-chain",
        level="L2",
        task="Reject a dependency that tries to acquire ambient network authority internally.",
        entry_path="main.ks",
        files=(
            (
                "attack.ks",
                "fn exfiltrate() { "
                "let response = net.get(\"https://evil.example\") or \"\" "
                "println(response) }\n",
            ),
            ("main.ks", "import attack\nfn main() { attack.exfiltrate() }\n"),
        ),
        expected_outcome="REJECTED",
        expected_diagnostic_code="KS2401",
    ),
    _SeedCase(
        case_id="l3-explicit-network-service-boundary",
        family="systems:declared-network",
        level="L3",
        task="Accept a program with declared network power while preserving an explicit origin boundary.",
        entry_path="main.ks",
        files=(
            (
                "main.ks",
                "fn fetch(net: NetCaps, url: String) -> String or Error { "
                "let response = net.get(url) or return Error(\"request failed\") "
                "return response } "
                "fn main(caps: SystemCaps) { "
                "let api = caps.net.allow(\"https://api.example\") "
                "let body = fetch(api, \"https://api.example/v1\") or \"\" "
                "println(body) }\n",
            ),
        ),
        expected_outcome="ACCEPTED",
    ),
    _SeedCase(
        case_id="l4-minimum-authority-import-repair",
        family="repair:dependency-authority",
        level="L4",
        task="Repair an imported network operation by passing one narrowed NetCaps token instead of granting ambient authority.",
        entry_path="main.ks",
        files=(
            (
                "attack.ks",
                "fn exfiltrate(net: NetCaps) { "
                "let response = net.get(\"https://evil.example/report\") or \"\" "
                "println(response) }\n",
            ),
            (
                "main.ks",
                "import attack\n"
                "fn main(caps: SystemCaps) { "
                "let outbound = caps.net.allow(\"https://evil.example\") "
                "attack.exfiltrate(outbound) }\n",
            ),
        ),
        expected_outcome="ACCEPTED",
    ),
)


def canonical_json(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def build_model_curriculum(
    repo_root: str | Path,
    *,
    source_commit: str,
) -> ModelCurriculum:
    """Build the v1 curriculum, failing closed on any compiler-oracle drift."""

    root = Path(repo_root).resolve()
    foundation = build_foundation_corpus(root, source_commit=source_commit)

    cases = tuple(_materialize_seed(seed) for seed in _SEEDS)
    level_counts = {level: 0 for level in LEVELS}
    diagnostics: dict[str, int] = {}
    capabilities: dict[str, int] = {}
    accepted = 0
    rejected = 0

    for case in cases:
        level_counts[case.level] += 1
        if case.outcome == "ACCEPTED":
            accepted += 1
            assert case.capability_manifest is not None
            for domain in case.capability_manifest.get("domains", []):
                capabilities[domain] = capabilities.get(domain, 0) + 1
        else:
            rejected += 1
            assert case.diagnostic_code is not None
            diagnostics[case.diagnostic_code] = diagnostics.get(case.diagnostic_code, 0) + 1

    payload: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "generator_version": GENERATOR_VERSION,
        "source_repository": SOURCE_REPOSITORY,
        "source_commit": source_commit,
        "compiler_version": __version__,
        "foundation_corpus_sha256": foundation.corpus_sha256,
        "case_count": len(cases),
        "family_count": len({case.family for case in cases}),
        "accepted_count": accepted,
        "rejected_count": rejected,
        "level_counts": level_counts,
        "diagnostic_distribution": dict(sorted(diagnostics.items())),
        "capability_distribution": dict(sorted(capabilities.items())),
        "cases": [asdict(case) for case in cases],
    }
    digest = hashlib.sha256(canonical_json(payload).encode("utf-8")).hexdigest()
    payload["curriculum_sha256"] = digest
    return verify_model_curriculum(payload)


def verify_model_curriculum(
    value: ModelCurriculum | dict[str, Any],
) -> ModelCurriculum:
    curriculum = value if isinstance(value, ModelCurriculum) else _parse_curriculum(value)

    if curriculum.schema_version != SCHEMA_VERSION:
        raise ModelCurriculumError("unsupported model curriculum schema")
    if curriculum.generator_version != GENERATOR_VERSION:
        raise ModelCurriculumError("unsupported model curriculum generator")
    if curriculum.source_repository != SOURCE_REPOSITORY:
        raise ModelCurriculumError("model curriculum source repository mismatch")
    if not _is_sha(curriculum.source_commit, length=40):
        raise ModelCurriculumError("model curriculum source commit is invalid")
    if not _is_sha(curriculum.foundation_corpus_sha256):
        raise ModelCurriculumError("foundation corpus digest is invalid")
    if not _is_sha(curriculum.curriculum_sha256):
        raise ModelCurriculumError("model curriculum digest is invalid")
    if not curriculum.compiler_version:
        raise ModelCurriculumError("compiler version is empty")
    if not curriculum.cases:
        raise ModelCurriculumError("model curriculum must contain cases")

    case_ids: set[str] = set()
    families: set[str] = set()
    accepted = 0
    rejected = 0
    level_counts = {level: 0 for level in LEVELS}
    diagnostics: dict[str, int] = {}
    capabilities: dict[str, int] = {}

    for case in curriculum.cases:
        if not case.case_id or case.case_id in case_ids:
            raise ModelCurriculumError("model curriculum case IDs must be unique and non-empty")
        case_ids.add(case.case_id)
        if not case.family:
            raise ModelCurriculumError(f"curriculum family is empty: {case.case_id}")
        families.add(case.family)
        if case.level not in LEVELS:
            raise ModelCurriculumError(f"invalid curriculum level: {case.case_id}")
        level_counts[case.level] += 1
        if case.outcome not in OUTCOMES:
            raise ModelCurriculumError(f"invalid curriculum outcome: {case.case_id}")
        _validate_relative_path(case.entry_path)
        if not case.files:
            raise ModelCurriculumError(f"curriculum case has no files: {case.case_id}")

        paths: list[str] = []
        for source_file in case.files:
            _validate_relative_path(source_file.path)
            if not source_file.path.endswith(".ks"):
                raise ModelCurriculumError(
                    f"curriculum source must be a .ks file: {source_file.path}"
                )
            if not _is_sha(source_file.source_sha256):
                raise ModelCurriculumError(
                    f"curriculum source digest is invalid: {source_file.path}"
                )
            raw = source_file.text.encode("utf-8")
            if hashlib.sha256(raw).hexdigest() != source_file.source_sha256:
                raise ModelCurriculumError(
                    f"curriculum source digest mismatch: {source_file.path}"
                )
            paths.append(source_file.path)
        if paths != sorted(paths) or len(paths) != len(set(paths)):
            raise ModelCurriculumError(
                f"curriculum source paths must be unique and sorted: {case.case_id}"
            )
        if case.entry_path not in paths:
            raise ModelCurriculumError(
                f"curriculum entry path is missing from case files: {case.case_id}"
            )

        if case.outcome == "ACCEPTED":
            accepted += 1
            if case.diagnostic_code is not None or case.diagnostic_title is not None:
                raise ModelCurriculumError(
                    f"accepted curriculum case carries a diagnostic: {case.case_id}"
                )
            if not isinstance(case.capability_manifest, dict):
                raise ModelCurriculumError(
                    f"accepted curriculum case lacks a capability manifest: {case.case_id}"
                )
            domains = case.capability_manifest.get("domains")
            if not isinstance(domains, list) or not all(
                isinstance(domain, str) for domain in domains
            ):
                raise ModelCurriculumError(
                    f"accepted curriculum capability domains are invalid: {case.case_id}"
                )
            for domain in domains:
                capabilities[domain] = capabilities.get(domain, 0) + 1
        else:
            rejected += 1
            if case.capability_manifest is not None:
                raise ModelCurriculumError(
                    f"rejected curriculum case carries a capability manifest: {case.case_id}"
                )
            if not isinstance(case.diagnostic_code, str) or lookup(
                case.diagnostic_code, "en"
            ) is None:
                raise ModelCurriculumError(
                    f"rejected curriculum case has an unknown diagnostic: {case.case_id}"
                )
            if not isinstance(case.diagnostic_title, str) or not case.diagnostic_title:
                raise ModelCurriculumError(
                    f"rejected curriculum case has no diagnostic title: {case.case_id}"
                )
            diagnostics[case.diagnostic_code] = diagnostics.get(case.diagnostic_code, 0) + 1

    if curriculum.case_count != len(curriculum.cases):
        raise ModelCurriculumError("model curriculum case count mismatch")
    if curriculum.family_count != len(families):
        raise ModelCurriculumError("model curriculum family count mismatch")
    if curriculum.accepted_count != accepted:
        raise ModelCurriculumError("model curriculum accepted count mismatch")
    if curriculum.rejected_count != rejected:
        raise ModelCurriculumError("model curriculum rejected count mismatch")
    if curriculum.level_counts != level_counts:
        raise ModelCurriculumError("model curriculum level distribution mismatch")
    if curriculum.diagnostic_distribution != dict(sorted(diagnostics.items())):
        raise ModelCurriculumError("model curriculum diagnostic distribution mismatch")
    if curriculum.capability_distribution != dict(sorted(capabilities.items())):
        raise ModelCurriculumError("model curriculum capability distribution mismatch")

    digest_payload = curriculum.to_dict()
    observed_digest = digest_payload.pop("curriculum_sha256")
    expected_digest = hashlib.sha256(
        canonical_json(digest_payload).encode("utf-8")
    ).hexdigest()
    if observed_digest != expected_digest:
        raise ModelCurriculumError("model curriculum digest mismatch")
    return curriculum


def load_model_curriculum(path: str | Path) -> ModelCurriculum:
    try:
        text = Path(path).read_text(encoding="utf-8")
    except UnicodeDecodeError as exc:
        raise ModelCurriculumError("model curriculum is not valid UTF-8") from exc
    try:
        payload = json.loads(text, object_pairs_hook=_unique_object_pairs)
    except (json.JSONDecodeError, RecursionError) as exc:
        raise ModelCurriculumError("model curriculum is not valid JSON") from exc
    if not isinstance(payload, dict):
        raise ModelCurriculumError("model curriculum must be a JSON object")
    return verify_model_curriculum(payload)


def write_model_curriculum(curriculum: ModelCurriculum, path: str | Path) -> None:
    verified = verify_model_curriculum(curriculum)
    payload = json.dumps(
        verified.to_dict(), ensure_ascii=False, indent=2, sort_keys=True
    ) + "\n"
    _atomic_no_replace(Path(path), payload)


def _materialize_seed(seed: _SeedCase) -> CurriculumCase:
    if seed.level not in LEVELS:
        raise ModelCurriculumError(f"seed has invalid level: {seed.case_id}")
    if seed.expected_outcome not in OUTCOMES:
        raise ModelCurriculumError(f"seed has invalid outcome: {seed.case_id}")

    files = tuple(
        CurriculumSourceFile(
            path=relative,
            source_sha256=hashlib.sha256(text.encode("utf-8")).hexdigest(),
            text=text,
        )
        for relative, text in sorted(seed.files)
    )
    observed = _run_compiler_oracle(seed.entry_path, files)
    outcome = observed["outcome"]
    diagnostic_code = observed["diagnostic_code"]

    if outcome != seed.expected_outcome:
        raise ModelCurriculumError(
            f"compiler oracle disagrees with seed {seed.case_id}: "
            f"expected {seed.expected_outcome}, observed {outcome}"
        )
    if seed.expected_diagnostic_code != diagnostic_code:
        raise ModelCurriculumError(
            f"compiler oracle diagnostic drift for {seed.case_id}: "
            f"expected {seed.expected_diagnostic_code!r}, observed {diagnostic_code!r}"
        )

    return CurriculumCase(
        case_id=seed.case_id,
        family=seed.family,
        level=seed.level,
        task=seed.task,
        entry_path=seed.entry_path,
        outcome=outcome,
        diagnostic_code=diagnostic_code,
        diagnostic_title=observed["diagnostic_title"],
        capability_manifest=observed["capability_manifest"],
        files=files,
    )


def _run_compiler_oracle(
    entry_path: str,
    files: tuple[CurriculumSourceFile, ...],
) -> dict[str, Any]:
    _validate_relative_path(entry_path)
    with tempfile.TemporaryDirectory(prefix="koschei-model-oracle-") as temporary:
        root = Path(temporary)
        for source_file in files:
            destination = root / source_file.path
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_text(source_file.text, encoding="utf-8")
        entry = root / entry_path
        if not entry.is_file():
            raise ModelCurriculumError(f"oracle entry file does not exist: {entry_path}")

        try:
            graph = load_graph(entry)
            check_graph(graph)
        except Exception as exc:
            payload = diagnostic_payload(str(exc), locale="en", source=entry_path, error=exc)
            code = payload.get("code")
            if not isinstance(code, str) or lookup(code, "en") is None:
                raise ModelCurriculumError(
                    f"compiler oracle failed without a known diagnostic: {type(exc).__name__}: {exc}"
                ) from exc
            title = payload.get("title")
            return {
                "outcome": "REJECTED",
                "diagnostic_code": code,
                "diagnostic_title": str(title),
                "capability_manifest": None,
            }

        manifest = analyze_graph(graph)
        stable_manifest = manifest_to_dict(manifest, entry_path)
        stable_manifest["domains"] = manifest.domains()
        return {
            "outcome": "ACCEPTED",
            "diagnostic_code": None,
            "diagnostic_title": None,
            "capability_manifest": stable_manifest,
        }


def _parse_curriculum(payload: dict[str, Any]) -> ModelCurriculum:
    expected = {
        "schema_version",
        "generator_version",
        "source_repository",
        "source_commit",
        "compiler_version",
        "foundation_corpus_sha256",
        "case_count",
        "family_count",
        "accepted_count",
        "rejected_count",
        "level_counts",
        "diagnostic_distribution",
        "capability_distribution",
        "curriculum_sha256",
        "cases",
    }
    if set(payload) != expected:
        raise ModelCurriculumError("model curriculum fields do not match v1 schema")
    raw_cases = payload.get("cases")
    if not isinstance(raw_cases, list):
        raise ModelCurriculumError("model curriculum cases must be a list")

    cases: list[CurriculumCase] = []
    case_fields = {
        "case_id",
        "family",
        "level",
        "task",
        "entry_path",
        "outcome",
        "diagnostic_code",
        "diagnostic_title",
        "capability_manifest",
        "files",
    }
    file_fields = {"path", "source_sha256", "text"}
    for index, raw in enumerate(raw_cases):
        if not isinstance(raw, dict) or set(raw) != case_fields:
            raise ModelCurriculumError(f"invalid curriculum case at index {index}")
        raw_files = raw.get("files")
        if not isinstance(raw_files, list):
            raise ModelCurriculumError(f"invalid curriculum source list at index {index}")
        files: list[CurriculumSourceFile] = []
        for file_index, raw_file in enumerate(raw_files):
            if not isinstance(raw_file, dict) or set(raw_file) != file_fields:
                raise ModelCurriculumError(
                    f"invalid curriculum source at case {index}, file {file_index}"
                )
            if not all(isinstance(raw_file[key], str) for key in file_fields):
                raise ModelCurriculumError(
                    f"curriculum source fields must be strings at case {index}"
                )
            files.append(CurriculumSourceFile(**raw_file))
        string_fields = ("case_id", "family", "level", "task", "entry_path", "outcome")
        if not all(isinstance(raw[key], str) for key in string_fields):
            raise ModelCurriculumError(f"curriculum case string fields are invalid at index {index}")
        cases.append(
            CurriculumCase(
                case_id=raw["case_id"],
                family=raw["family"],
                level=raw["level"],
                task=raw["task"],
                entry_path=raw["entry_path"],
                outcome=raw["outcome"],
                diagnostic_code=raw["diagnostic_code"],
                diagnostic_title=raw["diagnostic_title"],
                capability_manifest=raw["capability_manifest"],
                files=tuple(files),
            )
        )

    scalar_strings = (
        "schema_version",
        "generator_version",
        "source_repository",
        "source_commit",
        "compiler_version",
        "foundation_corpus_sha256",
        "curriculum_sha256",
    )
    if not all(isinstance(payload[key], str) for key in scalar_strings):
        raise ModelCurriculumError("model curriculum string fields are invalid")
    for key in ("case_count", "family_count", "accepted_count", "rejected_count"):
        if type(payload[key]) is not int or payload[key] < 0:
            raise ModelCurriculumError(f"model curriculum {key} is invalid")
    for key in ("level_counts", "diagnostic_distribution", "capability_distribution"):
        value = payload[key]
        if not isinstance(value, dict) or not all(
            isinstance(name, str) and type(count) is int and count >= 0
            for name, count in value.items()
        ):
            raise ModelCurriculumError(f"model curriculum {key} is invalid")

    return ModelCurriculum(
        schema_version=payload["schema_version"],
        generator_version=payload["generator_version"],
        source_repository=payload["source_repository"],
        source_commit=payload["source_commit"],
        compiler_version=payload["compiler_version"],
        foundation_corpus_sha256=payload["foundation_corpus_sha256"],
        case_count=payload["case_count"],
        family_count=payload["family_count"],
        accepted_count=payload["accepted_count"],
        rejected_count=payload["rejected_count"],
        level_counts=dict(payload["level_counts"]),
        diagnostic_distribution=dict(payload["diagnostic_distribution"]),
        capability_distribution=dict(payload["capability_distribution"]),
        curriculum_sha256=payload["curriculum_sha256"],
        cases=tuple(cases),
    )


def _unique_object_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ModelCurriculumError(f"duplicate JSON object member: {key}")
        result[key] = value
    return result


def _validate_relative_path(value: str) -> None:
    if not value:
        raise ModelCurriculumError("curriculum source path is empty")
    try:
        value.encode("utf-8")
    except UnicodeEncodeError as exc:
        raise ModelCurriculumError("curriculum source path is not valid UTF-8") from exc
    path = Path(value)
    canonical = PurePosixPath(value).as_posix()
    if (
        path.is_absolute()
        or ".." in path.parts
        or "\\" in value
        or "\x00" in value
        or value.startswith("~")
        or canonical != value
    ):
        raise ModelCurriculumError(f"unsafe or non-canonical curriculum path: {value}")


def _is_sha(value: str, *, length: int = 64) -> bool:
    if not isinstance(value, str) or len(value) != length:
        return False
    return all(character in "0123456789abcdef" for character in value)


def _atomic_no_replace(path: Path, payload: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o644)
    except FileExistsError:
        raise FileExistsError(f"model curriculum already exists: {path}") from None
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        directory_fd = os.open(path.parent, os.O_RDONLY)
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)
    except BaseException:
        path.unlink(missing_ok=True)
        raise


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="ks-model-curriculum",
        description="Build or verify the compiler-oracle Koschei model curriculum",
    )
    actions = parser.add_subparsers(dest="action", required=True)
    build = actions.add_parser("build")
    build.add_argument("--repo-root", default=".")
    build.add_argument("--source-commit", required=True)
    build.add_argument("--output", required=True)
    verify = actions.add_parser("verify")
    verify.add_argument("curriculum")
    args = parser.parse_args(argv)

    try:
        if args.action == "build":
            curriculum = build_model_curriculum(
                args.repo_root,
                source_commit=args.source_commit,
            )
            write_model_curriculum(curriculum, args.output)
            print(f"KOSCHEI MODEL CURRICULUM: {args.output}")
        else:
            curriculum = load_model_curriculum(args.curriculum)
            print(f"KOSCHEI MODEL CURRICULUM VERIFIED: {args.curriculum}")
        print(f"SOURCE COMMIT: {curriculum.source_commit}")
        print(f"COMPILER VERSION: {curriculum.compiler_version}")
        print(f"CASES: {curriculum.case_count}")
        print(f"ACCEPTED: {curriculum.accepted_count}")
        print(f"REJECTED: {curriculum.rejected_count}")
        print(f"CURRICULUM SHA256: {curriculum.curriculum_sha256}")
        return 0
    except (ModelCurriculumError, FileExistsError, OSError) as exc:
        print(f"ks-model-curriculum: {exc}")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())