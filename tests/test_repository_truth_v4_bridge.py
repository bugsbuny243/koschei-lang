from __future__ import annotations

from koschei.mir import MIR_VERSION
from tools import run_repository_truth_v4 as bridge


def test_repository_truth_bridge_uses_canonical_mir_version() -> None:
    patched = bridge.patched_verify_text()

    assert bridge.LEGACY_ASSERTION not in patched
    assert f'assert mir.get("version") == {MIR_VERSION}' in patched


def test_repository_truth_bridge_does_not_rewrite_other_gate_content() -> None:
    original = bridge.VERIFY.read_text(encoding="utf-8")
    patched = bridge.patched_verify_text()

    expected = original.replace(
        bridge.LEGACY_ASSERTION,
        f'assert mir.get("version") == {MIR_VERSION}',
        1,
    )
    assert patched == expected
