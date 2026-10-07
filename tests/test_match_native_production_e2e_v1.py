from __future__ import annotations

from koschei.mir import require_mir
from koschei.mir_extension_instructions_v4 import MirVariantConstruct
from koschei.mir_native_variant_construct_v1 import inspect_native_mir_support
from koschei.mir_scope_safety import inspect_mir_scope_safety
from koschei.modules import check_graph, load_graph
from koschei.runtime_budget import run_mir_with_budget, runtime_execution_mode


def _instructions(mir):
    return tuple(
        instruction
        for module in mir.in_dependency_order()
        for function in module.functions
        for block in function.blocks
        for instruction in block.instructions
    )


def _assert_native_admitted(mir) -> None:
    support = inspect_native_mir_support(mir)
    scope = inspect_mir_scope_safety(mir)
    assert support.supported, support.reasons
    assert scope.safe, scope.reasons
    assert runtime_execution_mode(mir) == "mir_native_v1"


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

    constructors = [
        item for item in _instructions(mir) if isinstance(item, MirVariantConstruct)
    ]
    assert [item.variant for item in constructors] == ["Option::Some"]
    _assert_native_admitted(mir)
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

    constructors = [
        item for item in _instructions(mir) if isinstance(item, MirVariantConstruct)
    ]
    assert [item.variant for item in constructors] == ["Result::Ok"]
    _assert_native_admitted(mir)
    assert run_mir_with_budget(mir) == 0
    assert capsys.readouterr().out == "7\n"


def test_user_enum_match_runs_source_to_native_with_exact_owner(tmp_path, capsys) -> None:
    source = tmp_path / "main.ks"
    source.write_text(
        """
enum State {
    Ready(Int),
    Idle,
}

fn main() {
    println(match Ready(99) {
        Ready(value) => value,
        Idle => 0,
    })
}
""".strip()
        + "\n",
        encoding="utf-8",
    )

    graph = load_graph(source)
    check_graph(graph)
    mir = require_mir(graph)

    constructors = [
        item for item in _instructions(mir) if isinstance(item, MirVariantConstruct)
    ]
    assert [item.variant for item in constructors] == ["State::Ready"]
    _assert_native_admitted(mir)
    assert run_mir_with_budget(mir) == 0
    assert capsys.readouterr().out == "99\n"


def test_payload_free_user_enum_value_is_canonicalized_before_match(tmp_path, capsys) -> None:
    source = tmp_path / "main.ks"
    source.write_text(
        """
enum State {
    Ready(Int),
    Idle,
}

fn main() {
    println(match Idle {
        Ready(value) => value,
        Idle => 5,
    })
}
""".strip()
        + "\n",
        encoding="utf-8",
    )

    graph = load_graph(source)
    check_graph(graph)
    mir = require_mir(graph)

    constructors = [
        item for item in _instructions(mir) if isinstance(item, MirVariantConstruct)
    ]
    assert [item.variant for item in constructors] == ["State::Idle"]
    assert constructors[0].source is None
    _assert_native_admitted(mir)
    assert run_mir_with_budget(mir) == 0
    assert capsys.readouterr().out == "5\n"
