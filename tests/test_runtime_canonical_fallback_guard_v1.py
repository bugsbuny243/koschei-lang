from __future__ import annotations

from types import SimpleNamespace

import pytest

from koschei.ast_nodes import SourceLocation
from koschei.interpreter import KoscheiRuntimeError
from koschei.mir_extension_instructions_v4 import MirVariantIs
from koschei.runtime_budget import run_mir_with_budget
from koschei.type_system import BOOL


def _graph_with(instruction):
    block = SimpleNamespace(instructions=(instruction,))
    function = SimpleNamespace(blocks=(block,))
    module = SimpleNamespace(functions=(function,))
    return SimpleNamespace(
        assert_sealed=lambda: None,
        in_dependency_order=lambda: [module],
    )


def test_canonical_variant_fact_may_not_fall_back_to_ast(monkeypatch) -> None:
    import koschei.runtime_budget as runtime_budget

    loc = SourceLocation(1, 1)
    graph = _graph_with(MirVariantIs(2, 1, "Option::Some", BOOL, loc))

    monkeypatch.setattr(
        runtime_budget,
        "runtime_execution_mode",
        lambda _graph: "ast_compat_v1",
    )
    monkeypatch.setattr(
        runtime_budget,
        "inspect_native_mir_support",
        lambda _graph: SimpleNamespace(reasons=("synthetic native blocker",)),
    )
    monkeypatch.setattr(
        runtime_budget,
        "inspect_mir_scope_safety",
        lambda _graph: SimpleNamespace(safe=True, reasons=()),
    )

    with pytest.raises(
        KoscheiRuntimeError,
        match="AST compatibility fallback is forbidden",
    ):
        run_mir_with_budget(graph)
