from pathlib import Path
import tempfile

from koschei.interpreter import KsUnit
from koschei.mir import require_mir
from koschei.mir_executor_v1 import execute_mir_v1
from koschei.mir_or_return_normalization_v1 import MirInterpolate
from koschei.modules import check_graph, load_graph


def _compiler_mir(source: str):
    directory = tempfile.TemporaryDirectory()
    path = Path(directory.name) / "interpolation.ks"
    path.write_text(source, encoding="utf-8")
    graph = load_graph(path)
    check_graph(graph)
    return directory, require_mir(graph)


def test_interpolated_string_has_no_ast_fallback_and_uses_mir_instruction():
    directory, mir = _compiler_mir(
        '''
fn main() {
    let value = 7
    println("value={value}")
}
'''
    )
    try:
        main = next(item for item in mir.root_module.functions if item.name == "main")
        instructions = [
            instruction
            for block in main.blocks
            for instruction in block.instructions
        ]
        assert main.resources.ast_fallbacks == 0
        assert sum(isinstance(item, MirInterpolate) for item in instructions) == 1
    finally:
        directory.cleanup()


def test_interpolated_string_executes_from_mir_v4(capsys):
    directory, mir = _compiler_mir(
        '''
fn main() {
    let value = 7
    println("value={value}")
}
'''
    )
    try:
        result = execute_mir_v1(mir)
        assert result is KsUnit
        assert capsys.readouterr().out == "value=7\n"
    finally:
        directory.cleanup()
