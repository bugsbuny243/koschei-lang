from __future__ import annotations

import io
import json
import os
import pathlib
import shutil
import subprocess
import tempfile
import threading
import time
import unittest
from contextlib import redirect_stdout
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from unittest.mock import patch

from koschei.codegen_go import generate_go
from koschei.interpreter import Interpreter
from koschei.parser import parse
from koschei.semantic import SemanticError, check

GO_BINARY = shutil.which("go")


def compile_source(source: str) -> str:
    program = parse(source)
    check(program)
    return generate_go(program)


def ks_string(value: str) -> str:
    return json.dumps(value, ensure_ascii=False)


class _Handler(BaseHTTPRequestHandler):
    redirect_target = ""

    def do_GET(self) -> None:  # noqa: N802 - stdlib callback adı
        if self.path == "/ok":
            body = "net-ok".encode()
            self.send_response(200)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        if self.path == "/redirect-out":
            self.send_response(302)
            self.send_header("Location", self.redirect_target)
            self.end_headers()
            return
        body = "secret".encode()
        self.send_response(200)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format: str, *args: object) -> None:
        return


@unittest.skipUnless(GO_BINARY, "Go kurulu değil; native capability testleri atlandı")
class NativeCapabilityCodegenTests(unittest.TestCase):
    def build(self, source: str, *, check_semantics: bool = True) -> pathlib.Path:
        program = parse(source)
        if check_semantics:
            check(program)
        generated = generate_go(program)
        workspace = tempfile.TemporaryDirectory(prefix="koschei-native-cap-")
        self.addCleanup(workspace.cleanup)
        directory = pathlib.Path(workspace.name)
        (directory / "main.go").write_text(generated, encoding="utf-8")
        (directory / "go.mod").write_text(
            "module koscheicapability\n\ngo 1.21\n", encoding="utf-8"
        )
        binary = directory / "program"
        completed = subprocess.run(
            [GO_BINARY, "build", "-o", str(binary), "."],
            cwd=directory,
            capture_output=True,
            text=True,
            timeout=180,
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        return binary

    def execute(
        self,
        source: str,
        *,
        env: dict[str, str] | None = None,
        check_semantics: bool = True,
    ) -> subprocess.CompletedProcess[str]:
        binary = self.build(source, check_semantics=check_semantics)
        process_env = os.environ.copy()
        process_env.update(env or {})
        return subprocess.run(
            [str(binary)],
            capture_output=True,
            text=True,
            timeout=60,
            env=process_env,
        )

    def test_runtime_demo_matches_interpreter_with_injected_system_caps(self) -> None:
        source = pathlib.Path("examples/runtime_demo.ks").read_text(encoding="utf-8")
        program = parse(source)
        check(program)
        interpreted = io.StringIO()
        with patch.dict(os.environ, {"KOSCHEI_RUNTIME_NAME": "Onur"}, clear=False):
            with redirect_stdout(interpreted):
                Interpreter(program, []).execute_main()

        completed = self.execute(source, env={"KOSCHEI_RUNTIME_NAME": "Onur"})
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertEqual(completed.stdout, interpreted.getvalue())

    def test_environment_scope_and_missing_value_match_interpreter_contract(self) -> None:
        source = """
        fn main(caps: SystemCaps) {
            let present = caps.env.allow("KOSCHEI_NATIVE_PRESENT")
            let missing = caps.env.allow("KOSCHEI_NATIVE_MISSING")
            let first = present.get() or "missing"
            let second = missing.get() or "fallback"
            println("{first}|{second}")
        }
        """
        completed = self.execute(source, env={"KOSCHEI_NATIVE_PRESENT": "ready"})
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertEqual(completed.stdout, "ready|fallback\n")

    def test_disk_scope_symlink_read_write_list_and_delete_are_enforced(self) -> None:
        with tempfile.TemporaryDirectory(prefix="koschei-disk-scope-") as scope:
            with tempfile.TemporaryDirectory(prefix="koschei-disk-outside-") as outside:
                scope_path = pathlib.Path(scope)
                outside_path = pathlib.Path(outside)
                (scope_path / "b.txt").write_text("inside", encoding="utf-8")
                (scope_path / "a.txt").write_text("alpha", encoding="utf-8")
                (scope_path / "empty").mkdir()
                secret = outside_path / "secret.txt"
                secret.write_text("SECRET", encoding="utf-8")
                link = scope_path / "link.txt"
                try:
                    link.symlink_to(secret)
                except (OSError, NotImplementedError):
                    self.skipTest("Sembolik bağ oluşturulamıyor")

                source = f"""
                fn main(caps: SystemCaps) {{
                    let disk = caps.disk.allow({ks_string(scope)})
                    let inside = disk.read({ks_string(str(scope_path / 'b.txt'))}) or "ERR"
                    let outside = disk.read({ks_string(str(secret))}) or "BLOCKED"
                    let linked = disk.read({ks_string(str(link))}) or "SYMLINK"
                    let wrote = disk.write({ks_string(str(scope_path / 'out.txt'))}, "written") or return Error("write")
                    let names = disk.list({ks_string(scope)}) or return Error("list")
                    let removed_file = disk.delete({ks_string(str(scope_path / 'b.txt'))}) or return Error("delete-file")
                    let removed_dir = disk.delete({ks_string(str(scope_path / 'empty'))}) or return Error("delete-dir")
                    println("{{inside}}|{{outside}}|{{linked}}|{{names}}")
                }}
                """
                completed = self.execute(source)
                self.assertEqual(completed.returncode, 0, completed.stderr)
                self.assertIn("inside|BLOCKED|SYMLINK|", completed.stdout)
                self.assertIn('"a.txt"', completed.stdout)
                self.assertIn('"b.txt"', completed.stdout)
                self.assertEqual(
                    (scope_path / "out.txt").read_text(encoding="utf-8"), "written"
                )
                self.assertFalse((scope_path / "b.txt").exists())
                self.assertFalse((scope_path / "empty").exists())
                self.assertEqual(secret.read_text(encoding="utf-8"), "SECRET")


    def test_disk_symlink_swap_race_never_reads_outside_secret(self) -> None:
        with tempfile.TemporaryDirectory(prefix="koschei-race-scope-") as scope:
            with tempfile.TemporaryDirectory(prefix="koschei-race-outside-") as outside:
                scope_path = pathlib.Path(scope)
                secret = pathlib.Path(outside) / "secret.txt"
                secret.write_text("SECRET", encoding="utf-8")
                target = scope_path / "victim.txt"
                target.write_text("SAFE", encoding="utf-8")

                source = f"""
                fn main(caps: SystemCaps) {{
                    let disk = caps.disk.allow({ks_string(scope)})
                    let mut index = 0
                    while index < 2000 {{
                        let value = disk.read({ks_string(str(target))}) or "BLOCKED"
                        if value == "SECRET" {{
                            println("LEAK")
                        }}
                        index = index + 1
                    }}
                    println("DONE")
                }}
                """
                binary = self.build(source)
                stop = threading.Event()

                def swap_target() -> None:
                    while not stop.is_set():
                        try:
                            target.unlink(missing_ok=True)
                            target.symlink_to(secret)
                        except (FileExistsError, FileNotFoundError, OSError):
                            pass
                        try:
                            target.unlink(missing_ok=True)
                            descriptor = os.open(
                                target,
                                os.O_WRONLY | os.O_CREAT | os.O_EXCL,
                                0o600,
                            )
                            try:
                                os.write(descriptor, b"SAFE")
                            finally:
                                os.close(descriptor)
                        except (FileExistsError, FileNotFoundError, OSError):
                            pass

                attacker = threading.Thread(target=swap_target, daemon=True)
                attacker.start()
                time.sleep(0.01)
                try:
                    completed = subprocess.run(
                        [str(binary)],
                        capture_output=True,
                        text=True,
                        timeout=60,
                    )
                finally:
                    stop.set()
                    attacker.join(timeout=2)

                self.assertEqual(completed.returncode, 0, completed.stderr)
                self.assertNotIn("LEAK", completed.stdout)
                self.assertEqual(completed.stdout.splitlines()[-1], "DONE")
                self.assertEqual(secret.read_text(encoding="utf-8"), "SECRET")

    def test_read_only_disk_capability_denies_write(self) -> None:
        with tempfile.TemporaryDirectory(prefix="koschei-readonly-") as scope:
            target = pathlib.Path(scope) / "new.txt"
            source = f"""
            fn main(caps: SystemCaps) {{
                let disk = caps.disk.allow_read_only({ks_string(scope)})
                let result = disk.write({ks_string(str(target))}, "nope") or "DENIED"
                println(result)
            }}
            """
            with self.assertRaises(SemanticError) as context:
                check(parse(source))
            self.assertEqual(context.exception.code, "KS2404")

            # Savunma derinliği: semantic kapısı atlatılsa bile native runtime
            # read-only jetonu yazma jetonuna çeviremez.
            completed = self.execute(source, check_semantics=False)
            self.assertEqual(completed.returncode, 0, completed.stderr)
            self.assertEqual(completed.stdout, "DENIED\n")
            self.assertFalse(target.exists())

    def test_network_origin_and_redirect_scope_are_enforced(self) -> None:
        outside = ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
        outside_thread = threading.Thread(target=outside.serve_forever, daemon=True)
        outside_thread.start()
        self.addCleanup(outside.server_close)
        self.addCleanup(outside.shutdown)

        allowed = ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
        allowed_thread = threading.Thread(target=allowed.serve_forever, daemon=True)
        allowed_thread.start()
        self.addCleanup(allowed.server_close)
        self.addCleanup(allowed.shutdown)

        allowed_origin = f"http://127.0.0.1:{allowed.server_port}"
        outside_url = f"http://127.0.0.1:{outside.server_port}/secret"
        _Handler.redirect_target = outside_url
        source = f"""
        fn main(caps: SystemCaps) {{
            let net = caps.net.allow({ks_string(allowed_origin)})
            let response = net.get({ks_string(allowed_origin + '/ok')}) or return Error("allowed")
            let body = response.text()
            let direct = net.get({ks_string(outside_url)}) or "DIRECT-BLOCKED"
            let redirect = net.get({ks_string(allowed_origin + '/redirect-out')}) or "REDIRECT-BLOCKED"
            println("{{body}}|{{direct}}|{{redirect}}")
        }}
        """
        completed = self.execute(source)
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertEqual(
            completed.stdout,
            "net-ok|DIRECT-BLOCKED|REDIRECT-BLOCKED\n",
        )

    def test_dynamic_file_scheme_cannot_bridge_network_to_disk(self) -> None:
        source = """
        fn main(caps: SystemCaps) {
            let origin = "file://localhost"
            let net = caps.net.allow(origin)
            let result = net.get("file://localhost/etc/passwd") or "BLOCKED"
            println(result)
        }
        """
        completed = self.execute(source)
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertEqual(completed.stdout, "BLOCKED\n")

    def test_process_capability_remains_fail_closed(self) -> None:
        source = """
        fn main(caps: SystemCaps) {
            let process = caps.process.allow("echo")
            let result = process.run("hello") or "BLOCKED"
            println(result)
        }
        """
        completed = self.execute(source)
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertEqual(completed.stdout, "BLOCKED\n")


if __name__ == "__main__":
    unittest.main()
