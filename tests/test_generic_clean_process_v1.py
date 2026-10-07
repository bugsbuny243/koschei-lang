from __future__ import annotations

import pathlib
import subprocess
import sys
import tempfile


REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]


def test_generic_function_executes_in_fresh_process_without_warmup() -> None:
    source_text = """fn first<T>(items: List<T>) -> Option<T> {
    return items.get(0)
}
fn main() {
    match first([7]) {
        Some(value) => println("{value}"),
        None => println("empty"),
    }
}
"""
    probe = r'''
import pathlib
import sys
from koschei.modules import check_graph, load_graph
from koschei.mir import require_mir
from koschei.runtime_boot_v1 import run_checked_mir

path = pathlib.Path(sys.argv[1])
graph = load_graph(path)
check_graph(graph)
mir = require_mir(graph)
try:
    raise SystemExit(run_checked_mir(mir, []))
except Exception as error:
    print(
        f"{type(error).__name__}: code={getattr(error, 'code', '')} message={getattr(error, 'message', str(error))!r}",
        file=sys.stderr,
    )
    raise
'''
    with tempfile.TemporaryDirectory() as directory:
        source = pathlib.Path(directory) / "main.ks"
        source.write_text(source_text, encoding="utf-8")
        result = subprocess.run(
            [sys.executable, "-c", probe, str(source)],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
        )

    assert result.returncode == 0, result.stderr
    assert result.stdout == "7\n"
