from __future__ import annotations

import pytest

from koschei.ast_nodes import SourceLocation
from koschei.interpreter import EnumValue
from koschei.mir import require_mir
from koschei.mir_extension_instructions_v4 import MirVariantIs, MirVariantPayload
from koschei.mir_native_runtime import MirNativeRuntimeError, _MirExecutor
from koschei.modules import check_graph, load_graph
from koschei.type_system import BOOL, INT


def _executor_for_minimal_graph(tmp_path):
    path = tmp_path / "main.ks"
    path.write_text("fn main() {}\n", encoding="utf-8")
    graph = load_graph(path)
    check_graph(graph)
    mir = require_mir(graph)
    return mir, _MirExecutor(mir, max_steps=100, max_call_depth=8)


def test_native_variant_test_uses_exact_owner_and_variant(tmp_path) -> None:
    mir, executor = _executor_for_minimal_graph(tmp_path)
    loc = SourceLocation(1, 1)
    values = {1: EnumValue("Alpha", "Ready", 41)}

    executor._execute_instruction(
        MirVariantIs(2, 1, "Alpha::Ready", BOOL, loc),
        values,
        {},
        set(),
        mir.root,
    )
    executor._execute_instruction(
        MirVariantIs(3, 1, "Beta::Ready", BOOL, loc),
        values,
        {},
        set(),
        mir.root,
    )

    assert values[2] is True
    assert values[3] is False


def test_native_variant_payload_requires_exact_owner_and_variant(tmp_path) -> None:
    mir, executor = _executor_for_minimal_graph(tmp_path)
    loc = SourceLocation(1, 1)
    values = {1: EnumValue("Alpha", "Ready", 41)}

    executor._execute_instruction(
        MirVariantPayload(2, 1, "Alpha::Ready", INT, loc),
        values,
        {},
        set(),
        mir.root,
    )
    assert values[2] == 41

    with pytest.raises(MirNativeRuntimeError, match="failed closed"):
        executor._execute_instruction(
            MirVariantPayload(3, 1, "Beta::Ready", INT, loc),
            values,
            {},
            set(),
            mir.root,
        )


def test_native_variant_runtime_rejects_host_shape(tmp_path) -> None:
    mir, executor = _executor_for_minimal_graph(tmp_path)
    loc = SourceLocation(1, 1)
    values = {1: {"enum_name": "Alpha", "variant": "Ready", "payload": 41}}

    with pytest.raises(MirNativeRuntimeError, match="failed closed"):
        executor._execute_instruction(
            MirVariantIs(2, 1, "Alpha::Ready", BOOL, loc),
            values,
            {},
            set(),
            mir.root,
        )


def test_native_variant_runtime_rejects_visible_only_identity(tmp_path) -> None:
    mir, executor = _executor_for_minimal_graph(tmp_path)
    loc = SourceLocation(1, 1)
    values = {1: EnumValue("Alpha", "Ready", 41)}

    with pytest.raises(MirNativeRuntimeError, match="failed closed"):
        executor._execute_instruction(
            MirVariantIs(2, 1, "Ready", BOOL, loc),
            values,
            {},
            set(),
            mir.root,
        )
