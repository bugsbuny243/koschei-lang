"""Network through the native capability broker (G2, third step).

`ks run` and the binary must give the same bytes for the same requests:
statuses, redirects, budgets, encodings, transport failures, proxies and TLS
follow net_v1 in both, and the request the server sees is the same.
"""
from __future__ import annotations

import http.server
import os
from pathlib import Path
import platform
import shutil
import socket
import ssl
import subprocess
import sys
import tempfile
import threading
import unittest

from koschei import net_v1

ROOT = Path(__file__).resolve().parent.parent
GO = shutil.which("go")
OPENSSL = shutil.which("openssl")
SUPPORTED = GO is not None and sys.platform == "linux" and platform.machine() in {"x86_64", "AMD64"}
SCHEMES = frozenset({"http", "https"})


class _Handler(http.server.BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, *arguments: object) -> None:
        pass

    def _send(self, status: int, body: bytes = b"", headers: dict[str, str] | None = None) -> None:
        self.send_response(status)
        for name, value in (headers or {}).items():
            self.send_header(name, value)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:  # noqa: N802 - http.server API
        path = self.path
        if "different.example" in self.requestline:
            # http.server folds a leading "//" in self.path; the request line
            # is what the client sent.
            self._send(200, self.requestline.encode())
        elif path == "/ok":
            self._send(200, "merhaba ğ".encode(), {"Content-Type": "text/plain; charset=utf-8"})
        elif path == "/404":
            self._send(404, b"nope")
        elif path == "/r":
            self._send(302, headers={"Location": "ok"})
        elif path == "/abs":
            self._send(301, headers={"Location": f"http://127.0.0.1:{self.server.server_port}/ok"})
        elif path == "/out":
            self._send(302, headers={"Location": "http://example.com/"})
        elif path == "/scheme":
            self._send(307, headers={"Location": "file:///etc/passwd"})
        elif path.startswith("/chain/"):
            left = int(path.rsplit("/", 1)[1])
            if left == 0:
                self._send(200, b"end")
            else:
                self._send(308, headers={"Location": f"/chain/{left - 1}"})
        elif path == "/noloc":
            self._send(302, b"no location")
        elif path == "/gz":
            self._send(200, b"x", {"Content-Encoding": "gzip"})
        elif path == "/identity":
            self._send(200, b"plain", {"Content-Encoding": " Identity "})
        elif path == "/latin":
            self._send(200, b"caf\xe9", {"Content-Type": "text/plain; charset=iso-8859-1"})
        elif path == "/exact":
            self._send(200, b"a" * 1_048_576)
        elif path == "/big":
            self._send(200, b"a" * 1_048_577)
        elif path == "/headers":
            self._send(200, repr(sorted(self.headers.items())).encode())
        elif path == "/close":
            self.close_connection = True
        elif path == "/short":
            self.send_response(200)
            self.send_header("Content-Length", "10")
            self.end_headers()
            self.wfile.write(b"abc")
            self.close_connection = True
        elif path == "/garbage":
            self.wfile.write(b"HELLO THERE\r\n\r\n")
            self.close_connection = True
        else:
            self._send(200, ("seen " + path).encode())


class _Proxy(http.server.BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, *arguments: object) -> None:
        pass

    def do_GET(self) -> None:  # noqa: N802
        body = f"proxy {self.requestline} host={self.headers.get('Host')}".encode()
        self.send_response(200)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_CONNECT(self) -> None:  # noqa: N802
        self.send_response(403)
        self.send_header("Content-Length", "0")
        self.end_headers()
        self.close_connection = True


def _serve(handler: type, context: ssl.SSLContext | None = None) -> http.server.ThreadingHTTPServer:
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
    if context is not None:
        server.socket = context.wrap_socket(server.socket, server_side=True)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server


def _closed_port() -> int:
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        return probe.getsockname()[1]


def _program(origin: str, urls: list[str], extra: str = "") -> str:
    listed = ", ".join(f'"{url}"' for url in urls)
    return f"""
fn main(caps: SystemCaps) {{
    let net = caps.net.allow("{origin}")
    for url in [{listed}] {{
        let response = net.get(url) or {{
            println(net.get(url))
            continue
        }}
        println("{{response.status()}} {{response.text().length()}} {{response.text()}}")
    }}
{extra}}}
"""


class NetRulesTests(unittest.TestCase):
    def test_url_grammar(self) -> None:
        accepted = {
            "http://Example.COM": ("http", "example.com", 80, "/"),
            "HTTPS://example.com:8443/a?b=1#frag": ("https", "example.com", 8443, "/a?b=1"),
            "http://127.0.0.1:18471?x": ("http", "127.0.0.1", 18471, "/?x"),
            "http://[::1]:8080/p": ("http", "::1", 8080, "/p"),
            "http://[::ffff:1.2.3.4]/": ("http", "::ffff:1.2.3.4", 80, "/"),
            "http://a_b.example/%41(b)": ("http", "a_b.example", 80, "/%41(b)"),
        }
        for url, expected in accepted.items():
            with self.subTest(url):
                parsed = net_v1.parse_url(url, SCHEMES)
                self.assertIsNotNone(parsed)
                self.assertEqual((parsed.scheme, parsed.host, parsed.port, parsed.target), expected)
        rejected = [
            "ftp://example.com/", "file:///etc/passwd", "example.com", "http://", "http:///x",
            "http://user@example.com/", "http://example.com:/", "http://example.com:0/",
            "http://example.com:65536/", "http://example.com:018080/", "http://exa mple.com/",
            "http://example.com/a b", "http://example.com/%zz", "http://example.com/%4",
            "http://example.com/{x}", "http://ex\\ample.com/", "http://[::1/", "http://[::1]x/",
            "http://ğ.example/", "http://example.com/ğ", "1http://example.com/",
            "http://[::::]/", "http://[1.2.3.4]/", "http://[1::2::3]/", "http://[::ffff:01.2.3.4]/",
        ]
        for url in rejected:
            with self.subTest(url):
                self.assertIsNone(net_v1.parse_url(url, SCHEMES))

    def test_redirect_resolution_keeps_the_path_as_written(self) -> None:
        base = net_v1.parse_url("http://h:81/a/b?q", SCHEMES)
        cases = {
            "c": "http://h:81/a/c",
            "../c": "http://h:81/a/../c",
            "/c": "http://h:81/c",
            "?z": "http://h:81/a/b?z",
            "//other/x": "http://other/x",
            "https://h:81/y#f": "https://h:81/y",
        }
        for location, expected in cases.items():
            with self.subTest(location):
                self.assertEqual(net_v1.resolve_location(base, location, SCHEMES).text(), expected)

    def test_proxy_choice(self) -> None:
        def proxy(url: str, **environ: str) -> str | None:
            return net_v1.proxy_for(net_v1.parse_url(url, SCHEMES), environ)

        self.assertIsNone(proxy("http://example.com/"))
        self.assertEqual(proxy("http://example.com/", HTTP_PROXY="p:3128"), "http://p:3128")
        self.assertEqual(proxy("http://example.com/", http_proxy="http://a:1", HTTP_PROXY="http://b:2"), "http://a:1")
        self.assertIsNone(proxy("https://example.com/", http_proxy="http://a:1"))
        for loopback in ("http://localhost/", "http://a.localhost/", "http://127.9.9.9/", "http://[::1]/"):
            self.assertIsNone(proxy(loopback, http_proxy="http://a:1"))
        bypass = {
            "*": "http://example.com/",
            "example.com": "http://api.example.com/",
            ".example.com": "http://example.com/",
            "*.example.com": "http://x.example.com/",
            "10.0.0.0/8": "http://10.1.2.3/",
            "10.1.2.3": "http://10.1.2.3/",
            "example.com:8080": "http://example.com:8080/",
        }
        for no_proxy, url in bypass.items():
            with self.subTest(no_proxy):
                self.assertIsNone(proxy(url, http_proxy="http://a:1", no_proxy=no_proxy))
        kept = {
            "example.com:8080": "http://example.com/",
            "ample.com": "http://example.com/",
            "10.0.0.0/8": "http://11.1.2.3/",
        }
        for no_proxy, url in kept.items():
            with self.subTest(kept=no_proxy):
                self.assertEqual(proxy(url, http_proxy="http://a:1", no_proxy=no_proxy), "http://a:1")


@unittest.skipUnless(SUPPORTED, "the broker is linux/amd64")
class NativeNetParityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.server = _serve(_Handler)
        cls.proxy = _serve(_Proxy)

    @classmethod
    def tearDownClass(cls) -> None:
        for server in (cls.server, cls.proxy):
            server.shutdown()
            server.server_close()

    def both(self, source: str, environ: dict[str, str] | None = None) -> bytes:
        clean = {
            key: value for key, value in os.environ.items()
            if key.lower() not in {"http_proxy", "https_proxy", "no_proxy", "ssl_cert_file", "ssl_cert_dir"}
        }
        clean.update(environ or {})
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            (base / "main.ks").write_text(source, encoding="utf-8")
            run = subprocess.run(
                [sys.executable, "-m", "koschei", "run", "main.ks"], cwd=base,
                env=dict(clean, PYTHONPATH=str(ROOT)), capture_output=True, timeout=180, check=False,
            )
            self.assertEqual(run.returncode, 0, run.stderr.decode())
            build = subprocess.run(
                [sys.executable, "-m", "koschei", "build", "main.ks", "-o", "app"], cwd=base,
                env=dict(os.environ, PYTHONPATH=str(ROOT)), capture_output=True, timeout=300, check=False,
            )
            self.assertEqual(build.returncode, 0, build.stderr.decode())
            native = subprocess.run(
                [str(base / "app")], cwd=base, env=clean, capture_output=True, timeout=180, check=False,
            )
            self.assertEqual(native.returncode, 0, native.stderr.decode())
            self.assertEqual(native.stdout, run.stdout)
            return run.stdout

    def test_requests_match_ks_run(self) -> None:
        origin = f"http://127.0.0.1:{self.server.server_port}"
        paths = [
            "/ok", "/404", "/r", "/abs", "/out", "/scheme", "/chain/5", "/chain/6", "/noloc",
            "/gz", "/identity", "/latin", "/exact", "/big", "/headers", "/close", "/short",
            "/garbage", "/a(b)/../c?x=1&y=%41", "/ok#fragment", "//different.example/p%2Fq?q=1",
        ]
        others = [
            f"HTTP://127.0.0.1:{self.server.server_port}/ok",
            f"http://user@127.0.0.1:{self.server.server_port}/ok",
            f"http://127.0.0.1:{self.server.server_port}/a%zz",
            f"http://127.0.0.1:{self.server.server_port}/a b",
            f"http://localhost:{self.server.server_port}/ok",
            "ftp://127.0.0.1/",
        ]
        closed = _closed_port()
        extra = (
            f'    println(caps.net.allow("http://127.0.0.1:{closed}").get("http://127.0.0.1:{closed}/"))\n'
            '    let bad = "file:///etc"\n'
            '    println(caps.net.allow(bad).get("file:///etc/passwd"))\n'
            '    println(caps.net.allow("http://127.0.0.1"))\n'
            f'    let kept = net.get("{origin}/ok") or return\n'
            "    println(kept)\n"
        )
        output = self.both(_program(origin, [origin + path for path in paths] + others, extra)).decode()
        lines = output.splitlines()
        self.assertEqual(lines[0], "200 9 merhaba ğ")
        self.assertEqual(lines[1], "404 4 nope")
        self.assertEqual(lines[2], "200 9 merhaba ğ")
        self.assertEqual(lines[4], "KS3402: Ağ yönlendirmesi kapsam dışına çıktı: http://example.com/")
        self.assertEqual(lines[5], "KS3402: Ağ yönlendirmesi kapsam dışına çıktı: file:///etc/passwd")
        self.assertEqual(lines[6], "200 3 end")
        self.assertEqual(lines[7], f"API isteği başarısız: çok fazla yönlendirme: {origin}/chain/6")
        self.assertEqual(lines[8], "302 11 no location")
        self.assertIn("KSNET_CONTENT_ENCODING", lines[9])
        self.assertEqual(lines[10], "200 5 plain")
        self.assertEqual(lines[11], f"API yanıtı geçerli UTF-8 metin değil: {origin}/latin")
        self.assertTrue(lines[12].startswith("200 1048576 "))
        self.assertIn("KSNET_RESPONSE_BUDGET", lines[13])
        self.assertIn("('User-Agent', 'koschei/1')", lines[14])
        self.assertIn("('Accept-Encoding', 'identity')", lines[14])
        self.assertEqual(lines[15], f"API isteği başarısız: ECONNRESET: {origin}/close")
        self.assertEqual(lines[16], f"API isteği başarısız: ECONNRESET: {origin}/short")
        self.assertEqual(lines[17], f"API isteği başarısız: EPROTO: {origin}/garbage")
        self.assertEqual(lines[18], "200 25 seen /a(b)/../c?x=1&y=%41")
        # A leading "//" stays a path; it never becomes an authority.
        self.assertEqual(lines[20], "200 42 GET //different.example/p%2Fq?q=1 HTTP/1.1")
        self.assertEqual(lines[-4], f"API isteği başarısız: ECONNREFUSED: http://127.0.0.1:{closed}/")
        self.assertEqual(lines[-3], "KS3402: Ağ origin kapsamı dışında erişim reddedildi: file:///etc/passwd")
        self.assertEqual(lines[-2:], ["<NetCaps>", "<Response>"])

    def test_proxies_match_ks_run(self) -> None:
        proxy = f"http://127.0.0.1:{self.proxy.server_port}"
        source = _program("http://koschei.proxy.test:8080", ["http://koschei.proxy.test:8080/p?q"], (
            '    println(caps.net.allow("https://koschei.proxy.test").get("https://koschei.proxy.test/"))\n'
        ))
        output = self.both(source, {"http_proxy": proxy, "HTTPS_PROXY": proxy, "no_proxy": "example.org"}).decode()
        seen = "proxy GET http://koschei.proxy.test:8080/p?q HTTP/1.1 host=koschei.proxy.test:8080"
        self.assertEqual(output.splitlines(), [
            f"200 {len(seen)} {seen}",
            "API isteği başarısız: EIO: https://koschei.proxy.test/",
        ])
        output = self.both(source, {"http_proxy": "socks5://127.0.0.1:1", "https_proxy": proxy}).decode()
        self.assertEqual(output.splitlines()[0], "API isteği başarısız: EIO: http://koschei.proxy.test:8080/p?q")
        loopback = _program(f"http://127.0.0.1:{self.server.server_port}", [f"http://127.0.0.1:{self.server.server_port}/ok"])
        self.assertEqual(self.both(loopback, {"http_proxy": proxy}).decode(), "200 9 merhaba ğ\n")

    @unittest.skipUnless(OPENSSL, "openssl is not installed")
    def test_tls_matches_ks_run(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            key, certificate = Path(directory) / "key.pem", Path(directory) / "cert.pem"
            subprocess.run(
                [OPENSSL, "req", "-x509", "-newkey", "rsa:2048", "-nodes", "-days", "2",
                 "-subj", "/CN=127.0.0.1", "-addext", "subjectAltName=IP:127.0.0.1",
                 "-keyout", str(key), "-out", str(certificate)],
                capture_output=True, check=True,
            )
            context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
            context.load_cert_chain(certificate, key)
            server = _serve(_Handler, context)
            try:
                origin = f"https://127.0.0.1:{server.server_port}"
                source = _program(origin, [origin + "/ok"])
                untrusted = self.both(source).decode()
                self.assertEqual(untrusted, f"API isteği başarısız: ETLS: {origin}/ok\n")
                trusted = self.both(source, {"SSL_CERT_FILE": str(certificate)}).decode()
                self.assertEqual(trusted, "200 9 merhaba ğ\n")
            finally:
                server.shutdown()
                server.server_close()


if __name__ == "__main__":
    unittest.main()
