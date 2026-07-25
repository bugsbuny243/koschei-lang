from pathlib import Path


def replace_once(path: str, old: str, new: str) -> None:
    p = Path(path)
    text = p.read_text(encoding='utf-8')
    count = text.count(old)
    if count != 1:
        raise SystemExit(f'{path}: expected one match, found {count}')
    p.write_text(text.replace(old, new), encoding='utf-8')

# semantic.py
replace_once(
    'koschei/semantic.py',
    '    KS2404  Bu yetki türü ilgili işleme izin vermez\n',
    '    KS2404  Bu yetki türü ilgili işleme izin vermez\n'
    '    KS2405  Ağ origin şeması HTTP/HTTPS değil\n',
)
replace_once(
    'koschei/semantic.py',
    'from dataclasses import dataclass\n',
    'from dataclasses import dataclass\nfrom urllib.parse import urlsplit\n',
)
replace_once(
    'koschei/semantic.py',
    'ROOT_CAPABILITY_TYPES = set(ROOT_METHODS) | {"SystemCaps"}\n',
    'ROOT_CAPABILITY_TYPES = set(ROOT_METHODS) | {"SystemCaps"}\n'
    'NET_ORIGIN_SCHEMES = frozenset({"http", "https"})\n',
)
replace_once(
    'koschei/semantic.py',
    '''                return self._check_method_call(\n                    receiver_type,\n                    expression.callee.member,\n                    expression.location,\n                    argument_types,\n                )\n''',
    '''                return self._check_method_call(\n                    receiver_type,\n                    expression.callee.member,\n                    expression.location,\n                    argument_types,\n                    expression.arguments,\n                )\n''',
)
replace_once(
    'koschei/semantic.py',
    '''    def _check_method_call(\n        self,\n        receiver_type: str | None,\n        method_name: str,\n        location: SourceLocation,\n        argument_types: list[str | None] | None = None,\n    ) -> str | None:\n''',
    '''    def _check_net_origin(\n        self,\n        arguments: list[Expression],\n        location: SourceLocation,\n    ) -> None:\n        """Sabit ağ origin'lerini derleme anında HTTP(S) ile sınırlar.\n\n        Dinamik origin ifadeleri burada tahmin edilmez; runtime aynı kuralı\n        _origin_key içinde fail-closed olarak yeniden uygular.\n        """\n        if not arguments:\n            return\n        origin = arguments[0]\n        if not isinstance(origin, Literal) or not isinstance(origin.value, str):\n            return\n        try:\n            parsed = urlsplit(origin.value)\n            scheme = parsed.scheme.lower()\n            hostname = parsed.hostname\n        except ValueError:\n            scheme = ""\n            hostname = None\n        if scheme not in NET_ORIGIN_SCHEMES or hostname is None:\n            raise SemanticError(\n                "KS2405",\n                "NetRoot.allow origin'i yalnızca mutlak http:// veya https:// "\n                f"olabilir; {origin.value!r} reddedildi.",\n                location,\n            )\n\n    def _check_method_call(\n        self,\n        receiver_type: str | None,\n        method_name: str,\n        location: SourceLocation,\n        argument_types: list[str | None] | None = None,\n        arguments: list[Expression] | None = None,\n    ) -> str | None:\n''',
)
replace_once(
    'koschei/semantic.py',
    '''        if receiver_type in ROOT_METHODS:\n            mapping = ROOT_METHODS[receiver_type]\n            if method_name in mapping:\n                self.capability_count += 1\n                return mapping[method_name]\n''',
    '''        if receiver_type in ROOT_METHODS:\n            mapping = ROOT_METHODS[receiver_type]\n            if method_name in mapping:\n                if receiver_type == "NetRoot" and method_name == "allow":\n                    self._check_net_origin(arguments or [], location)\n                self.capability_count += 1\n                return mapping[method_name]\n''',
)

# interpreter.py
replace_once(
    'koschei/interpreter.py',
    'LIST_METHODS = {"length", "get", "push", "contains"}\n',
    'LIST_METHODS = {"length", "get", "push", "contains"}\n'
    'ALLOWED_NET_SCHEMES = frozenset({"http", "https"})\n',
)
replace_once(
    'koschei/interpreter.py',
    '''class NetCaps(_NarrowedCapability):\n    __slots__ = ("origin", "origin_key", "_opener")\n\n    def __init__(self, origin: str) -> None:\n        self.origin = origin\n        self.origin_key = _origin_key(origin)\n        self._opener = urllib.request.build_opener(\n            _ScopedRedirectHandler(self.origin_key)\n        )\n''',
    '''def _build_http_only_opener(\n    origin_key: tuple[str, str, int | None] | None,\n) -> urllib.request.OpenerDirector:\n    """Yalnızca HTTP(S) handler'ları olan bir opener oluşturur.\n\n    urllib.request.build_opener() açık handler verilse bile varsayılan FileHandler,\n    FTPHandler ve DataHandler ekler. Ağ capability'sinin disk/veri şemalarına\n    dönüşmemesi için OpenerDirector elle ve allowlist ile kurulur.\n    """\n    opener = urllib.request.OpenerDirector()\n    for handler in (\n        urllib.request.ProxyHandler(),\n        urllib.request.UnknownHandler(),\n        urllib.request.HTTPHandler(),\n        urllib.request.HTTPDefaultErrorHandler(),\n        _ScopedRedirectHandler(origin_key),\n        urllib.request.HTTPSHandler(),\n        urllib.request.HTTPErrorProcessor(),\n    ):\n        opener.add_handler(handler)\n    return opener\n\n\nclass NetCaps(_NarrowedCapability):\n    __slots__ = ("origin", "origin_key", "_opener")\n\n    def __init__(self, origin: str) -> None:\n        self.origin = origin\n        self.origin_key = _origin_key(origin)\n        self._opener = _build_http_only_opener(self.origin_key)\n''',
)
replace_once(
    'koschei/interpreter.py',
    '''        scheme = parsed.scheme.lower()\n        host = parsed.hostname.lower()\n''',
    '''        scheme = parsed.scheme.lower()\n        if scheme not in ALLOWED_NET_SCHEMES:\n            return None\n        host = parsed.hostname.lower()\n''',
)

# diagnostics.py
replace_once(
    'koschei/diagnostics.py',
    '''    "KS3101": Diagnostic(\n''',
    '''    "KS2405": Diagnostic(\n        code="KS2405",\n        title="Ağ origin şeması reddedildi",\n        summary=(\n            "NetRoot.allow için HTTP/HTTPS dışında bir origin verildi veya "\n            "mutlak bir ağ origin'i oluşturulamadı."\n        ),\n        why=(\n            "urllib gibi genel amaçlı istemciler file:, ftp: veya data: şemalarını "\n            "açabilir. Ağ yetkisi bu şemaları kabul ederse disk ve veri erişimine "\n            "dönüşerek capability sınırını aşar."\n        ),\n        fix=(\n            "Origin'i mutlak bir http:// veya https:// adresi yapın. Yerel dosya "\n            "erişimi gerekiyorsa ayrı DiskCaps/DiskReadCaps jetonu kullanın."\n        ),\n        example=(\n            'let net = caps.net.allow("https://api.example.com")\\n'\n            'let response = net.get("https://api.example.com/data") or return'\n        ),\n    ),\n    "KS3101": Diagnostic(\n''',
)

# 7 regression tests
Path('tests/test_network_scheme_security.py').write_text(r'''from __future__ import annotations

import io
import pathlib
import tempfile
import unittest
import urllib.request
from contextlib import redirect_stderr, redirect_stdout

from koschei.cli import main
from koschei.interpreter import KsError, NetCaps, run
from koschei.parser import parse
from koschei.semantic import SemanticError, check


class NetworkSchemeSecurityTests(unittest.TestCase):
    def test_constant_file_origin_is_rejected_with_ks2405(self) -> None:
        program = parse(
            'fn main(caps: SystemCaps) { '
            'let net = caps.net.allow("file://localhost/tmp/secret.txt") '
            '}'
        )
        with self.assertRaisesRegex(SemanticError, "KS2405"):
            check(program)

    def test_constant_ftp_origin_is_rejected_with_ks2405(self) -> None:
        program = parse(
            'fn main(caps: SystemCaps) { '
            'let net = caps.net.allow("ftp://example.com/pub/data") '
            '}'
        )
        with self.assertRaisesRegex(SemanticError, "KS2405"):
            check(program)

    def test_constant_https_origin_is_accepted(self) -> None:
        check(
            parse(
                'fn main(caps: SystemCaps) { '
                'let net = caps.net.allow("https://api.example.com") '
                '}'
            )
        )

    def test_runtime_rejects_file_url_without_reading_secret(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            secret = pathlib.Path(directory) / "secret.txt"
            secret.write_text("FILE-BRIDGE-SECRET", encoding="utf-8")
            url = "file://localhost" + str(secret)
            result = NetCaps(url).get(url)

        self.assertIsInstance(result, KsError)
        self.assertIn("KS3402", result.message)
        self.assertNotIn("FILE-BRIDGE-SECRET", result.message)

    def test_dynamic_file_origin_is_blocked_by_runtime(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            secret = pathlib.Path(directory) / "secret.txt"
            secret.write_text("DYNAMIC-FILE-SECRET", encoding="utf-8")
            url = "file://localhost" + str(secret)
            source = (
                'fn main(caps: SystemCaps) { '
                f'let origin = "{url}" '
                'let net = caps.net.allow(origin) '
                'let result = net.get(origin) or "engellendi" '
                'println(result) '
                '}'
            )
            output = io.StringIO()
            error = io.StringIO()
            with redirect_stdout(output), redirect_stderr(error):
                exit_code = run(parse(source), [])

        self.assertEqual(exit_code, 0)
        self.assertEqual(output.getvalue(), "engellendi\n")
        self.assertEqual(error.getvalue(), "")
        self.assertNotIn("DYNAMIC-FILE-SECRET", output.getvalue())

    def test_http_opener_contains_no_cross_scheme_handlers(self) -> None:
        handlers = NetCaps("https://api.example.com")._opener.handlers
        forbidden = (
            urllib.request.FileHandler,
            urllib.request.FTPHandler,
            urllib.request.DataHandler,
        )
        for handler in handlers:
            self.assertNotIsInstance(handler, forbidden)

    def test_caps_command_rejects_file_origin_before_manifest(self) -> None:
        source = (
            'fn main(caps: SystemCaps) { '
            'let net = caps.net.allow("file://localhost/tmp/secret.txt") '
            '}'
        )
        with tempfile.TemporaryDirectory() as directory:
            path = pathlib.Path(directory) / "attack.ks"
            path.write_text(source, encoding="utf-8")
            output = io.StringIO()
            error = io.StringIO()
            with redirect_stdout(output), redirect_stderr(error):
                exit_code = main(["caps", str(path)])

        self.assertEqual(exit_code, 1)
        self.assertEqual(output.getvalue(), "")
        self.assertIn("KS2405", error.getvalue())
        self.assertNotIn("DİSK: yok", output.getvalue())


if __name__ == "__main__":
    unittest.main()
''', encoding='utf-8')
