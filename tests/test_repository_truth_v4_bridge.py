from __future__ import annotations

from tools import run_repository_truth_v4 as bridge


def test_repository_truth_bridge_is_transparent_wrapper() -> None:
    assert bridge.VERIFY.is_file()
    assert not hasattr(bridge, "patched_verify_text")
    assert not hasattr(bridge, "LEGACY_ASSERTION")


def test_repository_truth_script_uses_canonical_mir_version_directly() -> None:
    text = bridge.VERIFY.read_text(encoding="utf-8")

    assert "from koschei.mir import MIR_VERSION" in text
    assert 'assert mir.get("version") == MIR_VERSION' in text
    assert 'assert mir.get("version") == 3' not in text
