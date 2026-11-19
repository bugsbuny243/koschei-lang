"""A capability method name on a value of unknown legacy type is not KS2401.

The legacy checker does not track List/Map element types, so an element from
`List.get` or `Map.get` has no known type there. It refused `.hex()` on such a
value (a struct's Bytes field) as an unauthorized `RandomCaps.hex`, a false
KS2401. Capabilities cannot be stored in a List or Map, so that value is never
a capability; the typed HIR checks the call. Real misuse stays refused.
"""
from __future__ import annotations

from contextlib import redirect_stderr, redirect_stdout
import io
from pathlib import Path
import tempfile
import unittest

from koschei.cli_entry import main as cli_main


def _run(command: str, source: str) -> tuple[int, str, str]:
    with tempfile.TemporaryDirectory() as directory:
        path = Path(directory) / "main.ks"
        path.write_text(source, encoding="utf-8")
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            code = cli_main([command, str(path)])
        return code, out.getvalue(), err.getvalue()


ELEMENT_FIELD = """
struct Item {
    data: Bytes,
}

fn main() {
    let raw = bytes_from_hex("ab") or return
    let items = [Item { data: raw }]
    let lead = items.get(0) or return
    println(lead.data.hex())
    let table = {"k": raw}
    let value = table.get("k") or return
    println(value.hex())
}
"""

CAPABILITY_IN_LIST = """
struct Holder {
    rand: RandomCaps,
}

pure fn sneaky(items: List<Holder>) -> String {
    let lead = items.get(0) or return ""
    return lead.rand.hex(4) or ""
}

fn main() {
    println("x")
}
"""

WRONG_METHOD = """
fn main() {
    let items = [1, 2]
    let value = items.get(0) or return
    println(value.hex(4))
}
"""


class UnknownReceiverGuardTests(unittest.TestCase):
    def test_bytes_method_on_collection_element_runs(self) -> None:
        code, stdout, stderr = _run("run", ELEMENT_FIELD)
        self.assertEqual((code, stdout), (0, "ab\nab\n"), stderr)

    def test_capability_in_a_list_is_still_refused(self) -> None:
        code, _, stderr = _run("check", CAPABILITY_IN_LIST)
        self.assertNotEqual(code, 0)
        self.assertIn("KS2402", stderr)

    def test_wrong_method_on_an_element_is_still_refused(self) -> None:
        code, _, stderr = _run("check", WRONG_METHOD)
        self.assertNotEqual(code, 0)
        self.assertIn("KS1306", stderr)


if __name__ == "__main__":
    unittest.main()
