from __future__ import annotations

import unittest
from unittest.mock import patch

from koschei.cli_entry import _configure_utf8_stdio


class _ReconfigurableAsciiStream:
    def __init__(self) -> None:
        self.encoding = "ascii"
        self.errors = "strict"
        self.calls: list[dict[str, str]] = []

    def reconfigure(self, **kwargs: str) -> None:
        self.calls.append(dict(kwargs))
        self.encoding = kwargs.get("encoding", self.encoding)
        self.errors = kwargs.get("errors", self.errors)

    def write(self, text: str) -> int:
        text.encode(self.encoding, errors=self.errors)
        return len(text)

    def flush(self) -> None:
        return None


class CliUtf8StdioTests(unittest.TestCase):
    def test_ascii_public_streams_are_hardened_before_unicode_output(self) -> None:
        stdout = _ReconfigurableAsciiStream()
        stderr = _ReconfigurableAsciiStream()

        with patch("koschei.cli_entry.sys.stdout", stdout), patch(
            "koschei.cli_entry.sys.stderr", stderr
        ):
            _configure_utf8_stdio()
            stdout.write("İzin")
            stderr.write("erişim")

        expected = {"encoding": "utf-8", "errors": "backslashreplace"}
        self.assertEqual(stdout.calls, [expected])
        self.assertEqual(stderr.calls, [expected])

    def test_non_reconfigurable_streams_are_left_alone(self) -> None:
        class PlainStream:
            pass

        with patch("koschei.cli_entry.sys.stdout", PlainStream()), patch(
            "koschei.cli_entry.sys.stderr", PlainStream()
        ):
            _configure_utf8_stdio()


if __name__ == "__main__":
    unittest.main()
