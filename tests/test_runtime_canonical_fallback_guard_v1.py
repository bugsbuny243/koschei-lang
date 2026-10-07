from __future__ import annotations

from types import SimpleNamespace

from koschei.ast_nodes import SourceLocation
from koschei.mir_extension_instructions_v4 import MirVariantIs
from koschei.type_system import BOOL


def _graph_with(instruction):
    block = SimpleNamespace(instructions=(instruction,))
    function = SimpleNamespace(blocks=(block,))
    module = SimpleNamespace(functions=(function,))
    return SimpleNamespace(
        assert_sealed=lambda: None,
        in_dependency_order=lambda: [module],
        modules={"root": module},
    )


def test_canonical_variant_fact_routes_to_budgeted_canonical_mir_not_ast(monkeypatch) -> None:
    import koschei.canonical_mir_budget_runtime_v1 as canonical_runtime
    import koschei.runtime_budget as runtime_budget

    loc = SourceLocation(1, 1)
    graph = _graph_with(MirVariantIs(2, 1, "Option::Some", BOOL, loc))

    monkeypatch.setattr(
        runtime_budget,
        "runtime_execution_mode",
        lambda _graph: "ast_compat_v1",
    )

    observed = {}

    def fake_canonical_run(mir_graph, argv, budget):
        observed["graph"] = mir_graph
        observed["argv"] = list(argv or [])
        observed["max_steps"] = budget.max_steps
        observed["max_call_depth"] = budget.max_call_depth
        return 23

    monkeypatch.setattr(
        canonical_runtime,
        "_run_budgeted_canonical_mir",
        fake_canonical_run,
    )

    result = runtime_budget.run_mir_with_budget(
        graph,
        ["arg"],
        max_steps=17,
        max_call_depth=3,
    )

    assert result == 23
    assert observed == {
        "graph": graph,
        "argv": ["arg"],
        "max_steps": 17,
        "max_call_depth": 3,
    }
