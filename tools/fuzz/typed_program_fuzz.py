"""Generate well-typed Koschei programs and compare executors.

Usage: python3 tools/fuzz/typed_program_fuzz.py SEED COUNT [--native]

Every generated program is meant to pass `ks check`. For each one:
- `ks check` must accept it (a refusal is a finding: the generator or the
  checker is wrong, and either deserves a look);
- `ks run` must finish with output or a coded runtime error, never an
  internal error;
- with --native, a `ks build` binary must print the same output and exit the
  same way, or `ks build` must refuse with KS40xx.

Programs use Int, Bool, String, List<Int>, a struct, an enum with payloads,
helper functions, bounded loops, `if`, `match` with payload bindings, string interpolation and fallible
`get` with `or`. Values stay small so arithmetic never overflows.
"""

from __future__ import annotations

import random
import re
import subprocess
import sys
import tempfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path


class Gen:
    def __init__(self, rng: random.Random) -> None:
        self.rng = rng
        self.counter = 0
        self.functions: list[tuple[str, list[str], str]] = []  # name, param types, return type

    def fresh(self, prefix: str) -> str:
        self.counter += 1
        return f"{prefix}{self.counter}"

    # --- expressions -----------------------------------------------------

    def int_expr(self, env: dict[str, str], depth: int = 0) -> str:
        r = self.rng
        ints = [n for n, t in env.items() if t == "Int"]
        choice = r.randrange(9 if depth < 3 else 2)
        if choice == 0 or (choice == 1 and not ints):
            return str(r.randint(0, 20))
        if choice == 1:
            return r.choice(ints)
        if choice in (2, 3):
            op = r.choice(["+", "-", "*"])
            left, right = self.int_expr(env, depth + 1), self.int_expr(env, depth + 1)
            if op == "*":
                return f"(({left}) % 50) * (({right}) % 50)"
            return f"({left} {op} {right}) % 1000"
        if choice == 4:
            return f"({self.int_expr(env, depth + 1)}) / {r.randint(1, 9)}"
        if choice == 5:
            lists = [n for n, t in env.items() if t == "List<Int>"]
            if lists:
                name = r.choice(lists)
                if r.random() < 0.5:
                    return f"{name}.length()"
                return f"({name}.get({r.randint(0, 6)}) or {r.randint(0, 9)})"
            return str(r.randint(0, 20))
        if choice == 6:
            strings = [n for n, t in env.items() if t == "String"]
            if strings:
                name = r.choice(strings)
                if r.random() < 0.5:
                    return f"{name}.length()"
                return f"({name}.to_int() or {r.randint(0, 9)}) % 1000"
            return str(r.randint(0, 20))
        if choice == 7:
            candidates = [f for f in self.functions if f[2] == "Int"]
            if candidates:
                name, params, _ = r.choice(candidates)
                args = ", ".join(self.expr_of(t, env, depth + 1) for t in params)
                return f"{name}({args})"
            return str(r.randint(0, 20))
        structs = [n for n, t in env.items() if t == "Point"]
        if structs:
            return f"{r.choice(structs)}.{r.choice(['x', 'y'])}"
        return str(r.randint(0, 20))

    def bool_expr(self, env: dict[str, str], depth: int = 0) -> str:
        r = self.rng
        choice = r.randrange(5 if depth < 3 else 2)
        bools = [n for n, t in env.items() if t == "Bool"]
        if choice == 0:
            return r.choice(["true", "false"])
        if choice == 1:
            op = r.choice(["<", "<=", ">", ">=", "==", "!="])
            return f"{self.int_expr(env, depth + 1)} {op} {self.int_expr(env, depth + 1)}"
        if choice == 2 and bools:
            return r.choice(bools)
        if choice == 3:
            op = r.choice(["&&", "||"])
            return f"({self.bool_expr(env, depth + 1)}) {op} ({self.bool_expr(env, depth + 1)})"
        strings = [n for n, t in env.items() if t == "String"]
        if strings:
            return f'{r.choice(strings)}.contains("{r.choice(["a", "b", "1", ""])}")'
        return f"!({self.bool_expr(env, depth + 1)})"

    def string_expr(self, env: dict[str, str], depth: int = 0) -> str:
        r = self.rng
        choice = r.randrange(4)
        strings = [n for n, t in env.items() if t == "String"]
        if choice == 0 or not strings:
            return '"' + r.choice(["", "a", "b1", "ab", "koschei", "x y", "ğüşİı", "日本語", "e\u0301", "42", "-7", " 9 "]) + '"'
        if choice == 1:
            return r.choice(strings)
        if choice == 2:
            ints = [n for n, t in env.items() if t == "Int"]
            inner = r.choice(ints) if ints else "1"
            return f'"{r.choice(["v", "n="])}{{{inner}}}{r.choice(["", "!"])}"'
        return f"{r.choice(strings)}.trim()"

    def list_expr(self, env: dict[str, str]) -> str:
        items = ", ".join(str(self.rng.randint(0, 9)) for _ in range(self.rng.randint(0, 4)))
        return f"[{items}]"

    def expr_of(self, kind: str, env: dict[str, str], depth: int = 0) -> str:
        if kind == "Int":
            return self.int_expr(env, depth)
        if kind == "Bool":
            return self.bool_expr(env, depth)
        if kind == "String":
            return self.string_expr(env, depth)
        if kind == "List<Int>":
            return self.list_expr(env)
        return f"Point {{ x: {self.int_expr(env, depth)}, y: {self.int_expr(env, depth)} }}"

    # --- statements ------------------------------------------------------

    def block(self, env: dict[str, str], mutable: set[str], indent: int, size: int, loop_depth: int) -> list[str]:
        lines: list[str] = []
        pad = "    " * indent
        env = dict(env)
        for _ in range(size):
            r = self.rng
            choice = r.randrange(9)
            if choice in (0, 1):
                kind = r.choice(["Int", "Int", "Bool", "String", "List<Int>", "Point"])
                name = self.fresh("v")
                mut = r.random() < 0.6 and kind != "Point"
                lines.append(f"{pad}let {'mut ' if mut else ''}{name} = {self.expr_of(kind, env)}")
                env[name] = kind
                if mut:
                    mutable.add(name)
            elif choice == 2:
                targets = [n for n in mutable if n in env]
                if targets:
                    name = r.choice(targets)
                    if env[name] == "List<Int>":
                        lines.append(f"{pad}{name} = {name}.push({self.int_expr(env)})")
                    else:
                        lines.append(f"{pad}{name} = {self.expr_of(env[name], env)}")
            elif choice == 3:
                kind = r.choice(["Int", "Bool", "String"])
                lines.append(f"{pad}println({self.expr_of(kind, env)})")
            elif choice == 4 and indent < 4:
                lines.append(f"{pad}if {self.bool_expr(env)} {{")
                lines += self.block(env, set(mutable), indent + 1, r.randint(1, 3), loop_depth)
                if r.random() < 0.5:
                    lines.append(f"{pad}}} else {{")
                    lines += self.block(env, set(mutable), indent + 1, r.randint(1, 3), loop_depth)
                lines.append(f"{pad}}}")
            elif choice == 5 and indent < 4 and loop_depth < 2:
                counter = self.fresh("i")
                lines.append(f"{pad}let mut {counter} = 0")
                lines.append(f"{pad}while {counter} < {r.randint(0, 6)} {{")
                inner_env = dict(env)
                inner_env[counter] = "Int"
                lines += self.block(inner_env, set(mutable), indent + 1, r.randint(1, 3), loop_depth + 1)
                lines.append(f"{pad}    {counter} = {counter} + 1")
                lines.append(f"{pad}}}")
                env[counter] = "Int"
            elif choice == 6 and indent < 4 and loop_depth < 2:
                item = self.fresh("x")
                lines.append(f"{pad}for {item} in {self.list_expr(env)} {{")
                inner_env = dict(env)
                inner_env[item] = "Int"
                lines += self.block(inner_env, set(mutable), indent + 1, r.randint(1, 3), loop_depth + 1)
                lines.append(f"{pad}}}")
            elif choice == 7 and indent < 4:
                name = self.fresh("m")
                lines.append(f"{pad}let {name} = match shape_of({self.int_expr(env)}) {{")
                lines.append(f"{pad}    Empty => {self.int_expr(env)},")
                lines.append(f"{pad}    Circle(radius) => radius + {self.int_expr(env)},")
                lines.append(f"{pad}    Label(text) => text.length(),")
                lines.append(f"{pad}}}")
                env[name] = "Int"
            elif choice == 8 and r.random() < 0.15:
                # Overflow must stop the program the same way in every executor.
                ints = [n for n, t in env.items() if t == "Int"]
                if ints:
                    lines.append(f"{pad}println(9223372036854775800 + {r.choice(ints)} * 10)")
            else:
                ints = [n for n, t in env.items() if t == "Int"]
                if ints:
                    lines.append(f'{pad}println("{r.choice(ints)}={{{r.choice(ints)}}}")')
        return lines

    def function(self) -> list[str]:
        r = self.rng
        name = self.fresh("f")
        params = [r.choice(["Int", "Int", "Bool", "String", "List<Int>"]) for _ in range(r.randint(0, 3))]
        returns = r.choice(["Int", "Int", "Bool", "String"])
        env = {f"p{i}": t for i, t in enumerate(params)}
        signature = ", ".join(f"p{i}: {t}" for i, t in enumerate(params))
        body = self.block(env, set(), 1, r.randint(0, 3), 0)
        # Only functions defined earlier may be called, so there is no recursion.
        lines = [f"fn {name}({signature}) -> {returns} {{", *body, f"    return {self.expr_of(returns, env)}", "}", ""]
        self.functions.append((name, params, returns))
        return lines

    def program(self) -> str:
        lines = [
            "struct Point {", "    x: Int,", "    y: Int,", "}", "",
            "enum Shape {", "    Empty,", "    Circle(Int),", "    Label(String),", "}", "",
            "fn shape_of(n: Int) -> Shape {",
            "    if n % 3 == 0 {", "        return Empty", "    }",
            "    if n % 3 == 1 {", "        return Circle(n)", "    }",
            '    return Label("n{n}")', "}", "",
        ]
        for _ in range(self.rng.randint(0, 3)):
            lines += self.function()
        lines.append("fn main() {")
        lines += self.block({}, set(), 1, self.rng.randint(3, 10), 0)
        lines.append("}")
        return "\n".join(lines) + "\n"


def sh(command: list[str], cwd: str, timeout: int) -> tuple[object, str, str]:
    try:
        done = subprocess.run(command, cwd=cwd, capture_output=True, text=True, timeout=timeout)
        return done.returncode, done.stdout, done.stderr
    except subprocess.TimeoutExpired:
        return "timeout", "", ""


def internal(stderr: str) -> bool:
    return "Traceback" in stderr or ("Compiler error —" in stderr and not re.search(r"KS\d{4} \[", stderr))


def one(source: str, native: bool) -> tuple[str, str, str]:
    with tempfile.TemporaryDirectory() as directory:
        Path(directory, "main.ks").write_text(source)
        check = sh(["ks", "--lang", "en", "check", "main.ks"], directory, 60)
        if check[0] != 0:
            return ("rejected", source, check[2].strip()[:400])
        run = sh(["ks", "run", "main.ks"], directory, 60)
        if run[0] == "timeout" or internal(run[2]):
            return ("run_internal", source, str(run)[:600])
        if not native:
            return ("ok", "", "")
        build = sh(["ks", "build", "main.ks", "--output", "bin"], directory, 180)
        if build[0] != 0:
            if re.search(r"KS40\d\d", build[2]):
                return ("refused", "", "")
            return ("build_failed", source, build[2].strip()[:600])
        binary = sh(["./bin"], directory, 60)
        same_output = run[1] == binary[1]
        same_exit = (run[0] == 0) == (binary[0] == 0)
        if same_output and same_exit:
            return ("ok", "", "")
        return ("diff", source, f"RUN {run}\nNATIVE {binary}"[:1200])


def main() -> int:
    seed, count = int(sys.argv[1]), int(sys.argv[2])
    native = "--native" in sys.argv
    sources = [Gen(random.Random(seed * 100_003 + index)).program() for index in range(count)]
    with ThreadPoolExecutor(6) as pool:
        results = list(pool.map(lambda source: one(source, native), sources))
    from collections import Counter

    print(Counter(kind for kind, _, _ in results))
    findings = [result for result in results if result[0] not in ("ok", "refused")]
    for kind, source, detail in findings[:5]:
        print("----", kind)
        print(source)
        print(detail)
    return 1 if findings else 0


if __name__ == "__main__":
    raise SystemExit(main())
