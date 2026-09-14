from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from tools import acquisition_candidate_manifest_v1 as candidate


def _evidence_files(tmp_path: Path) -> dict[str, Path]:
    result = {}
    for name in (
        "source_archive",
        "build_artifact",
        "validation_receipt",
        "sbom",
        "benchmark_dossier",
        "threat_model",
        "license_lineage",
    ):
        path = tmp_path / f"{name}.bin"
        path.write_bytes(name.encode("utf-8"))
        result[name] = path
    return result


def test_evidence_record_binds_size_and_sha256(tmp_path: Path):
    path = tmp_path / "evidence.bin"
    path.write_bytes(b"koschei-evidence")

    record = candidate.evidence_record(path)

    assert record["bytes"] == len(b"koschei-evidence")
    assert record["sha256"] == hashlib.sha256(b"koschei-evidence").hexdigest()


def test_missing_evidence_fails_closed(tmp_path: Path):
    with pytest.raises(ValueError, match="required acquisition evidence is missing"):
        candidate.evidence_record(tmp_path / "missing.json")


def test_candidate_manifest_binds_exact_version_commit_and_all_evidence(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    (tmp_path / "pyproject.toml").write_text(
        '[project]\nname = "koschei-lang"\nversion = "0.10.0"\n',
        encoding="utf-8",
    )
    evidence = _evidence_files(tmp_path)
    monkeypatch.setattr(candidate, "require_clean_tree", lambda root: None)
    monkeypatch.setattr(candidate, "git_head", lambda root: "a" * 40)

    manifest = candidate.build_manifest(
        root=tmp_path,
        tag="v0.10.0",
        signing_identity="not-deployed: acquisition candidate only",
        **evidence,
    )

    assert manifest["schema"] == "koschei.acquisition-candidate/v1"
    assert manifest["repository"] == "bugsbuny243/koschei-lang"
    assert manifest["commit"] == "a" * 40
    assert manifest["version"] == "0.10.0"
    assert manifest["tag"] == "v0.10.0"
    assert set(manifest["evidence"]) == set(evidence)
    assert len(manifest["manifest_sha256"]) == 64


def test_version_tag_mismatch_fails_closed(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    (tmp_path / "pyproject.toml").write_text(
        '[project]\nname = "koschei-lang"\nversion = "0.10.0"\n',
        encoding="utf-8",
    )
    evidence = _evidence_files(tmp_path)
    monkeypatch.setattr(candidate, "require_clean_tree", lambda root: None)
    monkeypatch.setattr(candidate, "git_head", lambda root: "b" * 40)

    with pytest.raises(ValueError, match="tag/version mismatch"):
        candidate.build_manifest(
            root=tmp_path,
            tag="v0.9.0",
            signing_identity="not-deployed: acquisition candidate only",
            **evidence,
        )


def test_empty_signing_scope_is_rejected(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    (tmp_path / "pyproject.toml").write_text(
        '[project]\nname = "koschei-lang"\nversion = "0.10.0"\n',
        encoding="utf-8",
    )
    evidence = _evidence_files(tmp_path)
    monkeypatch.setattr(candidate, "require_clean_tree", lambda root: None)
    monkeypatch.setattr(candidate, "git_head", lambda root: "c" * 40)

    with pytest.raises(ValueError, match="signing identity must be explicit"):
        candidate.build_manifest(
            root=tmp_path,
            tag="v0.10.0",
            signing_identity="   ",
            **evidence,
        )
