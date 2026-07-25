"""Koschei AST -> Go kaynak kodu üreteci (native derleme, aşama 1).

Kapsam (v0.3 aşama 1): YETKİ İÇERMEYEN saf hesaplama programları.
Yetki (capability) taşıyan programlar bilinçli olarak REDDEDİLİR (KS4001);
yetki runtime'ı aşama 2'de üretilen koda taşınacaktır. Bu sıra kasıtlıdır:
zırh üretilen binary'ye doğru taşınmadan yetkili program derlemek, dili kâğıt
üstünde güvenli ama gerçekte açık bırakırdı.

Üretilen Go kodu kullanıcıya gösterilmek için değildir; Koschei için bir ara
temsildir (assembly gibi). Bu yüzden okunabilirlik değil, DAVRANIŞ EŞLİĞİ
önceliklidir: `ks run` ile üretilen binary aynı çıktıyı vermelidir.

Hata kodları:
    KS4001  Yetki içeren program bu aşamada derlenemez
    KS4002  Desteklenmeyen dil yapısı
    KS4003  Fonksiyon çağrısında argüman sayısı uyuşmuyor
"""

from __future__ import annotations

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
from .semantic import (
    CAPABILITY_TYPES,
    GUARDED_METHODS,
    INT_MAX,
    INT_MIN,
    INT_MIN_MAGNITUDE,
)

MAX_CALL_DEPTH = 512

STRING_METHODS = {"length", "to_int", "to_float", "contains"}

BINARY_HELPERS = {
    "+": "ksAdd",
    "-": "ksSub",
    "*": "ksMul",
    "/": "ksDiv",
    "==": "ksEq",
    "!=": "ksNotEq",
    "<": "ksLess",
    "<=": "ksLessEq",
    ">": "ksGreater",
    ">=": "ksGreaterEq",
}


class CodegenError(Exception):
    def __init__(self, code: str, message: str, location: SourceLocation) -> None:
        self.code = code
        self.message = message
        self.location = location
        super().__init__(
            f"{code} [satır {location.line}, sütun {location.column}]: {message}"
        )


RUNTIME_PRELUDE = '''// Koschei runtime — üretilmiş kod, elle düzenlemeyin.

type KsError struct {
	Message string
}

func (e *KsError) Error() string {
	return e.Message
}

type ksUnitType struct{}

var ksUnit any = ksUnitType{}

const ksMaxDepth = 512
const ksIntMin int64 = -9223372036854775808
const ksIntMax int64 = 9223372036854775807

var ksDepth int

func ksFatal(code string, message string) {
	fmt.Fprintln(os.Stderr, "KOSCHEI RUNTIME ERROR: "+code+": "+message)
	os.Exit(1)
}

func ksIsError(value any) bool {
	_, ok := value.(*KsError)
	return ok
}

func ksErrorf(message string) any {
	return &KsError{Message: message}
}

func ksToString(value any) string {
	switch item := value.(type) {
	case string:
		return item
	case bool:
		if item {
			return "true"
		}
		return "false"
	case int64:
		return strconv.FormatInt(item, 10)
	case float64:
		text := strconv.FormatFloat(item, 'g', -1, 64)
		if !strings.ContainsAny(text, ".eE") {
			text = text + ".0"
		}
		return text
	case ksUnitType:
		return "unit"
	case *KsError:
		return item.Message
	}
	return fmt.Sprintf("%v", value)
}

func ksPrintln(value any) any {
	fmt.Println(ksToString(value))
	return ksUnit
}

func ksPrint(value any) any {
	fmt.Print(ksToString(value))
	return ksUnit
}

func ksTruthy(value any) bool {
	if item, ok := value.(bool); ok {
		return item
	}
	return false
}

func ksNot(value any) any {
	return !ksTruthy(value)
}

func ksIntOverflow(operation string) any {
	return ksErrorf("KS3501: Int taşması: '" + operation + "' işlemi işaretli 64-bit aralığın dışına çıktı.")
}

func ksNegate(value any) any {
	switch item := value.(type) {
	case int64:
		if item == ksIntMin {
			return ksIntOverflow("unary -")
		}
		return -item
	case float64:
		return -item
	}
	return ksErrorf("KS1301: '-' işleci sayısal tip bekler")
}

func ksAdd(left any, right any) any {
	switch a := left.(type) {
	case int64:
		if b, ok := right.(int64); ok {
			if (b > 0 && a > ksIntMax-b) || (b < 0 && a < ksIntMin-b) {
				return ksIntOverflow("+")
			}
			return a + b
		}
	case float64:
		if b, ok := right.(float64); ok {
			return a + b
		}
	case string:
		if b, ok := right.(string); ok {
			return a + b
		}
	}
	return ksErrorf("KS1301: '+' işleci bu tiplere uygulanamaz")
}

func ksSub(left any, right any) any {
	switch a := left.(type) {
	case int64:
		if b, ok := right.(int64); ok {
			if (b > 0 && a < ksIntMin+b) || (b < 0 && a > ksIntMax+b) {
				return ksIntOverflow("-")
			}
			return a - b
		}
	case float64:
		if b, ok := right.(float64); ok {
			return a - b
		}
	}
	return ksErrorf("KS1301: '-' işleci bu tiplere uygulanamaz")
}

func ksMul(left any, right any) any {
	switch a := left.(type) {
	case int64:
		if b, ok := right.(int64); ok {
			if a == 0 || b == 0 {
				return int64(0)
			}
			if (a == ksIntMin && b == -1) || (b == ksIntMin && a == -1) {
				return ksIntOverflow("*")
			}
			result := a * b
			if result/b != a {
				return ksIntOverflow("*")
			}
			return result
		}
	case float64:
		if b, ok := right.(float64); ok {
			return a * b
		}
	}
	return ksErrorf("KS1301: '*' işleci bu tiplere uygulanamaz")
}

func ksDiv(left any, right any) any {
	switch a := left.(type) {
	case int64:
		if b, ok := right.(int64); ok {
			if b == 0 {
				return ksErrorf("Sıfıra bölme")
			}
			return float64(a) / float64(b)
		}
	case float64:
		if b, ok := right.(float64); ok {
			if b == 0 {
				return ksErrorf("Sıfıra bölme")
			}
			return a / b
		}
	}
	return ksErrorf("KS1301: '/' işleci bu tiplere uygulanamaz")
}

func ksCompare(left any, right any) (int, bool) {
	switch a := left.(type) {
	case int64:
		if b, ok := right.(int64); ok {
			switch {
			case a < b:
				return -1, true
			case a > b:
				return 1, true
			}
			return 0, true
		}
	case float64:
		if b, ok := right.(float64); ok {
			switch {
			case a < b:
				return -1, true
			case a > b:
				return 1, true
			}
			return 0, true
		}
	case string:
		if b, ok := right.(string); ok {
			return strings.Compare(a, b), true
		}
	}
	return 0, false
}

func ksLess(left any, right any) any {
	order, ok := ksCompare(left, right)
	if !ok {
		return ksErrorf("KS1301: '<' iki farklı tipi karşılaştıramaz")
	}
	return order < 0
}

func ksLessEq(left any, right any) any {
	order, ok := ksCompare(left, right)
	if !ok {
		return ksErrorf("KS1301: '<=' iki farklı tipi karşılaştıramaz")
	}
	return order <= 0
}

func ksGreater(left any, right any) any {
	order, ok := ksCompare(left, right)
	if !ok {
		return ksErrorf("KS1301: '>' iki farklı tipi karşılaştıramaz")
	}
	return order > 0
}

func ksGreaterEq(left any, right any) any {
	order, ok := ksCompare(left, right)
	if !ok {
		return ksErrorf("KS1301: '>=' iki farklı tipi karşılaştıramaz")
	}
	return order >= 0
}

func ksEq(left any, right any) any {
	return left == right
}

func ksNotEq(left any, right any) any {
	return left != right
}

func ksLength(value any) any {
	if item, ok := value.(string); ok {
		return int64(len([]rune(item)))
	}
	return ksErrorf("KS1301: 'length' yalnızca String üzerinde çağrılabilir")
}

func ksToInt(value any) any {
	item, ok := value.(string)
	if !ok {
		return ksErrorf("KS1301: 'to_int' yalnızca String üzerinde çağrılabilir")
	}
	parsed, err := strconv.ParseInt(strings.TrimSpace(item), 10, 64)
	if err != nil {
		return ksErrorf("Int dönüşümü başarısız: " + item)
	}
	return parsed
}

func ksToFloat(value any) any {
	item, ok := value.(string)
	if !ok {
		return ksErrorf("KS1301: 'to_float' yalnızca String üzerinde çağrılabilir")
	}
	parsed, err := strconv.ParseFloat(strings.TrimSpace(item), 64)
	if err != nil {
		return ksErrorf("Float dönüşümü başarısız: " + item)
	}
	return parsed
}

func ksContains(value any, needle any) any {
	item, ok := value.(string)
	if !ok {
		return ksErrorf("KS1301: 'contains' yalnızca String üzerinde çağrılabilir")
	}
	return strings.Contains(item, ksToString(needle))
}

func ksEnter(location string) {
	ksDepth++
	if ksDepth > ksMaxDepth {
		ksFatal("KS3105", "Çağrı derinliği sınırı aşıldı (512); sonsuz özyineleme olabilir. ["+location+"]")
	}
}

func ksLeave() {
	ksDepth--
}
'''


class GoCodegen:
    def __init__(self, program: Program) -> None:
        self.program = program
        self.functions = {
            declaration.name: declaration for declaration in program.declarations
        }
        self._temp_index = 0

    # ------------------------------------------------------------------
    # Genel akış
    # ------------------------------------------------------------------

    def generate(self) -> str:
        self._reject_unsupported()
        self._reject_capabilities()

        lines: list[str] = [
            "// Bu dosya Koschei derleyicisi tarafından üretilmiştir.",
            "// Elle düzenlemeyin: kaynak .ks dosyasını değiştirip yeniden derleyin.",
            "",
            "package main",
            "",
            "import (",
            '\t"fmt"',
            '\t"os"',
            '\t"strconv"',
            '\t"strings"',
            ")",
            "",
        ]
        lines.extend(RUNTIME_PRELUDE.splitlines())
        lines.append("")

        for declaration in self.program.declarations:
            lines.extend(self._function(declaration))
            lines.append("")

        lines.extend(self._entry_point())
        return "\n".join(lines) + "\n"

    def _reject_unsupported(self) -> None:
        if self.program.imports:
            raise CodegenError(
                "KS4002",
                "Modül içe aktarımı native derlemede henüz desteklenmiyor; şimdilik "
                "'koschei.py run' kullanın.",
                self.program.imports[0].location,
            )
        if self.program.structs:
            raise CodegenError(
                "KS4002",
                "Struct tanımları native derlemede henüz desteklenmiyor; şimdilik "
                "'koschei.py run' kullanın.",
                self.program.structs[0].location,
            )

    def _reject_capabilities(self) -> None:
        """Aşama 1: yetki taşıyan programlar bilinçli olarak reddedilir."""
        for declaration in self.program.declarations:
            for parameter in declaration.parameters:
                if any(name in CAPABILITY_TYPES for name in parameter.type_ref.names):
                    raise CodegenError(
                        "KS4001",
                        f"'{declaration.name}' fonksiyonu yetki (capability) parametresi "
                        f"alıyor: {parameter.type_ref}. Native derleme aşama 1 yalnızca "
                        "yetki içermeyen programları destekler; yetkili programlar için "
                        "şimdilik 'koschei.py run' kullanın.",
                        parameter.location,
                    )
            self._reject_capability_usage(declaration.body)

    def _reject_capability_usage(self, block: Block) -> None:
        for statement in block.statements:
            for expression in _walk_statement(statement):
                if isinstance(expression, MemberExpression) and (
                    expression.member in GUARDED_METHODS
                    or expression.member in {"allow", "allow_read_only"}
                ):
                    raise CodegenError(
                        "KS4001",
                        f"'{expression.member}' yetki işlemi native derlemede henüz "
                        "desteklenmiyor (aşama 2). Şimdilik 'koschei.py run' kullanın.",
                        expression.location,
                    )

    # ------------------------------------------------------------------
    # Fonksiyonlar
    # ------------------------------------------------------------------

    def _function(self, declaration: FunctionDeclaration) -> list[str]:
        parameters = ", ".join(
            f"{_var(parameter.name)} any" for parameter in declaration.parameters
        )
        lines = [f"func {_fn(declaration.name)}({parameters}) any {{"]
        lines.append(
            f'\tksEnter("{declaration.name}")'
        )
        lines.append("\tdefer ksLeave()")
        for parameter in declaration.parameters:
            lines.append(f"\t_ = {_var(parameter.name)}")
        lines.extend(self._block(declaration.body, 1))
        lines.append("\treturn ksUnit")
        lines.append("}")
        return lines

    def _entry_point(self) -> list[str]:
        main = self.functions.get("main")
        if main is None:
            raise CodegenError(
                "KS4002", "'main' fonksiyonu bulunamadı.", SourceLocation(1, 1)
            )
        if main.parameters:
            raise CodegenError(
                "KS4001",
                "Native derleme aşama 1'de 'main' yetki parametresi alamaz.",
                main.location,
            )
        return [
            "func main() {",
            f"\tresult := {_fn('main')}()",
            "\tif failure, ok := result.(*KsError); ok {",
            '\t\tfmt.Fprintln(os.Stderr, "KOSCHEI RUNTIME ERROR: "+failure.Message)',
            "\t\tos.Exit(1)",
            "\t}",
            "\tos.Exit(0)",
            "}",
        ]

    # ------------------------------------------------------------------
    # Statement üretimi
    # ------------------------------------------------------------------

    def _block(self, block: Block, depth: int) -> list[str]:
        lines: list[str] = []
        for statement in block.statements:
            lines.extend(self._statement(statement, depth))
        return lines

    def _statement(self, statement: Statement, depth: int) -> list[str]:
        pad = "\t" * depth

        if isinstance(statement, LetStatement):
            value, prelude = self._expression(statement.value, depth)
            lines = [pad + line for line in prelude]
            lines.append(f"{pad}var {_var(statement.name)} any = {value}")
            lines.append(f"{pad}_ = {_var(statement.name)}")
            return lines

        if isinstance(statement, ReturnStatement):
            if statement.value is None:
                return [f"{pad}return ksUnit"]
            value, prelude = self._expression(statement.value, depth)
            lines = [pad + line for line in prelude]
            lines.append(f"{pad}return {value}")
            return lines

        if isinstance(statement, ExpressionStatement):
            value, prelude = self._expression(statement.expression, depth)
            lines = [pad + line for line in prelude]
            lines.append(f"{pad}_ = {value}")
            return lines

        if isinstance(statement, ForStatement):
            raise CodegenError(
                "KS4002",
                "'for ... in' native derlemede henüz desteklenmiyor; şimdilik "
                "'koschei.py run' kullanın.",
                statement.location,
            )

        if isinstance(statement, IfStatement):
            return self._if_statement(statement, depth)

        if isinstance(statement, WhileStatement):
            return self._while_statement(statement, depth)

        raise CodegenError(
            "KS4002",
            f"Desteklenmeyen yapı: {type(statement).__name__}.",
            getattr(statement, "location", SourceLocation(1, 1)),
        )

    def _if_statement(self, statement: IfStatement, depth: int) -> list[str]:
        pad = "\t" * depth
        condition, prelude = self._expression(statement.condition, depth)
        lines = [pad + line for line in prelude]
        lines.append(f"{pad}if ksTruthy({condition}) {{")
        lines.extend(self._block(statement.then_block, depth + 1))

        branch = statement.else_branch
        if branch is None:
            lines.append(f"{pad}}}")
            return lines

        lines.append(f"{pad}}} else {{")
        if isinstance(branch, Block):
            lines.extend(self._block(branch, depth + 1))
        else:
            lines.extend(self._statement(branch, depth + 1))
        lines.append(f"{pad}}}")
        return lines

    def _while_statement(self, statement: WhileStatement, depth: int) -> list[str]:
        pad = "\t" * depth
        inner = "\t" * (depth + 1)
        condition, prelude = self._expression(statement.condition, depth + 1)

        lines = [f"{pad}for {{"]
        lines.extend(inner + line for line in prelude)
        lines.append(f"{inner}if !ksTruthy({condition}) {{")
        lines.append(f"{inner}\tbreak")
        lines.append(f"{inner}}}")
        lines.extend(self._block(statement.body, depth + 1))
        lines.append(f"{pad}}}")
        return lines

    # ------------------------------------------------------------------
    # İfade üretimi: (go_ifadesi, önce_çalışacak_satırlar)
    # ------------------------------------------------------------------

    def _expression(self, expression: Expression, depth: int) -> tuple[str, list[str]]:
        if isinstance(expression, Literal):
            return _literal(expression.value), []

        if isinstance(expression, Identifier):
            if expression.name in self.functions:
                raise CodegenError(
                    "KS4002",
                    "Fonksiyonlar değer olarak kullanılamaz.",
                    expression.location,
                )
            return _var(expression.name), []

        if isinstance(expression, InterpolatedString):
            return self._interpolation(expression, depth)

        if isinstance(expression, UnaryExpression):
            if (
                expression.operator == "-"
                and isinstance(expression.operand, Literal)
                and isinstance(expression.operand.value, int)
                and not isinstance(expression.operand.value, bool)
                and expression.operand.value == INT_MIN_MAGNITUDE
            ):
                return f"int64({INT_MIN})", []
            operand, prelude = self._expression(expression.operand, depth)
            helper = "ksNot" if expression.operator == "!" else "ksNegate"
            return f"{helper}({operand})", prelude

        if isinstance(expression, BinaryExpression):
            return self._binary(expression, depth)

        if isinstance(expression, AssignmentExpression):
            return self._assignment(expression, depth)

        if isinstance(expression, CallExpression):
            return self._call(expression, depth)

        if isinstance(expression, (ListLiteral, StructLiteral)):
            raise CodegenError(
                "KS4002",
                "Liste ve struct değerleri native derlemede henüz desteklenmiyor; "
                "şimdilik 'koschei.py run' kullanın.",
                expression.location,
            )

        if isinstance(expression, MemberExpression):
            raise CodegenError(
                "KS4002",
                f"Üye erişimi ('{expression.member}') yalnızca çağrı olarak desteklenir.",
                expression.location,
            )

        if isinstance(expression, OrReturnExpression):
            return self._or_return(expression, depth)

        if isinstance(expression, OrElseExpression):
            return self._or_else(expression, depth)

        if isinstance(expression, OrBlockExpression):
            return self._or_block(expression, depth)

        raise CodegenError(
            "KS4002",
            f"Desteklenmeyen ifade: {type(expression).__name__}.",
            getattr(expression, "location", SourceLocation(1, 1)),
        )

    def _interpolation(
        self, expression: InterpolatedString, depth: int
    ) -> tuple[str, list[str]]:
        prelude: list[str] = []
        parts: list[str] = []
        for part in expression.parts:
            value, part_prelude = self._expression(part, depth)
            prelude.extend(part_prelude)
            parts.append(f"ksToString({value})")
        if not parts:
            return '""', prelude
        return " + ".join(parts), prelude

    def _binary(self, expression: BinaryExpression, depth: int) -> tuple[str, list[str]]:
        operator = expression.operator

        if operator in {"&&", "||"}:
            left, prelude = self._expression(expression.left, depth)
            temp = self._temp()
            lines = list(prelude)
            lines.append(f"{temp} := {left}")
            if operator == "&&":
                lines.append(f"if ksTruthy({temp}) {{")
            else:
                lines.append(f"if !ksTruthy({temp}) {{")
            right, right_prelude = self._expression(expression.right, depth + 1)
            lines.extend("\t" + line for line in right_prelude)
            lines.append(f"\t{temp} = ksTruthy({right})")
            lines.append("} else {")
            lines.append(f"\t{temp} = {'false' if operator == '&&' else 'true'}")
            lines.append("}")
            return temp, lines

        helper = BINARY_HELPERS.get(operator)
        if helper is None:
            raise CodegenError(
                "KS4002",
                f"Desteklenmeyen işleç: '{operator}'.",
                expression.location,
            )
        left, left_prelude = self._expression(expression.left, depth)
        right, right_prelude = self._expression(expression.right, depth)
        return f"{helper}({left}, {right})", left_prelude + right_prelude

    def _assignment(
        self, expression: AssignmentExpression, depth: int
    ) -> tuple[str, list[str]]:
        if not isinstance(expression.target, Identifier):
            raise CodegenError(
                "KS4002",
                "Yalnızca değişkenlere atama yapılabilir.",
                expression.location,
            )
        value, prelude = self._expression(expression.value, depth)
        lines = list(prelude)
        lines.append(f"{_var(expression.target.name)} = {value}")
        return _var(expression.target.name), lines

    def _call(self, expression: CallExpression, depth: int) -> tuple[str, list[str]]:
        prelude: list[str] = []
        arguments: list[str] = []
        for argument in expression.arguments:
            value, argument_prelude = self._expression(argument, depth)
            prelude.extend(argument_prelude)
            arguments.append(value)

        callee = expression.callee

        if isinstance(callee, Identifier):
            name = callee.name
            if name in {"println", "print"}:
                self._check_arity(name, arguments, 1, expression.location)
                helper = "ksPrintln" if name == "println" else "ksPrint"
                return f"{helper}({arguments[0]})", prelude
            if name == "Error":
                self._check_arity(name, arguments, 1, expression.location)
                return f"ksErrorf(ksToString({arguments[0]}))", prelude

            function = self.functions.get(name)
            if function is None:
                raise CodegenError(
                    "KS4002",
                    f"Tanımsız fonksiyon: '{name}'.",
                    expression.location,
                )
            self._check_arity(
                name, arguments, len(function.parameters), expression.location
            )
            return f"{_fn(name)}({', '.join(arguments)})", prelude

        if isinstance(callee, MemberExpression):
            receiver, receiver_prelude = self._expression(callee.object, depth)
            prelude = receiver_prelude + prelude
            method = callee.member
            if method not in STRING_METHODS:
                raise CodegenError(
                    "KS4002",
                    f"Native derlemede desteklenmeyen metot: '{method}'.",
                    callee.location,
                )
            if method == "contains":
                self._check_arity(method, arguments, 1, callee.location)
                return f"ksContains({receiver}, {arguments[0]})", prelude
            self._check_arity(method, arguments, 0, callee.location)
            helper = {
                "length": "ksLength",
                "to_int": "ksToInt",
                "to_float": "ksToFloat",
            }[method]
            return f"{helper}({receiver})", prelude

        raise CodegenError(
            "KS4002", "Desteklenmeyen çağrı biçimi.", expression.location
        )

    def _or_return(
        self, expression: OrReturnExpression, depth: int
    ) -> tuple[str, list[str]]:
        value, prelude = self._expression(expression.value, depth)
        temp = self._temp()
        lines = list(prelude)
        lines.append(f"{temp} := {value}")
        lines.append(f"if ksIsError({temp}) {{")
        if expression.error is None:
            lines.append(f"\treturn {temp}")
        else:
            error, error_prelude = self._expression(expression.error, depth + 1)
            lines.extend("\t" + line for line in error_prelude)
            lines.append(f"\treturn {error}")
        lines.append("}")
        return temp, lines

    def _or_else(
        self, expression: OrElseExpression, depth: int
    ) -> tuple[str, list[str]]:
        value, prelude = self._expression(expression.value, depth)
        temp = self._temp()
        lines = list(prelude)
        lines.append(f"{temp} := {value}")
        lines.append(f"if ksIsError({temp}) {{")
        fallback, fallback_prelude = self._expression(expression.fallback, depth + 1)
        lines.extend("\t" + line for line in fallback_prelude)
        lines.append(f"\t{temp} = {fallback}")
        lines.append("}")
        return temp, lines

    def _or_block(
        self, expression: OrBlockExpression, depth: int
    ) -> tuple[str, list[str]]:
        value, prelude = self._expression(expression.value, depth)
        temp = self._temp()
        lines = list(prelude)
        lines.append(f"{temp} := {value}")
        lines.append(f"if ksIsError({temp}) {{")

        statements = expression.handler.statements
        body_statements = statements
        tail_value: str | None = None
        tail_prelude: list[str] = []

        if statements and isinstance(statements[-1], ExpressionStatement):
            body_statements = statements[:-1]
            tail_value, tail_prelude = self._expression(
                statements[-1].expression, depth + 1
            )

        for statement in body_statements:
            lines.extend(self._statement(statement, depth + 1))

        if tail_value is not None:
            lines.extend("\t" + line for line in tail_prelude)
            lines.append(f"\t{temp} = {tail_value}")
        elif not (statements and isinstance(statements[-1], ReturnStatement)):
            lines.append(f"\t{temp} = ksUnit")

        lines.append("}")
        return temp, lines

    # ------------------------------------------------------------------
    # Yardımcılar
    # ------------------------------------------------------------------

    def _temp(self) -> str:
        self._temp_index += 1
        return f"kstmp{self._temp_index}"

    @staticmethod
    def _check_arity(
        name: str, arguments: list[str], expected: int, location: SourceLocation
    ) -> None:
        if len(arguments) != expected:
            raise CodegenError(
                "KS4003",
                f"'{name}' için {expected} argüman bekleniyor, "
                f"{len(arguments)} verildi.",
                location,
            )


def _walk_statement(statement: Statement):
    """Statement içindeki tüm ifadeleri dolaşır (yetki taraması için)."""
    if isinstance(statement, LetStatement):
        yield from _walk_expression(statement.value)
    elif isinstance(statement, ReturnStatement):
        if statement.value is not None:
            yield from _walk_expression(statement.value)
    elif isinstance(statement, ExpressionStatement):
        yield from _walk_expression(statement.expression)
    elif isinstance(statement, IfStatement):
        yield from _walk_expression(statement.condition)
        for inner in statement.then_block.statements:
            yield from _walk_statement(inner)
        branch = statement.else_branch
        if isinstance(branch, Block):
            for inner in branch.statements:
                yield from _walk_statement(inner)
        elif isinstance(branch, IfStatement):
            yield from _walk_statement(branch)
    elif isinstance(statement, WhileStatement):
        yield from _walk_expression(statement.condition)
        for inner in statement.body.statements:
            yield from _walk_statement(inner)


def _walk_expression(expression: Expression):
    yield expression
    if isinstance(expression, MemberExpression):
        yield from _walk_expression(expression.object)
    elif isinstance(expression, CallExpression):
        yield from _walk_expression(expression.callee)
        for argument in expression.arguments:
            yield from _walk_expression(argument)
    elif isinstance(expression, BinaryExpression):
        yield from _walk_expression(expression.left)
        yield from _walk_expression(expression.right)
    elif isinstance(expression, UnaryExpression):
        yield from _walk_expression(expression.operand)
    elif isinstance(expression, AssignmentExpression):
        yield from _walk_expression(expression.target)
        yield from _walk_expression(expression.value)
    elif isinstance(expression, InterpolatedString):
        for part in expression.parts:
            yield from _walk_expression(part)
    elif isinstance(expression, OrReturnExpression):
        yield from _walk_expression(expression.value)
        if expression.error is not None:
            yield from _walk_expression(expression.error)
    elif isinstance(expression, OrElseExpression):
        yield from _walk_expression(expression.value)
        yield from _walk_expression(expression.fallback)
    elif isinstance(expression, OrBlockExpression):
        yield from _walk_expression(expression.value)
        for statement in expression.handler.statements:
            yield from _walk_statement(statement)


def _fn(name: str) -> str:
    return f"ksfn_{name}"


def _var(name: str) -> str:
    return f"ksv_{name}"


def _literal(value: object) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, int):
        if not INT_MIN <= value <= INT_MAX:
            raise CodegenError(
                "KS4002",
                f"Int literal native 64-bit aralığın dışında: {value}",
                SourceLocation(1, 1),
            )
        return f"int64({value})"
    if isinstance(value, float):
        return f"float64({value!r})"
    if isinstance(value, str):
        return _go_string(value)
    raise CodegenError(
        "KS4002", f"Desteklenmeyen sabit: {value!r}", SourceLocation(1, 1)
    )


def _go_string(value: str) -> str:
    escaped = (
        value.replace("\\", "\\\\")
        .replace('"', '\\"')
        .replace("\n", "\\n")
        .replace("\r", "\\r")
        .replace("\t", "\\t")
    )
    return f'"{escaped}"'


def generate_go(program: Program) -> str:
    """Koschei programını Go kaynak koduna çevirir."""
    return GoCodegen(program).generate()
