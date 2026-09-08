from pathlib import Path
import tempfile

from koschei.interpreter import run_mir
from koschei.mir import require_mir
from koschei.mir_executor_v1 import execute_mir_v1
from koschei.mir_extension_instructions_v4 import MirIsRuntimeError
from koschei.mir_ir import MirBranch, MirReturn
from koschei.modules import check_graph, load_graph


def _compiler_mir(source: str):
    directory = tempfile.TemporaryDirectory()
    path = Path(directory.name) / "statement_error.ks"
    path.write_text(source, encoding="utf-8")
    graph = load_graph(path)
    check_graph(graph)
    return directory, require_mir(graph)


def _instructions(function):
    return [instruction for block in function.blocks for instruction in block.instructions]


def test_if_error_condition_continues_enclosing_block_in_mir(capsys):
    source = '''
fn condition() -> Bool or Error {
    return Error("condition-error")
}
fn main() {
    if condition() {
        println("wrong-branch")
    }
    println("after-if")
}
'''
    directory, mir = _compiler_mir(source)
    try:
        assert run_mir(mir, []) == 0
        assert capsys.readouterr().out == "after-if\n"

        main = next(item for item in mir.root_module.functions if item.name == "main")
        instructions = _instructions(main)
        assert any(isinstance(item, MirIsRuntimeError) for item in instructions)
        assert sum(isinstance(block.terminator, MirBranch) for block in main.blocks) >= 2

        execute_mir_v1(mir)
        assert capsys.readouterr().out == "after-if\n"
    finally:
        directory.cleanup()


def test_while_error_condition_exits_loop_and_continues_enclosing_block(capsys):
    source = '''
fn condition() -> Bool or Error {
    return Error("condition-error")
}
fn main() {
    while condition() {
        println("wrong-loop")
    }
    println("after-while")
}
'''
    directory, mir = _compiler_mir(source)
    try:
        assert run_mir(mir, []) == 0
        assert capsys.readouterr().out == "after-while\n"

        main = next(item for item in mir.root_module.functions if item.name == "main")
        instructions = _instructions(main)
        assert any(isinstance(item, MirIsRuntimeError) for item in instructions)
        assert not any(
            isinstance(block.terminator, MirReturn)
            and block.terminator.value is not None
            for block in main.blocks
        )

        execute_mir_v1(mir)
        assert capsys.readouterr().out == "after-while\n"
    finally:
        directory.cleanup()


def test_while_body_error_terminates_loop_statement_and_continues_enclosing_block(capsys):
    source = '''
fn body_error() -> Error {
    println("body-once")
    return Error("body-error")
}
fn main() {
    while true {
        body_error()
    }
    println("after-while")
}
'''
    directory, mir = _compiler_mir(source)
    try:
        assert run_mir(mir, []) == 0
        assert capsys.readouterr().out == "body-once\nafter-while\n"

        main = next(item for item in mir.root_module.functions if item.name == "main")
        instructions = _instructions(main)
        assert sum(isinstance(item, MirIsRuntimeError) for item in instructions) >= 2

        execute_mir_v1(mir)
        assert capsys.readouterr().out == "body-once\nafter-while\n"
    finally:
        directory.cleanup()
