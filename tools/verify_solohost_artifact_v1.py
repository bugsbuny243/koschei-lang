"""Fail-closed publication gate for Koschei Pi SoloHost customer artifacts.

This verifier intentionally checks the *assembled customer artifact directory*, not
an ordinary source checkout. A normal koschei-lang repository checkout is expected
to fail this gate because it contains proprietary source.

Release authenticity is anchored OUTSIDE the artifact. A public key bundled beside
the binary may be useful as transport metadata, but it is never accepted as the
trust source by this verifier. Production publication must supply an independently
pinned Ed25519 public key with ``--trusted-public-key``.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile


POLICY_PATH = Path(__file__).resolve().parents[1] / "distribution" / "solohost" / "artifact-policy-v1.json"
REQUIRED_MANIFEST = "koschei-release-manifest.json"
REQUIRED_SIGNATURE = "koschei-release-manifest.sig"
RELEASE_SCHEMA = "koschei.solohost-release-manifest/v1"
SIGNATURE_SCHEME = "ed25519-openssl-raw-v1"
KEY_ID_PREFIX = "ed25519-sha256:"
SHA256_RE = re.compile(r"[0-9a-f]{64}\Z")
EXECUTABLE_CANDIDATES = {"ks", "ks.exe", "koschei", "koschei.exe"}
SOURCE_COMMIT_RE = re.compile(r"(?:[0-9a-f]{40}|[0-9a-f]{64})\Z")
SHA256_RE = re.compile(r"[0-9a-f]{64}\Z")


class ArtifactPolicyError(ValueError):
    pass


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _run_openssl(command: list[str]) -> subprocess.CompletedProcess[str]:
    try:
        return subprocess.run(command, check=False, capture_output=True, text=True)
    except OSError as exc:
        raise ArtifactPolicyError(f"cannot execute OpenSSL: {exc}") from exc


def _public_key_id(public_key: Path) -> str:
    if shutil.which("openssl") is None:
        raise ArtifactPolicyError("openssl executable is required for signed release verification")
    with tempfile.TemporaryDirectory() as tmp:
        public_der = Path(tmp) / "public.der"
        result = _run_openssl([
            "openssl",
            "pkey",
            "-pubin",
            "-in",
            str(public_key),
            "-outform",
            "DER",
            "-out",
            str(public_der),
        ])
        if result.returncode != 0:
            detail = (result.stderr or result.stdout).strip()
            raise ArtifactPolicyError(f"invalid release public key: {detail}")
        return "ed25519-sha256:" + hashlib.sha256(public_der.read_bytes()).hexdigest()


def _verify_ed25519_signature(*, manifest_path: Path, signature_path: Path, public_key: Path) -> bool:
    result = _run_openssl([
        "openssl",
        "pkeyutl",
        "-verify",
        "-rawin",
        "-in",
        str(manifest_path),
        "-pubin",
        "-inkey",
        str(public_key),
        "-sigfile",
        str(signature_path),
    ])
    return result.returncode == 0


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


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _simple_artifact_name(value: object, *, field: str) -> str:
    if not isinstance(value, str) or not value:
        raise ArtifactPolicyError(f"manifest {field} must be a non-empty filename")
    path = Path(value)
    if path.name != value or value in {".", ".."} or "/" in value or "\\" in value:
        raise ArtifactPolicyError(f"manifest {field} must be a simple artifact-local filename")
    return value


def _load_release_manifest(root: Path) -> tuple[Path, dict[str, object]]:
    manifest_path = root / REQUIRED_MANIFEST
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ArtifactPolicyError(f"missing required release manifest: {REQUIRED_MANIFEST}") from exc
    except (OSError, json.JSONDecodeError) as exc:
        raise ArtifactPolicyError(f"cannot load release manifest: {exc}") from exc
    if not isinstance(manifest, dict) or manifest.get("schema") != RELEASE_SCHEMA:
        raise ArtifactPolicyError("unexpected SoloHost release manifest schema")
    if manifest.get("product") != "koschei-lang" or manifest.get("channel") != "pi-solohost":
        raise ArtifactPolicyError("release manifest product/channel identity mismatch")
    return manifest_path, manifest


def _run_openssl(command: list[str]) -> subprocess.CompletedProcess[bytes]:
    try:
        return subprocess.run(command, check=False, capture_output=True)
    except OSError as exc:
        raise ArtifactPolicyError(f"cannot execute OpenSSL: {exc}") from exc


def _trusted_key_id(trusted_public_key: Path) -> str:
    if not trusted_public_key.is_file():
        raise ArtifactPolicyError(f"trusted public key does not exist: {trusted_public_key}")
    if shutil.which("openssl") is None:
        raise ArtifactPolicyError("openssl executable is required for release verification")
    with tempfile.TemporaryDirectory(prefix="koschei-release-trust-") as tmp:
        public_der = Path(tmp) / "trusted-public.der"
        result = _run_openssl([
            "openssl",
            "pkey",
            "-pubin",
            "-in",
            str(trusted_public_key),
            "-outform",
            "DER",
            "-out",
            str(public_der),
        ])
        if result.returncode != 0:
            detail = (result.stderr or result.stdout).decode("utf-8", errors="replace").strip()
            raise ArtifactPolicyError(f"trusted public key is not a valid OpenSSL public key: {detail}")
        return KEY_ID_PREFIX + hashlib.sha256(public_der.read_bytes()).hexdigest()


def _verify_release_integrity(root: Path, trusted_public_key: Path) -> list[str]:
    failures: list[str] = []
    try:
        manifest_path, manifest = _load_release_manifest(root)
    except ArtifactPolicyError as exc:
        return [str(exc)]

    try:
        entrypoint = _simple_artifact_name(manifest.get("entrypoint"), field="entrypoint")
    except ArtifactPolicyError as exc:
        failures.append(str(exc))
        entrypoint = ""
    if entrypoint and entrypoint not in EXECUTABLE_CANDIDATES:
        failures.append(f"release manifest entrypoint is not a Koschei executable: {entrypoint}")

    artifact = manifest.get("artifact")
    if not isinstance(artifact, dict):
        failures.append("release manifest artifact section is missing")
        artifact = {}
    try:
        artifact_name = _simple_artifact_name(artifact.get("path"), field="artifact.path")
    except ArtifactPolicyError as exc:
        failures.append(str(exc))
        artifact_name = ""

    if entrypoint and artifact_name and artifact_name != entrypoint:
        failures.append("release manifest entrypoint and artifact.path do not match")

    artifact_path = root / artifact_name if artifact_name else None
    expected_sha = artifact.get("sha256")
    expected_size = artifact.get("size_bytes")
    if not isinstance(expected_sha, str) or SHA256_RE.fullmatch(expected_sha) is None:
        failures.append("release manifest artifact.sha256 must be a lowercase SHA-256 digest")
    if not isinstance(expected_size, int) or isinstance(expected_size, bool) or expected_size < 0:
        failures.append("release manifest artifact.size_bytes must be a non-negative integer")

    if artifact_path is not None:
        if not artifact_path.is_file():
            failures.append(f"manifest-bound executable is missing: {artifact_name}")
        else:
            if isinstance(expected_sha, str) and SHA256_RE.fullmatch(expected_sha):
                actual_sha = _sha256(artifact_path)
                if actual_sha != expected_sha:
                    failures.append(
                        f"artifact SHA-256 mismatch: manifest={expected_sha} actual={actual_sha}"
                    )
            if isinstance(expected_size, int) and not isinstance(expected_size, bool) and expected_size >= 0:
                actual_size = artifact_path.stat().st_size
                if actual_size != expected_size:
                    failures.append(
                        f"artifact size mismatch: manifest={expected_size} actual={actual_size}"
                    )

    signature = manifest.get("signature")
    if not isinstance(signature, dict):
        failures.append("release manifest signature section is missing")
        signature = {}
    if signature.get("status") != "SIGNED":
        failures.append("release manifest is not marked SIGNED")
    if signature.get("scheme") != SIGNATURE_SCHEME:
        failures.append(f"release signature scheme must be {SIGNATURE_SCHEME}")
    key_id = signature.get("key_id")
    if not isinstance(key_id, str) or not key_id.startswith(KEY_ID_PREFIX) or SHA256_RE.fullmatch(key_id[len(KEY_ID_PREFIX):]) is None:
        failures.append("release manifest signature.key_id is not a valid Ed25519 key identity")
    try:
        signature_name = _simple_artifact_name(
            signature.get("signature_file"), field="signature.signature_file"
        )
    except ArtifactPolicyError as exc:
        failures.append(str(exc))
        signature_name = ""
    if signature_name and signature_name != REQUIRED_SIGNATURE:
        failures.append(f"release signature file must be {REQUIRED_SIGNATURE}")

    signature_path = root / signature_name if signature_name else None
    if signature_path is not None and not signature_path.is_file():
        failures.append(f"detached release signature is missing: {signature_name}")

    try:
        trusted_key_id = _trusted_key_id(trusted_public_key.resolve())
    except ArtifactPolicyError as exc:
        failures.append(str(exc))
        trusted_key_id = ""

    if trusted_key_id and isinstance(key_id, str) and trusted_key_id != key_id:
        failures.append(
            "release signer does not match independently trusted key: "
            f"manifest={key_id} trusted={trusted_key_id}"
        )

    if (
        trusted_key_id
        and isinstance(key_id, str)
        and trusted_key_id == key_id
        and signature_path is not None
        and signature_path.is_file()
        and signature.get("status") == "SIGNED"
        and signature.get("scheme") == SIGNATURE_SCHEME
    ):
        result = _run_openssl([
            "openssl",
            "pkeyutl",
            "-verify",
            "-rawin",
            "-in",
            str(manifest_path),
            "-pubin",
            "-inkey",
            str(trusted_public_key.resolve()),
            "-sigfile",
            str(signature_path),
        ])
        if result.returncode != 0:
            failures.append("detached release signature does not verify against trusted public key")

    return failures


def verify_artifact(root: Path, *, trusted_public_key: Path | None = None) -> list[str]:
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
        _verify_manifest(
            root,
            manifest,
            failures,
            allow_unsigned_staging=allow_unsigned_staging,
            public_key=public_key,
        )

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

    if trusted_public_key is None:
        failures.append(
            "missing independent trusted public key; artifact-bundled keys are not trust anchors"
        )
    else:
        failures.extend(_verify_release_integrity(root, trusted_public_key))

    return failures


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("artifact_directory", type=Path)
    parser.add_argument(
        "--trusted-public-key",
        required=True,
        type=Path,
        help=(
            "independently pinned Ed25519 release public key; do not point this at "
            "a key learned only from inside the artifact being verified"
        ),
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    root = args.artifact_directory.resolve()
    try:
        failures = verify_artifact(root, trusted_public_key=args.trusted_public_key.resolve())
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
    print("source-leak, artifact digest, signer identity, and detached-signature checks passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
