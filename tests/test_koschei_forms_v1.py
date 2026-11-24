"""Koschei Forms (products/forms): the whole product, driven over HTTP.

Every flow runs twice: under `ks run`, and as the native binary `ks build`
makes, where a broker holds the authority and a seccomp-confined worker runs
the program.
"""
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


GO = shutil.which("go")


class _FormsServer(unittest.TestCase):
    """Starts one Koschei Forms server per test class."""

    native = False

    @classmethod
    def setUpClass(cls) -> None:
        cls.directory = tempfile.TemporaryDirectory(prefix="koschei-forms-")
        cls.root = Path(cls.directory.name)
        cls.data = cls.root / "data"
        cls.data.mkdir()
        cls.port = free_port()
        for name in ("rules.ks", "pages.ks", "csv.ks", "store.ks"):
            shutil.copy(PRODUCT / name, cls.root / name)
        # The product's data directory and bind are literals; the test copy
        # points them at a temporary directory and a free loopback port.
        source = (PRODUCT / "main.ks").read_text(encoding="utf-8")
        source = source.replace("/data/koschei-forms", str(cls.data))
        source = source.replace("0.0.0.0:8080", f"127.0.0.1:{cls.port}")
        (cls.root / "main.ks").write_text(source, encoding="utf-8")
        environment = dict(os.environ, PYTHONPATH=str(ROOT), KOSCHEI_FORMS_PASSWORD=PASSWORD)
        if cls.native:
            binary = cls.root / "koschei-forms"
            built = subprocess.run(
                [sys.executable, "-m", "koschei", "build", str(cls.root / "main.ks"), "-o", str(binary)],
                # Static, as products/forms/Dockerfile builds it.
                capture_output=True, text=True, env=dict(environment, CGO_ENABLED="0"), timeout=600,
            )
            if built.returncode != 0:
                raise RuntimeError(f"ks build failed: {built.stdout}{built.stderr}")
            command = [str(binary)]
        else:
            command = [sys.executable, "-m", "koschei", "run", "--max-steps", "1000000000000", str(cls.root / "main.ks")]
        cls.process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=environment)
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
        for expected in ('"serve"', "0.0.0.0:8080", '"domain": "disk"', '"scope": "/data/koschei-forms"', "KOSCHEI_FORMS_PASSWORD", '"clock"', '"random"'):
            self.assertIn(expected, output)
        for domain in ('"domain": "db"', '"domain": "net"', '"domain": "process"'):
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

        # Storage: one file per form and per kept submission, never the
        # session token itself.
        names = sorted(path.name for path in self.data.iterdir())
        self.assertIn("form_survey", names)
        self.assertEqual(sum(name.startswith("sub_survey_") for name in names), 2)
        self.assertFalse(any(token in name for name in names))

    def test_fields_round_trip_exactly(self) -> None:
        token = self.sign_in()
        self.assertEqual(self.request("POST", "/admin/forms", {"slug": "exact", "redirect_url": ""}, token)[0], 303)
        sent = {"e-mail": "a+b@example.com", "note": "x=1&y=2 %41 Ayşe\n\"q\"", "empty": ""}
        self.assertEqual(self.request("POST", "/f/exact", sent)[0], 200)
        _, _, csv_text = self.request("GET", "/admin/f/exact/csv", cookie=token)
        lines = csv_text.split("\r\n")
        self.assertEqual(lines[0], '"id","received","e-mail","note","empty"')
        self.assertTrue(lines[1].endswith('"a+b@example.com","x=1&y=2 %41 Ayşe\n""q""",""'), lines[1])

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


@unittest.skipUnless(GO, "Go unavailable: the native Forms binary was not built")
class KoscheiFormsNativeTests(KoscheiFormsTests):
    native = True

    def test_worker_is_confined(self) -> None:
        # The process the test started is the broker; its child runs the
        # program under seccomp with no_new_privs and an empty environment.
        # The broker starts its worker right after it starts listening, so
        # give the worker a moment to appear instead of racing it.
        listing = Path(f"/proc/{self.process.pid}/task/{self.process.pid}/children")
        deadline = time.monotonic() + 10
        children = listing.read_text().split()
        while not children and time.monotonic() < deadline:
            time.sleep(0.05)
            children = listing.read_text().split()
        self.assertEqual(len(children), 1)
        status = Path(f"/proc/{children[0]}/status").read_text()
        self.assertIn("Seccomp:\t2", status)
        self.assertIn("NoNewPrivs:\t1", status)
        environment = Path(f"/proc/{children[0]}/environ").read_bytes().split(b"\0")
        self.assertEqual([item for item in environment if item], [b"KOSCHEI_NATIVE_WORKER=v1"])


@unittest.skipUnless(GO, "Go unavailable: the native Forms binary was not built")
class SignInPauseNativeTests(SignInPauseTests):
    native = True


if __name__ == "__main__":
    unittest.main()
