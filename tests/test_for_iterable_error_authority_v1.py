from pathlib import Path
import tempfile

from koschei.ast_nodes import (
    Block,
    ExpressionStatement,
    ForStatement,
    FunctionDeclaration,
    Identifier,
    Parameter,
    Program,
    SourceLocation,
    TypeRef,
)
from koschei.interpreter import run_mir
from koschei.mir import require_mir
from koschei.mir_executor_v1 import execute_mir_v1
from koschei.mir_extension_instructions_v4 import MirIsRuntimeError
from koschei.mir_ir import MirAstFallback, MirBranch, MirIterInit
from koschei.modules import check_graph, load_graph
from koschei.typed_hir import lower_typed_hir
from koschei.type_system import render_type


def _loc(column: int = 1) -> SourceLocation:
    return SourceLocation(1, column)


def _instructions(function):
    return [instruction for block in function.blocks for instruction in block.instructions]


def test_typed_hir_checks_for_body_from_error_bearing_list_success_type():
    location = _loc()
    iterable = Identifier("items", _loc(4))
    body_value = Identifier("item", _loc(12))
    loop = ForStatement(
        "item",
        iterable,
        Block((ExpressionStatement(body_value, _loc(12)),)),
        _loc(6),
    )
    function = FunctionDeclaration(
        "consume",
        (Parameter("items", TypeRef(("List<Int>", "Error"), location), location),),
        None,
        Block((loop,)),
        location,
    )

    report = lower_typed_hir(Program((function,)))

    assert tuple(render_type(item) for item in report.binding_types("item")) == ("Int",)
    body_fact = next(item for item in report.expressions if item.expression is body_value)
    assert render_type(body_fact.type) == "Int"


def test_for_iterable_error_skips_iterator_and_continues_enclosing_block(capsys):
    source = '''
fn items() -> List<Int> or Error {
    return Error("iterable-error")
}
fn main() {
    for item in items() {
        println("wrong-loop")
    }
    println("after-for")
}
'''
    directory = tempfile.TemporaryDirectory()
    path = Path(directory.name) / "for_iterable_error.ks"
    path.write_text(source, encoding="utf-8")
    try:
        graph = load_graph(path)
        check_graph(graph)
        mir = require_mir(graph)

        assert run_mir(mir, []) == 0
        assert capsys.readouterr().out == "after-for\n"

        main = next(item for item in mir.root_module.functions if item.name == "main")
        instructions = _instructions(main)
        assert any(isinstance(item, MirIsRuntimeError) for item in instructions)
        assert any(isinstance(item, MirIterInit) for item in instructions)
        assert any(isinstance(block.terminator, MirBranch) for block in main.blocks)
        assert not any(isinstance(item, MirAstFallback) for item in instructions)

        execute_mir_v1(mir)
        assert capsys.readouterr().out == "after-for\n"
    finally:
        directory.cleanup()
