from __future__ import annotations

import io
import socket
import subprocess
import tempfile
import threading
import time
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
import shutil

from koschei.capabilities import analyze_graph
from koschei.modules import check_graph
from koschei.workspace import WorkspaceError, load_workspace, write_workspace_lock
from koschei.workspace_execution import (
    build_locked_workspace_package,
    run_locked_workspace_package,
    verify_workspace_build,
)
from koschei.workspace_modules import load_workspace_member_graph
from koschei.workspace_package_lock import build_workspace_package_lock


REPO_ROOT = Path(__file__).resolve().parents[1]
REFERENCE = REPO_ROOT / "examples" / "production_reference_v1"
REPORT = (
    "trade quantity=25 price=10100 notional=252500 buyer_cash=-252626 "
    "seller_cash=252450 fees=176 balanced=true"
)
EXPECTED_STATE = '{"a":1,"b":2}\n' + REPORT
EXPECTED_OUTPUT = EXPECTED_STATE + "\n"


def _free_loopback_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        probe.bind(("127.0.0.1", 0))
        return int(probe.getsockname()[1])


def _copy_reference_with_runtime(
    port: int,
) -> tuple[tempfile.TemporaryDirectory[str], Path, Path]:
    temporary = tempfile.TemporaryDirectory()
    root = Path(temporary.name) / "production_reference_v1"
    shutil.copytree(REFERENCE, root)
    state_dir = root / "runtime-state"
    state_dir.mkdir()
    state_path = state_dir / "order-state.txt"

    ingress = root / "realms" / "http_ingress" / "matter.ks"
    source = ingress.read_text(encoding="utf-8")
    source = source.replace(
        '"127.0.0.1:18080"',
        f'"localhost:{port}"',
        1,
    )
    source = source.replace(
        '"/tmp/koschei-production-reference/state.txt"',
        f'"{state_path}"',
        1,
    )
    ingress.write_text(source, encoding="utf-8")
    return temporary, root, state_path


def _lock(root: Path):
    workspace = load_workspace(root)
    lock = build_workspace_package_lock(workspace)
    write_workspace_lock(lock, root / "koschei.workspace.lock.json")
    return workspace, lock


def _request() -> bytes:
    body = b'{"b":2,"a":1}'
    return (
        b"POST /orders HTTP/1.1\r\n"
        b"Host: localhost\r\n"
        + f"Content-Length: {len(body)}\r\n".encode("ascii")
        + b"\r\n"
        + body
    )


def _connect_thread(port: int, thread: threading.Thread) -> socket.socket:
    deadline = time.monotonic() + 3.0
    last_error: OSError | None = None
    while time.monotonic() < deadline:
        if not thread.is_alive():
            break
        try:
            return socket.create_connection(("127.0.0.1", port), timeout=0.2)
        except OSError as error:
            last_error = error
            time.sleep(0.01)
    raise AssertionError(f"workspace ingress listener did not become ready: {last_error}")


def _connect_process(port: int, process: subprocess.Popen[str]) -> socket.socket:
    deadline = time.monotonic() + 4.0
    last_error: OSError | None = None
    while time.monotonic() < deadline:
        if process.poll() is not None:
            break
        try:
            return socket.create_connection(("127.0.0.1", port), timeout=0.2)
        except OSError as error:
            last_error = error
            time.sleep(0.01)
    stdout, stderr = process.communicate(timeout=1)
    raise AssertionError(
        f"native workspace ingress listener did not become ready: {last_error}; "
        f"returncode={process.returncode}; stdout={stdout!r}; stderr={stderr!r}"
    )


class ProductionReferenceHttpIngressV1Tests(unittest.TestCase):
    def test_ingress_composes_serve_and_persist_without_contaminating_worker(self) -> None:
        workspace = load_workspace(REFERENCE)
        ingress = load_workspace_member_graph(workspace, "http_ingress")
        worker = load_workspace_member_graph(workspace, "order_worker")
        store = load_workspace_member_graph(workspace, "state_store")
        check_graph(ingress)
        check_graph(worker)
        check_graph(store)

        self.assertEqual(len(ingress.modules), 13)
        self.assertEqual(analyze_graph(ingress).domains(), ["serve", "persist"])
        self.assertEqual(analyze_graph(store).domains(), ["persist"])
        self.assertEqual(analyze_graph(worker).domains(), [])

    def test_locked_workspace_http_result_is_atomically_persisted_and_reloaded(self) -> None:
        port = _free_loopback_port()
        temporary, root, state_path = _copy_reference_with_runtime(port)
        self.addCleanup(temporary.cleanup)
        workspace, _ = _lock(root)

        output = io.StringIO()
        error = io.StringIO()
        result: dict[str, int] = {}

        def execute() -> None:
            with redirect_stdout(output), redirect_stderr(error):
                result["code"] = run_locked_workspace_package(
                    workspace,
                    "http_ingress",
                )

        thread = threading.Thread(target=execute, daemon=True)
        thread.start()
        with _connect_thread(port, thread) as client:
            client.settimeout(2.0)
            client.sendall(_request())
            response = bytearray()
            while True:
                chunk = client.recv(4096)
                if not chunk:
                    break
                response.extend(chunk)

        thread.join(timeout=3.0)
        self.assertFalse(thread.is_alive(), "locked workspace ingress did not finish")
        self.assertEqual(result.get("code"), 0, error.getvalue())
        self.assertEqual(error.getvalue(), "")
        self.assertEqual(output.getvalue(), EXPECTED_OUTPUT)
        self.assertEqual(state_path.read_text(encoding="utf-8"), EXPECTED_STATE)
        self.assertEqual(state_path.stat().st_mode & 0o777, 0o600)
        self.assertIn(b"HTTP/1.1 200 OK\r\n", response)
        self.assertTrue(response.endswith(b"\r\n\r\naccepted"), response)

    def test_state_store_source_drift_fails_before_listener_or_state_mutation(self) -> None:
        port = _free_loopback_port()
        temporary, root, state_path = _copy_reference_with_runtime(port)
        self.addCleanup(temporary.cleanup)
        workspace, _ = _lock(root)
        store = root / "realms" / "state_store" / "matter.ks"
        store.write_text(
            store.read_text(encoding="utf-8").replace(
                "return payload",
                'return "tampered"',
                1,
            ),
            encoding="utf-8",
        )

        with self.assertRaisesRegex(WorkspaceError, "state_store"):
            run_locked_workspace_package(workspace, "http_ingress")
        self.assertFalse(state_path.exists())

    @unittest.skipUnless(shutil.which("go"), "Go is required for native persistence parity")
    @unittest.skipUnless(__import__("sys").platform.startswith("linux"), "Native persistence v1 Linux-only")
    def test_native_locked_workspace_http_persistence_matches_interpreter_contract(self) -> None:
        port = _free_loopback_port()
        temporary, root, state_path = _copy_reference_with_runtime(port)
        self.addCleanup(temporary.cleanup)
        workspace, lock = _lock(root)
        result = build_locked_workspace_package(
            workspace,
            "http_ingress",
            output=root / "http-ingress",
        )
        verify_workspace_build(result)
        self.assertEqual(result.workspace_digest, lock.workspace_digest)

        process = subprocess.Popen(
            [str(result.artifact)],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        self.addCleanup(lambda: process.poll() is None and process.kill())

        with _connect_process(port, process) as client:
            client.settimeout(2.0)
            client.sendall(_request())
            response = bytearray()
            while True:
                chunk = client.recv(4096)
                if not chunk:
                    break
                response.extend(chunk)

        stdout, stderr = process.communicate(timeout=4)
        self.assertEqual(process.returncode, 0, stderr)
        self.assertEqual(stderr, "")
        self.assertEqual(stdout, EXPECTED_OUTPUT)
        self.assertEqual(state_path.read_text(encoding="utf-8"), EXPECTED_STATE)
        self.assertEqual(state_path.stat().st_mode & 0o777, 0o600)
        self.assertIn(b"HTTP/1.1 200 OK\r\n", response)
        self.assertTrue(response.endswith(b"\r\n\r\naccepted"), response)


if __name__ == "__main__":
    unittest.main()
