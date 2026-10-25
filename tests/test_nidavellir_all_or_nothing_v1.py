"""Nidavellir: a value or a write is built completely or not at all.

In memory, a struct literal whose field fails is the Error itself in every
executor; no half-built struct is ever observable. On disk, `disk.write`
replaces a file in one rename after the new bytes reached the disk, so a
write that fails or is cut short leaves the previous file and no partial one.
"""
from __future__ import annotations

from contextlib import redirect_stderr, redirect_stdout
import errno
import io
import os
from pathlib import Path
import shutil
import stat
import subprocess
import tempfile
import unittest
from unittest import mock

from koschei import runtime_budget
from koschei.canonical_mir_budget_runtime_v1 import _run_budgeted_canonical_mir
from koschei.cli_entry import main as cli_main
from koschei.interpreter import DiskCaps, KsError
from koschei.modules import check_graph, load_graph
from koschei.runtime_budget import BudgetedInterpreter, RuntimeBudget

GO = shutil.which("go")

STRUCTS = """
struct Pair {
    label: String,
    count: Int,
}

fn build(label: String, count: Int) -> Pair or Error {
    return Pair { label: label, count: count + 1 }
}

fn main() {
    let max = 9223372036854775807
    let good = build("a", 1) or Pair { label: "fallback", count: 0 }
    println(good)
    let bad = build("b", max) or Pair { label: "fallback", count: 0 }
    println(bad)
    let direct = Pair { label: "c", count: max + 1 }
    println(direct)
    let recovered = direct or Pair { label: "rescued", count: 0 }
    println(recovered)
}
"""

STRUCTS_OUTPUT = (
    'Pair { label: "a", count: 2 }\n'
    'Pair { label: "fallback", count: 0 }\n'
    "KS3501: Int taşması: '+' işlemi işaretli 64-bit aralığın dışına çıktı.\n"
    'Pair { label: "rescued", count: 0 }\n'
)


def _leftovers(directory: Path) -> list[str]:
    return sorted(name for name in os.listdir(directory) if name.startswith(".ks-write-"))


class InMemoryConstructionTests(unittest.TestCase):
    def program(self) -> Path:
        temporary = tempfile.TemporaryDirectory(prefix="koschei-nidavellir-")
        self.addCleanup(temporary.cleanup)
        path = Path(temporary.name) / "main.ks"
        path.write_text(STRUCTS, encoding="utf-8")
        return path

    def test_failing_field_makes_the_whole_literal_an_error(self) -> None:
        path = self.program()
        stdout = io.StringIO()
        with redirect_stdout(stdout), redirect_stderr(io.StringIO()) as errors:
            self.assertEqual(cli_main(["run", str(path)]), 0, errors.getvalue())
        self.assertEqual(stdout.getvalue(), STRUCTS_OUTPUT)

        graph = load_graph(path)
        check_graph(graph)
        canonical = io.StringIO()
        with redirect_stdout(canonical):
            _run_budgeted_canonical_mir(graph.mir, [], RuntimeBudget())
        self.assertEqual(canonical.getvalue(), STRUCTS_OUTPUT)

        mir = graph.mir
        root = mir.root_module
        checked = io.StringIO()
        with redirect_stdout(checked):
            BudgetedInterpreter(
                root.program,
                [],
                namespaces=mir.namespaces(),
                imports=dict(root.imports),
                enums=mir.enums(),
                module_imports=mir.module_imports(),
                structs=mir.structs(),
                budget=runtime_budget.RuntimeBudget(),
            ).execute_main()
        self.assertEqual(checked.getvalue(), STRUCTS_OUTPUT)

    @unittest.skipUnless(GO, "Go toolchain is required")
    def test_native_binary_agrees(self) -> None:
        path = self.program()
        binary = path.parent / "app"
        with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()) as errors:
            self.assertEqual(cli_main(["build", str(path), "-o", str(binary)]), 0, errors.getvalue())
        completed = subprocess.run([str(binary)], capture_output=True, timeout=60, check=False)
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertEqual(completed.stdout.decode("utf-8"), STRUCTS_OUTPUT)


class AtomicDiskWriteTests(unittest.TestCase):
    def scope(self) -> Path:
        temporary = tempfile.TemporaryDirectory(prefix="koschei-nidavellir-disk-")
        self.addCleanup(temporary.cleanup)
        return Path(temporary.name)

    def test_write_replaces_content_and_leaves_nothing_behind(self) -> None:
        scope = self.scope()
        (scope / "data.txt").write_text("old", encoding="utf-8")
        capability = DiskCaps(str(scope))
        self.assertNotIsInstance(capability.write_file(str(scope / "data.txt"), "new"), KsError)
        self.assertNotIsInstance(capability.write_file(str(scope / "fresh.txt"), "çğ"), KsError)
        self.assertEqual((scope / "data.txt").read_text(encoding="utf-8"), "new")
        self.assertEqual((scope / "fresh.txt").read_text(encoding="utf-8"), "çğ")
        self.assertEqual(stat.S_IMODE((scope / "fresh.txt").stat().st_mode), 0o600)
        self.assertEqual(_leftovers(scope), [])

    def test_failed_write_keeps_the_previous_file(self) -> None:
        scope = self.scope()
        target = scope / "data.txt"
        target.write_text("previous", encoding="utf-8")
        capability = DiskCaps(str(scope))
        no_space = OSError(errno.ENOSPC, os.strerror(errno.ENOSPC))
        for failing in ("os.fsync", "os.rename"):
            with self.subTest(failing=failing):
                with mock.patch(failing, side_effect=no_space):
                    result = capability.write_file(str(target), "half-written" * 1000)
                self.assertIsInstance(result, KsError)
                self.assertIn("Dosya yazılamadı", result.message)
                self.assertEqual(target.read_text(encoding="utf-8"), "previous")
                self.assertEqual(_leftovers(scope), [])

    def test_existing_permissions_are_kept(self) -> None:
        scope = self.scope()
        target = scope / "shared.txt"
        target.write_text("old", encoding="utf-8")
        target.chmod(0o644)
        capability = DiskCaps(str(scope))
        self.assertNotIsInstance(capability.write_file(str(target), "new"), KsError)
        self.assertEqual(stat.S_IMODE(target.stat().st_mode), 0o644)

    def test_hard_link_to_another_file_is_never_written_through(self) -> None:
        scope = self.scope()
        outside = self.scope()
        secret = outside / "secret.txt"
        secret.write_text("DOKUNMA", encoding="utf-8")
        try:
            os.link(secret, scope / "link.txt")
        except OSError:
            self.skipTest("hard links across these directories are not available")
        capability = DiskCaps(str(scope))
        self.assertNotIsInstance(capability.write_file(str(scope / "link.txt"), "YENI"), KsError)
        self.assertEqual(secret.read_text(encoding="utf-8"), "DOKUNMA")
        self.assertEqual((scope / "link.txt").read_text(encoding="utf-8"), "YENI")

    def test_symlink_and_directory_targets_are_refused(self) -> None:
        scope = self.scope()
        outside = self.scope()
        (outside / "target.txt").write_text("DOKUNMA", encoding="utf-8")
        try:
            os.symlink(outside / "target.txt", scope / "link.txt")
        except (OSError, NotImplementedError):
            self.skipTest("symlinks are not available")
        (scope / "folder").mkdir()
        capability = DiskCaps(str(scope))
        refused = capability.write_file(str(scope / "link.txt"), "YENI")
        self.assertIsInstance(refused, KsError)
        self.assertIn("KS3402", refused.message)
        self.assertEqual((outside / "target.txt").read_text(encoding="utf-8"), "DOKUNMA")
        folder = capability.write_file(str(scope / "folder"), "YENI")
        self.assertIsInstance(folder, KsError)
        self.assertEqual(folder.message, f"Dosya yazılamadı: [Errno {errno.EISDIR}] {os.strerror(errno.EISDIR)}: 'folder'")
        self.assertEqual(_leftovers(scope), [])

    def test_program_writes_then_reads(self) -> None:
        scope = self.scope()
        source = scope / "main.ks"
        source.write_text(
            "fn main(caps: SystemCaps) {\n"
            '    let disk = caps.disk.allow(".") or return\n'
            '    disk.write("note.txt", "ilk") or return\n'
            '    disk.write("note.txt", "ikinci") or return\n'
            '    let text = disk.read("note.txt") or "?"\n'
            "    println(text)\n"
            "}\n",
            encoding="utf-8",
        )
        previous = os.getcwd()
        os.chdir(scope)
        try:
            stdout = io.StringIO()
            with redirect_stdout(stdout), redirect_stderr(io.StringIO()) as errors:
                code = cli_main(["run", str(source)])
        finally:
            os.chdir(previous)
        self.assertEqual(code, 0, errors.getvalue())
        self.assertEqual(stdout.getvalue(), "ikinci\n")
        self.assertEqual(_leftovers(scope), [])


if __name__ == "__main__":
    unittest.main()
