from __future__ import annotations

import unittest

from koschei.lsp_v5 import LspServer, diagnostics_for_source


class TypedLspParityTests(unittest.TestCase):
    def test_typed_list_contract_is_accepted_live(self) -> None:
        source = (
            "fn total(values: List<Int>) -> Int { return 0 } "
            "fn main() { println(total([1, 2])) }"
        )
        self.assertEqual(diagnostics_for_source(source), [])

    def test_typed_list_mismatch_is_reported_live(self) -> None:
        source = (
            "fn total(values: List<Int>) -> Int { return 0 } "
            'fn main() { println(total([1, "two"])) }'
        )
        diagnostics = diagnostics_for_source(source)
        self.assertEqual(len(diagnostics), 1)
        self.assertEqual(diagnostics[0]["code"], "KS1301")

    def test_live_server_uses_typed_pipeline_on_change(self) -> None:
        server = LspServer()
        uri = "file:///tmp/typed.ks"
        response = server.handle(
            {
                "jsonrpc": "2.0",
                "method": "textDocument/didOpen",
                "params": {
                    "textDocument": {
                        "uri": uri,
                        "text": (
                            "fn total(values: List<Int>) -> Int { return 0 } "
                            'fn main() { println(total([1, "two"])) }'
                        ),
                    }
                },
            }
        )
        self.assertEqual(response[0]["params"]["diagnostics"][0]["code"], "KS1301")

    def test_capability_containment_error_is_live(self) -> None:
        diagnostics = diagnostics_for_source("fn hide(values: List<NetCaps>) {}")
        self.assertEqual(len(diagnostics), 1)
        self.assertEqual(diagnostics[0]["code"], "KS2402")


if __name__ == "__main__":
    unittest.main()
