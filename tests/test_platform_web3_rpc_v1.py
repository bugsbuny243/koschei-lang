"""Real bounded, read-only Koschei Web3 JSON-RPC over loopback NetCaps.

This is NOT a blockchain node or a remote-chain finality attestation.
"""
from __future__ import annotations

from contextlib import redirect_stderr, redirect_stdout
import http.server
import io
import json
import os
from pathlib import Path
import platform
import shutil
import socket
import subprocess
import sys
import tempfile
import threading
import unittest

from koschei.capabilities import analyze_graph
from koschei.cli_entry import main as cli_main
from koschei.modules import check_graph, load_graph

ROOT = Path(__file__).resolve().parents[1]
SAMPLE = ROOT / "examples/web3_readonly_rpc_v1/main.ks"
NATIVE = (shutil.which("go") is not None and
          sys.platform.startswith("linux") and
          platform.machine() in {"x86_64", "AMD64"})

REQUEST_CHAIN = {
    "jsonrpc": "2.0", "id": 1, "method": "eth_chainId", "params": []
}
REQUEST_BLOCK = {
    "jsonrpc": "2.0", "id": 2, "method": "eth_blockNumber", "params": []
}


class RpcHandler(http.server.BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, *args: object) -> None:
        pass

    def do_POST(self) -> None:  # noqa: N802
        n = int(self.headers.get("Content-Length", "0"))
        raw = self.rfile.read(n)
        self.server.requests.append((self.path, self.headers.get("Content-Type"), raw))
        status = 200
        try:
            call = json.loads(raw)
            method = call.get("method") if isinstance(call, dict) else None
        except (ValueError, TypeError):
            method = None
        if self.path != "/rpc" or self.headers.get("Content-Type") != "application/json":
            status, body = 400, b"not-rpc"
        elif method == "eth_chainId":
            body = b'{"id":1,"jsonrpc":"2.0","result":"0x1"}'
            case = self.server.case
            if case == "wrong-chain":
                body = b'{"id":1,"jsonrpc":"2.0","result":"0x2"}'
            elif case == "chain-noncanonical-order":
                body = b'{"result":"0x1","jsonrpc":"2.0","id":1}'
            elif case == "chain-id-mismatch":
                body = b'{"result":"0x1","jsonrpc":"2.0","id":99}'
            elif case == "chain-error":
                body = b'{"error":{"code":-1,"message":"invalid"},"id":1,"jsonrpc":"2.0"}'
            elif case == "chain-malformed":
                body = b'{"result":'
            elif case == "chain-duplicate":
                body = b'{"result":"0x1","result":"0x1","jsonrpc":"2.0","id":1}'
            elif case == "chain-not-200":
                status = 503
            elif case == "chain-redirect":
                status = 302
        elif method == "eth_blockNumber":
            body = b'{"id":2,"jsonrpc":"2.0","result":"0x2a"}'
            case = self.server.case
            if case == "block-noncanonical-order":
                body = b'{"result":"0x2a","jsonrpc":"2.0","id":2}'
            elif case == "block-id-mismatch":
                body = b'{"result":"0x2a","jsonrpc":"2.0","id":1}'
            elif case == "block-version-mismatch":
                body = b'{"result":"0x2a","jsonrpc":"1.0","id":2}'
            elif case == "block-extra":
                body = b'{"result":"0x2a","jsonrpc":"2.0","id":2,"admin":true}'
            elif case == "block-error":
                body = b'{"error":{"code":-32601},"jsonrpc":"2.0","id":2}'
            elif case == "block-noncanonical":
                body = b'{"result":"0x02a","jsonrpc":"2.0","id":2}'
            elif case == "block-upper":
                body = b'{"result":"0x2A","jsonrpc":"2.0","id":2}'
            elif case == "block-malformed":
                body = b'{"result":"0x2a",'
            elif case == "block-duplicate":
                body = b'{"result":"0x2a","result":"0x2a","jsonrpc":"2.0","id":2}'
            elif case == "block-not-200":
                status = 500
            elif case == "block-redirect":
                status = 307
            elif case == "block-oversize":
                body = b"x" * 1048577
        else:
            status, body = 400, b"unsupported"
        self.send_response(status)
        if status in {302, 307}:
            self.send_header("Location", "http://not-the-origin.example/")
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        try:
            self.wfile.write(body)
        except (BrokenPipeError, ConnectionResetError):
            pass


class Web3RpcLiveTests(unittest.TestCase):
    def setUp(self) -> None:
        self.server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), RpcHandler)
        self.server.case = "success"
        self.server.requests = []
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.tmp = tempfile.TemporaryDirectory(prefix="ks-web3-rpc-v1-")
        self.path = Path(self.tmp.name) / "main.ks"
        port = self.server.server_port
        self.path.write_text(
            SAMPLE.read_text(encoding="utf-8").replace(
                "127.0.0.1:PORT", f"127.0.0.1:{port}"),
            encoding="utf-8",
        )

    def tearDown(self) -> None:
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=5)
        self.tmp.cleanup()

    def _run(self, native: bool) -> tuple[int, str, str]:
        if native:
            result = subprocess.run([str(Path(self.tmp.name) / "web3-rpc")],
                                    capture_output=True, text=True,
                                    timeout=30, check=False)
            return result.returncode, result.stdout, result.stderr
        stdout, stderr = io.StringIO(), io.StringIO()
        with redirect_stdout(stdout), redirect_stderr(stderr):
            code = cli_main(["run", str(self.path)])
        return code, stdout.getvalue(), stderr.getvalue()

    def _build_native(self) -> None:
        stdout, stderr = io.StringIO(), io.StringIO()
        with redirect_stdout(stdout), redirect_stderr(stderr):
            code = cli_main(["build", str(self.path), "-o",
                             str(Path(self.tmp.name) / "web3-rpc")])
        self.assertEqual(code, 0, stderr.getvalue())

    def _assert_cases(self, native: bool) -> None:
        cases = (
            "success", "wrong-chain", "chain-noncanonical-order",
            "chain-id-mismatch", "chain-error",
            "chain-malformed", "chain-duplicate", "chain-not-200",
            "chain-redirect", "block-noncanonical-order", "block-id-mismatch",
            "block-version-mismatch",
            "block-extra", "block-error", "block-noncanonical", "block-upper",
            "block-malformed", "block-duplicate", "block-not-200",
            "block-redirect", "block-oversize",
        )
        for case in cases:
            with self.subTest(backend="native" if native else "interpreter",
                              case=case):
                self.server.case = case
                self.server.requests = []
                outcome = self._run(native)
                self.assertEqual(
                    outcome,
                    (0, "web3-rpc-block=0x2a\n" if case == "success"
                     else "web3-rpc-block=DENY\n", ""),
                )
                received = self.server.requests
                if case.startswith("chain-") or case == "wrong-chain":
                    self.assertEqual(len(received), 1)
                else:
                    self.assertEqual(len(received), 2)
                expected = (REQUEST_CHAIN, REQUEST_BLOCK)
                for index, (path, content_type, request) in enumerate(received):
                    self.assertEqual((path, content_type), ("/rpc", "application/json"))
                    self.assertEqual(json.loads(request), expected[index])
                    self.assertLess(len(request), 512)

    def test_checker_and_single_origin_capability(self) -> None:
        graph = load_graph(self.path)
        check_graph(graph)
        report = analyze_graph(graph)
        self.assertTrue(report.has_any)
        # No disk/serve/env/process/clock/random/persist capability grants.
        self.assertFalse(any(term in str(report).lower() for term in
                             ("diskcaps", "servecaps", "persistcaps")))
        module_imports = Path(self.tmp.name) / "no_network.ks"
        module_imports.write_text(
            "import web3_rpc\nfn main() { return }\n", encoding="utf-8"
        )
        graph = load_graph(module_imports)
        check_graph(graph)
        # Imported functions expose an explicit NetCaps requirement to
        # capability analysis, even when main does not invoke them. The
        # unused import alone must never cause a network request.
        self.assertTrue(analyze_graph(graph).has_any)
        stdout, stderr = io.StringIO(), io.StringIO()
        with redirect_stdout(stdout), redirect_stderr(stderr):
            code = cli_main(["run", str(module_imports)])
        self.assertEqual((code, stdout.getvalue(), stderr.getvalue()),
                         (0, "", ""))
        self.assertEqual(self.server.requests, [])

    def test_interpreter_read_only_rpc_and_adversarial_response_denials(self) -> None:
        self._assert_cases(native=False)

    @unittest.skipUnless(NATIVE, "requires native Go/Linux x86-64")
    def test_native_read_only_rpc_and_adversarial_response_denials(self) -> None:
        self._build_native()
        self._assert_cases(native=True)

    def test_cross_origin_request_has_no_network_side_effect(self) -> None:
        # NetCaps is narrowed to this server but the outbound URL is
        # syntactically valid and targets a different origin. No request
        # reaches the server in either interpreter or native mode.
        port = self.server.server_port
        source = SAMPLE.read_text(encoding="utf-8")
        source = source.replace("127.0.0.1:PORT", f"127.0.0.1:{port}")
        source = source.replace(
            f"127.0.0.1:{port}/rpc", "127.0.0.1:1/rpc")
        self.path.write_text(source, encoding="utf-8")
        self.assertEqual(self._run(native=False), (0, "web3-rpc-block=DENY\n", ""))
        self.assertEqual(self.server.requests, [])
        if NATIVE:
            self._build_native()
            self.assertEqual(self._run(native=True),
                             (0, "web3-rpc-block=DENY\n", ""))
            self.assertEqual(self.server.requests, [])


if __name__ == "__main__":
    unittest.main()
