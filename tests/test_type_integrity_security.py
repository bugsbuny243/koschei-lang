from __future__ import annotations

import io
import pathlib
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout

from koschei.capabilities import analyze, render
from koschei.cli import main
from koschei.interpreter import Interpreter, KoscheiRuntimeError
from koschei.parser import parse
from koschei.semantic import SemanticError, check


ROOT_TUNNEL = """
struct FakeRoot { net: NetRoot }

fn steal(fake: FakeRoot) {
    let net = fake.net.allow("https://evil.example.com")
    let response = net.get("https://evil.example.com/loot") or return
    println(response.text())
}

fn main(caps: SystemCaps) {
    steal(caps)
}
"""


class CapabilityTypeIntegrityTests(unittest.TestCase):
    def assert_security_rejection(self, source: str) -> None:
        with self.assertRaises(SemanticError) as context:
            check(parse(source))
        self.assertIn(context.exception.code, {"KS2401", "KS2402"})

    def test_root_capability_cannot_be_stored_in_struct(self) -> None:
        self.assert_security_rejection(ROOT_TUNNEL)

    def test_main_cannot_receive_system_caps_under_fake_type(self) -> None:
        self.assert_security_rejection(
            'fn main(fake: String) { println("not a capability") }'
        )

    def test_system_caps_cannot_impersonate_capability_bundle_argument(self) -> None:
        self.assert_security_rejection(
            """
            struct NetBox { net: NetCaps }
            fn use(box: NetBox) {
                let response = box.net.get("https://evil.example.com") or return
            }
            fn main(caps: SystemCaps) { use(caps) }
            """
        )

    def test_return_type_cannot_launder_system_caps(self) -> None:
        self.assert_security_rejection(
            """
            struct NetBox { net: NetCaps }
            fn disguise(caps: SystemCaps) -> NetBox { return caps }
            fn main(caps: SystemCaps) { let box = disguise(caps) }
            """
        )

    def test_struct_field_cannot_launder_system_caps(self) -> None:
        self.assert_security_rejection(
            """
            struct NetBox { net: NetCaps }
            fn main(caps: SystemCaps) {
                let box = NetBox { net: caps }
            }
            """
        )

    def test_legitimate_narrowed_capability_bundle_passes(self) -> None:
        program = parse(
            """
            struct NetBox { net: NetCaps }
            fn use(box: NetBox) {
                let response = box.net.get("https://api.example.com") or return
            }
            fn main(caps: SystemCaps) {
                let net = caps.net.allow("https://api.example.com")
                let box = NetBox { net: net }
                use(box)
            }
            """
        )
        report = check(program)
        self.assertGreaterEqual(report.capability_values, 2)

    def test_runtime_rejects_type_laundering_without_semantic_check(self) -> None:
        program = parse(
            """
            struct NetBox { net: NetCaps }
            fn use(box: NetBox) { println("should not run") }
            fn main(caps: SystemCaps) { use(caps) }
            """
        )
        with self.assertRaises(KoscheiRuntimeError) as context:
            Interpreter(program, []).execute_main()
        self.assertEqual(context.exception.code, "KS3401")

    def test_manifest_marks_capability_bearing_struct_parameter(self) -> None:
        source = """
        struct NetBox { net: NetCaps }
        fn use(box: NetBox) {
            let response = box.net.get("https://api.example.com") or return
        }
        fn main() { println("safe") }
        """
        program = parse(source)
        check(program)
        manifest = analyze(program)
        text = render(manifest, "bundle.ks")

        self.assertIn("net", manifest.required_domains)
        self.assertIn("use", manifest.holder_functions)
        self.assertFalse(manifest.is_exact)
        self.assertNotIn("saf hesaplama", text)

    def test_deny_net_blocks_capability_bearing_struct_parameter(self) -> None:
        source = """
        struct NetBox { net: NetCaps }
        fn use(box: NetBox) {
            let response = box.net.get("https://api.example.com") or return
        }
        fn main() { println("safe") }
        """
        with tempfile.TemporaryDirectory() as directory:
            path = pathlib.Path(directory) / "bundle.ks"
            path.write_text(source, encoding="utf-8")
            output = io.StringIO()
            error = io.StringIO()
            with redirect_stdout(output), redirect_stderr(error):
                exit_code = main(["caps", str(path), "--deny", "net"])

        self.assertEqual(exit_code, 2)
        self.assertIn("denied capability domain", error.getvalue())


if __name__ == "__main__":
    unittest.main()
