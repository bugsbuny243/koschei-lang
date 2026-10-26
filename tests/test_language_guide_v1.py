"""Every program in the language guides runs and prints what the guide says.

A ```ks block that defines `main` must pass the checker. When it is followed
by an ```output block, `ks run` must print exactly that block, and when the
native backend admits the program the binary must print the same bytes.
"""
from __future__ import annotations

from contextlib import redirect_stderr, redirect_stdout
import io
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import unittest

from koschei.cli_entry import main as cli_main
from koschei.mir_go_native import inspect_mir_go_support
from koschei.modules import check_graph, load_graph

ROOT = Path(__file__).resolve().parent.parent
GUIDES = (
    ROOT / "docs" / "guide" / "LANGUAGE_GUIDE.en.md",
    ROOT / "docs" / "guide" / "LANGUAGE_GUIDE.tr.md",
)
GO = shutil.which("go")
_BLOCK = re.compile(r"```(ks|output)\n(.*?)```", re.DOTALL)


def guide_programs(path: Path) -> list[tuple[str, str | None]]:
    programs: list[tuple[str, str | None]] = []
    for kind, body in _BLOCK.findall(path.read_text(encoding="utf-8")):
        if kind == "ks":
            programs.append((body, None))
        elif programs and programs[-1][1] is None:
            programs[-1] = (programs[-1][0], body)
    return [item for item in programs if "fn main(" in item[0]]


class LanguageGuideTests(unittest.TestCase):
    def test_every_guide_program_runs_as_documented(self) -> None:
        for guide in GUIDES:
            programs = guide_programs(guide)
            self.assertGreaterEqual(len(programs), 10, guide)
            for index, (source, expected) in enumerate(programs, start=1):
                with self.subTest(guide=guide.name, program=index):
                    self.check_program(source, expected)

    def test_both_editions_run_the_same_programs(self) -> None:
        english, turkish = (guide_programs(path) for path in GUIDES)
        self.assertEqual(english, turkish)

    def check_program(self, source: str, expected: str | None) -> None:
        with tempfile.TemporaryDirectory(prefix="koschei-guide-") as directory:
            path = Path(directory) / "main.ks"
            path.write_text(source, encoding="utf-8")
            graph = load_graph(path)
            check_graph(graph)
            if expected is None:
                return
            stdout = io.StringIO()
            with redirect_stdout(stdout), redirect_stderr(io.StringIO()) as errors:
                code = cli_main(["run", str(path)])
            self.assertEqual(code, 0, errors.getvalue())
            self.assertEqual(stdout.getvalue(), expected)
            if GO is None or not inspect_mir_go_support(graph.mir).supported:
                return
            binary = Path(directory) / "app"
            with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()) as errors:
                self.assertEqual(
                    cli_main(["build", str(path), "-o", str(binary)]), 0, errors.getvalue()
                )
            completed = subprocess.run(
                [str(binary)], stdin=subprocess.DEVNULL, capture_output=True, timeout=60, check=False
            )
            self.assertEqual(completed.returncode, 0, completed.stderr)
            self.assertEqual(completed.stdout.decode("utf-8"), expected)


if __name__ == "__main__":
    unittest.main()
