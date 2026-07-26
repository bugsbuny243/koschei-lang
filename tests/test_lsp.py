from __future__ import annotations

import io
import unittest

from koschei.lsp import (
    LspServer,
    completion_items,
    definition_for_source,
    diagnostics_for_source,
    document_symbols_for_source,
    formatting_edits,
    hover_for_source,
    read_message,
    write_message,
)


class LspAnalysisTests(unittest.TestCase):
    def test_valid_source_has_no_diagnostics(self) -> None:
        self.assertEqual(diagnostics_for_source("fn main() { return }"), [])

    def test_semantic_error_becomes_lsp_diagnostic(self) -> None:
        diagnostics = diagnostics_for_source(
            "fn answer(flag: Bool) -> Int { if flag { return 1 } }"
        )
        self.assertEqual(len(diagnostics), 1)
        self.assertEqual(diagnostics[0]["code"], "KS1303")
        self.assertEqual(diagnostics[0]["severity"], 1)
        self.assertEqual(diagnostics[0]["source"], "koschei")

    def test_formatter_returns_full_document_edit(self) -> None:
        edits = formatting_edits("fn main(){println(\"x\")}\n")
        self.assertEqual(len(edits), 1)
        self.assertIn("fn main() {", edits[0]["newText"])
        self.assertEqual(formatting_edits(edits[0]["newText"]), [])

    def test_hover_and_definition_find_top_level_symbol(self) -> None:
        source = (
            "fn helper(value: Int) -> Int { return value }\n"
            "fn main() { println(helper(1)) }"
        )
        hover = hover_for_source(source, {"line": 1, "character": 22})
        self.assertIsNotNone(hover)
        assert hover is not None
        self.assertIn("fn helper(value: Int) -> Int", hover["contents"]["value"])

        definition = definition_for_source(
            "file:///tmp/main.ks", source, {"line": 1, "character": 22}
        )
        self.assertIsNotNone(definition)
        assert definition is not None
        self.assertEqual(definition["uri"], "file:///tmp/main.ks")
        self.assertEqual(
            definition["range"]["start"], {"line": 0, "character": 3}
        )

    def test_document_symbols_include_types_and_functions(self) -> None:
        source = (
            "struct User { name: String }\n"
            "enum State { Ready, Failed(Error) }\n"
            "fn main() { return }"
        )
        symbols = document_symbols_for_source(source)
        self.assertEqual(
            [item["name"] for item in symbols], ["main", "User", "State"]
        )
        self.assertEqual(symbols[0]["kind"], 12)
        self.assertEqual(symbols[1]["kind"], 23)
        self.assertEqual(symbols[2]["kind"], 10)

    def test_completion_contains_language_core(self) -> None:
        labels = {item["label"] for item in completion_items()}
        self.assertTrue({"fn", "match", "Option", "SystemCaps"}.issubset(labels))


class LspProtocolTests(unittest.TestCase):
    def test_initialize_advertises_editor_features(self) -> None:
        server = LspServer()
        responses = server.handle(
            {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}}
        )
        capabilities = responses[0]["result"]["capabilities"]
        self.assertEqual(capabilities["textDocumentSync"], 1)
        self.assertTrue(capabilities["documentFormattingProvider"])
        self.assertTrue(capabilities["hoverProvider"])
        self.assertTrue(capabilities["definitionProvider"])
        self.assertTrue(capabilities["documentSymbolProvider"])
        self.assertIn("completionProvider", capabilities)

    def test_open_and_change_publish_diagnostics(self) -> None:
        server = LspServer()
        uri = "file:///tmp/main.ks"
        opened = server.handle(
            {
                "jsonrpc": "2.0",
                "method": "textDocument/didOpen",
                "params": {
                    "textDocument": {
                        "uri": uri,
                        "text": "fn helper() { return 1 }",
                    }
                },
            }
        )
        self.assertEqual(opened[0]["params"]["diagnostics"][0]["code"], "KS1304")

        changed = server.handle(
            {
                "jsonrpc": "2.0",
                "method": "textDocument/didChange",
                "params": {
                    "textDocument": {"uri": uri},
                    "contentChanges": [{"text": "fn helper() { return }"}],
                },
            }
        )
        self.assertEqual(changed[0]["params"]["diagnostics"], [])

    def test_protocol_routes_hover_request(self) -> None:
        server = LspServer()
        uri = "file:///tmp/main.ks"
        server.documents[uri] = "fn main() { return }"
        response = server.handle(
            {
                "jsonrpc": "2.0",
                "id": 3,
                "method": "textDocument/hover",
                "params": {
                    "textDocument": {"uri": uri},
                    "position": {"line": 0, "character": 4},
                },
            }
        )[0]
        self.assertIn("fn main", response["result"]["contents"]["value"])

    def test_content_length_round_trip(self) -> None:
        message = {
            "jsonrpc": "2.0",
            "id": 7,
            "result": {"message": "Türkçe"},
        }
        stream = io.BytesIO()
        write_message(stream, message)
        stream.seek(0)
        self.assertEqual(read_message(stream), message)

    def test_unknown_request_returns_method_not_found(self) -> None:
        response = LspServer().handle(
            {"jsonrpc": "2.0", "id": 9, "method": "koschei/unknown"}
        )[0]
        self.assertEqual(response["error"]["code"], -32601)


if __name__ == "__main__":
    unittest.main()
