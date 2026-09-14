from __future__ import annotations

from koschei.mir import require_mir
from koschei.mir_native_runtime import inspect_native_mir_support
from koschei.modules import check_graph, load_graph
from koschei.runtime_budget import run_mir_with_budget, runtime_execution_mode


def test_option_match_runs_source_to_native_without_ast_compat(tmp_path, capsys) -> None:
    source = tmp_path / "main.ks"
    source.write_text(
        """
fn main() {
    println(match Some(41) {
        Some(value) => value,
        None => 0,
    })
}
""".strip()
        + "\n",
        encoding="utf-8",
    )

    graph = load_graph(source)
    check_graph(graph)
    mir = require_mir(graph)

    support = inspect_native_mir_support(mir)
    assert support.supported, support.reasons
    assert runtime_execution_mode(mir) == "mir_native_v1"
    assert run_mir_with_budget(mir) == 0
    assert capsys.readouterr().out == "41\n"


def test_result_match_runs_source_to_native_without_ast_compat(tmp_path, capsys) -> None:
    source = tmp_path / "main.ks"
    source.write_text(
        """
fn main() {
    println(match Ok(7) {
        Ok(value) => value,
        Err(problem) => 0,
    })
}
""".strip()
        + "\n",
        encoding="utf-8",
    )

    graph = load_graph(source)
    check_graph(graph)
    mir = require_mir(graph)

    support = inspect_native_mir_support(mir)
    assert support.supported, support.reasons
    assert runtime_execution_mode(mir) == "mir_native_v1"
    assert run_mir_with_budget(mir) == 0
    assert capsys.readouterr().out == "7\n"
