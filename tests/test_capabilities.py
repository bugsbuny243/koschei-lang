from __future__ import annotations

import io
import json
import pathlib
import unittest
from contextlib import redirect_stderr, redirect_stdout

from koschei.capabilities import DYNAMIC, analyze, render, to_dict
from koschei.cli import main
from koschei.parser import parse
from koschei.semantic import check

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent


def manifest_for(source: str):
    program = parse(source)
    check(program)
    return analyze(program)


class CapabilityManifestTests(unittest.TestCase):
    def test_pure_program_reports_no_capabilities(self) -> None:
        manifest = manifest_for('fn main() { println("selam") }')
        self.assertFalse(manifest.has_any)
        self.assertEqual(manifest.grants, [])
        text = render(manifest, "test.ks")
        self.assertIn("hiçbir yan etki yeteneği taşımıyor", text)

    def test_disk_grant_records_scope_and_read_only(self) -> None:
        manifest = manifest_for(
            'fn main(caps: SystemCaps) { '
            'let cfg = caps.disk.allow_read_only("/etc/app/") '
            'let content = cfg.read("/etc/app/config.json") or "" '
            "}"
        )
        self.assertEqual(len(manifest.grants), 1)
        grant = manifest.grants[0]
        self.assertEqual(grant.domain, "disk")
        self.assertEqual(grant.scope, "/etc/app/")
        self.assertTrue(grant.read_only)
        self.assertIn("read", manifest.operations["disk"])

    def test_writable_disk_grant_is_not_read_only(self) -> None:
        manifest = manifest_for(
            'fn main(caps: SystemCaps) { let cache = caps.disk.allow("/var/cache/") }'
        )
        self.assertFalse(manifest.grants[0].read_only)

    def test_get_is_attributed_to_the_right_domain(self) -> None:
        # 'get' hem NetCaps hem EnvCaps üzerinde bulunur; alıcıya göre ayrışmalı.
        manifest = manifest_for(
            'fn main(caps: SystemCaps) { '
            'let env = caps.env.allow("HOME") '
            'let value = env.get() or "" '
            "}"
        )
        self.assertIn("get", manifest.operations.get("env", set()))
        self.assertNotIn("net", manifest.operations)

    def test_dynamic_scope_marks_manifest_inexact(self) -> None:
        manifest = manifest_for(
            'fn main(caps: SystemCaps) { '
            'let path = "/tmp/dinamik" '
            "let disk = caps.disk.allow(path) "
            "}"
        )
        self.assertEqual(manifest.grants[0].scope, DYNAMIC)
        self.assertFalse(manifest.is_exact)
        self.assertIn("KESİN DEĞİLDİR", render(manifest, "test.ks"))

    def test_capability_holding_functions_are_listed(self) -> None:
        manifest = manifest_for(
            "fn load(disk: DiskReadCaps, path: String) -> String or Error { "
            'let content = disk.read(path) or return Error("x") '
            "return content "
            "} "
            'fn main(caps: SystemCaps) { let cfg = caps.disk.allow_read_only("/etc/") }'
        )
        self.assertIn("load", manifest.holder_functions)

    def test_showcase_example_manifest(self) -> None:
        source = (REPO_ROOT / "examples" / "showcase.ks").read_text(encoding="utf-8")
        manifest = manifest_for(source)
        domains = {grant.domain for grant in manifest.grants}
        self.assertEqual(domains, {"disk", "net"})
        self.assertTrue(manifest.is_exact)

    def test_to_dict_is_json_serializable(self) -> None:
        manifest = manifest_for(
            'fn main(caps: SystemCaps) { let api = caps.net.allow("https://x.example") }'
        )
        payload = json.loads(json.dumps(to_dict(manifest, "test.ks")))
        self.assertEqual(payload["grants"][0]["domain"], "net")
        self.assertTrue(payload["exact"])


class CapsCommandTests(unittest.TestCase):
    def run_cli(self, argv: list[str]) -> tuple[int, str, str]:
        output = io.StringIO()
        error = io.StringIO()
        with redirect_stdout(output), redirect_stderr(error):
            exit_code = main(argv)
        return exit_code, output.getvalue(), error.getvalue()

    def test_caps_prints_manifest(self) -> None:
        code, output, _ = self.run_cli(
            ["caps", str(REPO_ROOT / "examples" / "showcase.ks")]
        )
        self.assertEqual(code, 0)
        self.assertIn("YETKİ MANİFESTOSU", output)
        self.assertIn("/etc/app/", output)

    def test_caps_json_output(self) -> None:
        code, output, _ = self.run_cli(
            ["caps", str(REPO_ROOT / "examples" / "runtime_demo.ks"), "--json"]
        )
        self.assertEqual(code, 0)
        payload = json.loads(output)
        self.assertEqual(payload["grants"][0]["domain"], "env")

    def test_deny_policy_fails_when_domain_requested(self) -> None:
        code, _, error = self.run_cli(
            ["caps", str(REPO_ROOT / "examples" / "showcase.ks"), "--deny", "net"]
        )
        self.assertEqual(code, 2)
        self.assertIn("denied capability domain", error)

    def test_deny_policy_passes_for_pure_program(self) -> None:
        code, _, _ = self.run_cli(
            [
                "caps",
                str(REPO_ROOT / "examples" / "hello.ks"),
                "--deny",
                "net",
                "--deny",
                "disk",
            ]
        )
        self.assertEqual(code, 0)


if __name__ == "__main__":
    unittest.main()
