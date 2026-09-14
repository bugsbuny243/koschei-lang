from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from tools.reproducible_artifact_receipt_v1 import build_receipt


def test_byte_identical_artifacts_seal_one_digest(tmp_path: Path):
    first = tmp_path / "first.zip"
    second = tmp_path / "second.zip"
    payload = b"koschei-release\n"
    first.write_bytes(payload)
    second.write_bytes(payload)

    receipt = build_receipt(first, second, "a" * 40)

    assert receipt["schema"] == "koschei.reproducible-artifact-receipt/v1"
    assert receipt["source_commit"] == "a" * 40
    assert receipt["artifact_sha256"] == hashlib.sha256(payload).hexdigest()
    assert receipt["artifact_bytes"] == len(payload)
    assert receipt["independent_builds"] == 2
    assert receipt["byte_identical"] is True
    assert receipt["authority"] is False
    assert len(receipt["receipt_sha256"]) == 64


def test_different_artifacts_fail_closed(tmp_path: Path):
    first = tmp_path / "first.zip"
    second = tmp_path / "second.zip"
    first.write_bytes(b"first")
    second.write_bytes(b"second")

    with pytest.raises(ValueError, match="not byte-identical"):
        build_receipt(first, second, "b" * 40)


def test_invalid_commit_fails_closed(tmp_path: Path):
    first = tmp_path / "first.zip"
    second = tmp_path / "second.zip"
    first.write_bytes(b"same")
    second.write_bytes(b"same")

    with pytest.raises(ValueError, match="full lowercase Git SHA-1"):
        build_receipt(first, second, "not-a-commit")
