from __future__ import annotations

import io
import pathlib
import shutil
import subprocess
import tempfile
import unittest
from contextlib import redirect_stdout

from koschei.codegen_go import generate_go
from koschei.interpreter import run
from koschei.parser import parse
from koschei.semantic import check

GO_BINARY = shutil.which("go")
REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent


@unittest.skipUnless(GO_BINARY, "Go kurulu değil; native struct testleri atlandı")
class NativeStructCodegenTests(unittest.TestCase):
    def native_output(self, source: str, *, check_semantics: bool = True) -> str:
        program = parse(source)
        if check_semantics:
            check(program)
        generated = generate_go(program)
        workspace = tempfile.TemporaryDirectory(prefix="koschei-native-struct-")
        self.addCleanup(workspace.cleanup)
        directory = pathlib.Path(workspace.name)
        (directory / "main.go").write_text(generated, encoding="utf-8")
        (directory / "go.mod").write_text(
            "module koscheistruct\n\ngo 1.21\n", encoding="utf-8"
        )
        binary = directory / "program"
        built = subprocess.run(
            [GO_BINARY, "build", "-o", str(binary), "."],
            cwd=directory,
            capture_output=True,
            text=True,
            timeout=180,
        )
        self.assertEqual(built.returncode, 0, built.stderr)
        completed = subprocess.run(
            [str(binary)], capture_output=True, text=True, timeout=60
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        return completed.stdout

    @staticmethod
    def interpreter_output(source: str) -> str:
        program = parse(source)
        check(program)
        output = io.StringIO()
        with redirect_stdout(output):
            code = run(program, [])
        if code != 0:
            raise AssertionError(f"interpreter exit: {code}")
        return output.getvalue()

    def assert_native_parity(self, source: str) -> None:
        self.assertEqual(self.native_output(source), self.interpreter_output(source))

    def test_holders_example_matches_interpreter(self) -> None:
        source = (REPO_ROOT / "examples" / "holders.ks").read_text(encoding="utf-8")
        self.assert_native_parity(source)

    def test_nested_structs_lists_maps_and_field_access(self) -> None:
        source = """
        struct Address { city: String }
        struct User { name: String, address: Address, tags: List }
        fn main() {
            let user = User {
                name: "Onur",
                address: Address { city: "İstanbul" },
                tags: ["compiler", "security"],
            }
            let table = {"owner": user}
            let owner = table.get("owner") or user
            println(owner.name)
            println(owner.address.city)
            println(owner.tags)
            println(user)
        }
        """
        self.assert_native_parity(source)

    def test_struct_equality_is_structural_and_type_sensitive(self) -> None:
        source = """
        struct User { id: Int, name: String }
        fn main() {
            println(User { id: 1, name: "a" } == User { id: 1, name: "a" })
            println(User { id: 1, name: "a" } == User { id: 2, name: "a" })
        }
        """
        self.assert_native_parity(source)

        # Semantic checker farklı nominal struct tiplerini zaten karşılaştırmaz.
        # Native savunmanın tip adını da eşitliğe kattığını doğrudan kanıtla.
        different_types = """
        struct User { id: Int }
        struct Other { id: Int }
        fn main() {
            println(User { id: 1 } == Other { id: 1 })
        }
        """
        self.assertEqual(
            self.native_output(different_types, check_semantics=False), "false\n"
        )

    def test_native_runtime_rejects_capability_inside_struct(self) -> None:
        source = """
        struct Hidden { value: NetCaps }
        fn main(caps: SystemCaps) {
            let net = caps.net.allow("https://example.com")
            println(Hidden { value: net })
        }
        """
        output = self.native_output(source, check_semantics=False)
        self.assertIn("KS3401", output)


if __name__ == "__main__":
    unittest.main()
