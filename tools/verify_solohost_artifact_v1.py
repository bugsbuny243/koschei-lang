"""Fail-closed publication gate for Koschei Pi SoloHost customer artifacts.

This verifier checks the assembled customer artifact directory, validates the
release manifest against the executable bytes, and rejects unsigned staging
artifacts unless the caller explicitly asks for staging-only verification.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys


POLICY_PATH = Path(__file__).resolve().parents[1] / "distribution" / "solohost" / "artifact-policy-v1.json"
REQUIRED_MANIFEST = "koschei-release-manifest.json"
MANIFEST_SCHEMA = "koschei.solohost-release-manifest/v1"
EXECUTABLE_CANDIDATES = {"ks", "ks.exe", "koschei", "koschei.exe"}


class ArtifactPolicyError(ValueError):
    pass


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


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


def _load_manifest(root: Path, failures: list[str]) -> dict[str, object] | None:
    path = root / REQUIRED_MANIFEST
    if not path.is_file():
        failures.append(f"missing required release metadata file: {REQUIRED_MANIFEST}")
        return None
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        failures.append(f"invalid release manifest: {exc}")
        return None
    if not isinstance(value, dict):
        failures.append("release manifest must be a JSON object")
        return None
    return value


def _verify_manifest(root: Path, manifest: dict[str, object], failures: list[str], *, allow_unsigned_staging: bool) -> None:
    if manifest.get("schema") != MANIFEST_SCHEMA:
        failures.append("unexpected release manifest schema")
    if manifest.get("product") != "koschei-lang":
        failures.append("release manifest product must be koschei-lang")
    if manifest.get("channel") != "pi-solohost":
        failures.append("release manifest channel must be pi-solohost")

    version = manifest.get("version")
    if not isinstance(version, str) or not version.strip():
        failures.append("release manifest version must be non-empty")
    platform = manifest.get("platform")
    if not isinstance(platform, str) or not platform.strip():
        failures.append("release manifest platform must be non-empty")

    commercial = manifest.get("commercial")
    if not isinstance(commercial, dict):
        failures.append("release manifest commercial section is missing")
    else:
        if commercial.get("billing_mode") != "one_time_pi":
            failures.append("release billing mode must be one_time_pi")
        if commercial.get("recurring_subscription") is not False:
            failures.append("recurring_subscription must be false")

    artifact = manifest.get("artifact")
    if not isinstance(artifact, dict):
        failures.append("release manifest artifact section is missing")
    else:
        rel_path = artifact.get("path")
        expected_sha = artifact.get("sha256")
        expected_size = artifact.get("size_bytes")
        if not isinstance(rel_path, str) or not rel_path:
            failures.append("manifest artifact.path must be non-empty")
        else:
            artifact_path = root / rel_path
            if artifact_path.parent.resolve() != root.resolve():
                failures.append("manifest artifact.path must name a top-level artifact file")
            elif not artifact_path.is_file():
                failures.append(f"manifest artifact file is missing: {rel_path}")
            else:
                actual_sha = _sha256(artifact_path)
                if expected_sha != actual_sha:
                    failures.append("manifest artifact sha256 does not match executable bytes")
                if expected_size != artifact_path.stat().st_size:
                    failures.append("manifest artifact size_bytes does not match executable bytes")

    signature = manifest.get("signature")
    if not isinstance(signature, dict):
        failures.append("release manifest signature section is missing")
        return
    status = signature.get("status")
    if status == "UNSIGNED-STAGING":
        if not allow_unsigned_staging:
            failures.append("release manifest is unsigned staging; publication is blocked")
        return
    if status != "SIGNED":
        failures.append("release manifest signature status must be SIGNED or UNSIGNED-STAGING")
        return

    scheme = signature.get("scheme")
    key_id = signature.get("key_id")
    signature_file = signature.get("signature_file")
    if not all(isinstance(value, str) and value for value in (scheme, key_id, signature_file)):
        failures.append("SIGNED manifest requires scheme, key_id and signature_file")
        return
    sig_path = root / str(signature_file)
    if sig_path.parent.resolve() != root.resolve() or not sig_path.is_file():
        failures.append("signature_file must reference an existing top-level file")
        return

    # V1 deliberately refuses to claim cryptographic verification until one
    # concrete public-key scheme and trust anchor are committed.
    failures.append("SIGNED manifest present but cryptographic signature verification is not implemented; publication remains blocked")


def verify_artifact(root: Path, *, allow_unsigned_staging: bool = False) -> list[str]:
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
        return ["artifact directory is empty"]

    if not any(path.name in EXECUTABLE_CANDIDATES for path in files):
        failures.append("missing Koschei executable entrypoint (ks/koschei)")

    manifest = _load_manifest(root, failures)
    if manifest is not None:
        _verify_manifest(root, manifest, failures, allow_unsigned_staging=allow_unsigned_staging)

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


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("artifact_directory", type=Path)
    parser.add_argument(
        "--allow-unsigned-staging",
        action="store_true",
        help="validate an unsigned local staging artifact without making it publishable",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    root = args.artifact_directory.resolve()
    try:
        failures = verify_artifact(root, allow_unsigned_staging=args.allow_unsigned_staging)
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
    if args.allow_unsigned_staging:
        print("mode: unsigned staging validation only — NOT PUBLISHABLE")
    else:
        print("mode: publication gate")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
