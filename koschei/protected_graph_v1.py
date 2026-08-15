"""Fail-closed protected source object graph loading for Koschei v1.

Physical paths are storage locators only. They never grant authority and are
never used to infer dependency structure for protected projects.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
import stat
from typing import Any

from .ast_nodes import SourceLocation
from .modules import ModuleError, ModuleGraph, load_graph

SCHEMA = "koschei.opaque-source-graph/v1"
_MAX_GRAPH_BYTES = 4 * 1024 * 1024
_MAX_OBJECT_BYTES = 16 * 1024 * 1024


@dataclass(frozen=True, slots=True)
class ProtectedSourceObject:
    object_id: str
    artifact_hash: str
    policy_hash: str
    epoch_alias: str
    provenance: str
    requested_capabilities: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class ProtectedSourceEdge:
    from_object_id: str
    import_name: str
    to_object_id: str
    expected_artifact_hash: str
    requested_capabilities: tuple[str, ...]


class ProtectedGraphError(ModuleError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(code, message, SourceLocation(1, 1))


def _fail(code: str, message: str) -> None:
    raise ProtectedGraphError(code, message)


def _require_string(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value:
        _fail("KS5601", f"Protected graph alanı geçersiz: {field}")
    return value


def _validate_object_id(value: str) -> str:
    if len(value) < 32 or any(ch not in "0123456789abcdefABCDEF" for ch in value):
        _fail("KS5602", "Protected object_id en az 128-bit hexadecimal kimlik olmalıdır.")
    return value.lower()


def _validate_hash(value: str, field: str) -> str:
    if not value.startswith("sha256:"):
        _fail("KS5603", f"{field} sha256: öneki taşımalıdır.")
    digest = value[7:]
    if len(digest) != 64 or any(ch not in "0123456789abcdefABCDEF" for ch in digest):
        _fail("KS5603", f"{field} geçerli SHA-256 özeti değildir.")
    return "sha256:" + digest.lower()


def _safe_alias(alias: str) -> str:
    if alias in {".", ".."} or "/" in alias or "\\" in alias:
        _fail("KS5604", "epoch_alias dizin yolu içeremez; yalnız opaque locator olabilir.")
    if len(alias) < 8 or len(alias) > 128:
        _fail("KS5604", "epoch_alias 8-128 karakterlik opaque locator olmalıdır.")
    if any(not (ch.isascii() and (ch.isalnum() or ch in "_-")) for ch in alias):
        _fail("KS5604", "epoch_alias yalnız ASCII harf, rakam, '_' ve '-' içerebilir.")
    return alias


def _strict_object_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            _fail("KS5600", f"Protected object graph tekrarlanan JSON alanı içeriyor: {key}")
        result[key] = value
    return result


def _read_graph(path: Path) -> dict[str, Any]:
    try:
        raw = path.read_bytes()
    except OSError as error:
        _fail("KS5600", f"Protected object graph okunamadı: {error}")
    if len(raw) > _MAX_GRAPH_BYTES:
        _fail("KS5600", "Protected object graph boyut sınırını aşıyor.")
    try:
        text = raw.decode("utf-8")
        payload = json.loads(text, object_pairs_hook=_strict_object_pairs)
    except UnicodeError as error:
        _fail("KS5600", f"Protected object graph UTF-8 değil: {error}")
    except json.JSONDecodeError as error:
        _fail("KS5600", f"Protected object graph JSON olarak okunamadı: {error}")
    if not isinstance(payload, dict):
        _fail("KS5600", "Protected object graph kökü nesne olmalıdır.")
    return payload


def _parse_objects(payload: dict[str, Any]) -> dict[str, ProtectedSourceObject]:
    raw_objects = payload.get("objects")
    if not isinstance(raw_objects, list) or not raw_objects:
        _fail("KS5605", "Protected object graph en az bir canonical object içermelidir.")

    objects: dict[str, ProtectedSourceObject] = {}
    aliases: set[str] = set()
    for raw in raw_objects:
        if not isinstance(raw, dict):
            _fail("KS5605", "Protected object kaydı nesne olmalıdır.")
        object_id = _validate_object_id(_require_string(raw.get("object_id"), "object_id"))
        if object_id in objects:
            _fail("KS5606", f"Tekrarlanan protected object_id: {object_id}")
        alias = _safe_alias(_require_string(raw.get("epoch_alias"), "epoch_alias"))
        if alias in aliases:
            _fail("KS5606", "İki canonical object aynı epoch_alias değerini kullanamaz.")
        aliases.add(alias)
        capabilities = raw.get("requested_capabilities", [])
        if not isinstance(capabilities, list) or not all(isinstance(item, str) for item in capabilities):
            _fail("KS5605", "requested_capabilities yalnız string listesi olabilir.")
        item = ProtectedSourceObject(
            object_id=object_id,
            artifact_hash=_validate_hash(_require_string(raw.get("artifact_hash"), "artifact_hash"), "artifact_hash"),
            policy_hash=_validate_hash(_require_string(raw.get("policy_hash"), "policy_hash"), "policy_hash"),
            epoch_alias=alias,
            provenance=_require_string(raw.get("provenance"), "provenance"),
            requested_capabilities=tuple(capabilities),
        )
        objects[object_id] = item
    return objects


def _parse_edges(payload: dict[str, Any], objects: dict[str, ProtectedSourceObject]) -> dict[tuple[str, str], ProtectedSourceEdge]:
    raw_edges = payload.get("edges", [])
    if not isinstance(raw_edges, list):
        _fail("KS5610", "Protected graph edges listesi geçersiz.")
    edges: dict[tuple[str, str], ProtectedSourceEdge] = {}
    for raw in raw_edges:
        if not isinstance(raw, dict):
            _fail("KS5610", "Protected dependency edge nesne olmalıdır.")
        source = _validate_object_id(_require_string(raw.get("from_object_id"), "from_object_id"))
        target = _validate_object_id(_require_string(raw.get("to_object_id"), "to_object_id"))
        import_name = _require_string(raw.get("import_name"), "import_name")
        if source not in objects or target not in objects:
            _fail("KS5611", "Protected dependency edge bilinmeyen object_id kullanıyor.")
        expected_hash = _validate_hash(
            _require_string(raw.get("expected_artifact_hash"), "expected_artifact_hash"),
            "expected_artifact_hash",
        )
        if expected_hash != objects[target].artifact_hash:
            _fail("KS5612", "Dependency edge hedef artifact hash ile uyuşmuyor.")
        capabilities = raw.get("requested_capabilities", [])
        if not isinstance(capabilities, list) or not all(isinstance(item, str) for item in capabilities):
            _fail("KS5610", "Edge requested_capabilities yalnız string listesi olabilir.")
        key = (source, import_name)
        if key in edges:
            _fail("KS5613", "Aynı protected import slotu birden fazla hedefe bağlanamaz.")
        edges[key] = ProtectedSourceEdge(
            from_object_id=source,
            import_name=import_name,
            to_object_id=target,
            expected_artifact_hash=expected_hash,
            requested_capabilities=tuple(capabilities),
        )
    return edges


def _validate_constraints(payload: dict[str, Any]) -> None:
    required = {
        "physical_path_is_authority": False,
        "semantic_filename_required": False,
        "plaintext_fallback_allowed": False,
        "decoy_is_deployable": False,
    }
    constraints = payload.get("constraints")
    if not isinstance(constraints, dict):
        _fail("KS5614", "Protected graph fail-closed constraints bloğu eksik.")
    for name, expected in required.items():
        if constraints.get(name) is not expected:
            _fail("KS5614", f"Protected graph güvenlik constraint'i ihlal edildi: {name}")


def _read_verified_object(
    item: ProtectedSourceObject,
    object_store: Path,
    expected_policy_hash: str,
) -> tuple[Path, str]:
    if item.provenance != "canonical":
        _fail("KS5620", f"Canonical build decoy/non-canonical object reddetti: {item.object_id}")
    if item.policy_hash != expected_policy_hash:
        _fail("KS5621", f"Protected object policy_hash yerel policy ile uyuşmuyor: {item.object_id}")

    path = object_store / item.epoch_alias
    try:
        before = path.lstat()
    except OSError as error:
        _fail("KS5622", f"Protected object fiziksel locator bulunamadı: {item.object_id}: {error}")
    if stat.S_ISLNK(before.st_mode) or not stat.S_ISREG(before.st_mode):
        _fail("KS5622", f"Protected object locator normal dosya olmalıdır; symlink/device yasak: {item.object_id}")

    flags = os.O_RDONLY | getattr(os, "O_BINARY", 0) | getattr(os, "O_NOFOLLOW", 0)
    try:
        fd = os.open(path, flags)
    except OSError as error:
        _fail("KS5622", f"Protected object güvenli açılamadı: {item.object_id}: {error}")

    try:
        opened = os.fstat(fd)
        try:
            after = path.lstat()
        except OSError as error:
            _fail("KS5622", f"Protected object locator doğrulama sırasında değişti: {item.object_id}: {error}")
        if stat.S_ISLNK(after.st_mode) or not stat.S_ISREG(opened.st_mode):
            _fail("KS5622", f"Protected object locator symlink/device olamaz: {item.object_id}")
        before_identity = (before.st_dev, before.st_ino)
        opened_identity = (opened.st_dev, opened.st_ino)
        after_identity = (after.st_dev, after.st_ino)
        if before_identity != opened_identity or opened_identity != after_identity:
            _fail("KS5622", f"Protected object locator doğrulama sırasında değişti: {item.object_id}")
        if opened.st_size > _MAX_OBJECT_BYTES:
            _fail("KS5622", f"Protected object boyut sınırını aşıyor: {item.object_id}")

        chunks: list[bytes] = []
        total = 0
        while True:
            chunk = os.read(fd, 1024 * 1024)
            if not chunk:
                break
            total += len(chunk)
            if total > _MAX_OBJECT_BYTES:
                _fail("KS5622", f"Protected object boyut sınırını aşıyor: {item.object_id}")
            chunks.append(chunk)
        data = b"".join(chunks)
    finally:
        os.close(fd)

    actual = "sha256:" + hashlib.sha256(data).hexdigest()
    if actual != item.artifact_hash:
        _fail("KS5623", f"Protected object artifact hash doğrulaması başarısız: {item.object_id}")
    try:
        source = data.decode("utf-8")
    except UnicodeDecodeError:
        _fail("KS5623", f"Protected object UTF-8 source değildir: {item.object_id}")
    return path.resolve(strict=False), source


def load_protected_graph(
    graph_path: str | Path,
    object_store: str | Path,
    root_object_id: str,
    *,
    expected_policy_hash: str,
) -> ModuleGraph:
    """Load a protected project without semantic filename/path fallback.

    The JSON object graph is trusted metadata only after its surrounding Trust
    Plane signature/authorization gate has admitted it. This function then
    enforces object identity, hash, policy, provenance and dependency binding.

    Canonical object bytes are read once through a symlink/race-resistant file
    descriptor, hashed, decoded, cached in memory, and passed to the parser through
    ``source_reader``. The ordinary module loader never reopens those object paths.
    """

    graph_file = Path(graph_path).resolve()
    store_input = Path(object_store)
    if store_input.is_symlink():
        _fail("KS5622", "Protected object_store symlink olamaz.")
    try:
        store = store_input.resolve(strict=True)
    except OSError as error:
        _fail("KS5622", f"Protected object_store bulunamadı: {error}")
    if not store.is_dir():
        _fail("KS5622", "Protected object_store dizin olmalıdır.")

    payload = _read_graph(graph_file)
    if payload.get("schema") != SCHEMA:
        _fail("KS5600", f"Desteklenmeyen protected graph schema: {payload.get('schema')!r}")
    _validate_constraints(payload)
    policy_hash = _validate_hash(expected_policy_hash, "expected_policy_hash")
    objects = _parse_objects(payload)
    edges = _parse_edges(payload, objects)
    root_id = _validate_object_id(root_object_id)
    if root_id not in objects:
        _fail("KS5624", "Protected root_object_id object graph içinde yok.")

    paths: dict[str, Path] = {}
    reverse: dict[str, str] = {}
    verified_sources: dict[str, str] = {}
    for object_id, item in objects.items():
        path, source = _read_verified_object(item, store, policy_hash)
        key = str(path)
        if key in reverse:
            _fail("KS5622", "İki protected object aynı fiziksel dosyaya bağlanamaz.")
        paths[object_id] = path
        reverse[key] = object_id
        verified_sources[key] = source

    def resolver(importer: Path, name: str, location: SourceLocation) -> Path:
        importer_id = reverse.get(str(importer))
        if importer_id is None:
            raise ModuleError(
                "KS5625",
                "Protected import kaynağı object graph kimliğine bağlı değil; path fallback yasak.",
                location,
            )
        edge = edges.get((importer_id, name))
        if edge is None:
            raise ModuleError(
                "KS5626",
                f"Protected import '{name}' signed object graph içinde bağlı değil; sibling/path fallback yasak.",
                location,
            )
        target = objects[edge.to_object_id]
        if target.artifact_hash != edge.expected_artifact_hash:
            raise ModuleError(
                "KS5627",
                "Protected import edge artifact binding değişmiş; build fail-closed.",
                location,
            )
        return paths[edge.to_object_id]

    def source_reader(path: Path) -> str:
        source = verified_sources.get(str(path))
        if source is None:
            raise ModuleError(
                "KS5628",
                "Protected source doğrulanmış byte cache içinde yok; filesystem fallback yasak.",
                SourceLocation(1, 1),
            )
        return source

    return load_graph(
        paths[root_id],
        import_resolver=resolver,
        source_reader=source_reader,
    )
