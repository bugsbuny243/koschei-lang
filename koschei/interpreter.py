"""Koschei AST için tree-walking runtime yorumlayıcısı."""

from __future__ import annotations

import errno
import os
import stat
import sys
import urllib.error
import urllib.request
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from .ast_nodes import (
    AssignmentExpression,
    EnumVariant,
    ForStatement,
    ListLiteral,
    MapLiteral,
    StructLiteral,
    BinaryExpression,
    Block,
    CallExpression,
    Expression,
    ExpressionStatement,
    FunctionDeclaration,
    Identifier,
    IfStatement,
    InterpolatedString,
    LetStatement,
    Literal,
    MatchExpression,
    MemberExpression,
    OrBlockExpression,
    OrElseExpression,
    OrReturnExpression,
    Program,
    ReturnStatement,
    SourceLocation,
    Statement,
    UnaryExpression,
    WhileStatement,
)
from .semantic import (
    INT_MAX,
    INT_MIN,
    INT_MIN_MAGNITUDE,
    check as semantic_check,
)


@dataclass(frozen=True, slots=True)
class KsError:
    message: str

    def __str__(self) -> str:
        return self.message


@dataclass(frozen=True, slots=True)
class ModuleValue:
    """Çalışma anında içe aktarılmış bir modül.

    Modül bir DEĞERDİR ama yetki taşımaz: içindeki fonksiyonlar da, tıpkı yerel
    fonksiyonlar gibi, yalnızca kendilerine verilen jetonlarla iş yapabilir.
    """

    name: str


@dataclass(frozen=True, slots=True)
class ModuleFunction:
    """Bir modüle ait fonksiyon; çağrılırken kendi ad alanında çalışır."""

    declaration: Any
    module_name: str


@dataclass(slots=True)
class StructValue:
    """Çalışma anında bir struct örneği."""

    type_name: str
    fields: dict[str, Any]


_NO_PAYLOAD = object()


@dataclass(frozen=True, slots=True)
class EnumValue:
    """Kullanıcı enum'u, Option veya Result varyantı."""

    enum_name: str
    variant: str
    payload: Any = _NO_PAYLOAD


@dataclass(frozen=True, slots=True)
class _EnumConstructor:
    enum_name: str
    variant: str
    payload_type: tuple[str, ...] | None


LIST_METHODS = {"length", "get", "push", "contains", "sort", "filter"}
ALLOWED_NET_SCHEMES = frozenset({"http", "https"})
MAP_METHODS = {"get", "set", "keys", "contains"}


class _KsUnit:
    __slots__ = ()

    def __repr__(self) -> str:
        return "KsUnit"

    def __str__(self) -> str:
        return "unit"


KsUnit = _KsUnit()


def ks_to_string(value: Any) -> str:
    """Koschei değerlerinin kanonik metin gösterimi.

    Host dilin (Python) gösterimine güvenilmez: kaynak kodda 'true' yazan bir
    değer çıktıda da 'true' görünmelidir. Native derleyici de aynı kuralları
    uygular; böylece 'run' ve derlenmiş binary aynı çıktıyı verir.
    """
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, float):
        text = repr(value)
        if "." not in text and "e" not in text and "E" not in text:
            text += ".0"
        return text
    if isinstance(value, list):
        return "[" + ", ".join(_ks_repr(item) for item in value) + "]"
    if isinstance(value, dict):
        inner = ", ".join(
            f"{_ks_repr(key)}: {_ks_repr(item)}" for key, item in value.items()
        )
        return "{" + inner + "}"
    if isinstance(value, StructValue):
        inner = ", ".join(
            f"{name}: {_ks_repr(item)}" for name, item in value.fields.items()
        )
        return f"{value.type_name} {{ {inner} }}"
    if isinstance(value, EnumValue):
        if value.payload is _NO_PAYLOAD:
            return value.variant
        return f"{value.variant}({_ks_repr(value.payload)})"
    return str(value)


def _ks_repr(value: Any) -> str:
    """Kapsayıcı içindeki değerler: metinler tırnaklı gösterilir."""
    if isinstance(value, str):
        return f'"{value}"'
    return ks_to_string(value)


class KoscheiRuntimeError(Exception):
    def __init__(self, code: str, message: str, location: SourceLocation) -> None:
        self.code = code
        self.message = message
        self.location = location
        super().__init__(
            f"{code} [satır {location.line}, sütun {location.column}]: {message}"
        )


@dataclass(slots=True)
class _Cell:
    value: Any
    is_mutable: bool


class _Environment:
    def __init__(self) -> None:
        self.scopes: list[dict[str, _Cell]] = [{}]

    def push(self) -> None:
        self.scopes.append({})

    def pop(self) -> None:
        self.scopes.pop()

    def define(self, name: str, value: Any, is_mutable: bool) -> None:
        self.scopes[-1][name] = _Cell(value, is_mutable)

    def resolve(self, name: str, location: SourceLocation) -> _Cell:
        for scope in reversed(self.scopes):
            cell = scope.get(name)
            if cell is not None:
                return cell
        raise KoscheiRuntimeError(
            "KS3101", f"Tanımsız isim: '{name}'.", location
        )

    def assign(self, name: str, value: Any, location: SourceLocation) -> Any:
        cell = self.resolve(name, location)
        if not cell.is_mutable:
            raise KoscheiRuntimeError(
                "KS3201",
                f"'{name}' immutable bir değerdir; runtime ataması reddedildi.",
                location,
            )
        cell.value = value
        return value


class _ReturnSignal(Exception):
    def __init__(self, value: Any) -> None:
        self.value = value


@dataclass(frozen=True, slots=True)
class _BoundMember:
    receiver: Any
    name: str
    location: SourceLocation


@dataclass(frozen=True, slots=True)
class Response:
    body: str
    status_code: int

    def text(self) -> str:
        return self.body

    def status(self) -> int:
        return self.status_code


class SystemCaps:
    __slots__ = ("net", "disk", "env", "process")

    def __init__(self) -> None:
        self.net = NetRoot()
        self.disk = DiskRoot()
        self.env = EnvRoot()
        self.process = ProcessRoot()


class NetRoot:
    __slots__ = ()

    def allow(self, origin: str) -> "NetCaps":
        return NetCaps(origin)


class DiskRoot:
    __slots__ = ()

    def allow(self, prefix: str) -> "DiskCaps":
        return DiskCaps(prefix)

    def allow_read_only(self, prefix: str) -> "DiskReadCaps":
        return DiskReadCaps(prefix)


class EnvRoot:
    __slots__ = ()

    def allow(self, name: str) -> "EnvCaps":
        return EnvCaps(name)


class ProcessRoot:
    __slots__ = ()

    def allow(self, command: str) -> "ProcessCaps":
        return ProcessCaps(command)


class _NarrowedCapability:
    __slots__ = ()


def _is_symlink_at(name: str, dir_fd: int) -> bool:
    """`name` bileşeni `dir_fd` içinde sembolik bağ mı?

    Yalnızca hata İLETİSİNİ netleştirmek için kullanılır; erişim kararı
    zaten O_NOFOLLOW tarafından verilmiştir, dolayısıyla buradaki ikinci
    bakış yeni bir TOCTOU penceresi açmaz.
    """
    try:
        return stat.S_ISLNK(os.lstat(name, dir_fd=dir_fd).st_mode)
    except OSError:
        return False


class _SymlinkDenied(Exception):
    """Kapsam içinde bir yol bileşeni sembolik bağ çıktı.

    Ara bileşenlerde O_NOFOLLOW ELOOP verir; bu istisna hangi bileşenin
    reddedildiğini taşıyarak hata iletisini anlamlı kılar.
    """

    def __init__(self, name: str) -> None:
        self.name = name
        super().__init__(name)


_DIR_FD_SUPPORTED = (
    os.open in os.supports_dir_fd
    and os.stat in os.supports_dir_fd
    and os.unlink in os.supports_dir_fd
    and os.rmdir in os.supports_dir_fd
    and os.listdir in os.supports_fd
    and hasattr(os, "O_NOFOLLOW")
    and hasattr(os, "O_DIRECTORY")
)
"""Disk yetkisi openat tarzı geçiş gerektirir.

Desteklenmeyen platformlarda disk işlemleri KS3406 ile reddedilir. Sessizce
yarışa açık eski davranışa DÜŞÜLMEZ: bir yetki jetonunun anlamı platforma
göre zayıflayamaz.
"""


class _DiskCapability(_NarrowedCapability):
    """Kapsam sınırı, yol metniyle değil dosya tanıtıcısıyla korunur.

    Eski uygulama `realpath` ile doğrulayıp AYRI bir çağrıda açıyordu. Bu
    iki adım arasındaki pencerede sandbox'a yazabilen bir saldırgan, normal
    bir dosyayı symlink'e çevirerek açmayı kapsam dışına yönlendirebiliyordu
    (TOCTOU). Doğrulanan nesne ile açılan nesnenin aynı olduğu garanti
    edilmiyordu.

    Yeni uygulama kapsam kökünden başlayarak her yol bileşenini
    `O_NOFOLLOW` ile, bir önceki bileşenin dosya tanıtıcısına bağlı olarak
    açar. Böylece:

    - Kapsam içinde HİÇBİR sembolik bağ takip edilmez (KS3405).
    - Doğrulama ile kullanım arasında pencere kalmaz: doğrulanan şey zaten
      açılmış tanıtıcının kendisidir.
    - '..' bileşenleri sözlüksel olarak reddedilir; kapsam kökünün üstüne
      çıkılamaz.

    Kapsam kökü jeton üretilirken bir kez çözülür; bu, güvenilmeyen kod
    çalışmadan önce belirlenen güven çıpasıdır.
    """

    __slots__ = ("prefix", "_root_fd", "_root_open_error")

    def __init__(self, prefix: str) -> None:
        self.prefix = os.path.realpath(os.fspath(prefix))
        self._root_fd: int | None = None
        self._root_open_error: OSError | None = None
        if not _DIR_FD_SUPPORTED:
            return
        try:
            # Güven çıpasını jeton oluşturulurken açıp sabitleriz. Sonraki
            # işlemler yol adını yeniden çözmez; bu dizin yeniden adlandırılıp
            # yerine kapsam dışına giden bir symlink konsa bile aynı inode'a
            # bağlı kalır. O_NOFOLLOW son bileşenin yaratılış anında da bağ
            # olmasını reddeder.
            self._root_fd = os.open(
                self.prefix,
                os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW,
            )
        except OSError as error:
            self._root_open_error = error

    def __del__(self) -> None:
        handle = getattr(self, "_root_fd", None)
        if handle is None:
            return
        try:
            os.close(handle)
        except OSError:
            pass
        self._root_fd = None

    # ------------------------------------------------------------------
    # Yol çözümleme
    # ------------------------------------------------------------------

    def _relative_parts(self, path: str) -> list[str] | None:
        """Kapsam köküne göre bileşen listesi; kapsam dışıysa None.

        Sözlüksel çalışır: `realpath` KULLANILMAZ, çünkü o da yarışa açık
        bir dosya sistemi okumasıdır. Sembolik bağlar zaten geçiş sırasında
        reddedildiği için sözlüksel normalleştirme burada güvenlidir.
        """
        target = os.path.abspath(os.fspath(path))
        try:
            relative = os.path.relpath(target, self.prefix)
        except ValueError:
            return None
        if relative == os.curdir:
            return []
        parts = relative.split(os.sep)
        if any(part == os.pardir for part in parts):
            return None
        return [part for part in parts if part and part != os.curdir]

    @contextmanager
    def _scope_root_fd(self) -> "Iterator[int]":
        if self._root_fd is None:
            error = self._root_open_error
            if error is not None:
                raise OSError(error.errno, error.strerror, error.filename)
            raise OSError(errno.EBADF, "Disk kapsam kökü açık değil", self.prefix)
        # Her işlem kendi kopyasını kullanır; iç içe çağrılar veya fdopen kapanışı
        # jetonun ömür boyu tuttuğu güven çıpasını kapatamaz.
        handle = os.dup(self._root_fd)
        try:
            yield handle
        finally:
            os.close(handle)

    @contextmanager
    def _parent_fd(self, parts: list[str]) -> "Iterator[int]":
        """Son bileşenin ANA dizinine ait tanıtıcıyı verir.

        Her ara bileşen O_NOFOLLOW ile açılır; biri sembolik bağsa
        ELOOP alınır ve _SymlinkDenied yükseltilir.
        """
        with self._scope_root_fd() as root:
            current = root
            opened: list[int] = []
            try:
                for component in parts[:-1]:
                    try:
                        nxt = os.open(
                            component,
                            os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW,
                            dir_fd=current,
                        )
                    except OSError as error:
                        # O_NOFOLLOW + O_DIRECTORY bir sembolik bağda ELOOP
                        # DEĞİL ENOTDIR üretir (bağ dizin değildir). İkisini
                        # de yakalayıp gerçekten bağ mı diye lstat ile
                        # bakıyoruz; öyleyse hata iletisi net olsun.
                        if error.errno in (errno.ELOOP, errno.ENOTDIR):
                            if _is_symlink_at(component, current):
                                raise _SymlinkDenied(component) from error
                        raise
                    opened.append(nxt)
                    current = nxt
                yield current
            finally:
                for handle in reversed(opened):
                    os.close(handle)

    def _reject(self, path: str) -> KsError:
        return KsError(
            f"KS3402: Disk kapsamı dışında erişim reddedildi: {path}"
        )

    @staticmethod
    def _unsupported() -> KsError:
        return KsError(
            "KS3406: Disk yetkisi bu platformda desteklenmiyor: openat "
            "(dir_fd) ve O_NOFOLLOW gerekli. Yarışa açık bir uygulamaya "
            "geri düşülmez."
        )

    @staticmethod
    def _symlink_denied(name: str) -> KsError:
        # KS3402 geriye dönük kapsam-ihlali sözleşmesini korur; KS3405
        # reddin özel sebebini (symlink) makine-okunur biçimde açıklar.
        return KsError(
            "KS3402: Disk kapsamı sembolik bağ üzerinden aşılamaz; "
            f"KS3405: Kapsam içinde sembolik bağ takip edilmez: {name}"
        )

    # ------------------------------------------------------------------
    # Okuma işlemleri
    # ------------------------------------------------------------------

    def read(self, path: str) -> str | KsError:
        return self.read_file(path)

    def read_file(self, path: str) -> str | KsError:
        if not _DIR_FD_SUPPORTED:
            return self._unsupported()
        parts = self._relative_parts(path)
        if parts is None:
            return self._reject(path)
        if not parts:
            return KsError(f"Dosya okunamadı: kapsam kökü bir dizindir: {path}")
        try:
            with self._parent_fd(parts) as parent:
                handle = os.open(
                    parts[-1],
                    os.O_RDONLY | os.O_NOFOLLOW,
                    dir_fd=parent,
                )
                with os.fdopen(handle, "r", encoding="utf-8") as stream:
                    return stream.read()
        except _SymlinkDenied as denied:
            return self._symlink_denied(denied.name)
        except OSError as error:
            if error.errno in (errno.ELOOP, errno.EMLINK):
                return self._symlink_denied(parts[-1])
            return KsError(f"Dosya okunamadı: {error}")

    def list(self, path: str) -> list[str] | KsError:
        if not _DIR_FD_SUPPORTED:
            return self._unsupported()
        parts = self._relative_parts(path)
        if parts is None:
            return self._reject(path)
        try:
            if not parts:
                with self._scope_root_fd() as root:
                    return sorted(os.listdir(root))
            with self._parent_fd(parts) as parent:
                handle = os.open(
                    parts[-1],
                    os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW,
                    dir_fd=parent,
                )
                try:
                    return sorted(os.listdir(handle))
                finally:
                    os.close(handle)
        except _SymlinkDenied as denied:
            return self._symlink_denied(denied.name)
        except OSError as error:
            if error.errno in (errno.ELOOP, errno.EMLINK):
                return self._symlink_denied(parts[-1])
            return KsError(f"Dizin listelenemedi: {error}")


class DiskReadCaps(_DiskCapability):
    __slots__ = ()

    @staticmethod
    def _denied(operation: str) -> KsError:
        return KsError(
            f"KS3404: DiskReadCaps '{operation}' işlemine izin vermez."
        )

    def _scope_then_deny(self, path: str, operation: str) -> KsError:
        """Kapsam ihlali, yetki ihlalinden ÖNCE bildirilir.

        Kapsam dışı bir yol için 'bu jeton yazamaz' demek, saldırgana
        kapsamın nerede bittiğini değil jetonun türünü sızdırır. Eski
        davranış da böyleydi; korunuyor.
        """
        if self._relative_parts(path) is None:
            return self._reject(path)
        return self._denied(operation)

    def write(self, path: str, value: str) -> KsError:
        return self._scope_then_deny(path, "write")

    def write_file(self, path: str, value: str) -> KsError:
        return self._scope_then_deny(path, "write_file")

    def delete(self, path: str) -> KsError:
        return self._scope_then_deny(path, "delete")


class DiskCaps(_DiskCapability):
    __slots__ = ()

    def write(self, path: str, value: str) -> _KsUnit | KsError:
        return self.write_file(path, value)

    def write_file(self, path: str, value: str) -> _KsUnit | KsError:
        if not _DIR_FD_SUPPORTED:
            return self._unsupported()
        parts = self._relative_parts(path)
        if parts is None:
            return self._reject(path)
        if not parts:
            return KsError(f"Dosya yazılamadı: kapsam kökü bir dizindir: {path}")
        try:
            with self._parent_fd(parts) as parent:
                handle = os.open(
                    parts[-1],
                    os.O_WRONLY | os.O_CREAT | os.O_TRUNC | os.O_NOFOLLOW,
                    0o600,
                    dir_fd=parent,
                )
                with os.fdopen(handle, "w", encoding="utf-8") as stream:
                    stream.write(str(value))
        except _SymlinkDenied as denied:
            return self._symlink_denied(denied.name)
        except OSError as error:
            if error.errno in (errno.ELOOP, errno.EMLINK):
                return self._symlink_denied(parts[-1])
            return KsError(f"Dosya yazılamadı: {error}")
        return KsUnit

    def delete(self, path: str) -> _KsUnit | KsError:
        if not _DIR_FD_SUPPORTED:
            return self._unsupported()
        parts = self._relative_parts(path)
        if parts is None:
            return self._reject(path)
        if not parts:
            return KsError(f"Dosya silinemedi: kapsam kökü silinemez: {path}")
        try:
            with self._parent_fd(parts) as parent:
                name = parts[-1]
                info = os.stat(name, dir_fd=parent, follow_symlinks=False)
                if stat.S_ISLNK(info.st_mode):
                    # Bağın kendisi silinebilir (kapsam dışına çıkmaz), ama
                    # sessizce yapmak yerine açıkça reddediyoruz: kapsam
                    # içinde sembolik bağ hiç bulunmamalı.
                    return self._symlink_denied(name)
                if stat.S_ISDIR(info.st_mode):
                    os.rmdir(name, dir_fd=parent)
                else:
                    os.unlink(name, dir_fd=parent)
        except _SymlinkDenied as denied:
            return self._symlink_denied(denied.name)
        except OSError as error:
            if error.errno in (errno.ELOOP, errno.EMLINK):
                return self._symlink_denied(parts[-1])
            return KsError(f"Dosya silinemedi: {error}")
        return KsUnit


class _ScopedRedirectHandler(urllib.request.HTTPRedirectHandler):
    """Yönlendirmeyi yalnızca aynı origin içinde izler.

    Kapsam dışı bir yönlendirme hedefi görülürse istek TAKİP EDİLMEZ ve
    _ScopedRedirectDenied yükseltilir; NetCaps.get bunu KS3402 hata DEĞERİNE
    çevirir. Böylece izinli sunucu 302 ile başka bir host'a yönlendirse bile
    yetki sınırı aşılamaz.
    """

    max_redirections = 5

    def __init__(self, origin_key: tuple[str, str, int | None] | None) -> None:
        self.origin_key = origin_key

    def redirect_request(self, request, fp, code, msg, headers, newurl):
        if self.origin_key is None or _origin_key(newurl) != self.origin_key:
            raise _ScopedRedirectDenied(newurl)
        return super().redirect_request(request, fp, code, msg, headers, newurl)


class _ScopedRedirectDenied(Exception):
    def __init__(self, target: str) -> None:
        self.target = target
        super().__init__(target)


def _build_http_only_opener(
    origin_key: tuple[str, str, int | None] | None,
) -> urllib.request.OpenerDirector:
    """Yalnızca HTTP(S) handler'ları olan bir opener oluşturur.

    urllib.request.build_opener() açık handler verilse bile varsayılan FileHandler,
    FTPHandler ve DataHandler ekler. Ağ capability'sinin disk/veri şemalarına
    dönüşmemesi için OpenerDirector elle ve allowlist ile kurulur.
    """
    opener = urllib.request.OpenerDirector()
    for handler in (
        urllib.request.ProxyHandler(),
        urllib.request.UnknownHandler(),
        urllib.request.HTTPHandler(),
        urllib.request.HTTPDefaultErrorHandler(),
        _ScopedRedirectHandler(origin_key),
        urllib.request.HTTPSHandler(),
        urllib.request.HTTPErrorProcessor(),
    ):
        opener.add_handler(handler)
    return opener


class NetCaps(_NarrowedCapability):
    __slots__ = ("origin", "origin_key", "_opener")

    def __init__(self, origin: str) -> None:
        self.origin = origin
        self.origin_key = _origin_key(origin)
        self._opener = _build_http_only_opener(self.origin_key)

    def _allows(self, url: str) -> bool:
        return self.origin_key is not None and _origin_key(url) == self.origin_key

    def get(self, url: str) -> Response | KsError:
        if not self._allows(url):
            return KsError(
                f"KS3402: Ağ origin kapsamı dışında erişim reddedildi: {url}"
            )
        try:
            request = urllib.request.Request(url, method="GET")
            with self._opener.open(request, timeout=10) as response:
                charset = response.headers.get_content_charset() or "utf-8"
                body = response.read().decode(charset, errors="replace")
                return Response(body, int(response.status))
        except _ScopedRedirectDenied as denied:
            return KsError(
                f"KS3402: Ağ yönlendirmesi kapsam dışına çıktı: {denied.target}"
            )
        except (OSError, urllib.error.URLError) as error:
            if isinstance(getattr(error, "reason", None), _ScopedRedirectDenied):
                return KsError(
                    "KS3402: Ağ yönlendirmesi kapsam dışına çıktı: "
                    f"{error.reason.target}"
                )
            return KsError(f"API isteği başarısız: {error}")

    @staticmethod
    def post(*arguments: Any) -> KsError:
        return KsError("post henüz desteklenmiyor")

    @staticmethod
    def put(*arguments: Any) -> KsError:
        return KsError("put henüz desteklenmiyor")

    @staticmethod
    def delete(*arguments: Any) -> KsError:
        return KsError("delete henüz desteklenmiyor")

    @staticmethod
    def request(*arguments: Any) -> KsError:
        return KsError("request henüz desteklenmiyor")


class EnvCaps(_NarrowedCapability):
    __slots__ = ("name",)

    def __init__(self, name: str) -> None:
        self.name = name

    def get(self) -> str | KsError:
        value = os.environ.get(self.name)
        if value is None:
            return KsError(f"Ortam değişkeni bulunamadı: {self.name}")
        return value


class ProcessCaps(_NarrowedCapability):
    __slots__ = ("command",)

    def __init__(self, command: str) -> None:
        self.command = command

    @staticmethod
    def run(*arguments: Any) -> KsError:
        return KsError("process yetkisi bu sürümde kapalı")

    @staticmethod
    def spawn(*arguments: Any) -> KsError:
        return KsError("process yetkisi bu sürümde kapalı")


def _contains_capability(value: Any, seen: set[int] | None = None) -> bool:
    """Dinamik kapsayıcıların capability type-laundering yapmasını engeller."""
    if isinstance(
        value,
        (
            SystemCaps,
            NetRoot,
            DiskRoot,
            EnvRoot,
            ProcessRoot,
            _NarrowedCapability,
        ),
    ):
        return True

    visited = seen if seen is not None else set()
    identity = id(value)
    if identity in visited:
        return False

    if isinstance(value, StructValue):
        visited.add(identity)
        return any(
            _contains_capability(item, visited)
            for item in value.fields.values()
        )
    if isinstance(value, EnumValue):
        if value.payload is _NO_PAYLOAD:
            return False
        visited.add(identity)
        return _contains_capability(value.payload, visited)
    if isinstance(value, list):
        visited.add(identity)
        return any(_contains_capability(item, visited) for item in value)
    if isinstance(value, dict):
        visited.add(identity)
        return any(
            _contains_capability(key, visited) or _contains_capability(item, visited)
            for key, item in value.items()
        )
    return False


def _origin_key(url: str) -> tuple[str, str, int | None] | None:
    try:
        parsed = urlsplit(url)
        if not parsed.scheme or not parsed.hostname:
            return None
        scheme = parsed.scheme.lower()
        if scheme not in ALLOWED_NET_SCHEMES:
            return None
        host = parsed.hostname.lower()
        port = parsed.port
        if port is None:
            port = 443 if scheme == "https" else 80 if scheme == "http" else None
        return scheme, host, port
    except ValueError:
        return None


class Interpreter:
    def __init__(
        self,
        program: Program,
        argv: list[str] | None = None,
        namespaces: dict[str, dict[str, FunctionDeclaration]] | None = None,
        imports: dict[str, str] | None = None,
        enums: dict[str, Any] | None = None,
        module_imports: dict[str, dict[str, str]] | None = None,
    ) -> None:
        self.program = program
        self.argv = list(argv or [])
        self.functions = {
            declaration.name: declaration for declaration in program.declarations
        }
        self.structs = {
            declaration.name: declaration for declaration in program.structs
        }
        self.constructors: dict[str, _EnumConstructor] = {
            "Some": _EnumConstructor("Option", "Some", ("_",)),
            "None": _EnumConstructor("Option", "None", None),
            "Ok": _EnumConstructor("Result", "Ok", ("_",)),
            "Err": _EnumConstructor("Result", "Err", ("_",)),
        }
        all_enums = dict(enums or {})
        for declaration in program.enums:
            all_enums[declaration.name] = declaration
        for declaration in all_enums.values():
            for variant in declaration.variants:
                self.constructors[variant.name] = _EnumConstructor(
                    declaration.name,
                    variant.name,
                    (
                        variant.payload_type.names
                        if variant.payload_type is not None
                        else None
                    ),
                )
        # Modül anahtarı -> o modülün fonksiyon tablosu
        self.namespaces = namespaces or {}
        # Yerel import adı -> modül anahtarı
        self.imports = imports or {}
        # Modül anahtarı -> o modülün kendi import alias tablosu
        self.module_imports = module_imports or {}
        self.environment = _Environment()
        self._depth = 0

    MAX_CALL_DEPTH = 512

    # Her Koschei çağrısı birden fazla Python çerçevesi kullanır; KS3105'in
    # Python'un kendi RecursionError'ından ÖNCE devreye girmesi için yorumlayıcı
    # çalışırken Python limiti yükseltilir.
    _PYTHON_RECURSION_HEADROOM = 20000

    def execute_main(self) -> Any:
        previous_limit = sys.getrecursionlimit()
        if previous_limit < self._PYTHON_RECURSION_HEADROOM:
            sys.setrecursionlimit(self._PYTHON_RECURSION_HEADROOM)
        try:
            return self._execute_main()
        except RecursionError as error:  # güvenlik ağı: KS koduna çevrilir
            raise KoscheiRuntimeError(
                "KS3105",
                f"Çağrı derinliği sınırı aşıldı ({self.MAX_CALL_DEPTH}); "
                "sonsuz özyineleme olabilir.",
                SourceLocation(1, 1),
            ) from error
        finally:
            sys.setrecursionlimit(previous_limit)

    def _execute_main(self) -> Any:
        main = self.functions.get("main")
        if main is None:
            raise KoscheiRuntimeError(
                "KS3101", "'main' fonksiyonu bulunamadı.", SourceLocation(1, 1)
            )
        if len(main.parameters) == 0:
            arguments: list[Any] = []
        elif (
            len(main.parameters) == 1
            and main.parameters[0].type_ref.names == ("SystemCaps",)
        ):
            arguments = [SystemCaps()]
        else:
            raise KoscheiRuntimeError(
                "KS3401",
                "'main' sıfır parametre veya yalnızca bir SystemCaps parametresi "
                "almalıdır; runtime başka bir tipe kök yetki enjekte etmez.",
                main.location,
            )
        return self._call_function(main, arguments)

    def _call_function(
        self,
        function: FunctionDeclaration,
        arguments: list[Any],
        namespace: dict[str, FunctionDeclaration] | None = None,
        imports: dict[str, str] | None = None,
    ) -> Any:
        if len(arguments) != len(function.parameters):
            raise KoscheiRuntimeError(
                "KS3101",
                f"'{function.name}' için {len(function.parameters)} argüman bekleniyor, "
                f"{len(arguments)} verildi.",
                function.location,
            )

        for parameter, value in zip(function.parameters, arguments):
            if not self._runtime_matches_type(value, parameter.type_ref.names):
                raise KoscheiRuntimeError(
                    "KS3401",
                    f"'{function.name}' çağrısında '{parameter.name}: "
                    f"{parameter.type_ref}' sözleşmesi ihlal edildi; "
                    f"{self._runtime_type_name(value)} verildi. Runtime capability "
                    "type-laundering girişimini reddetti.",
                    parameter.location,
                )

        if self._depth >= self.MAX_CALL_DEPTH:
            raise KoscheiRuntimeError(
                "KS3105",
                f"Çağrı derinliği sınırı aşıldı ({self.MAX_CALL_DEPTH}); "
                "sonsuz özyineleme olabilir.",
                function.location,
            )
        previous = self.environment
        previous_functions = self.functions
        previous_imports = self.imports
        self.environment = _Environment()
        if namespace is not None:
            self.functions = namespace
        if imports is not None:
            self.imports = imports
        self._depth += 1
        try:
            for parameter, value in zip(function.parameters, arguments):
                self.environment.define(parameter.name, value, False)
            try:
                result = self._execute_block(function.body, create_scope=False)
            except _ReturnSignal as signal:
                result = signal.value

            if (
                function.return_type is not None
                and not self._runtime_matches_type(
                    result,
                    function.return_type.names,
                )
            ):
                raise KoscheiRuntimeError(
                    "KS3401",
                    f"'{function.name}' dönüş sözleşmesi {function.return_type} "
                    f"beklerken {self._runtime_type_name(result)} döndürdü.",
                    function.location,
                )
            return result
        finally:
            self._depth -= 1
            self.environment = previous
            self.functions = previous_functions
            self.imports = previous_imports

    def _execute_block(self, block: Block, *, create_scope: bool = True) -> Any:
        if create_scope:
            self.environment.push()
        try:
            result: Any = KsUnit
            for statement in block.statements:
                result = self._execute_statement(statement)
            return result
        finally:
            if create_scope:
                self.environment.pop()

    def _execute_statement(self, statement: Statement) -> Any:
        if isinstance(statement, LetStatement):
            value = self._evaluate(statement.value)
            self.environment.define(statement.name, value, statement.is_mutable)
            return KsUnit

        if isinstance(statement, ReturnStatement):
            value = KsUnit if statement.value is None else self._evaluate(statement.value)
            raise _ReturnSignal(value)

        if isinstance(statement, ExpressionStatement):
            return self._evaluate(statement.expression)

        if isinstance(statement, IfStatement):
            condition = self._evaluate(statement.condition)
            if isinstance(condition, KsError):
                return condition
            if bool(condition):
                return self._execute_block(statement.then_block)
            if isinstance(statement.else_branch, Block):
                return self._execute_block(statement.else_branch)
            if isinstance(statement.else_branch, IfStatement):
                return self._execute_statement(statement.else_branch)
            return KsUnit

        if isinstance(statement, ForStatement):
            iterable = self._evaluate(statement.iterable)
            if isinstance(iterable, KsError):
                return iterable
            if not isinstance(iterable, list):
                raise KoscheiRuntimeError(
                    "KS3101",
                    "'for ... in' yalnızca List üzerinde çalışır.",
                    statement.location,
                )
            result: Any = KsUnit
            for item in iterable:
                self.environment.push()
                try:
                    self.environment.define(statement.variable, item, False)
                    result = self._execute_block(statement.body, create_scope=False)
                finally:
                    self.environment.pop()
                if isinstance(result, KsError):
                    return result
            return result

        if isinstance(statement, WhileStatement):
            result: Any = KsUnit
            while True:
                condition = self._evaluate(statement.condition)
                if isinstance(condition, KsError):
                    return condition
                if not bool(condition):
                    return result
                result = self._execute_block(statement.body)
                if isinstance(result, KsError):
                    return result

        raise AssertionError(f"Desteklenmeyen statement: {type(statement).__name__}")

    def _evaluate(self, expression: Expression) -> Any:
        if isinstance(expression, Literal):
            value = expression.value
            if (
                isinstance(value, int)
                and not isinstance(value, bool)
                and not INT_MIN <= value <= INT_MAX
            ):
                return KsError(
                    "KS3501: Int literal çalışma anında 64-bit aralığı aştı: "
                    f"{value}"
                )
            return value

        if isinstance(expression, Identifier):
            if expression.name in self.functions:
                return self.functions[expression.name]
            constructor = self.constructors.get(expression.name)
            if constructor is not None:
                return constructor
            if expression.name in {"print", "println", "Error"}:
                return expression.name
            if expression.name in self.imports:
                return ModuleValue(expression.name)
            return self.environment.resolve(expression.name, expression.location).value

        if isinstance(expression, InterpolatedString):
            return "".join(
                ks_to_string(self._evaluate(part)) for part in expression.parts
            )

        if isinstance(expression, ListLiteral):
            items: list[Any] = []
            for item in expression.items:
                value = self._evaluate(item)
                if isinstance(value, KsError):
                    return value
                if _contains_capability(value):
                    raise KoscheiRuntimeError(
                        "KS3401",
                        "Capability taşıyan değerler List içine konamaz; runtime "
                        "type-laundering girişimini reddetti.",
                        item.location,
                    )
                items.append(value)
            return items

        if isinstance(expression, MapLiteral):
            entries: dict[str, Any] = {}
            for key_expression, value_expression in expression.entries:
                key = self._evaluate(key_expression)
                if isinstance(key, KsError):
                    return key
                if not isinstance(key, str):
                    raise KoscheiRuntimeError(
                        "KS3401",
                        f"Map anahtarı String olmalıdır, "
                        f"{self._runtime_type_name(key)} bulundu.",
                        key_expression.location,
                    )
                if key in entries:
                    raise KoscheiRuntimeError(
                        "KS3101",
                        f"Map literalinde '{key}' anahtarı birden fazla yazılmış.",
                        key_expression.location,
                    )
                value = self._evaluate(value_expression)
                if isinstance(value, KsError):
                    return value
                if _contains_capability(value):
                    raise KoscheiRuntimeError(
                        "KS3401",
                        "Capability taşıyan değerler Map içine konamaz; runtime "
                        "type-laundering girişimini reddetti.",
                        value_expression.location,
                    )
                entries[key] = value
            return entries

        if isinstance(expression, StructLiteral):
            fields: dict[str, Any] = {}
            declaration = self.structs.get(expression.type_name)
            expected = (
                {field.name: field for field in declaration.fields}
                if declaration is not None
                else {}
            )
            for name, value_expression in expression.fields:
                value = self._evaluate(value_expression)
                if isinstance(value, KsError):
                    return value
                field = expected.get(name)
                if (
                    field is not None
                    and not self._runtime_matches_type(value, field.type_ref.names)
                ):
                    raise KoscheiRuntimeError(
                        "KS3401",
                        f"'{expression.type_name}.{name}' alanı "
                        f"{field.type_ref} beklerken "
                        f"{self._runtime_type_name(value)} aldı.",
                        value_expression.location,
                    )
                fields[name] = value
            return StructValue(expression.type_name, fields)

        if isinstance(expression, MemberExpression):
            receiver = self._evaluate(expression.object)
            return self._member(receiver, expression.member, expression.location)

        if isinstance(expression, CallExpression):
            callee = self._evaluate(expression.callee)
            arguments = [self._evaluate(item) for item in expression.arguments]
            return self._invoke(callee, arguments, expression.location)

        if isinstance(expression, MatchExpression):
            value = self._evaluate(expression.value)
            if not isinstance(value, EnumValue):
                raise KoscheiRuntimeError(
                    "KS3101",
                    "match çalışma anında bir enum, Option veya Result değeri bekler.",
                    expression.location,
                )
            for arm in expression.arms:
                if arm.variant != value.variant:
                    continue
                self.environment.push()
                try:
                    if arm.binding is not None:
                        if value.payload is _NO_PAYLOAD:
                            raise KoscheiRuntimeError(
                                "KS3101",
                                f"'{value.variant}' payload taşımıyor.",
                                arm.location,
                            )
                        self.environment.define(arm.binding, value.payload, False)
                    return self._evaluate(arm.body)
                finally:
                    self.environment.pop()
            raise KoscheiRuntimeError(
                "KS3101",
                f"match içinde '{value.variant}' varyantı için kol yok.",
                expression.location,
            )

        if isinstance(expression, AssignmentExpression):
            value = self._evaluate(expression.value)
            if isinstance(expression.target, Identifier):
                return self.environment.assign(
                    expression.target.name, value, expression.location
                )
            raise KoscheiRuntimeError(
                "KS3201", "Yalnızca değişkenlere atama yapılabilir.", expression.location
            )

        if isinstance(expression, BinaryExpression):
            return self._binary(expression)

        if isinstance(expression, UnaryExpression):
            if (
                expression.operator == "-"
                and isinstance(expression.operand, Literal)
                and isinstance(expression.operand.value, int)
                and not isinstance(expression.operand.value, bool)
            ):
                magnitude = expression.operand.value
                if magnitude == INT_MIN_MAGNITUDE:
                    return INT_MIN
                if magnitude > INT_MAX:
                    return self._int_overflow("unary -")
            operand = self._evaluate(expression.operand)
            if isinstance(operand, KsError):
                return operand
            if expression.operator == "!":
                return not bool(operand)
            if expression.operator == "-":
                if type(operand) is int:
                    if operand == INT_MIN:
                        return self._int_overflow("unary -")
                    return -operand
                return -operand
            raise AssertionError(expression.operator)

        if isinstance(expression, OrReturnExpression):
            value = self._evaluate(expression.value)
            success, payload = self._unwrap_fallible(value)
            if not success:
                replacement = (
                    value
                    if expression.error is None
                    else self._evaluate(expression.error)
                )
                raise _ReturnSignal(replacement)
            return payload

        if isinstance(expression, OrElseExpression):
            value = self._evaluate(expression.value)
            success, payload = self._unwrap_fallible(value)
            return payload if success else self._evaluate(expression.fallback)

        if isinstance(expression, OrBlockExpression):
            value = self._evaluate(expression.value)
            success, payload = self._unwrap_fallible(value)
            return payload if success else self._execute_block(expression.handler)

        raise AssertionError(f"Desteklenmeyen expression: {type(expression).__name__}")

    def _binary(self, expression: BinaryExpression) -> Any:
        left = self._evaluate(expression.left)
        if isinstance(left, KsError):
            return left
        if expression.operator == "&&":
            if not bool(left):
                return False
            right = self._evaluate(expression.right)
            return right if isinstance(right, KsError) else bool(right)
        if expression.operator == "||":
            if bool(left):
                return True
            right = self._evaluate(expression.right)
            return right if isinstance(right, KsError) else bool(right)

        right = self._evaluate(expression.right)
        if isinstance(right, KsError):
            return right
        operator = expression.operator
        if operator in {"+", "-", "*"} and type(left) is int and type(right) is int:
            if operator == "+":
                result = left + right
            elif operator == "-":
                result = left - right
            else:
                result = left * right
            if not INT_MIN <= result <= INT_MAX:
                return self._int_overflow(operator)
            return result
        if operator == "+":
            return left + right
        if operator == "-":
            return left - right
        if operator == "*":
            return left * right
        if operator == "/":
            if right == 0:
                return KsError("Sıfıra bölme")
            return left / right
        if operator == "==":
            return left == right
        if operator == "!=":
            return left != right
        if operator == "<":
            return left < right
        if operator == "<=":
            return left <= right
        if operator == ">":
            return left > right
        if operator == ">=":
            return left >= right
        raise AssertionError(operator)

    @staticmethod
    def _int_overflow(operation: str) -> KsError:
        return KsError(
            f"KS3501: Int taşması: '{operation}' işlemi işaretli 64-bit "
            "aralığın dışına çıktı."
        )

    def _member(self, receiver: Any, name: str, location: SourceLocation) -> Any:
        if isinstance(receiver, SystemCaps):
            if name in {"net", "disk", "env", "process"}:
                return getattr(receiver, name)

        if isinstance(receiver, ModuleValue):
            key = self.imports[receiver.name]
            function = self.namespaces.get(key, {}).get(name)
            if function is None:
                raise KoscheiRuntimeError(
                    "KS3101",
                    f"'{receiver.name}' modülünde '{name}' adında bir fonksiyon yok.",
                    location,
                )
            return ModuleFunction(function, key)

        if isinstance(receiver, StructValue):
            if name in receiver.fields:
                return receiver.fields[name]
            raise KoscheiRuntimeError(
                "KS3101",
                f"'{receiver.type_name}' struct'ında '{name}' alanı yok.",
                location,
            )

        if isinstance(receiver, list):
            if name in LIST_METHODS:
                return _BoundMember(receiver, name, location)
            raise KoscheiRuntimeError(
                "KS3101", f"List üzerinde '{name}' metodu yok.", location
            )

        if isinstance(receiver, dict):
            if name in MAP_METHODS:
                return _BoundMember(receiver, name, location)
            raise KoscheiRuntimeError(
                "KS3101", f"Map üzerinde '{name}' metodu yok.", location
            )

        if isinstance(receiver, _NarrowedCapability) and name in {
            "allow", "allow_read_only"
        }:
            raise KoscheiRuntimeError(
                "KS3403",
                f"Daraltılmış yetki '{name}' ile yeniden genişletilemez.",
                location,
            )

        allowed_members: dict[type[Any], set[str]] = {
            NetRoot: {"allow"},
            DiskRoot: {"allow", "allow_read_only"},
            EnvRoot: {"allow"},
            ProcessRoot: {"allow"},
            NetCaps: {"get", "post", "put", "delete", "request"},
            DiskCaps: {"read", "read_file", "write", "write_file", "list", "delete"},
            DiskReadCaps: {"read", "read_file", "write", "write_file", "list", "delete"},
            EnvCaps: {"get"},
            ProcessCaps: {"run", "spawn"},
            Response: {"text", "status"},
            str: {
                "length",
                "to_int",
                "to_float",
                "contains",
                "trim",
                "split",
                "join",
            },
        }
        for receiver_type, members in allowed_members.items():
            if isinstance(receiver, receiver_type) and name in members:
                return _BoundMember(receiver, name, location)

        raise KoscheiRuntimeError(
            "KS3101", f"Tanımsız alan veya metot: '{name}'.", location
        )

    def _invoke(
        self, callee: Any, arguments: list[Any], location: SourceLocation
    ) -> Any:
        if isinstance(callee, FunctionDeclaration):
            return self._call_function(callee, arguments)
        if isinstance(callee, ModuleFunction):
            return self._call_function(
                callee.declaration,
                arguments,
                namespace=self.namespaces.get(callee.module_name, {}),
                imports=self.module_imports.get(callee.module_name, {}),
            )
        if isinstance(callee, _EnumConstructor):
            expected = 0 if callee.payload_type is None else 1
            self._require_arity(callee.variant, arguments, expected, location)
            if callee.payload_type is None:
                return EnumValue(callee.enum_name, callee.variant)
            payload = arguments[0]
            if _contains_capability(payload):
                raise KoscheiRuntimeError(
                    "KS3401",
                    "Capability taşıyan değerler enum/Option/Result payload'ına konamaz.",
                    location,
                )
            if not self._runtime_matches_type(payload, callee.payload_type):
                raise KoscheiRuntimeError(
                    "KS3401",
                    f"'{callee.variant}' payload sözleşmesi "
                    f"{' or '.join(callee.payload_type)} beklerken "
                    f"{self._runtime_type_name(payload)} aldı.",
                    location,
                )
            return EnumValue(callee.enum_name, callee.variant, payload)
        if callee == "println":
            self._require_arity("println", arguments, 1, location)
            print(ks_to_string(arguments[0]))
            return KsUnit
        if callee == "print":
            self._require_arity("print", arguments, 1, location)
            print(ks_to_string(arguments[0]), end="")
            return KsUnit
        if callee == "Error":
            self._require_arity("Error", arguments, 1, location)
            return KsError(ks_to_string(arguments[0]))
        if isinstance(callee, _BoundMember):
            return self._invoke_member(callee, arguments)
        raise KoscheiRuntimeError(
            "KS3101", "Çağrılabilir bir değer bekleniyordu.", location
        )

    def _invoke_member(self, member: _BoundMember, arguments: list[Any]) -> Any:
        receiver = member.receiver
        name = member.name
        if isinstance(receiver, str):
            if name == "length":
                self._require_arity(name, arguments, 0, member.location)
                return len(receiver)
            if name == "to_int":
                self._require_arity(name, arguments, 0, member.location)
                try:
                    return int(receiver.strip())
                except ValueError:
                    return KsError(f"Int dönüşümü başarısız: {receiver}")
            if name == "to_float":
                self._require_arity(name, arguments, 0, member.location)
                try:
                    return float(receiver.strip())
                except ValueError:
                    return KsError(f"Float dönüşümü başarısız: {receiver}")
            if name == "contains":
                self._require_arity(name, arguments, 1, member.location)
                return str(arguments[0]) in receiver
            if name == "trim":
                self._require_arity(name, arguments, 0, member.location)
                return receiver.strip()
            if name == "split":
                self._require_arity(name, arguments, 1, member.location)
                separator = arguments[0]
                if not isinstance(separator, str):
                    return KsError("String.split() ayıracı String olmalıdır")
                if separator == "":
                    return KsError("String.split() ayıracı boş olamaz")
                return receiver.split(separator)
            if name == "join":
                self._require_arity(name, arguments, 1, member.location)
                values = arguments[0]
                if not isinstance(values, list):
                    return KsError("String.join() bir List bekler")
                if any(not isinstance(value, str) for value in values):
                    return KsError("String.join() yalnızca String öğeleri birleştirir")
                return receiver.join(values)

        if isinstance(receiver, list):
            if name == "length":
                self._require_arity(name, arguments, 0, member.location)
                return len(receiver)
            if name == "get":
                self._require_arity(name, arguments, 1, member.location)
                index = arguments[0]
                if not isinstance(index, int) or isinstance(index, bool):
                    return KsError("Liste indeksi Int olmalıdır")
                if index < 0 or index >= len(receiver):
                    return KsError(
                        f"Liste indeksi aralık dışında: {index} "
                        f"(uzunluk {len(receiver)})"
                    )
                return receiver[index]
            if name == "push":
                self._require_arity(name, arguments, 1, member.location)
                if _contains_capability(arguments[0]):
                    raise KoscheiRuntimeError(
                        "KS3401",
                        "Capability taşıyan değerler List içine konamaz; runtime "
                        "type-laundering girişimini reddetti.",
                        member.location,
                    )
                # Değerler değişmezdir: push YENİ bir liste döndürür.
                return receiver + [arguments[0]]
            if name == "contains":
                self._require_arity(name, arguments, 1, member.location)
                return arguments[0] in receiver
            if name == "sort":
                self._require_arity(name, arguments, 0, member.location)
                if _contains_capability(receiver):
                    raise KoscheiRuntimeError(
                        "KS3401",
                        "Capability taşıyan List sıralanamaz.",
                        member.location,
                    )
                if not receiver:
                    return []
                numeric = all(type(value) in {int, float} for value in receiver)
                strings = all(isinstance(value, str) for value in receiver)
                if not (numeric or strings):
                    return KsError(
                        "List.sort() yalnızca homojen String veya sayısal öğeleri sıralar"
                    )
                return sorted(receiver)
            if name == "filter":
                self._require_arity(name, arguments, 1, member.location)
                predicate = arguments[0]
                if not isinstance(predicate, FunctionDeclaration):
                    return KsError(
                        "List.filter() yerel, adlandırılmış bir predicate fonksiyonu bekler"
                    )
                filtered: list[Any] = []
                for value in receiver:
                    decision = self._call_function(predicate, [value])
                    if isinstance(decision, KsError):
                        return decision
                    if not isinstance(decision, bool):
                        return KsError("List.filter() predicate'i Bool döndürmelidir")
                    if decision:
                        filtered.append(value)
                return filtered

        if isinstance(receiver, dict):
            if name == "get":
                self._require_arity(name, arguments, 1, member.location)
                key = arguments[0]
                if not isinstance(key, str):
                    return KsError("Map anahtarı String olmalıdır")
                if key not in receiver:
                    return KsError(f"Map anahtarı bulunamadı: {key}")
                return receiver[key]
            if name == "set":
                self._require_arity(name, arguments, 2, member.location)
                key, value = arguments
                if not isinstance(key, str):
                    return KsError("Map anahtarı String olmalıdır")
                if _contains_capability(value):
                    raise KoscheiRuntimeError(
                        "KS3401",
                        "Capability taşıyan değerler Map içine konamaz; runtime "
                        "type-laundering girişimini reddetti.",
                        member.location,
                    )
                # Değerler değişmezdir: set YENİ bir Map döndürür.
                updated = dict(receiver)
                updated[key] = value
                return updated
            if name == "keys":
                self._require_arity(name, arguments, 0, member.location)
                return list(receiver.keys())
            if name == "contains":
                self._require_arity(name, arguments, 1, member.location)
                key = arguments[0]
                if not isinstance(key, str):
                    return KsError("Map anahtarı String olmalıdır")
                return key in receiver

        method = getattr(receiver, name)
        try:
            return method(*arguments)
        except TypeError as error:
            raise KoscheiRuntimeError(
                "KS3101", f"'{name}' çağrısı geçersiz: {error}", member.location
            ) from error

    @staticmethod
    def _split_generic_arguments(text: str) -> tuple[str, ...]:
        arguments: list[str] = []
        depth = 0
        start = 0
        for index, char in enumerate(text):
            if char == "<":
                depth += 1
            elif char == ">":
                depth -= 1
            elif char == "," and depth == 0:
                arguments.append(text[start:index].strip())
                start = index + 1
        arguments.append(text[start:].strip())
        return tuple(argument for argument in arguments if argument)

    @classmethod
    def _generic_type(cls, name: str) -> tuple[str, tuple[str, ...]]:
        if "<" not in name or not name.endswith(">"):
            return name, ()
        base, rest = name.split("<", 1)
        return base.strip(), cls._split_generic_arguments(rest[:-1])

    @staticmethod
    def _unwrap_fallible(value: Any) -> tuple[bool, Any]:
        if isinstance(value, KsError):
            return False, value
        if isinstance(value, EnumValue):
            if value.enum_name == "Option":
                if value.variant == "Some":
                    return True, value.payload
                if value.variant == "None":
                    return False, value
            if value.enum_name == "Result":
                if value.variant == "Ok":
                    return True, value.payload
                if value.variant == "Err":
                    return False, value
        return True, value

    def _runtime_matches_type(
        self,
        value: Any,
        expected_names,
    ) -> bool:
        for name in expected_names:
            if name == "_":
                return True
            base, arguments = self._generic_type(name)
            if base == "Option" and len(arguments) == 1 and isinstance(value, EnumValue) and value.enum_name == "Option":
                if value.variant == "None":
                    return True
                if value.variant == "Some" and value.payload is not _NO_PAYLOAD:
                    return self._runtime_matches_type(value.payload, (arguments[0],))
            if base == "Result" and len(arguments) == 2 and isinstance(value, EnumValue) and value.enum_name == "Result":
                if value.variant == "Ok" and value.payload is not _NO_PAYLOAD:
                    return self._runtime_matches_type(value.payload, (arguments[0],))
                if value.variant == "Err" and value.payload is not _NO_PAYLOAD:
                    return self._runtime_matches_type(value.payload, (arguments[1],))
            if isinstance(value, EnumValue) and value.enum_name == name:
                return True
            if name == "SystemCaps" and isinstance(value, SystemCaps):
                return True
            if name == "NetRoot" and isinstance(value, NetRoot):
                return True
            if name == "DiskRoot" and isinstance(value, DiskRoot):
                return True
            if name == "EnvRoot" and isinstance(value, EnvRoot):
                return True
            if name == "ProcessRoot" and isinstance(value, ProcessRoot):
                return True
            if name == "NetCaps" and isinstance(value, NetCaps):
                return True
            if name == "DiskCaps" and isinstance(value, DiskCaps):
                return True
            if name == "DiskReadCaps" and isinstance(value, DiskReadCaps):
                return True
            if name == "EnvCaps" and isinstance(value, EnvCaps):
                return True
            if name == "ProcessCaps" and isinstance(value, ProcessCaps):
                return True
            if name == "Response" and isinstance(value, Response):
                return True
            if name == "Error" and isinstance(value, KsError):
                return True
            if name == "Void" and value is KsUnit:
                return True
            if name == "String" and isinstance(value, str):
                return True
            if name == "Bool" and isinstance(value, bool):
                return True
            if name == "Int" and isinstance(value, int) and not isinstance(value, bool):
                return True
            if name == "Float" and isinstance(value, float):
                return True
            if name == "List" and isinstance(value, list):
                return True
            if name == "Map" and isinstance(value, dict):
                return True
            if isinstance(value, StructValue) and value.type_name == name:
                return True
        return False

    @staticmethod
    def _runtime_type_name(value: Any) -> str:
        if value is KsUnit:
            return "Void"
        if isinstance(value, StructValue):
            return value.type_name
        if isinstance(value, EnumValue):
            if value.enum_name == "Option":
                inner = "_" if value.payload is _NO_PAYLOAD else Interpreter._runtime_type_name(value.payload)
                return f"Option<{inner}>"
            if value.enum_name == "Result":
                inner = "_" if value.payload is _NO_PAYLOAD else Interpreter._runtime_type_name(value.payload)
                return f"Result<{inner}>"
            return value.enum_name
        if isinstance(value, KsError):
            return "Error"
        mapping = (
            (SystemCaps, "SystemCaps"),
            (NetRoot, "NetRoot"),
            (DiskRoot, "DiskRoot"),
            (EnvRoot, "EnvRoot"),
            (ProcessRoot, "ProcessRoot"),
            (NetCaps, "NetCaps"),
            (DiskCaps, "DiskCaps"),
            (DiskReadCaps, "DiskReadCaps"),
            (EnvCaps, "EnvCaps"),
            (ProcessCaps, "ProcessCaps"),
            (Response, "Response"),
            (bool, "Bool"),
            (str, "String"),
            (float, "Float"),
            (int, "Int"),
            (list, "List"),
            (dict, "Map"),
        )
        for runtime_type, name in mapping:
            if isinstance(value, runtime_type):
                return name
        return type(value).__name__

    @staticmethod
    def _require_arity(
        name: str, arguments: list[Any], expected: int, location: SourceLocation
    ) -> None:
        if len(arguments) != expected:
            raise KoscheiRuntimeError(
                "KS3101",
                f"'{name}' için {expected} argüman bekleniyor, {len(arguments)} verildi.",
                location,
            )


def run(
    program: Program,
    argv: list[str],
    namespaces: dict[str, dict[str, FunctionDeclaration]] | None = None,
    imports: dict[str, str] | None = None,
    enums: dict[str, Any] | None = None,
    module_imports: dict[str, dict[str, str]] | None = None,
) -> int:
    """Programı çalıştırır.

    namespaces/imports verilmezse tek dosyalık program varsayılır. Modül grafiği
    varsa semantic denetimi çağıran taraf (CLI) yapmıştır; burada tekrarlanmaz.
    """
    if namespaces is None:
        semantic_check(program)
    result = Interpreter(
        program, argv, namespaces, imports, enums, module_imports
    ).execute_main()
    if isinstance(result, KsError):
        print(f"KOSCHEI RUNTIME ERROR: {result.message}", file=sys.stderr)
        return 1
    return 0
