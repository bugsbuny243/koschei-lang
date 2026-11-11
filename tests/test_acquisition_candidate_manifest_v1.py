from __future__ import annotations

from dataclasses import asdict
import hashlib
import json
from pathlib import Path

import pytest

from koschei.local_validation_v1 import (
    seal_local_validation_receipt_v1,
    seal_local_validation_step_v1,
)
from tools import acquisition_candidate_manifest_v1 as candidate
from tools.reproducible_artifact_receipt_v1 import build_receipt


ZERO64 = "0" * 64


def _write_release_inputs(root: Path) -> None:
    for name in candidate.RELEASE_INPUTS:
        (root / name).write_text(f"{name}\n", encoding="utf-8")


def _write_receipt(path: Path, commit: str) -> None:
    step = seal_local_validation_step_v1(
        step_id="fixture",
        command=("fixture",),
        returncode=0,
        stdout_sha256=ZERO64,
        stderr_sha256=ZERO64,
    )
    receipt = seal_local_validation_receipt_v1(
        source_commit=commit,
        checkout_clean=True,
        profile="full",
        python_version="3.12.fixture",
        go_version="go1.24.fixture",
        platform="linux-amd64-fixture",
        steps=(step,),
    )
    path.write_text(json.dumps(asdict(receipt)), encoding="utf-8")


def _write_sbom(path: Path, version: str, *, reproducible: bool = True) -> None:
    payload = {
        "schema": "koschei.acquisition-sbom/v1",
        "project": {"version": version},
        "reproducible_inputs": reproducible,
        "mutable_roots": [] if reproducible else ["fixture:mutable"],
    }
    canonical = json.dumps(
        payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode("utf-8")
    payload["sbom_sha256"] = hashlib.sha256(canonical).hexdigest()
    path.write_text(json.dumps(payload), encoding="utf-8")


def _write_reproducibility_receipt(
    path: Path, artifact: Path, commit: str
) -> None:
    mirror = path.with_name("independent-build-copy.bin")
    mirror.write_bytes(artifact.read_bytes())
    path.write_text(
        json.dumps(build_receipt(artifact, mirror, commit)),
        encoding="utf-8",
    )


def _evidence_files(tmp_path: Path, commit: str = "a" * 40) -> dict[str, Path]:
    result: dict[str, Path] = {}
    for name in (
        "source_archive",
        "build_artifact",
        "benchmark_dossier",
        "threat_model",
        "license_lineage",
    ):
        path = tmp_path / f"{name}.bin"
        path.write_bytes(name.encode("utf-8"))
        result[name] = path

    receipt = tmp_path / "validation_receipt.json"
    _write_receipt(receipt, commit)
    result["validation_receipt"] = receipt

    repro = tmp_path / "reproducibility_receipt.json"
    _write_reproducibility_receipt(repro, result["build_artifact"], commit)
    result["reproducibility_receipt"] = repro

    sbom = tmp_path / "sbom.json"
    _write_sbom(sbom, "0.10.0")
    result["sbom"] = sbom
    return result


def _root(tmp_path: Path) -> None:
    (tmp_path / "pyproject.toml").write_text(
        '[project]\nname = "koschei-lang"\nversion = "0.10.0"\n',
        encoding="utf-8",
    )
    _write_release_inputs(tmp_path)


def test_evidence_record_binds_size_and_sha256(tmp_path: Path):
    path = tmp_path / "evidence.bin"
    path.write_bytes(b"koschei-evidence")
    record = candidate.evidence_record(path)
    assert record["bytes"] == len(b"koschei-evidence")
    assert record["sha256"] == hashlib.sha256(b"koschei-evidence").hexdigest()


def test_missing_evidence_fails_closed(tmp_path: Path):
    with pytest.raises(ValueError, match="required acquisition evidence is missing"):
        candidate.evidence_record(tmp_path / "missing.json")


def test_candidate_manifest_binds_exact_version_commit_evidence_and_release_inputs(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    _root(tmp_path)
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
    assert set(manifest["release_inputs"]) == set(candidate.RELEASE_INPUTS)
    assert len(manifest["manifest_sha256"]) == 64


def test_receipt_for_different_commit_fails_closed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    _root(tmp_path)
    evidence = _evidence_files(tmp_path, commit="b" * 40)
    monkeypatch.setattr(candidate, "require_clean_tree", lambda root: None)
    monkeypatch.setattr(candidate, "git_head", lambda root: "a" * 40)
    with pytest.raises(ValueError, match="validation receipt is not release-valid"):
        candidate.build_manifest(
            root=tmp_path,
            tag="v0.10.0",
            signing_identity="not-deployed: acquisition candidate only",
            **evidence,
        )


def test_mutable_sbom_fails_closed(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    _root(tmp_path)
    evidence = _evidence_files(tmp_path)
    _write_sbom(evidence["sbom"], "0.10.0", reproducible=False)
    monkeypatch.setattr(candidate, "require_clean_tree", lambda root: None)
    monkeypatch.setattr(candidate, "git_head", lambda root: "a" * 40)
    with pytest.raises(ValueError, match="reproducible production inputs"):
        candidate.build_manifest(
            root=tmp_path,
            tag="v0.10.0",
            signing_identity="not-deployed: acquisition candidate only",
            **evidence,
        )


def test_reproducibility_receipt_must_match_build_artifact(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    _root(tmp_path)
    evidence = _evidence_files(tmp_path)
    evidence["build_artifact"].write_bytes(b"tampered-after-receipt")
    monkeypatch.setattr(candidate, "require_clean_tree", lambda root: None)
    monkeypatch.setattr(candidate, "git_head", lambda root: "a" * 40)
    with pytest.raises(ValueError, match="artifact digest mismatch"):
        candidate.build_manifest(
            root=tmp_path,
            tag="v0.10.0",
            signing_identity="not-deployed: acquisition candidate only",
            **evidence,
        )


def test_version_tag_mismatch_fails_closed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    _root(tmp_path)
    evidence = _evidence_files(tmp_path)
    monkeypatch.setattr(candidate, "require_clean_tree", lambda root: None)
    monkeypatch.setattr(candidate, "git_head", lambda root: "a" * 40)
    with pytest.raises(ValueError, match="tag/version mismatch"):
        candidate.build_manifest(
            root=tmp_path,
            tag="v0.9.0",
            signing_identity="not-deployed: acquisition candidate only",
            **evidence,
        )


def test_empty_signing_scope_is_rejected(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    _root(tmp_path)
    evidence = _evidence_files(tmp_path)
    monkeypatch.setattr(candidate, "require_clean_tree", lambda root: None)
    monkeypatch.setattr(candidate, "git_head", lambda root: "a" * 40)
    with pytest.raises(ValueError, match="signing identity must be explicit"):
        candidate.build_manifest(
            root=tmp_path,
            tag="v0.10.0",
            signing_identity="   ",
            **evidence,
        )
