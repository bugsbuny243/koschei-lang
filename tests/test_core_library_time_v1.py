"""The `time` Core Library module agrees with Python's datetime, under ks run and natively."""
from __future__ import annotations

from contextlib import redirect_stderr, redirect_stdout
from datetime import datetime, timedelta, timezone
import io
from pathlib import Path
import random
import shutil
import subprocess
import tempfile
import unittest

from koschei.cli_entry import main as cli_main

GO = shutil.which("go")
EPOCH = datetime(1970, 1, 1, tzinfo=timezone.utc)
MIN_MS = -62135596800000
MAX_MS = 253402300799999

EDGES = [
    MIN_MS, MIN_MS + 1, -1, 0, 1, 86399999, 86400000, 951782400000, 951868799999,
    4107542400000, 1762933548123, MAX_MS - 1, MAX_MS,
]


def sample() -> list[int]:
    rng = random.Random(20261112)
    return EDGES + [rng.randint(MIN_MS, MAX_MS) for _ in range(300)]


def expected_line(ms: int) -> str:
    moment = EPOCH + timedelta(milliseconds=ms)
    stamp = (
        f"{moment.year:04d}-{moment.month:02d}-{moment.day:02d}T"
        f"{moment.hour:02d}:{moment.minute:02d}:{moment.second:02d}.{moment.microsecond // 1000:03d}Z"
    )
    back = int((moment.replace(microsecond=0) - EPOCH) / timedelta(milliseconds=1))
    return f"{stamp} {moment.isoweekday()} {back}"


def program(values: list[int]) -> str:
    calls = "\n".join(f"    show({value})" for value in values)
    return f"""import time

fn line(ms: Int) -> String or Error {{
    let t = time.utc(ms) or return Error("out of range")
    let text = time.iso_utc_ms(ms) or "?"
    let back = time.from_utc(t.year, t.month, t.day, t.hour, t.minute, t.second) or 0
    return "{{text}} {{t.weekday}} {{back}}"
}}

fn show(ms: Int) {{
    println(line(ms) or "?")
}}

fn main() {{
{calls}
}}
"""


ERRORS = """import time

fn main() {
    println(time.iso_utc(253402300800000))
    println(time.date_utc(-62135596800001))
    println(time.from_utc(0, 1, 1, 0, 0, 0))
    println(time.from_utc(1900, 2, 29, 0, 0, 0))
    println(time.from_utc(2026, 13, 1, 0, 0, 0))
    println(time.from_utc(2026, 4, 31, 0, 0, 0))
    println(time.from_utc(2026, 11, 12, 24, 0, 0))
    println(time.from_utc(2026, 11, 12, 0, 60, 0))
    println(time.days_in_month(2026, 0))
    println(time.days_in_month(2024, 2) or 0)
    println(time.days_in_month(2023, 2) or 0)
    println(time.is_leap_year(2000))
    println(time.is_leap_year(2100))
    println(time.date_utc(0) or "?")
    println(time.iso_utc(0) or "?")
    println(time.seconds(2) or 0)
    println(time.minutes(2) or 0)
    println(time.hours(2) or 0)
    println(time.days(2) or 0)
    println(time.days(9223372036854775807))
}
"""

ERRORS_EXPECTED = "\n".join([
    "time.iso_utc: the timestamp is outside years 1 to 9999",
    "time.date_utc: the timestamp is outside years 1 to 9999",
    "time.from_utc: year must be 1 to 9999",
    "time.from_utc: day 29 is not in month 2 of 1900",
    "time.from_utc: month must be 1 to 12",
    "time.from_utc: day 31 is not in month 4 of 2026",
    "time.from_utc: time must be 00:00:00 to 23:59:59",
    "time.from_utc: time must be 00:00:00 to 23:59:59",
    "time.days_in_month: month must be 1 to 12",
    "29", "28", "true", "false",
    "1970-01-01", "1970-01-01T00:00:00Z",
    "2000", "120000", "7200000", "172800000",
    "time.days: the duration is outside Int",
]) + "\n"


class CoreLibraryTimeTests(unittest.TestCase):
    def write(self, source: str) -> Path:
        temporary = tempfile.TemporaryDirectory(prefix="koschei-time-")
        self.addCleanup(temporary.cleanup)
        path = Path(temporary.name) / "main.ks"
        path.write_text(source, encoding="utf-8")
        return path

    def ks_run(self, path: Path) -> str:
        stdout = io.StringIO()
        with redirect_stdout(stdout), redirect_stderr(io.StringIO()) as errors:
            self.assertEqual(cli_main(["run", "--max-steps", "50000000", str(path)]), 0, errors.getvalue())
        return stdout.getvalue()

    def native(self, path: Path) -> str:
        binary = path.parent / "app"
        with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()) as errors:
            self.assertEqual(cli_main(["build", str(path), "-o", str(binary)]), 0, errors.getvalue())
        completed = subprocess.run([str(binary)], capture_output=True, text=True, timeout=120, check=False)
        self.assertEqual(completed.returncode, 0, completed.stderr)
        return completed.stdout

    def test_matches_python_datetime(self) -> None:
        values = sample()
        expected = "".join(expected_line(value) + "\n" for value in values)
        path = self.write(program(values))
        self.assertEqual(self.ks_run(path), expected)
        if GO is not None:
            self.assertEqual(self.native(path), expected)

    def test_errors_and_helpers(self) -> None:
        path = self.write(ERRORS)
        self.assertEqual(self.ks_run(path), ERRORS_EXPECTED)
        if GO is not None:
            self.assertEqual(self.native(path), ERRORS_EXPECTED)


if __name__ == "__main__":
    unittest.main()
