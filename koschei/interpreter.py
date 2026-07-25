"""Koschei AST için tree-walking runtime yorumlayıcısı."""

from __future__ import annotations

import os
import sys
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from .ast_nodes import (
    AssignmentExpression,
    ForStatement,
    ListLiteral,
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
from .semantic import check as semantic_check


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


LIST_METHODS = {"length", "get", "push", "contains"}
ALLOWED_NET_SCHEMES = frozenset({"http", "https"})


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
    if isinstance(value, StructValue):
        inner = ", ".join(
            f"{name}: {_ks_repr(item)}" for name, item in value.fields.items()
        )
        return f"{value.type_name} {{ {inner} }}"
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


class _DiskCapability(_NarrowedCapability):
    __slots__ = ("prefix",)

    def __init__(self, prefix: str) -> None:
        self.prefix = os.path.realpath(os.fspath(prefix))

    def _checked_path(self, path: str) -> str | KsError:
        target = os.path.realpath(os.fspath(path))
        try:
            inside = os.path.commonpath((self.prefix, target)) == self.prefix
        except ValueError:
            inside = False
        if not inside:
            return KsError(
                f"KS3402: Disk kapsamı dışında erişim reddedildi: {path}"
            )
        return target

    def read(self, path: str) -> str | KsError:
        return self.read_file(path)

    def read_file(self, path: str) -> str | KsError:
        checked = self._checked_path(path)
        if isinstance(checked, KsError):
            return checked
        try:
            return Path(checked).read_text(encoding="utf-8")
        except OSError as error:
            return KsError(f"Dosya okunamadı: {error}")

    def list(self, path: str) -> list[str] | KsError:
        checked = self._checked_path(path)
        if isinstance(checked, KsError):
            return checked
        try:
            return sorted(os.listdir(checked))
        except OSError as error:
            return KsError(f"Dizin listelenemedi: {error}")


class DiskReadCaps(_DiskCapability):
    __slots__ = ()

    @staticmethod
    def _denied(operation: str) -> KsError:
        return KsError(
            f"KS3404: DiskReadCaps '{operation}' işlemine izin vermez."
        )

    def write(self, path: str, value: str) -> KsError:
        checked = self._checked_path(path)
        return checked if isinstance(checked, KsError) else self._denied("write")

    def write_file(self, path: str, value: str) -> KsError:
        checked = self._checked_path(path)
        return checked if isinstance(checked, KsError) else self._denied("write_file")

    def delete(self, path: str) -> KsError:
        checked = self._checked_path(path)
        return checked if isinstance(checked, KsError) else self._denied("delete")


class DiskCaps(_DiskCapability):
    __slots__ = ()

    def write(self, path: str, value: str) -> _KsUnit | KsError:
        return self.write_file(path, value)

    def write_file(self, path: str, value: str) -> _KsUnit | KsError:
        checked = self._checked_path(path)
        if isinstance(checked, KsError):
            return checked
        try:
            Path(checked).write_text(str(value), encoding="utf-8")
        except OSError as error:
            return KsError(f"Dosya yazılamadı: {error}")
        return KsUnit

    def delete(self, path: str) -> _KsUnit | KsError:
        checked = self._checked_path(path)
        if isinstance(checked, KsError):
            return checked
        try:
            if os.path.isdir(checked):
                os.rmdir(checked)
            else:
                os.remove(checked)
        except OSError as error:
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
        return KsError("process yetkisi v0.1'de kapalı")

    @staticmethod
    def spawn(*arguments: Any) -> KsError:
        return KsError("process yetkisi v0.1'de kapalı")


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
    ) -> None:
        self.program = program
        self.argv = list(argv or [])
        self.functions = {
            declaration.name: declaration for declaration in program.declarations
        }
        self.structs = {
            declaration.name: declaration for declaration in program.structs
        }
        # Modül anahtarı -> o modülün fonksiyon tablosu
        self.namespaces = namespaces or {}
        # Yerel import adı -> modül anahtarı
        self.imports = imports or {}
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
        self.environment = _Environment()
        if namespace is not None:
            self.functions = namespace
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
            return expression.value

        if isinstance(expression, Identifier):
            if expression.name in self.functions:
                return self.functions[expression.name]
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
                items.append(value)
            return items

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
            operand = self._evaluate(expression.operand)
            if isinstance(operand, KsError):
                return operand
            if expression.operator == "!":
                return not bool(operand)
            if expression.operator == "-":
                return -operand
            raise AssertionError(expression.operator)

        if isinstance(expression, OrReturnExpression):
            value = self._evaluate(expression.value)
            if isinstance(value, KsError):
                replacement = (
                    value
                    if expression.error is None
                    else self._evaluate(expression.error)
                )
                raise _ReturnSignal(replacement)
            return value

        if isinstance(expression, OrElseExpression):
            value = self._evaluate(expression.value)
            return self._evaluate(expression.fallback) if isinstance(value, KsError) else value

        if isinstance(expression, OrBlockExpression):
            value = self._evaluate(expression.value)
            return self._execute_block(expression.handler) if isinstance(value, KsError) else value

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
            str: {"length", "to_int", "to_float", "contains"},
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
            )
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
                # Değerler değişmezdir: push YENİ bir liste döndürür.
                return receiver + [arguments[0]]
            if name == "contains":
                self._require_arity(name, arguments, 1, member.location)
                return arguments[0] in receiver

        method = getattr(receiver, name)
        try:
            return method(*arguments)
        except TypeError as error:
            raise KoscheiRuntimeError(
                "KS3101", f"'{name}' çağrısı geçersiz: {error}", member.location
            ) from error

    def _runtime_matches_type(
        self,
        value: Any,
        expected_names,
    ) -> bool:
        for name in expected_names:
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
            if isinstance(value, StructValue) and value.type_name == name:
                return True
        return False

    @staticmethod
    def _runtime_type_name(value: Any) -> str:
        if value is KsUnit:
            return "Void"
        if isinstance(value, StructValue):
            return value.type_name
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
) -> int:
    """Programı çalıştırır.

    namespaces/imports verilmezse tek dosyalık program varsayılır. Modül grafiği
    varsa semantic denetimi çağıran taraf (CLI) yapmıştır; burada tekrarlanmaz.
    """
    if namespaces is None:
        semantic_check(program)
    result = Interpreter(program, argv, namespaces, imports).execute_main()
    if isinstance(result, KsError):
        print(f"KOSCHEI RUNTIME ERROR: {result.message}", file=sys.stderr)
        return 1
    return 0
