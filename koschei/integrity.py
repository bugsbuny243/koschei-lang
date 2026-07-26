"""Backend-independent compiler integrity checks.

This pass runs before the ordinary semantic/type checker. It prevents source
program mistakes from leaking into the interpreter or native backend and keeps
control-flow rules in one small, testable layer.
"""

from __future__ import annotations

from .ast_nodes import (
    Block,
    ForStatement,
    IfStatement,
    Program,
    ReturnStatement,
    Statement,
    WhileStatement,
)
from .semantic import SemanticError


def _error(code: str, message: str, statement) -> None:
    raise SemanticError(code, message, statement.location)


def _validate_top_level(program: Program) -> None:
    for kind, declarations in (
        ("function", program.declarations),
        ("struct", program.structs),
        ("enum", program.enums),
    ):
        seen: set[str] = set()
        for declaration in declarations:
            if declaration.name in seen:
                _error(
                    "KS1102",
                    f"'{declaration.name}' {kind} is declared more than once in the global scope.",
                    declaration,
                )
            seen.add(declaration.name)

    struct_names = {declaration.name for declaration in program.structs}
    for declaration in program.enums:
        if declaration.name in struct_names:
            _error(
                "KS1701",
                f"'{declaration.name}' cannot be declared as both a struct and an enum.",
                declaration,
            )


def _check_block(block: Block, function) -> bool:
    terminated = False
    for statement in block.statements:
        if terminated:
            _error(
                "KS1305",
                "This statement is unreachable because the previous control flow always returns.",
                statement,
            )
        terminated = _check_statement(statement, function)
    return terminated


def _check_statement(statement: Statement, function) -> bool:
    if isinstance(statement, ReturnStatement):
        if function.return_type is None and statement.value is not None and function.name != "main":
            _error(
                "KS1304",
                f"'{function.name}' is a Void function and cannot return a value.",
                statement,
            )
        return True

    if isinstance(statement, IfStatement):
        then_returns = _check_block(statement.then_block, function)
        else_returns = False
        if isinstance(statement.else_branch, Block):
            else_returns = _check_block(statement.else_branch, function)
        elif isinstance(statement.else_branch, IfStatement):
            else_returns = _check_statement(statement.else_branch, function)
        return statement.else_branch is not None and then_returns and else_returns

    if isinstance(statement, WhileStatement):
        _check_block(statement.body, function)
        return False

    if isinstance(statement, ForStatement):
        _check_block(statement.body, function)
        return False

    return False


def check_program_integrity(program: Program) -> None:
    """Validate declaration uniqueness and function return control flow."""

    _validate_top_level(program)
    for function in program.declarations:
        always_returns = _check_block(function.body, function)
        if function.return_type is not None and not always_returns:
            _error(
                "KS1303",
                f"'{function.name}' declares return type {function.return_type} but not every control-flow path returns a value.",
                function,
            )


def _register_diagnostics() -> None:
    """Register this pass's stable errors in both human-language catalogs.

    The catalog module is already initialized before ``modules`` imports this
    pass through the public CLI. Keeping registration beside the pass prevents
    new integrity errors from existing without an explanation.
    """

    from .diagnostics import CATALOG, ENGLISH_CATALOG, Diagnostic

    turkish = {
        "KS1303": Diagnostic(
            code="KS1303",
            title="Her kontrol akışı değer döndürmüyor",
            summary="Dönüş tipi bildiren fonksiyonun en az bir yolu değer döndürmeden bitebilir.",
            why="Çağıran kod bildirilen tipe güvenir. Eksik dönüş ancak runtime'da görülürse interpreter ve native hedef farklı davranabilir.",
            fix="Her if/else kolunun ve fonksiyonun sonuna ulaşabilen her yolun bildirilen tipte değer döndürmesini sağlayın.",
            example="fn sign(x: Int) -> Int {\n    if x < 0 { return -1 } else { return 1 }\n}",
        ),
        "KS1304": Diagnostic(
            code="KS1304",
            title="Void fonksiyon değer döndüremez",
            summary="Dönüş tipi olmayan bir fonksiyonda 'return değer' kullanıldı.",
            why="Void fonksiyonun çağıranına değer vermeyeceği sözleşmenin parçasıdır; gizli bir sonuç bu sözleşmeyi belirsizleştirir.",
            fix="Yalnız 'return' kullanın veya fonksiyona açık bir dönüş tipi ekleyin.",
            example="fn log_done() {\n    println(\"done\")\n    return\n}",
        ),
        "KS1305": Diagnostic(
            code="KS1305",
            title="Ulaşılamayan kod",
            summary="Kesin dönüşten sonra hiçbir zaman çalışamayacak bir ifade bulundu.",
            why="Ölü kod genellikle yanlış yerleştirilmiş return veya eksik kontrol akışı işaretidir ve backend farklarını gizleyebilir.",
            fix="Ulaşılamayan ifadeyi kaldırın ya da return/if yapısını kodun gerçekten çalışacağı biçimde düzenleyin.",
            example="fn answer() -> Int {\n    return 42\n}",
        ),
        "KS1801": Diagnostic(
            code="KS1801",
            title="Binary giriş noktası geçersiz",
            summary="Çalıştırılabilir hedefte geçerli bir 'fn main()' bulunamadı.",
            why="Kütüphane kaynakları main olmadan denetlenebilir; run/build hedefinin ise tek ve açık bir başlangıç noktası olmalıdır.",
            fix="Kök modüle dönüş tipi bildirmeyen 'fn main()' ekleyin. Yetki gerekiyorsa tek SystemCaps parametresi kullanın.",
            example="fn main() {\n    println(\"hello\")\n}",
        ),
    }
    english = {
        "KS1303": Diagnostic(
            code="KS1303",
            title="Not every control-flow path returns a value",
            summary="A function with a declared return type can finish without returning a value.",
            why="Callers rely on the declared type; discovering a missing return at runtime would allow interpreter and native behavior to diverge.",
            fix="Make every reachable path, including all if/else branches, return a value of the declared type.",
            example="fn sign(x: Int) -> Int {\n    if x < 0 { return -1 } else { return 1 }\n}",
        ),
        "KS1304": Diagnostic(
            code="KS1304",
            title="A Void function cannot return a value",
            summary="A function without a return type used 'return value'.",
            why="The absence of a result is part of the function contract; a hidden value would make that contract ambiguous.",
            fix="Use a bare return or declare an explicit return type.",
            example="fn log_done() {\n    println(\"done\")\n    return\n}",
        ),
        "KS1305": Diagnostic(
            code="KS1305",
            title="Unreachable code",
            summary="A statement can never execute because an earlier path always returns.",
            why="Dead code often signals a misplaced return or broken control-flow assumption and can hide backend differences.",
            fix="Remove the unreachable statement or restructure the return and conditional flow.",
            example="fn answer() -> Int {\n    return 42\n}",
        ),
        "KS1801": Diagnostic(
            code="KS1801",
            title="Invalid binary entry point",
            summary="The executable target has no valid 'fn main()' entry point.",
            why="Library sources may be checked without main, but run/build targets need one explicit start function.",
            fix="Add a root-level main without a declared return type; accept one SystemCaps parameter only when authority is required.",
            example="fn main() {\n    println(\"hello\")\n}",
        ),
    }
    for code, diagnostic in turkish.items():
        CATALOG.setdefault(code, diagnostic)
    for code, diagnostic in english.items():
        ENGLISH_CATALOG.setdefault(code, diagnostic)


_register_diagnostics()
