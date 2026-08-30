"""Fail-closed publication gate for Koschei Pi SoloHost customer artifacts.

This verifier intentionally checks the *assembled customer artifact directory*, not
an ordinary source checkout. A normal koschei-lang repository checkout is expected
to fail this gate because it contains proprietary source.
"""
from __future__ import annotations

import json
from pathlib import Path
import sys


POLICY_PATH = Path(__file__).resolve().parents[1] / "distribution" / "solohost" / "artifact-policy-v1.json"
REQUIRED_MANIFEST = "koschei-release-manifest.json"
EXECUTABLE_CANDIDATES = {"ks", "ks.exe", "koschei", "koschei.exe"}


class ArtifactPolicyError(ValueError):
    pass


def _load_policy() -> dict[str, object]:
    try:
        data = json.loads(POLICY_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ArtifactPolicyError(f"cannot load SoloHost artifact policy: {exc}") from exc
    if data.get("schema") != "koschei.solohost-artifact-policy/v1":
        raise ArtifactPolicyError("unexpected SoloHost artifact policy schema")
    return data


def _as_string_set(policy: dict[str, object], name: str) -> set[str]:
    raw = policy.get(name)
    if not isinstance(raw, list) or not all(isinstance(item, str) for item in raw):
        raise ArtifactPolicyError(f"policy field {name!r} must be a list of strings")
    return set(raw)


def verify_artifact(root: Path) -> list[str]:
    policy = _load_policy()
    forbidden_path_names = _as_string_set(policy, "forbidden_path_names")
    forbidden_suffixes = _as_string_set(policy, "forbidden_suffixes")
    forbidden_file_names = _as_string_set(policy, "forbidden_file_names")
    secret_markers = {item.lower() for item in _as_string_set(policy, "secret_name_markers")}

    failures: list[str] = []
    if not root.exists():
        return [f"artifact directory does not exist: {root}"]
    if not root.is_dir():
        return [f"artifact path is not a directory: {root}"]

    files = [path for path in root.rglob("*") if path.is_file()]
    if not files:
        failures.append("artifact directory is empty")
        return failures

    names = {path.name for path in files}
    if REQUIRED_MANIFEST not in names:
        failures.append(f"missing required signed-release metadata file: {REQUIRED_MANIFEST}")

    if not any(path.name in EXECUTABLE_CANDIDATES for path in files):
        failures.append("missing Koschei executable entrypoint (ks/koschei)")

    for path in files:
        rel = path.relative_to(root)
        parts = set(rel.parts)
        blocked_parts = sorted(parts.intersection(forbidden_path_names))
        if blocked_parts:
            failures.append(f"forbidden private/source path component {blocked_parts!r}: {rel}")

        if path.name in forbidden_file_names:
            failures.append(f"forbidden source/build file: {rel}")

        if path.suffix.lower() in forbidden_suffixes:
            failures.append(f"forbidden source suffix {path.suffix}: {rel}")

        lower_name = path.name.lower()
        matched_markers = sorted(marker for marker in secret_markers if marker in lower_name)
        if matched_markers:
            failures.append(f"secret-like filename marker {matched_markers!r}: {rel}")

    return failures


def main(argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    if len(args) != 1:
        print("usage: python tools/verify_solohost_artifact_v1.py <artifact-directory>", file=sys.stderr)
        return 2

    root = Path(args[0]).resolve()
    try:
        failures = verify_artifact(root)
    except ArtifactPolicyError as exc:
        print(f"SOLOHOST ARTIFACT POLICY ERROR: {exc}", file=sys.stderr)
        return 2

    if failures:
        print("KOSCHEI SOLOHOST ARTIFACT: REJECTED")
        for failure in failures:
            print(f"- {failure}")
        return 1

    print("KOSCHEI SOLOHOST ARTIFACT: PASS")
    print(f"root: {root}")
    print("source-leak and packaging boundary checks passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
