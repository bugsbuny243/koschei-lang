from pathlib import Path
import tempfile

from koschei.mir import require_mir
from koschei.mir_executor_v1 import execute_mir_v1
from koschei.mir_extension_instructions_v4 import MirIsRuntimeError
from koschei.mir_ir import MirBinary, MirBranch, MirCall
from koschei.modules import check_graph, load_graph


def _compiler_mir(source: str):
    directory = tempfile.TemporaryDirectory()
    path = Path(directory.name) / "short_circuit.ks"
    path.write_text(source, encoding="utf-8")
    graph = load_graph(path)
    check_graph(graph)
    return directory, require_mir(graph)


def _instructions(function):
    return [instruction for block in function.blocks for instruction in block.instructions]


def test_boolean_short_circuit_lowers_to_cfg_not_eager_mir_binary():
    directory, mir = _compiler_mir(
        '''
fn rhs() -> Bool {
    println("rhs")
    return true
}
fn main() {
    println(false && rhs())
    println(true || rhs())
}
'''
    )
    try:
        main = next(item for item in mir.root_module.functions if item.name == "main")
        instructions = _instructions(main)
        assert not any(
            isinstance(item, MirBinary) and item.operator in {"&&", "||"}
            for item in instructions
        )
        # Each short-circuit expression has one explicit runtime-error gate and
        # one ordinary Bool decision branch. Runtime does not infer continuation.
        assert sum(isinstance(item, MirIsRuntimeError) for item in instructions) == 2
        assert sum(isinstance(block.terminator, MirBranch) for block in main.blocks) == 4
        # The two rhs() call sites still exist in MIR, but each is isolated in a
        # branch that is unreachable for the constant LHS used by this test.
        assert sum(isinstance(item, MirCall) for item in instructions) >= 4
        assert main.resources.ast_fallbacks == 0
    finally:
        directory.cleanup()


def test_boolean_short_circuit_does_not_execute_rhs_on_skip_paths(capsys):
    directory, mir = _compiler_mir(
        '''
fn rhs() -> Bool {
    println("rhs")
    return true
}
fn main() {
    println(false && rhs())
    println(true || rhs())
}
'''
    )
    try:
        execute_mir_v1(mir)
        assert capsys.readouterr().out == "false\ntrue\n"
    finally:
        directory.cleanup()


def test_boolean_short_circuit_executes_rhs_exactly_when_required(capsys):
    directory, mir = _compiler_mir(
        '''
fn rhs_true() -> Bool {
    println("rhs-true")
    return true
}
fn rhs_false() -> Bool {
    println("rhs-false")
    return false
}
fn main() {
    println(true && rhs_true())
    println(false || rhs_false())
}
'''
    )
    try:
        execute_mir_v1(mir)
        assert capsys.readouterr().out == "rhs-true\ntrue\nrhs-false\nfalse\n"
    finally:
        directory.cleanup()
