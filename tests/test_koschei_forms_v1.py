"""Koschei Forms (products/forms): the whole product, driven over HTTP."""
from __future__ import annotations

from contextlib import redirect_stderr, redirect_stdout
import http.client
import io
import os
from pathlib import Path
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import unittest
from urllib.parse import urlencode

from koschei.cli_entry import main as cli_main

ROOT = Path(__file__).resolve().parent.parent
PRODUCT = ROOT / "products" / "forms"
PASSWORD = "correct-horse-battery"


def free_port() -> int:
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        return probe.getsockname()[1]


class _FormsServer(unittest.TestCase):
    """Starts one Koschei Forms server per test class."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.directory = tempfile.TemporaryDirectory(prefix="koschei-forms-")
        cls.root = Path(cls.directory.name)
        cls.port = free_port()
        for name in ("rules.ks", "pages.ks", "csv.ks"):
            shutil.copy(PRODUCT / name, cls.root / name)
        # The product's database path and bind are literals; the test copy
        # points them at a temporary directory and a free loopback port.
        source = (PRODUCT / "main.ks").read_text(encoding="utf-8")
        source = source.replace("/data/koschei-forms.db", str(cls.root / "forms.db"))
        source = source.replace("0.0.0.0:8080", f"127.0.0.1:{cls.port}")
        (cls.root / "main.ks").write_text(source, encoding="utf-8")
        cls.process = subprocess.Popen(
            [sys.executable, "-m", "koschei", "run", "--max-steps", "1000000000000", str(cls.root / "main.ks")],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            env=dict(os.environ, PYTHONPATH=str(ROOT), KOSCHEI_FORMS_PASSWORD=PASSWORD),
        )
        deadline = time.monotonic() + 30
        while True:
            try:
                status, _, _ = cls.request("GET", "/")
                if status == 200:
                    break
            except OSError:
                pass
            if time.monotonic() > deadline:
                raise RuntimeError("Koschei Forms did not start")
            time.sleep(0.1)

    @classmethod
    def tearDownClass(cls) -> None:
        cls.process.kill()
        cls.process.communicate(timeout=10)
        cls.directory.cleanup()

    @classmethod
    def request(cls, method: str, path: str, form: dict | None = None, cookie: str = "", raw: bytes | None = None):
        connection = http.client.HTTPConnection("127.0.0.1", cls.port, timeout=15)
        headers = {"Host": "forms.example"}
        body = raw
        if form is not None:
            body = urlencode(form).encode()
            headers["Content-Type"] = "application/x-www-form-urlencoded"
        if cookie:
            headers["Cookie"] = f"kf_session={cookie}"
        connection.request(method, path, body=body, headers=headers)
        response = connection.getresponse()
        return response.status, dict(response.getheaders()), response.read().decode("utf-8")

    def sign_in(self) -> str:
        status, headers, _ = self.request("POST", "/admin/login", {"password": PASSWORD})
        self.assertEqual(status, 303)
        cookie = headers["Set-Cookie"]
        self.assertIn("HttpOnly; Secure; SameSite=Strict", cookie)
        return cookie.split("kf_session=", 1)[1].split(";", 1)[0]



class KoscheiFormsTests(_FormsServer):
    def test_manifest_names_everything_it_reaches(self) -> None:
        stdout = io.StringIO()
        with redirect_stdout(stdout), redirect_stderr(stdout):
            self.assertEqual(cli_main(["caps", "--json", str(PRODUCT / "main.ks")]), 0)
        output = stdout.getvalue()
        for expected in ('"serve"', "0.0.0.0:8080", '"db"', "/data/koschei-forms.db", "KOSCHEI_FORMS_PASSWORD", '"clock"', '"random"'):
            self.assertIn(expected, output)
        for domain in ('"domain": "disk"', '"domain": "net"', '"domain": "process"'):
            self.assertNotIn(domain, output)

    def test_full_flow(self) -> None:
        self.assertEqual(self.request("POST", "/f/survey", {"a": "1"})[0], 404)
        token = self.sign_in()
        status, _, _ = self.request("POST", "/admin/forms", {"slug": "survey", "redirect_url": ""}, token)
        self.assertEqual(status, 303)
        status, _, body = self.request("POST", "/admin/forms", {"slug": "survey", "redirect_url": ""}, token)
        self.assertEqual(status, 409)

        status, _, body = self.request(
            "POST", "/f/survey",
            {"email": "ada@example.com", "message": "<script>alert(1)</script> çay", "_gotcha": "", "_source": "x"},
        )
        self.assertEqual(status, 200)
        self.assertIn("Thank you", body)
        self.assertEqual(self.request("POST", "/f/survey", {"email": "bot", "_gotcha": "spam"})[0], 200)
        self.assertEqual(self.request("POST", "/f/survey", {"email": "=HYPERLINK(\"x\")", "message": "2"})[0], 200)

        status, headers, page = self.request("GET", "/admin/f/survey", cookie=token)
        self.assertEqual(status, 200)
        self.assertIn("default-src 'none'", headers["Content-Security-Policy"])
        self.assertIn("&lt;script&gt;alert(1)&lt;/script&gt; çay", page)
        self.assertNotIn("<script>", page)
        self.assertNotIn("_source", page)
        self.assertIn("Showing the latest 2 of 2", page)

        status, headers, csv_text = self.request("GET", "/admin/f/survey/csv", cookie=token)
        self.assertEqual(status, 200)
        self.assertEqual(headers["Content-Disposition"], 'attachment; filename="survey.csv"')
        lines = csv_text.split("\r\n")
        self.assertEqual(lines[0], '"id","received","email","message"')
        self.assertIn('"ada@example.com","<script>alert(1)</script> çay"', lines[1])
        self.assertIn('"\'=HYPERLINK(""x"")","2"', lines[2])

        status, _, dashboard = self.request("GET", "/admin", cookie=token)
        self.assertIn('<a href="/admin/f/survey">survey</a></td><td>2</td>', dashboard)
        self.assertIn("http://forms.example/f/contact", dashboard)

    def test_redirects_are_set_by_the_administrator_only(self) -> None:
        token = self.sign_in()
        self.assertEqual(self.request("POST", "/admin/forms", {"slug": "jobs", "redirect_url": "https://example.com/thanks"}, token)[0], 303)
        status, headers, _ = self.request("POST", "/f/jobs", {"name": "x", "_next": "https://evil.example"})
        self.assertEqual(status, 303)
        self.assertEqual(headers["Location"], "https://example.com/thanks")
        for bad in ("javascript:alert(1)", "https://x.example/a b", 'https://x.example/"'):
            self.assertEqual(self.request("POST", "/admin/forms", {"slug": "bad", "redirect_url": bad}, token)[0], 400)
        for bad in ("Bad", "a/b", "x" * 41, ""):
            self.assertEqual(self.request("POST", "/admin/forms", {"slug": bad}, token)[0], 400, bad)

    def test_admin_requires_a_session(self) -> None:
        for path in ("/admin/f/survey", "/admin/f/survey/csv"):
            status, headers, _ = self.request("GET", path)
            self.assertEqual(status, 303, path)
            self.assertEqual(headers["Location"], "/admin")
            status, _, _ = self.request("GET", path, cookie="a" * 64)
            self.assertEqual(status, 303, path)
        self.assertIn("Sign in", self.request("GET", "/admin")[2])
        self.assertEqual(self.request("POST", "/admin/forms", {"slug": "sneaky"})[0], 303)
        self.assertEqual(self.request("GET", "/f/survey")[0], 405)
        self.assertEqual(self.request("GET", "/admin/f/%22%0d%0a/csv")[0], 404)

    def test_sign_out_ends_the_session(self) -> None:
        token = self.sign_in()
        self.assertEqual(self.request("GET", "/admin/f/survey", cookie=token)[0], 200)
        status, headers, _ = self.request("POST", "/admin/logout", {}, token)
        self.assertEqual(status, 303)
        self.assertIn("Max-Age=0", headers["Set-Cookie"])
        self.assertEqual(self.request("GET", "/admin/f/survey", cookie=token)[0], 303)



class SignInPauseTests(_FormsServer):
    def test_wrong_passwords_pause_sign_in(self) -> None:
        # Its own server: after ten failures sign-in pauses for 15 minutes.
        statuses = [self.request("POST", "/admin/login", {"password": f"wrong-{index}"})[0] for index in range(10)]
        self.assertEqual(statuses, [401] * 10)
        self.assertEqual(self.request("POST", "/admin/login", {"password": PASSWORD})[0], 429)


if __name__ == "__main__":
    unittest.main()
