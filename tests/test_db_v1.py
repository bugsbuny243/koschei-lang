"""Database authority v1: one SQLite file, literal SQL, parameters as data."""
from __future__ import annotations

from contextlib import redirect_stderr, redirect_stdout
import io
import json
import os
from pathlib import Path
import shutil
import tempfile
import unittest

from koschei.cli_entry import main as cli_main
from koschei import untrusted

GO = shutil.which("go")


class DbTests(unittest.TestCase):
    def setUp(self) -> None:
        directory = tempfile.TemporaryDirectory(prefix="koschei-db-")
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name)
        self.database = self.root / "app.db"

    def write(self, source: str, name: str = "main.ks") -> Path:
        path = self.root / name
        path.write_text(source.replace("DB", str(self.database)), encoding="utf-8")
        return path

    def cli(self, *arguments: str) -> tuple[int, str, str]:
        stdout, stderr = io.StringIO(), io.StringIO()
        with redirect_stdout(stdout), redirect_stderr(stderr):
            code = cli_main(list(arguments))
        return code, stdout.getvalue(), stderr.getvalue()

    def run_lines(self, source: str) -> list[str]:
        code, out, err = self.cli("run", str(self.write(source)))
        self.assertEqual(code, 0, err + out)
        return out.splitlines()

    def test_rows_round_trip_with_their_types(self) -> None:
        lines = self.run_lines("""import json

fn main(caps: SystemCaps) {
    let db = caps.db.allow("DB", 100, 1048576, 2000)
    let made = db.exec("CREATE TABLE notes (id INTEGER PRIMARY KEY, body TEXT, score REAL, done INTEGER, extra TEXT, n INTEGER)", "[]") or return Error("create")
    let body = "Robert'); DROP TABLE notes; --"
    let one = db.exec("INSERT INTO notes (body, score, done, extra) VALUES (?, ?, ?, ?)", json.array([json.string(body), json.float(2.5) or "null", json.bool(true), json.null()])) or return Error("insert")
    let two = db.exec("INSERT INTO notes (body, score, done, n) VALUES (?, ?, ?, ?)", json.array([json.string("çay"), json.int(3), json.bool(false), json.int(-9223372036854775807 - 1)])) or return Error("insert")
    println(one + two)
    let changed = db.exec("UPDATE notes SET done = ? WHERE id > ?", json.array([json.int(1), json.int(0)])) or return Error("update")
    println(changed)
    let rows = db.query("SELECT id, body, score, done, extra, n FROM notes ORDER BY id", "[]") or return Error("query")
    println(encode_json(rows) or "?")
    println(json_length(rows) or -1)
    let first = json_at(rows, 0) or return Error("row")
    let text = json_get(first, "body") or return Error("body")
    println(json_text(text) or "?")
    let none = db.query("SELECT id FROM notes WHERE body = ?", json.array([json.string("missing")])) or return Error("query")
    println(encode_json(none) or "?")
}
""")
        self.assertEqual(lines[0], "2")
        self.assertEqual(lines[1], "2")
        self.assertEqual(
            json.loads(lines[2]),
            [
                {"id": 1, "body": "Robert'); DROP TABLE notes; --", "score": 2.5, "done": 1, "extra": None, "n": None},
                {"id": 2, "body": "çay", "score": 3.0, "done": 1, "extra": None, "n": -9223372036854775808},
            ],
        )
        self.assertEqual(lines[3:], ["2", "Robert'); DROP TABLE notes; --", "[]"])

    def test_data_persists_between_runs(self) -> None:
        source = """import json

fn main(caps: SystemCaps) {
    let db = caps.db.allow("DB", 100, 1048576, 2000)
    let made = db.exec("CREATE TABLE IF NOT EXISTS visits (n INTEGER)", "[]") or return Error("create")
    let added = db.exec("INSERT INTO visits (n) VALUES (?)", json.array([json.int(1)])) or return Error("insert")
    let rows = db.query("SELECT count(*) AS total FROM visits", "[]") or return Error("query")
    let row = json_at(rows, 0) or return Error("row")
    let total = json_get(row, "total") or return Error("total")
    println(json_int(total) or -1)
}
"""
        self.assertEqual(self.run_lines(source), ["1"])
        self.assertEqual(self.run_lines(source), ["2"])

    def test_statements_reach_this_file_only(self) -> None:
        other = self.root / "other.db"
        lines = self.run_lines(f"""fn main(caps: SystemCaps) {{
    let db = caps.db.allow("DB", 10, 1048576, 2000)
    println(db.exec("ATTACH '{other}' AS other", "[]"))
    println(db.exec("VACUUM INTO '{other}'", "[]"))
    println(db.exec("PRAGMA writable_schema = ON", "[]"))
    println(db.query("PRAGMA table_info(sqlite_master)", "[]"))
    println(db.query("SELECT load_extension('x')", "[]"))
    println(db.exec("CREATE VIRTUAL TABLE v USING fts5(body)", "[]"))
}}
""")
        self.assertEqual(len(lines), 6)
        for line in lines:
            self.assertTrue(line.startswith("KS3484: "), line)
        self.assertFalse(other.exists())

    def test_parameters_and_statement_errors_are_values(self) -> None:
        lines = self.run_lines("""fn main(caps: SystemCaps) {
    let db = caps.db.allow("DB", 10, 1048576, 2000)
    println(db.exec("CREATE TABLE t (v TEXT NOT NULL)", "[]"))
    println(db.exec("INSERT INTO t (v) VALUES (?)", "not json"))
    println(db.exec("INSERT INTO t (v) VALUES (?)", "[[1]]"))
    println(db.exec("INSERT INTO t (v) VALUES (?)", "\\{\\}"))
    println(db.exec("INSERT INTO t (v) VALUES (?)", "[1e999]"))
    println(db.exec("INSERT INTO t (v) VALUES (?)", "[9223372036854775808]"))
    println(db.exec("INSERT INTO t (v) VALUES (?)", "[null]"))
    println(db.exec("INSERT INTO t (v) VALUES (?, ?)", "[1]"))
    println(db.exec("SELEC 1", "[]"))
    println(db.exec("SELECT 1; SELECT 2", "[]"))
    println(db.exec("CREATE TABLE b (x BLOB)", "[]"))
    println(db.exec("INSERT INTO b VALUES (x'00ff')", "[]"))
    println(db.query("SELECT x FROM b", "[]"))
}
""")
        self.assertEqual(lines[0], "0")
        for line in lines[1:6]:
            self.assertTrue(line.startswith("KS3481: "), line)
        for line in lines[6:10]:
            self.assertTrue(line.startswith("KS3480: "), line)
        self.assertIn("NOT NULL", lines[6])
        self.assertEqual(lines[10:12], ["0", "1"])
        self.assertEqual(lines[12], "KS3480: BLOB sütunları v1'de okunamaz.")

    def test_budgets(self) -> None:
        lines = self.run_lines("""fn main(caps: SystemCaps) {
    let db = caps.db.allow("DB", 3, 65536, 300)
    println(db.query("WITH RECURSIVE r(x) AS (SELECT 1 UNION ALL SELECT x + 1 FROM r WHERE x < 3) SELECT x FROM r", "[]"))
    println(db.query("WITH RECURSIVE r(x) AS (SELECT 1 UNION ALL SELECT x + 1 FROM r WHERE x < 4) SELECT x FROM r", "[]"))
    println(db.query("WITH RECURSIVE r(x) AS (SELECT 1 UNION ALL SELECT x + 1 FROM r) SELECT count(*) AS n FROM r", "[]"))
    println(db.exec("CREATE TABLE big (v TEXT)", "[]"))
    println(db.exec("WITH RECURSIVE r(x) AS (SELECT 1 UNION ALL SELECT x + 1 FROM r WHERE x < 1000) INSERT INTO big SELECT printf('%0500d', x) FROM r", "[]"))
    println(db.exec("INSERT INTO big VALUES ('still works')", "[]"))
}
""")
        self.assertEqual(lines[0], "<data>")
        self.assertEqual(lines[1], "KS3482: Sorgu en fazla 3 satır döndürebilir.")
        self.assertEqual(lines[2], "KS3483: SQL deyimi 300 ms içinde bitmedi.")
        self.assertEqual(lines[3], "0")
        self.assertEqual(lines[4], "KS3482: Veritabanı dosyası en fazla 65536 bayt olabilir.")
        self.assertEqual(lines[5], "1")
        self.assertLessEqual(self.database.stat().st_size, 65536)

    def test_a_symbolic_link_is_not_followed(self) -> None:
        target = self.root / "target.db"
        os.symlink(target, self.database)
        lines = self.run_lines("""fn main(caps: SystemCaps) {
    let db = caps.db.allow("DB", 10, 1048576, 2000)
    println(db.exec("CREATE TABLE t (v TEXT)", "[]"))
}
""")
        self.assertEqual(lines, ["KS3485: Veritabanı dosyası açılamadı: not a regular file"])
        self.assertFalse(target.exists())

    def test_checker_rules(self) -> None:
        cases = {
            'let path = "DB"\n    let db = caps.db.allow(path, 10, 1048576, 2000)': "KS2460",
            'let db = caps.db.allow("DB", 10, 1048576)': "KS2460",
            'let db = caps.db.allow("relative.db", 10, 1048576, 2000)': "KS2461",
            'let db = caps.db.allow("/srv/../etc/x.db", 10, 1048576, 2000)': "KS2461",
            'let db = caps.db.allow("DB", 0, 1048576, 2000)': "KS2461",
            'let db = caps.db.allow("DB", 10, 1024, 2000)': "KS2461",
            'let db = caps.db.allow("DB", 10, 1048576, 0)': "KS2461",
            'let db = caps.db.allow("DB", 10, 1048576, 2000)\n    let id = "1"\n    let r = db.query("SELECT * FROM t WHERE id = {id}", "[]")': "KS2462",
            'let db = caps.db.allow("DB", 10, 1048576, 2000)\n    let sql = "SELECT 1"\n    let r = db.query(sql, "[]")': "KS2462",
            'let db = caps.db.allow("DB", 10, 1048576, 2000)\n    let r = db.query("SELECT 1")': "KS1301",
            'let db = caps.db.allow("DB", 10, 1048576, 2000)\n    let r = db.query("SELECT 1", 7)': "KS1301",
            'let db = caps.db.allow("DB", 10, 1048576, 2000)\n    let r = db.delete("t")': "KS2404",
            'let r = caps.db.exec("SELECT 1", "[]")': "KS2402",
        }
        for body, code in cases.items():
            path = self.write(f"fn main(caps: SystemCaps) {{\n    {body}\n}}\n", "check.ks")
            status, out, err = self.cli("check", str(path))
            self.assertEqual(status, 1, body)
            self.assertIn(code, out + err, body)

    def test_manifest_deny_and_native_refusal(self) -> None:
        path = self.write("""fn main(caps: SystemCaps) {
    let db = caps.db.allow("DB", 10, 1048576, 2000)
    println(db.exec("CREATE TABLE t (v TEXT)", "[]"))
}
""")
        code, out, _ = self.cli("caps", str(path))
        self.assertEqual(code, 0)
        self.assertIn(f"{self.database} | max_rows=10 | max_bytes=1048576 | deadline_ms=2000", out)
        code, out, _ = self.cli("caps", "--json", str(path))
        self.assertEqual(code, 0)
        self.assertIn('"db"', out)
        code, _, _ = self.cli("caps", "--deny", "db", str(path))
        self.assertEqual(code, 2)
        if GO is not None:
            code, out, err = self.cli("build", str(path), "-o", str(self.root / "app"))
            self.assertNotEqual(code, 0)
            self.assertIn("KS4004", out + err)

    def test_untrusted_code_is_denied_the_database(self) -> None:
        result = untrusted.evaluate(
            'fn main(caps: SystemCaps) {\n    let db = caps.db.allow("/tmp/x.db", 10, 1048576, 2000)\n}\n',
            "run",
        )
        self.assertEqual(result["stage"], "policy")
        self.assertFalse(result["ran"])
        self.assertIn("denied capability domain requested: db", result["policy"]["stderr"])


if __name__ == "__main__":
    unittest.main()
