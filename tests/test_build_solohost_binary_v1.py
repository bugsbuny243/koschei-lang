from __future__ import annotations

from pathlib import Path

import pytest

from tools.build_solohost_binary_v1 import (
    SoloHostBinaryBuildError,
    _candidate_binaries,
)


def _touch(path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"candidate")
    return path.resolve()


def test_onefile_selects_root_customer_binary_and_ignores_dist_helper(tmp_path: Path) -> None:
    customer = _touch(tmp_path / "ks")
    _touch(tmp_path / "solohost_binary_entry_v1.dist" / "ks.bin")

    assert _candidate_binaries(tmp_path, mode="onefile") == [customer]


def test_onefile_preserves_fail_closed_ambiguity_for_multiple_root_candidates(tmp_path: Path) -> None:
    first = _touch(tmp_path / "ks")
    second = _touch(tmp_path / "ks.bin")

    assert _candidate_binaries(tmp_path, mode="onefile") == sorted([first, second])


def test_standalone_selects_direct_dist_entrypoint_and_ignores_nested_helpers(tmp_path: Path) -> None:
    customer = _touch(tmp_path / "solohost_binary_entry_v1.dist" / "ks")
    _touch(tmp_path / "solohost_binary_entry_v1.dist" / "internal" / "ks.bin")
    _touch(tmp_path / "ks")

    assert _candidate_binaries(tmp_path, mode="standalone") == [customer]


def test_candidate_selection_rejects_unknown_mode(tmp_path: Path) -> None:
    with pytest.raises(SoloHostBinaryBuildError, match="mode must be standalone or onefile"):
        _candidate_binaries(tmp_path, mode="other")
