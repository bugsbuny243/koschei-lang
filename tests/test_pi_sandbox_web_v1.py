from __future__ import annotations

from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
WEB = ROOT / "distribution" / "pi-sandbox-web"


class PiSandboxWebV1Tests(unittest.TestCase):
    def test_sdk_is_initialized_in_sandbox_mode(self) -> None:
        app = (WEB / "app.js").read_text(encoding="utf-8")
        self.assertIn("sandbox: true", app)
        self.assertIn("version: '2.0'", app)
        self.assertIn("window.Pi.authenticate", app)

    def test_frontend_contains_no_server_secret_or_payment_completion(self) -> None:
        text = "\n".join(
            path.read_text(encoding="utf-8")
            for path in WEB.iterdir()
            if path.is_file()
        ).lower()
        self.assertNotIn("pi_api_key", text)
        self.assertNotIn("authorization: key", text)
        self.assertNotIn("/approve", text)
        self.assertNotIn("/complete", text)
        self.assertNotIn("createpayment", text)

    def test_sdk_is_loaded_from_official_endpoint(self) -> None:
        html = (WEB / "index.html").read_text(encoding="utf-8")
        self.assertIn('https://sdk.minepi.com/pi-sdk.js', html)

    def test_local_server_defaults_to_port_3000_and_loopback(self) -> None:
        server = (ROOT / "tools" / "serve_pi_sandbox_v1.py").read_text(encoding="utf-8")
        self.assertIn('default="127.0.0.1"', server)
        self.assertIn("default=3000", server)
        self.assertIn('"127.0.0.1", "localhost", "::1"', server)


if __name__ == "__main__":
    unittest.main()
