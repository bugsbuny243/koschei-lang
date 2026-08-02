"""Fail-closed validation for the Koschei Foreign Contract v1.

This module deliberately validates contracts only. It never starts a process,
loads a shared library, imports foreign code, or grants capabilities. Foreign
execution can be added only after the contract, artifact identity, protocol,
and resource budgets are sealed.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

SCHEMA = "koschei.foreign/v1"
PROTOCOL = "koschei-json/v1"
MAX_CONTRACT_BYTES = 1_048_576
MAX_FUNCTIONS = 256
MAX_PARAMETERS = 32
MAX_TYPE_DEPTH = 8
MAX_TYPE_LENGTH = 256
MAX_ARTIFACT_BYTES = 268_435_456

LANGUAGES = frozenset(
    {
        "c",
        "cpp",
        "rust",
        "go",
        "python",
        "javascript",
        "java",
        "dotnet",
        "wasm",
    }
)
BASE_TYPES = frozenset({"Bool", "Int", "Float", "String", "Data", "Void"})
CAPABILITY_NAMES = frozenset(
    {
        "SystemCaps",
        "NetRoot",
        "DiskRoot",
        "EnvRoot",
        "ProcessRoot",
        "NetCaps",
        "DiskCaps",
        "DiskReadCaps",
        "EnvCaps",
        "ProcessCaps",
    }
)
IDENTIFIER = re.compile(r"^[a-z][a-z0-9_]{0,63}$")
MODULE_NAME = re.compile(r"^[a-z][a-z0-9_]{0,63}(?:\.[a-z][a-z0-9_]{0,63})*$")
SHA256_HEX = re.compile(r"^[0-9a-f]{64}$")
ARTIFACT_PART = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
RESERVED_FUNCTIONS = frozenset({"main", "init", "__init__", "__main__"})

_LIMITS = {
    "max_request_bytes": (1, 16_777_216),
    "max_response_bytes": (1, 16_777_216),
    "max_millis": (1, 60_000),
    "max_memory_bytes": (1_048_576, 2_147_483_648),
    "max_calls": (1, 100_000),
}


class ForeignContractError(ValueError):
    """A public, coded foreign-contract validation failure."""

    def __init__(self, code: str, message: str) -> None:
        self.code = code
        self.message = message
        super().__init__(f"{code}: {message}")


@dataclass(frozen=True, slots=True)
class ForeignContract:
    source: Path
    module: str
    language: str
    isolation: str
    artifact: Path
    artifact_sha256: str
    fingerprint: str
    functions: int
    canonical: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": True,
            "schema": SCHEMA,
            "source": str(self.source),
            "module": self.module,
            "language": self.language,
            "isolation": self.isolation,
            "protocol": PROTOCOL,
            "artifact": str(self.artifact),
            "artifact_sha256": self.artifact_sha256,
            "fingerprint": self.fingerprint,
            "functions": self.functions,
        }


def _error(code: str, message: str) -> ForeignContractError:
    return ForeignContractError(code, message)


def _duplicate_safe_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise _error("KS3801", f"Yabancı sözleşmede yinelenen JSON anahtarı: {key}")
        result[key] = value
    return result


def _expect_object(value: Any, where: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise _error("KS3801", f"{where} bir JSON object olmalıdır.")
    return value


def _expect_array(value: Any, where: str) -> list[Any]:
    if not isinstance(value, list):
        raise _error("KS3801", f"{where} bir JSON array olmalıdır.")
    return value


def _expect_string(value: Any, where: str) -> str:
    if not isinstance(value, str):
        raise _error("KS3801", f"{where} String olmalıdır.")
    if "\x00" in value:
        raise _error("KS3801", f"{where} NUL karakteri içeremez.")
    return value


def _exact_keys(value: dict[str, Any], expected: set[str], where: str) -> None:
    missing = sorted(expected - set(value))
    unknown = sorted(set(value) - expected)
    if missing:
        raise _error("KS3801", f"{where} eksik alanlar: {', '.join(missing)}")
    if unknown:
        raise _error("KS3801", f"{where} tanımsız alanlar: {', '.join(unknown)}")


def _positive_limit(value: Any, name: str) -> int:
    if type(value) is not int:
        raise _error("KS3804", f"limits.{name} Int olmalıdır.")
    minimum, maximum = _LIMITS[name]
    if not minimum <= value <= maximum:
        raise _error(
            "KS3804",
            f"limits.{name} {minimum} ile {maximum} arasında olmalıdır; {value} verildi.",
        )
    return value


class _TypeParser:
    def __init__(self, text: str) -> None:
        if len(text) > MAX_TYPE_LENGTH:
            raise _error("KS3803", "Foreign ABI tipi çok uzun.")
        self.text = text
        self.index = 0

    def parse(self, *, allow_void: bool) -> str:
        result = self._type(0)
        self._space()
        if self.index != len(self.text):
            raise _error(
                "KS3803",
                f"Foreign ABI tipinde beklenmeyen metin: {self.text[self.index:]}",
            )
        if result == "Void" and not allow_void:
            raise _error("KS3803", "Void yalnızca foreign fonksiyon dönüş tipi olabilir.")
        return result

    def _space(self) -> None:
        while self.index < len(self.text) and self.text[self.index].isspace():
            self.index += 1

    def _name(self) -> str:
        self._space()
        start = self.index
        while self.index < len(self.text) and (
            self.text[self.index].isalnum() or self.text[self.index] == "_"
        ):
            self.index += 1
        if start == self.index:
            raise _error("KS3803", f"Foreign ABI tipi bekleniyordu: {self.text!r}")
        return self.text[start : self.index]

    def _take(self, expected: str) -> None:
        self._space()
        if not self.text.startswith(expected, self.index):
            raise _error("KS3803", f"Foreign ABI tipinde '{expected}' bekleniyordu.")
        self.index += len(expected)

    def _type(self, depth: int) -> str:
        if depth > MAX_TYPE_DEPTH:
            raise _error("KS3803", f"Foreign ABI tip derinliği {MAX_TYPE_DEPTH} sınırını aşıyor.")
        name = self._name()
        if name in CAPABILITY_NAMES or name.endswith("Caps") or name.endswith("Root"):
            raise _error(
                "KS3803",
                f"Capability tipi Foreign ABI sınırından geçirilemez: {name}",
            )
        self._space()
        if self.index >= len(self.text) or self.text[self.index] != "<":
            if name not in BASE_TYPES:
                raise _error("KS3803", f"Foreign ABI için desteklenmeyen tip: {name}")
            return name

        self.index += 1
        arguments: list[str] = []
        while True:
            arguments.append(self._type(depth + 1))
            self._space()
            if self.index < len(self.text) and self.text[self.index] == ",":
                self.index += 1
                continue
            self._take(">")
            break

        expected_arity = {"List": 1, "Map": 2, "Option": 1, "Result": 2}
        if name not in expected_arity:
            raise _error("KS3803", f"Foreign ABI generic tipi desteklenmiyor: {name}")
        if len(arguments) != expected_arity[name]:
            raise _error(
                "KS3803",
                f"{name}<{', '.join(arguments)}> {expected_arity[name]} tip argümanı bekler.",
            )
        if name == "Map" and arguments[0] != "String":
            raise _error("KS3803", "Foreign ABI Map anahtarı yalnızca String olabilir.")
        if any(item == "Void" for item in arguments):
            raise _error("KS3803", "Void bir generic tipin içine konamaz.")
        return f"{name}<{','.join(arguments)}>"


def normalize_type(text: Any, *, allow_void: bool) -> str:
    value = _expect_string(text, "foreign tip")
    return _TypeParser(value).parse(allow_void=allow_void)


def _safe_artifact_path(contract_path: Path, raw: Any) -> Path:
    value = _expect_string(raw, "artifact.path")
    path = Path(value)
    if path.is_absolute() or not path.parts:
        raise _error("KS3806", "artifact.path sözleşmeye göre göreli bir yol olmalıdır.")
    if "\\" in value or any(part in {"", ".", ".."} for part in path.parts):
        raise _error("KS3806", "artifact.path '.', '..' veya ters bölü içeremez.")
    if any(not ARTIFACT_PART.fullmatch(part) for part in path.parts):
        raise _error(
            "KS3806",
            "artifact.path yalnızca taşınabilir ASCII harf, sayı, nokta, alt çizgi ve tire içerebilir.",
        )

    root = contract_path.parent.resolve()
    current = root
    for part in path.parts:
        current = current / part
        if current.is_symlink():
            raise _error("KS3806", "Foreign artifact yolu sembolik bağ içeremez.")
    resolved = (root / path).resolve()
    try:
        resolved.relative_to(root)
    except ValueError as error:
        raise _error("KS3806", "Foreign artifact sözleşme dizininin dışına çıkamaz.") from error
    if not resolved.is_file():
        raise _error("KS3806", f"Foreign artifact bulunamadı: {resolved}")
    size = resolved.stat().st_size
    if size > MAX_ARTIFACT_BYTES:
        raise _error(
            "KS3806",
            f"Foreign artifact {MAX_ARTIFACT_BYTES} byte sınırını aşıyor: {size}",
        )
    return resolved


def _hash_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(1_048_576):
            digest.update(chunk)
    return digest.hexdigest()


def _canonical_bytes(value: dict[str, Any]) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def _validate_function(raw: Any, seen: set[str]) -> dict[str, Any]:
    function = _expect_object(raw, "functions[]")
    _exact_keys(function, {"name", "parameters", "returns", "effects"}, "functions[]")
    name = _expect_string(function["name"], "functions[].name")
    if not IDENTIFIER.fullmatch(name):
        raise _error("KS3805", f"Geçersiz foreign fonksiyon adı: {name}")
    if name in RESERVED_FUNCTIONS:
        raise _error("KS3805", f"Ayrılmış foreign fonksiyon adı kullanılamaz: {name}")
    if name in seen:
        raise _error("KS3805", f"Foreign fonksiyon adı yinelendi: {name}")
    seen.add(name)

    parameters = _expect_array(function["parameters"], f"functions.{name}.parameters")
    if len(parameters) > MAX_PARAMETERS:
        raise _error(
            "KS3805",
            f"{name} en fazla {MAX_PARAMETERS} parametre alabilir.",
        )
    normalized_parameters: list[dict[str, str]] = []
    parameter_names: set[str] = set()
    for raw_parameter in parameters:
        parameter = _expect_object(raw_parameter, f"functions.{name}.parameters[]")
        _exact_keys(parameter, {"name", "type"}, f"functions.{name}.parameters[]")
        parameter_name = _expect_string(
            parameter["name"], f"functions.{name}.parameters[].name"
        )
        if not IDENTIFIER.fullmatch(parameter_name):
            raise _error("KS3805", f"Geçersiz foreign parametre adı: {parameter_name}")
        if parameter_name in parameter_names:
            raise _error(
                "KS3805", f"{name} içinde parametre adı yinelendi: {parameter_name}"
            )
        parameter_names.add(parameter_name)
        normalized_parameters.append(
            {
                "name": parameter_name,
                "type": normalize_type(parameter["type"], allow_void=False),
            }
        )

    effects = _expect_array(function["effects"], f"functions.{name}.effects")
    if effects:
        raise _error(
            "KS3802",
            f"Foreign ABI v1 authority taşımaz; {name}.effects boş olmalıdır.",
        )

    return {
        "name": name,
        "parameters": normalized_parameters,
        "returns": normalize_type(function["returns"], allow_void=True),
        "effects": [],
    }


def load_foreign_contract(path: str | Path) -> ForeignContract:
    source = Path(path).expanduser().resolve()
    if not source.is_file():
        raise _error("KS3801", f"Foreign sözleşme bulunamadı: {source}")
    if source.stat().st_size > MAX_CONTRACT_BYTES:
        raise _error(
            "KS3801",
            f"Foreign sözleşme {MAX_CONTRACT_BYTES} byte sınırını aşıyor.",
        )
    try:
        document = json.loads(
            source.read_text(encoding="utf-8"),
            object_pairs_hook=_duplicate_safe_object,
        )
    except UnicodeDecodeError as error:
        raise _error("KS3801", "Foreign sözleşme geçerli UTF-8 olmalıdır.") from error
    except json.JSONDecodeError as error:
        raise _error(
            "KS3801",
            f"Foreign sözleşme geçerli JSON değil: satır {error.lineno}, sütun {error.colno}",
        ) from error

    root = _expect_object(document, "foreign contract")
    _exact_keys(
        root,
        {"schema", "module", "adapter", "artifact", "limits", "functions"},
        "foreign contract",
    )
    if root["schema"] != SCHEMA:
        raise _error("KS3801", f"Foreign sözleşme şeması tam olarak '{SCHEMA}' olmalıdır.")

    module = _expect_string(root["module"], "module")
    if not MODULE_NAME.fullmatch(module):
        raise _error("KS3805", f"Geçersiz foreign modül adı: {module}")

    adapter = _expect_object(root["adapter"], "adapter")
    _exact_keys(adapter, {"language", "isolation", "protocol"}, "adapter")
    language = _expect_string(adapter["language"], "adapter.language")
    if language not in LANGUAGES:
        raise _error(
            "KS3802",
            "adapter.language desteklenmiyor; izin verilenler: "
            + ", ".join(sorted(LANGUAGES)),
        )
    isolation = _expect_string(adapter["isolation"], "adapter.isolation")
    expected_isolation = "wasm" if language == "wasm" else "process"
    if isolation != expected_isolation:
        raise _error(
            "KS3802",
            f"{language} adapter'ı Foreign ABI v1 içinde '{expected_isolation}' izolasyonu kullanmalıdır.",
        )
    if adapter["protocol"] != PROTOCOL:
        raise _error("KS3802", f"adapter.protocol tam olarak '{PROTOCOL}' olmalıdır.")

    artifact = _expect_object(root["artifact"], "artifact")
    _exact_keys(artifact, {"path", "sha256"}, "artifact")
    expected_sha = _expect_string(artifact["sha256"], "artifact.sha256")
    if not SHA256_HEX.fullmatch(expected_sha):
        raise _error("KS3806", "artifact.sha256 64 karakter küçük harf hex olmalıdır.")
    artifact_path = _safe_artifact_path(source, artifact["path"])
    actual_sha = _hash_file(artifact_path)
    if actual_sha != expected_sha:
        raise _error(
            "KS3806",
            f"Foreign artifact özeti uyuşmuyor; beklenen {expected_sha}, bulunan {actual_sha}.",
        )

    limits = _expect_object(root["limits"], "limits")
    _exact_keys(limits, set(_LIMITS), "limits")
    normalized_limits = {
        name: _positive_limit(limits[name], name) for name in sorted(_LIMITS)
    }

    functions = _expect_array(root["functions"], "functions")
    if not functions:
        raise _error("KS3805", "Foreign sözleşme en az bir fonksiyon içermelidir.")
    if len(functions) > MAX_FUNCTIONS:
        raise _error("KS3805", f"Foreign sözleşme en fazla {MAX_FUNCTIONS} fonksiyon içerebilir.")
    seen: set[str] = set()
    normalized_functions = [_validate_function(item, seen) for item in functions]
    normalized_functions.sort(key=lambda item: item["name"])

    canonical: dict[str, Any] = {
        "schema": SCHEMA,
        "module": module,
        "adapter": {
            "language": language,
            "isolation": isolation,
            "protocol": PROTOCOL,
        },
        "artifact": {
            "path": artifact["path"],
            "sha256": expected_sha,
        },
        "limits": normalized_limits,
        "functions": normalized_functions,
    }
    fingerprint = hashlib.sha256(_canonical_bytes(canonical)).hexdigest()
    return ForeignContract(
        source=source,
        module=module,
        language=language,
        isolation=isolation,
        artifact=artifact_path,
        artifact_sha256=actual_sha,
        fingerprint=fingerprint,
        functions=len(normalized_functions),
        canonical=canonical,
    )
