from __future__ import annotations

import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from koschei.modules import ModuleError, check_graph
from koschei.protected_graph_v1 import load_protected_graph


POLICY = "sha256:" + ("11" * 32)
ROOT_ID = "0123456789abcdef0123456789abcdef"
DEP_ID = "fedcba9876543210fedcba9876543210"


def sha256_text(text: str) -> str:
    return "sha256:" + hashlib.sha256(text.encode("utf-8")).hexdigest()


class ProtectedGraphV1Tests(unittest.TestCase):
    def write_graph(self, directory: Path, *, include_edge: bool = True, dep_provenance: str = "canonical"):
        store = directory / "objects"
        store.mkdir()
        root_source = "import dep\nfn main() { println(dep.value()) }\n"
        dep_source = "fn value() -> Int { return 7 }\n"
        root_alias = "7Q2A9M4K"
        dep_alias = "P19MX8D4"
        (store / root_alias).write_text(root_source, encoding="utf-8")
        (store / dep_alias).write_text(dep_source, encoding="utf-8")
        graph = {
            "schema": "koschei.opaque-source-graph/v1",
            "project_id": "opaque-test",
            "objects": [
                {
                    "object_id": ROOT_ID,
                    "artifact_hash": sha256_text(root_source),
                    "policy_hash": POLICY,
                    "epoch_alias": root_alias,
                    "provenance": "canonical",
                    "requested_capabilities": [],
                },
                {
                    "object_id": DEP_ID,
                    "artifact_hash": sha256_text(dep_source),
                    "policy_hash": POLICY,
                    "epoch_alias": dep_alias,
                    "provenance": dep_provenance,
                    "requested_capabilities": [],
                },
            ],
            "edges": [],
            "constraints": {
                "physical_path_is_authority": False,
                "semantic_filename_required": False,
                "plaintext_fallback_allowed": False,
                "decoy_is_deployable": False,
            },
        }
        if include_edge:
            graph["edges"].append(
                {
                    "from_object_id": ROOT_ID,
                    "import_name": "dep",
                    "to_object_id": DEP_ID,
                    "expected_artifact_hash": sha256_text(dep_source),
                    "requested_capabilities": [],
                }
            )
        graph_path = directory / "graph.json"
        graph_path.write_text(json.dumps(graph), encoding="utf-8")
        return graph_path, store

    def test_import_resolves_from_object_graph_not_sibling_filename(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            graph_path, store = self.write_graph(Path(temp))
            graph = load_protected_graph(
                graph_path,
                store,
                ROOT_ID,
                expected_policy_hash=POLICY,
            )
            report = check_graph(graph)
            self.assertIsNotNone(report)
            physical_names = {module.path.name for module in graph.modules.values()}
            self.assertEqual(physical_names, {"7Q2A9M4K", "P19MX8D4"})
            self.assertNotIn("dep.ks", physical_names)

    def test_missing_signed_edge_does_not_fall_back_to_dep_filename(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            directory = Path(temp)
            graph_path, store = self.write_graph(directory, include_edge=False)
            (store / "dep.ks").write_text("fn value() -> Int { return 99 }\n", encoding="utf-8")
            with self.assertRaises(ModuleError) as caught:
                load_protected_graph(
                    graph_path,
                    store,
                    ROOT_ID,
                    expected_policy_hash=POLICY,
                )
            self.assertEqual(caught.exception.code, "KS5626")

    def test_decoy_object_is_rejected_from_canonical_build(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            graph_path, store = self.write_graph(Path(temp), dep_provenance="decoy")
            with self.assertRaises(ModuleError) as caught:
                load_protected_graph(
                    graph_path,
                    store,
                    ROOT_ID,
                    expected_policy_hash=POLICY,
                )
            self.assertEqual(caught.exception.code, "KS5620")

    def test_hash_mismatch_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            graph_path, store = self.write_graph(Path(temp))
            (store / "P19MX8D4").write_text("fn value() -> Int { return 8 }\n", encoding="utf-8")
            with self.assertRaises(ModuleError) as caught:
                load_protected_graph(
                    graph_path,
                    store,
                    ROOT_ID,
                    expected_policy_hash=POLICY,
                )
            self.assertEqual(caught.exception.code, "KS5623")

    def test_policy_mismatch_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            graph_path, store = self.write_graph(Path(temp))
            with self.assertRaises(ModuleError) as caught:
                load_protected_graph(
                    graph_path,
                    store,
                    ROOT_ID,
                    expected_policy_hash="sha256:" + ("22" * 32),
                )
            self.assertEqual(caught.exception.code, "KS5621")


if __name__ == "__main__":
    unittest.main()
