from __future__ import annotations

import io
from contextlib import redirect_stdout
from pathlib import Path
import unittest

from koschei.cli import main as cli_main


REPO_ROOT = Path(__file__).resolve().parents[1]


class FinancialDecimalRuntimeIsolationTests(unittest.TestCase):
    def test_existing_collection_examples_still_run(self) -> None:
        for relative in ("examples/daily.ks", "examples/holders.ks", "examples/maps.ks"):
            with self.subTest(relative=relative):
                output = io.StringIO()
                with redirect_stdout(output):
                    code = cli_main(["run", str(REPO_ROOT / relative)])
                self.assertEqual(code, 0, output.getvalue())


if __name__ == "__main__":
    unittest.main()
