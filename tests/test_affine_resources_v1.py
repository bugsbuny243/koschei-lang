from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from koschei.diagnostics import lookup as lookup_diagnostic
from koschei.modules import check_graph, load_graph
from koschei.semantic import SemanticError


class AffineResourceV1Tests(unittest.TestCase):
    @staticmethod
    def _check(source: str):
        with tempfile.TemporaryDirectory(prefix="koschei-affine-") as directory:
            path = Path(directory) / "main.ks"
            path.write_text(source, encoding="utf-8")
            graph = load_graph(path)
            return check_graph(graph)

    def test_plain_values_remain_copyable(self) -> None:
        self._check(
            """
fn main() {
    let first = 7
    let second = first
    println(first)
    println(second)
}
"""
        )

    def test_method_receiver_borrows_capability_and_can_be_reused(self) -> None:
        self._check(
            """
fn inspect_twice(authority: NetCaps) {
    let first = authority.get("https://example.com/a") or return
    let second = authority.get("https://example.com/b") or return
    println(first.status())
    println(second.status())
}

fn main(caps: SystemCaps) {
    let authority = caps.net.allow("https://example.com")
    inspect_twice(authority)
}
"""
        )

    def test_alias_move_blocks_old_binding(self) -> None:
        source = """
fn main(caps: SystemCaps) {
    let authority = caps.net.allow("https://example.com")
    let next = authority
    let illegal = authority
    println(next)
    println(illegal)
}
"""
        with self.assertRaisesRegex(SemanticError, "KS3931"):
            self._check(source)

    def test_function_argument_moves_affine_owner(self) -> None:
        source = """
fn consume(authority: NetCaps) {}

fn main(caps: SystemCaps) {
    let authority = caps.net.allow("https://example.com")
    consume(authority)
    consume(authority)
}
"""
        with self.assertRaisesRegex(SemanticError, "KS3931"):
            self._check(source)

    def test_handoff_return_transfers_ownership(self) -> None:
        self._check(
            """
fn handoff(authority: NetCaps) -> NetCaps {
    return authority
}

fn consume(authority: NetCaps) {}

fn main(caps: SystemCaps) {
    let authority = caps.net.allow("https://example.com")
    let next = handoff(authority)
    consume(next)
}
"""
        )

    def test_old_owner_after_handoff_is_rejected(self) -> None:
        source = """
fn handoff(authority: NetCaps) -> NetCaps {
    return authority
}

fn main(caps: SystemCaps) {
    let authority = caps.net.allow("https://example.com")
    let next = handoff(authority)
    let illegal = authority
    println(next)
    println(illegal)
}
"""
        with self.assertRaisesRegex(SemanticError, "KS3931"):
            self._check(source)

    def test_capability_bearing_struct_is_affine(self) -> None:
        source = """
struct AuthorityBox {
    authority: NetCaps
}

fn main(caps: SystemCaps) {
    let authority = caps.net.allow("https://example.com")
    let box = AuthorityBox { authority: authority }
    let illegal = authority
    println(box)
    println(illegal)
}
"""
        with self.assertRaisesRegex(SemanticError, "KS3931"):
            self._check(source)

    def test_moving_affine_field_moves_whole_owner_v1(self) -> None:
        source = """
struct AuthorityBox {
    authority: NetCaps
}

fn consume(authority: NetCaps) {}

fn main(caps: SystemCaps) {
    let authority = caps.net.allow("https://example.com")
    let box = AuthorityBox { authority: authority }
    consume(box.authority)
    consume(box.authority)
}
"""
        with self.assertRaisesRegex(SemanticError, "KS3931"):
            self._check(source)

    def test_affine_binding_cannot_be_mutable(self) -> None:
        source = """
fn main(caps: SystemCaps) {
    let mut authority = caps.net.allow("https://example.com")
    println(authority)
}
"""
        with self.assertRaisesRegex(SemanticError, "KS3930"):
            self._check(source)

    def test_move_in_one_branch_poison_joins_after_if(self) -> None:
        source = """
fn consume(authority: NetCaps) {}

fn main(caps: SystemCaps) {
    let authority = caps.net.allow("https://example.com")
    if true {
        consume(authority)
    }
    consume(authority)
}
"""
        with self.assertRaisesRegex(SemanticError, "KS3931"):
            self._check(source)

    def test_outer_affine_move_in_repeating_loop_is_rejected(self) -> None:
        source = """
fn consume(authority: NetCaps) {}

fn main(caps: SystemCaps) {
    let authority = caps.net.allow("https://example.com")
    while false {
        consume(authority)
    }
}
"""
        with self.assertRaisesRegex(SemanticError, "KS3932"):
            self._check(source)

    def test_system_caps_member_projection_does_not_consume_whole_root(self) -> None:
        self._check(
            """
fn main(caps: SystemCaps) {
    let net_root = caps.net
    let disk_root = caps.disk
    let net = net_root.allow("https://example.com")
    let disk = disk_root.allow("/tmp")
    println(net)
    println(disk)
}
"""
        )

    def test_copying_whole_system_caps_is_a_move(self) -> None:
        source = """
fn main(caps: SystemCaps) {
    let other = caps
    let net = caps.net
    println(other)
    println(net)
}
"""
        with self.assertRaisesRegex(SemanticError, "KS3931"):
            self._check(source)

    def test_affine_diagnostics_are_explainable(self) -> None:
        for code in ("KS3930", "KS3931", "KS3932"):
            with self.subTest(code=code):
                self.assertIsNotNone(lookup_diagnostic(code, "tr"))
                self.assertIsNotNone(lookup_diagnostic(code, "en"))


if __name__ == "__main__":
    unittest.main()
