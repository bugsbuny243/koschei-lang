from __future__ import annotations

import unittest

from koschei.parser import parse
from koschei.semantic import SemanticError, check


class SemanticTests(unittest.TestCase):
    def test_rejects_assignment_to_immutable_variable(self) -> None:
        program = parse("fn main() { let value = 1 value = 2 }")
        with self.assertRaisesRegex(SemanticError, "KS1201"):
            check(program)

    def test_accepts_assignment_to_mutable_variable(self) -> None:
        program = parse("fn main() { let mut value = 1 value = 2 }")
        report = check(program)
        self.assertEqual(report.variables, 1)

    def test_rejects_network_access_without_net_caps(self) -> None:
        program = parse('fn steal() { net.get("https://evil.example") }')
        with self.assertRaisesRegex(SemanticError, "KS2401"):
            check(program)

    def test_accepts_network_access_with_net_caps(self) -> None:
        program = parse(
            'fn fetch(net: NetCaps) { let response = net.get("https://api.example") }'
        )
        report = check(program)
        self.assertGreaterEqual(report.capability_values, 1)

    def test_system_caps_can_create_restricted_net_caps(self) -> None:
        program = parse(
            'fn main(caps: SystemCaps) { '
            'let api = caps.net.allow("https://api.example") '
            'let response = api.get("https://api.example/v1") '
            '}'
        )
        report = check(program)
        self.assertGreaterEqual(report.capability_values, 2)

    def test_root_capability_cannot_do_io_directly(self) -> None:
        program = parse(
            'fn main(caps: SystemCaps) { '
            'let raw = caps.disk '
            'let secret = raw.read("/etc/shadow") '
            '}'
        )
        with self.assertRaisesRegex(SemanticError, "KS2402"):
            check(program)

    def test_narrowed_capability_cannot_be_rewidened(self) -> None:
        program = parse(
            'fn main(caps: SystemCaps) { '
            'let ro = caps.disk.allow_read_only("/tmp/safe") '
            'let widened = ro.allow("/") '
            '}'
        )
        with self.assertRaisesRegex(SemanticError, "KS2403"):
            check(program)

    def test_read_only_capability_cannot_write(self) -> None:
        program = parse(
            'fn main(caps: SystemCaps) { '
            'let ro = caps.disk.allow_read_only("/tmp/safe") '
            'ro.write("/tmp/safe/x", "data") '
            '}'
        )
        with self.assertRaisesRegex(SemanticError, "KS2404"):
            check(program)

    def test_narrowed_capability_passed_to_function_keeps_permissions(self) -> None:
        program = parse(
            'fn load(disk: DiskReadCaps, path: String) -> String or Error { '
            'let content = disk.read(path) or return Error("okunamadı") '
            'return content '
            '} '
            'fn main(caps: SystemCaps) { '
            'let ro = caps.disk.allow_read_only("/etc/app/") '
            'let cfg = load(ro, "/etc/app/config.json") or return '
            '}'
        )
        report = check(program)
        self.assertGreaterEqual(report.capability_values, 3)

    def test_system_caps_has_no_direct_operations(self) -> None:
        program = parse('fn main(caps: SystemCaps) { caps.allow("https://x") }')
        with self.assertRaisesRegex(SemanticError, "KS2402"):
            check(program)

    def test_arithmetic_type_mismatch_is_rejected(self) -> None:
        program = parse('fn main() { let x = "abc" + 5 }')
        with self.assertRaisesRegex(SemanticError, "KS1301"):
            check(program)

    def test_if_condition_must_be_bool(self) -> None:
        program = parse("fn main() { let x = 3 if x { return } }")
        with self.assertRaisesRegex(SemanticError, "KS1301"):
            check(program)

    def test_while_with_comparison_condition_passes(self) -> None:
        program = parse(
            "fn main() { let mut n = 3 while n > 0 { n = n - 1 } }"
        )
        report = check(program)
        self.assertEqual(report.variables, 1)

    def test_block_scoped_let_does_not_leak(self) -> None:
        program = parse(
            "fn main() { if true { let inner = 1 } let x = inner }"
        )
        with self.assertRaisesRegex(SemanticError, "KS1101"):
            check(program)

    def test_interpolation_checks_identifiers(self) -> None:
        program = parse('fn main() { let msg = "selam {missing_name}" }')
        with self.assertRaisesRegex(SemanticError, "KS1101"):
            check(program)

    def test_interpolation_with_known_member_path_passes(self) -> None:
        program = parse(
            'fn greet(user: String) { println("selam {user}") } '
        )
        report = check(program)
        self.assertEqual(report.functions, 1)

    def test_or_else_and_or_block_pass(self) -> None:
        program = parse(
            'fn read_port(raw: String) -> Int or Error { '
            'return raw.to_int() or return Error("geçersiz") '
            '} '
            'fn main() { '
            'let port = read_port("8080") or 8080 '
            'let other = read_port("x") or { println("varsayılan") } '
            '}'
        )
        report = check(program)
        self.assertEqual(report.functions, 2)

    def test_unhandled_capability_call_is_rejected(self) -> None:
        program = parse(
            'fn main(caps: SystemCaps) { '
            'let ro = caps.disk.allow_read_only("/tmp") '
            'ro.read("/etc/passwd") '
            '}'
        )
        with self.assertRaisesRegex(SemanticError, "KS1401"):
            check(program)

    def test_unhandled_error_constructor_is_rejected(self) -> None:
        program = parse('fn main() { Error("bos") }')
        with self.assertRaisesRegex(SemanticError, "KS1401"):
            check(program)

    def test_unhandled_fallible_function_call_is_rejected(self) -> None:
        program = parse(
            'fn f() -> Int or Error { return Error("x") } '
            'fn main() { f() }'
        )
        with self.assertRaisesRegex(SemanticError, "KS1401"):
            check(program)

    def test_error_bound_with_let_is_accepted(self) -> None:
        program = parse(
            'fn main(caps: SystemCaps) { '
            'let ro = caps.disk.allow_read_only("/tmp") '
            'let x = ro.read("/etc/passwd") or "" '
            '}'
        )
        report = check(program)
        self.assertEqual(report.functions, 1)

    def test_error_handled_with_or_block_is_accepted(self) -> None:
        program = parse(
            'fn main(caps: SystemCaps) { '
            'let ro = caps.disk.allow_read_only("/tmp") '
            'ro.read("/etc/passwd") or { println("ele alındı") } '
            '}'
        )
        report = check(program)
        self.assertEqual(report.functions, 1)


    def test_unknown_string_method_is_rejected(self) -> None:
        program = parse('fn main() { let value = "x".reverse() }')
        with self.assertRaisesRegex(SemanticError, "KS1502"):
            check(program)

    def test_fallible_interpolation_requires_or(self) -> None:
        program = parse('fn main() { println("değer: {\"x\".to_int()}") }')
        with self.assertRaisesRegex(SemanticError, "KS1401"):
            check(program)

    def test_fallible_interpolation_with_or_passes(self) -> None:
        program = parse(
            'fn main() { println("değer: {\"x\".to_int() or 0}") }'
        )
        report = check(program)
        self.assertEqual(report.functions, 1)


if __name__ == "__main__":
    unittest.main()
