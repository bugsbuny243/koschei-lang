"""Interpreter and Go backend parity for v0.10 ergonomics."""
from __future__ import annotations
import re
from typing import Any
from . import ast_nodes as ast
from . import codegen_go as codegen
from . import interpreter as runtime
from .ergonomics_nodes import BreakSignal, BreakStatement, ContinueSignal, ContinueStatement

_INSTALLED = False

def _member(self, member, arguments):
    if isinstance(member.receiver, list) and member.name == "get":
        self._require_arity("get", arguments, 1, member.location); index = arguments[0]
        if not isinstance(index, int) or isinstance(index, bool): return runtime.KsError("Liste indeksi Int olmalıdır")
        if index < 0 or index >= len(member.receiver): return runtime.EnumValue("Option", "None")
        return runtime.EnumValue("Option", "Some", member.receiver[index])
    return _member.original(self, member, arguments)

def _statement(self, statement):
    if isinstance(statement, BreakStatement): raise BreakSignal()
    if isinstance(statement, ContinueStatement): raise ContinueSignal()
    if isinstance(statement, ast.ForStatement):
        iterable = self._evaluate(statement.iterable)
        if isinstance(iterable, runtime.KsError): return iterable
        if not isinstance(iterable, list): raise runtime.KoscheiRuntimeError("KS3101", "'for ... in' yalnızca List üzerinde çalışır.", statement.location)
        result: Any = runtime.KsUnit
        for item in iterable:
            self.environment.push()
            try:
                self.environment.define(statement.variable, item, False)
                try: result = self._execute_block(statement.body, create_scope=False)
                except ContinueSignal: continue
                except BreakSignal: break
            finally: self.environment.pop()
            if isinstance(result, runtime.KsError): return result
        return result
    if isinstance(statement, ast.WhileStatement):
        result: Any = runtime.KsUnit
        while True:
            condition = self._evaluate(statement.condition)
            if isinstance(condition, runtime.KsError): return condition
            if not bool(condition): return result
            try: result = self._execute_block(statement.body)
            except ContinueSignal: continue
            except BreakSignal: return result
            if isinstance(result, runtime.KsError): return result
    return _statement.original(self, statement)

def _match(self, expression):
    value = self._evaluate(expression.value)
    if not isinstance(value, runtime.EnumValue): raise runtime.KoscheiRuntimeError("KS3101", "match çalışma anında enum, Option veya Result bekler.", expression.location)
    for arm in expression.arms:
        if arm.variant != value.variant: continue
        self.environment.push()
        try:
            if arm.binding is not None:
                if value.payload is runtime._NO_PAYLOAD: raise runtime.KoscheiRuntimeError("KS3101", f"'{value.variant}' payload taşımıyor.", arm.location)
                self.environment.define(arm.binding, value.payload, False)
            return self._execute_block(arm.body) if isinstance(arm.body, ast.Block) else self._evaluate(arm.body)
        finally: self.environment.pop()
    raise runtime.KoscheiRuntimeError("KS3101", f"match içinde '{value.variant}' varyantı için kol yok.", expression.location)

def _evaluate(self, expression):
    if isinstance(expression, ast.MatchExpression) and any(isinstance(a.body, ast.Block) for a in expression.arms): return _match(self, expression)
    if isinstance(expression, ast.AssignmentExpression) and isinstance(expression.target, ast.MemberExpression):
        target = expression.target
        if not isinstance(target.object, ast.Identifier): raise runtime.KoscheiRuntimeError("KS3201", "İç içe struct alan ataması desteklenmiyor.", expression.location)
        cell = self.environment.resolve(target.object.name, target.object.location)
        if not cell.is_mutable: raise runtime.KoscheiRuntimeError("KS3201", f"'{target.object.name}' immutable; 'let mut' gerekir.", expression.location)
        if not isinstance(cell.value, runtime.StructValue): raise runtime.KoscheiRuntimeError("KS3201", "Alan atamasının hedefi struct olmalıdır.", expression.location)
        if target.member not in cell.value.fields: raise runtime.KoscheiRuntimeError("KS3101", f"'{cell.value.type_name}' struct'ında '{target.member}' alanı yok.", target.location)
        value = self._evaluate(expression.value); declaration = self.structs.get(cell.value.type_name)
        if declaration is not None:
            field = next((x for x in declaration.fields if x.name == target.member), None)
            if field is not None and not self._runtime_matches_type(value, field.type_ref.names): self._raise_runtime_contract_error(f"'{cell.value.type_name}.{target.member}' alan ataması", field.type_ref.names, value, expression.location)
        cell.value.fields[target.member] = value; return value
    return _evaluate.original(self, expression)

def _binary(self, expression):
    if expression.operator != "%": return _binary.original(self, expression)
    left = self._evaluate(expression.left); right = self._evaluate(expression.right)
    if isinstance(left, runtime.KsError): return left
    if isinstance(right, runtime.KsError): return right
    if type(left) is not int or type(right) is not int: return runtime.KsError("KS1301: '%' yalnızca Int % Int kabul eder")
    if right == 0: return runtime.KsError("Sıfıra bölme")
    if left == runtime.INT_MIN and right == -1: return self._int_overflow("%")
    quotient = abs(left) // abs(right)
    if (left < 0) != (right < 0): quotient = -quotient
    return left - quotient * right

def _patch_native_runtime():
    replacement = '''func ksListGet(value any, index any) any {
\tlist, ok := value.([]any)
\tif !ok { return ksErrorf("List.get() bir List bekler") }
\tposition, ok := index.(int64)
\tif !ok { return ksErrorf("Liste indeksi Int olmalıdır") }
\tif position < 0 || position >= int64(len(list)) { return ksEnum("Option", "None", ksUnit, false) }
\treturn ksEnum("Option", "Some", list[position], true)
}
'''
    pattern = re.compile(r"func ksListGet\(value any, index any\) any \{.*?\n\}\n", re.DOTALL)
    if pattern.search(codegen.RUNTIME_PRELUDE): codegen.RUNTIME_PRELUDE = pattern.sub(replacement, codegen.RUNTIME_PRELUDE, count=1)
    elif replacement not in codegen.RUNTIME_PRELUDE: raise RuntimeError("native List.get ABI changed; v0.10 patch refused")
    if "func ksMod(" not in codegen.RUNTIME_PRELUDE:
        codegen.RUNTIME_PRELUDE += r'''
func ksMod(left any, right any) any {
\ta, aok := left.(int64); b, bok := right.(int64)
\tif !aok || !bok { return ksErrorf("KS1301: '%' only accepts Int % Int") }
\tif b == 0 { return ksErrorf("Sıfıra bölme") }
\tif a == ksIntMin && b == -1 { return ksIntOverflow("%") }
\treturn a % b
}
func ksSetStructField(receiver any, name string, value any) any {
\titem, ok := receiver.(*KsStruct)
\tif !ok { return ksErrorf("KS3201: struct field assignment requires a struct") }
\tif _, exists := item.Fields[name]; !exists { return ksErrorf("KS3101: undefined struct field: " + name) }
\tif ksContainsCapability(value) { return ksErrorf("KS3401: capabilities cannot be stored in struct fields") }
\titem.Fields[name] = value; return value
}
'''

def _cg_init(self, program):
    _cg_init.original(self, program); self._v010_loop_labels = []; self._v010_loop_index = 0

def _label(self):
    self._v010_loop_index += 1; return f"ksloop{self._v010_loop_index}"

def _cg_statement(self, statement, depth):
    pad = "\t" * depth
    if isinstance(statement, BreakStatement):
        if not self._v010_loop_labels: raise codegen.CodegenError("KS4002", "break döngü dışında üretilemez.", statement.location)
        return [f"{pad}break {self._v010_loop_labels[-1]}"]
    if isinstance(statement, ContinueStatement):
        if not self._v010_loop_labels: raise codegen.CodegenError("KS4002", "continue döngü dışında üretilemez.", statement.location)
        return [f"{pad}continue {self._v010_loop_labels[-1]}"]
    if isinstance(statement, ast.ForStatement):
        value, prelude = self._expression(statement.iterable, depth); source, items, ok, label = self._temp(), self._temp(), self._temp(), _label(self)
        lines = [pad + x for x in prelude] + [f"{pad}{source} := {value}", f"{pad}{items}, {ok} := {source}.([]any)", f"{pad}if !{ok} {{", f'{pad}\treturn ksErrorf("KS3101: for yalnızca List üzerinde çalışır")', f"{pad}}}", f"{pad}{label}: for _, {codegen._var(statement.variable)} := range {items} {{", f"{pad}\t_ = {codegen._var(statement.variable)}"]
        self._v010_loop_labels.append(label)
        try: lines.extend(self._block(statement.body, depth + 1))
        finally: self._v010_loop_labels.pop()
        lines.append(f"{pad}}}"); return lines
    if isinstance(statement, ast.WhileStatement):
        label = _label(self); inner = "\t" * (depth + 1); condition, prelude = self._expression(statement.condition, depth + 1)
        lines = [f"{pad}{label}: for {{"] + [inner + x for x in prelude] + [f"{inner}if !ksTruthy({condition}) {{", f"{inner}\tbreak {label}", f"{inner}}}"]
        self._v010_loop_labels.append(label)
        try: lines.extend(self._block(statement.body, depth + 1))
        finally: self._v010_loop_labels.pop()
        lines.append(f"{pad}}}"); return lines
    return _cg_statement.original(self, statement, depth)

def _cg_assignment(self, expression, depth):
    target = expression.target
    if isinstance(target, ast.MemberExpression):
        if not isinstance(target.object, ast.Identifier): raise codegen.CodegenError("KS4002", "İç içe struct alan ataması desteklenmiyor.", expression.location)
        receiver, rp = self._expression(target.object, depth); value, vp = self._expression(expression.value, depth)
        return f"ksSetStructField({receiver}, {codegen._go_string(target.member)}, {value})", rp + vp
    return _cg_assignment.original(self, expression, depth)

def _block_result(self, block, result, depth):
    statements = block.statements; body = statements; tail = None; prelude = []
    if statements and isinstance(statements[-1], ast.ExpressionStatement): body = statements[:-1]; tail, prelude = self._expression(statements[-1].expression, depth)
    lines = []
    for item in body: lines.extend(self._statement(item, depth))
    pad = "\t" * depth
    if tail is not None: lines.extend(pad + x for x in prelude); lines.append(f"{pad}{result} = {tail}")
    elif not (statements and isinstance(statements[-1], ast.ReturnStatement)): lines.append(f"{pad}{result} = ksUnit")
    return lines

def _cg_match(self, expression, depth):
    if not any(isinstance(a.body, ast.Block) for a in expression.arms): return _cg_match.original(self, expression, depth)
    value, prelude = self._expression(expression.value, depth); source, enum, result, ok = self._temp(), self._temp(), self._temp(), self._temp()
    lines = list(prelude) + [f"{source} := {value}", f"{enum}, {ok} := {source}.(*KsEnum)", f"var {result} any", f"if !{ok} {{", f'\t{result} = ksErrorf("KS3101: match çalışma anında enum, Option veya Result bekler")', "} else {", f"\tswitch {enum}.Variant {{"]
    for arm in expression.arms:
        lines += [f"\tcase {codegen._go_string(arm.variant)}:", "\t\t{"]
        if arm.binding is not None: lines += [f"\t\t\tvar {codegen._var(arm.binding)} any = {enum}.Payload", f"\t\t\t_ = {codegen._var(arm.binding)}"]
        if isinstance(arm.body, ast.Block): lines.extend(_block_result(self, arm.body, result, 3))
        else:
            body, bp = self._expression(arm.body, depth + 3); lines.extend("\t\t\t" + x for x in bp); lines.append(f"\t\t\t{result} = {body}")
        lines.append("\t\t}")
    lines += ["\tdefault:", f'\t\t{result} = ksErrorf("KS3101: match içinde varyant kolu yok: " + {enum}.Variant)', "\t}", "}"]
    return result, lines

def install_runtime_v010() -> None:
    global _INSTALLED
    if _INSTALLED: return
    _member.original = runtime.Interpreter._invoke_member; runtime.Interpreter._invoke_member = _member
    _statement.original = runtime.Interpreter._execute_statement; runtime.Interpreter._execute_statement = _statement
    _evaluate.original = runtime.Interpreter._evaluate; runtime.Interpreter._evaluate = _evaluate
    _binary.original = runtime.Interpreter._binary; runtime.Interpreter._binary = _binary
    _patch_native_runtime(); codegen.BINARY_HELPERS["%"] = "ksMod"
    _cg_init.original = codegen.GoCodegen.__init__; codegen.GoCodegen.__init__ = _cg_init
    _cg_statement.original = codegen.GoCodegen._statement; codegen.GoCodegen._statement = _cg_statement
    _cg_assignment.original = codegen.GoCodegen._assignment; codegen.GoCodegen._assignment = _cg_assignment
    _cg_match.original = codegen.GoCodegen._match; codegen.GoCodegen._match = _cg_match
    _INSTALLED = True
