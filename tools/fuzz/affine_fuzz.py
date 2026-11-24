"""Soundness fuzzing for the affine ownership checker.

Usage: python3 tools/fuzz/affine_fuzz.py SEED COUNT

Generates programs that move, rebind and borrow capability tokens inside
nested `if`, `while` and `for` statements, in loop and branch conditions, and
around early `return`. Each program is judged twice:

* by `ks check` (the affine checker in koschei/affine_resources_v1.py), and
* by an independent oracle that runs the program symbolically along every
  path: unknown booleans (`takes(tok)`, `flag > N`) take both values, loops
  run with their exact counters, and `&&` short-circuits.

The oracle defines the rule in docs/OWNERSHIP_MODEL_V1.md: on no execution
path may a token be used after it was moved. Findings:

* **unsound**: `ks check` accepts a program that uses a moved token on some
  path. This is a security bug: authority was duplicated.
* **crash**: `ks check` fails without a KS diagnostic.

Programs the oracle accepts but the checker refuses are counted, not
reported: the checker is deliberately conservative.
"""

from __future__ import annotations

import io
import random
import re
import sys
import tempfile
from contextlib import redirect_stderr, redirect_stdout
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from koschei.cli_entry import main as ks_main  # noqa: E402

PATH_LIMIT = 20_000

PRELUDE = """struct Holder {
    t: DiskCaps,
}

fn consume(t: DiskCaps) {
    println("consumed")
}

fn takes(t: DiskCaps) -> Bool {
    return true
}

fn main(caps: SystemCaps) {
    let flag = 3
    let tok0 = caps.disk.allow("/tmp")
    let tok1 = caps.disk.allow("/tmp")
"""


# --- program AST --------------------------------------------------------------


@dataclass
class Use:
    """A token use. kind: borrow | consume | rebind (declares `new`)."""

    kind: str
    name: str
    new: str = ""


@dataclass
class Cond:
    """`flag > N`, `takes(name)`, or `flag > N && takes(name)`."""

    takes: str = ""
    guarded: bool = False


@dataclass
class If:
    cond: Cond
    then: list
    other: list | None


@dataclass
class While:
    counter: str
    limit: int
    takes: str
    body: list


@dataclass
class For:
    count: int
    body: list


@dataclass
class Return:
    pass


@dataclass
class Jump:
    """`break` or `continue`; generated only inside a loop, as a block's last statement."""

    kind: str


@dataclass
class Wrap:
    """`let new = Holder { t: name }`: moves the token into an affine struct."""

    name: str
    new: str


@dataclass
class Unwrap:
    """`consume(holder.t)` moves the whole holder; `holder.t.read` borrows it."""

    name: str
    move: bool


# --- generator ----------------------------------------------------------------


@dataclass
class Gen:
    rng: random.Random
    fresh: int = 0
    scopes: list = field(default_factory=lambda: [["tok0", "tok1"]])
    holders: list = field(default_factory=lambda: [[]])
    loops: int = 0
    moved: set = field(default_factory=set)

    def name(self, prefix: str) -> str:
        self.fresh += 1
        return f"{prefix}{self.fresh}"

    def token(self, move: bool = False) -> str:
        """Pick a token; mostly one not yet moved, so most programs are safe
        and reach deep into the statement mix before the checker stops them."""

        names = [name for scope in self.scopes for name in scope]
        unmoved = [name for name in names if name not in self.moved]
        name = self.rng.choice(unmoved if unmoved and self.rng.random() < 0.85 else names)
        if move:
            self.moved.add(name)
        return name

    def cond(self) -> Cond:
        shape = self.rng.randrange(3)
        if shape == 0:
            return Cond()
        return Cond(takes=self.token(move=True), guarded=shape == 2)

    def block(self, depth: int) -> list:
        self.scopes.append([])
        self.holders.append([])
        try:
            body = [self.statement(depth) for _ in range(self.rng.randint(1, 3))]
            ending = self.rng.random()
            if ending < 0.12:
                body.append(Return())  # last only: code after it is KS1305
            elif ending < 0.24 and self.loops:
                body.append(Jump(self.rng.choice(["break", "continue"])))
            return body
        finally:
            self.scopes.pop()
            self.holders.pop()

    def loop_block(self, depth: int) -> list:
        self.loops += 1
        try:
            return self.block(depth)
        finally:
            self.loops -= 1

    def other(self, depth: int):
        roll = self.rng.random()
        if roll < 0.4:
            return None
        if roll < 0.6 and depth > 0:
            return [If(self.cond(), self.block(depth - 1), self.other(depth - 1))]  # else if
        return self.block(depth - 1)

    def statement(self, depth: int):
        roll = self.rng.random()
        if depth > 0 and roll < 0.25:
            return If(self.cond(), self.block(depth - 1), self.other(depth))
        if depth > 0 and roll < 0.38:
            takes = self.token(move=True) if self.rng.random() < 0.25 else ""
            return While(self.name("g"), self.rng.randint(1, 2), takes, self.loop_block(depth - 1))
        if depth > 0 and roll < 0.48:
            return For(self.rng.randint(1, 2), self.loop_block(depth - 1))
        holders = [name for scope in self.holders for name in scope]
        if roll < 0.56:
            new = self.name("h")
            wrap = Wrap(self.token(move=True), new)
            self.holders[-1].append(new)
            return wrap
        if roll < 0.66 and holders:
            holder, move = self.rng.choice(holders), self.rng.random() < 0.5
            if move:
                self.moved.add(holder)
            return Unwrap(holder, move)
        # Inside a loop, moving an outer token is always refused (KS3932), so
        # loop bodies mostly borrow to let the fuzzer reach deeper code.
        kinds = ["borrow"] * (6 if self.loops else 2) + ["consume", "rebind"]
        kind = self.rng.choice(kinds)
        use = Use(kind, self.token(move=kind != "borrow"))
        if kind == "rebind":
            use.new = self.name("t")
            self.scopes[-1].append(use.new)
        return use


# --- rendering ----------------------------------------------------------------


def render_cond(cond: Cond) -> str:
    if not cond.takes:
        return "flag > 2"
    if cond.guarded:
        return f"flag > 2 && takes({cond.takes})"
    return f"takes({cond.takes})"


def render(statements: list, level: int, seen: list | None = None) -> list[str]:
    seen = seen if seen is not None else [0]

    def fresh() -> str:
        seen[0] += 1
        return f"s{seen[0]}"

    pad = "    " * level
    lines: list[str] = []
    for statement in statements:
        if isinstance(statement, Use):
            if statement.kind == "borrow":
                lines.append(f'{pad}let {fresh()} = {statement.name}.read("/tmp/koschei-affine-fuzz") or ""')
            elif statement.kind == "consume":
                lines.append(f"{pad}consume({statement.name})")
            else:
                lines.append(f"{pad}let {statement.new} = {statement.name}")
        elif isinstance(statement, If):
            lines.append(f"{pad}if {render_cond(statement.cond)} {{")
            lines += render(statement.then, level + 1, seen)
            if statement.other is not None:
                lines.append(f"{pad}}} else {{")
                lines += render(statement.other, level + 1, seen)
            lines.append(f"{pad}}}")
        elif isinstance(statement, While):
            condition = f"{statement.counter} < {statement.limit}"
            if statement.takes:
                condition += f" && takes({statement.takes})"
            lines.append(f"{pad}let mut {statement.counter} = 0")
            lines.append(f"{pad}while {condition} {{")
            lines.append(f"{pad}    {statement.counter} = {statement.counter} + 1")
            lines += render(statement.body, level + 1, seen)
            lines.append(f"{pad}}}")
        elif isinstance(statement, For):
            items = ", ".join(str(n) for n in range(statement.count))
            lines.append(f"{pad}for item in [{items}] {{")
            lines += render(statement.body, level + 1, seen)
            lines.append(f"{pad}}}")
        elif isinstance(statement, Wrap):
            lines.append(f"{pad}let {statement.new} = Holder {{ t: {statement.name} }}")
        elif isinstance(statement, Unwrap):
            if statement.move:
                lines.append(f"{pad}consume({statement.name}.t)")
            else:
                lines.append(f'{pad}let {fresh()} = {statement.name}.t.read("/tmp/koschei-affine-fuzz") or ""')
        elif isinstance(statement, Jump):
            lines.append(f"{pad}{statement.kind}")
        else:
            lines.append(f"{pad}return")
    return lines


def program(statements: list) -> str:
    return PRELUDE + "\n".join(render(statements, 1)) + "\n}\n"


# --- oracle -------------------------------------------------------------------


class Violation(Exception):
    pass


class TooManyPaths(Exception):
    pass


def explore(statements: list, live: dict, budget: list) -> list:
    """Return every (live, control) outcome of running `statements`.

    `live` maps a token or holder name to whether it still owns its authority;
    control is "" (fell through), "return", "break" or "continue".
    Raises Violation when some path uses a moved value.
    """

    outcomes = [(dict(live), "")]
    for statement in statements:
        following = []
        for state, control in outcomes:
            if control:
                following.append((state, control))
            else:
                following += step(statement, state, budget)
        outcomes = following
        budget[0] += len(outcomes)
        if budget[0] > PATH_LIMIT:
            raise TooManyPaths
    return outcomes


def use(state: dict, name: str, move: bool) -> dict:
    if not state[name]:
        raise Violation(name)
    if move:
        state = dict(state, **{name: False})
    return state


def scoped(outcomes: list, outer: dict) -> list:
    """Drop names declared inside a block once it ends."""

    return [({name: state[name] for name in outer}, control) for state, control in outcomes]


def condition(cond: Cond, state: dict) -> list:
    """Return (state, value) pairs for evaluating `cond`."""

    if not cond.takes:
        return [(state, True), (state, False)]
    results = []
    guards = [True, False] if cond.guarded else [True]
    for guard in guards:
        if not guard:
            results.append((state, False))
            continue
        moved = use(state, cond.takes, move=True)
        results += [(moved, True), (moved, False)]
    return results


def run_body(body: list, state: dict, budget: list) -> list:
    """One loop iteration: ("next" | "exit" | "return", state)."""

    results = []
    for after, control in scoped(explore(body, state, budget), state):
        if control == "return":
            results.append(("return", after))
        elif control == "break":
            results.append(("exit", after))
        else:
            results.append(("next", after))
    return results


def step(statement, state: dict, budget: list) -> list:
    if isinstance(statement, Use):
        if statement.kind == "borrow":
            return [(use(state, statement.name, move=False), "")]
        moved = use(state, statement.name, move=True)
        if statement.kind == "rebind":
            moved = dict(moved, **{statement.new: True})
        return [(moved, "")]
    if isinstance(statement, Wrap):
        return [(dict(use(state, statement.name, move=True), **{statement.new: True}), "")]
    if isinstance(statement, Unwrap):
        return [(use(state, statement.name, move=statement.move), "")]
    if isinstance(statement, Return):
        return [(state, "return")]
    if isinstance(statement, Jump):
        return [(state, statement.kind)]
    if isinstance(statement, If):
        outcomes = []
        for after, value in condition(statement.cond, state):
            branch = statement.then if value else (statement.other or [])
            outcomes += scoped(explore(branch, after, budget), after)
        return outcomes
    outcomes = []
    if isinstance(statement, For):
        frontier = [(state, 0)]
        while frontier:
            current, count = frontier.pop()
            if count >= statement.count:
                outcomes.append((current, ""))
                continue
            for kind, after in run_body(statement.body, current, budget):
                if kind == "return":
                    outcomes.append((after, "return"))
                elif kind == "exit":
                    outcomes.append((after, ""))
                else:
                    frontier.append((after, count + 1))
        return outcomes
    # While: the counter is exact (it is incremented first, so `continue`
    # cannot skip it), `takes` is unknown, `&&` short-circuits.
    frontier = [(state, 0)]
    while frontier:
        current, count = frontier.pop()
        if count >= statement.limit:
            outcomes.append((current, ""))
            continue
        if statement.takes:
            current = use(current, statement.takes, move=True)
            outcomes.append((current, ""))
        for kind, after in run_body(statement.body, current, budget):
            if kind == "return":
                outcomes.append((after, "return"))
            elif kind == "exit":
                outcomes.append((after, ""))
            else:
                frontier.append((after, count + 1))
    return outcomes


def oracle(statements: list) -> bool | None:
    """True if no path uses a moved token; None if there are too many paths."""

    try:
        explore(statements, {"tok0": True, "tok1": True}, [0])
    except Violation:
        return False
    except TooManyPaths:
        return None
    return True


# --- checker ------------------------------------------------------------------


def check(source: str) -> tuple[str, str]:
    """Return ("ok" | code | "crash", detail)."""

    with tempfile.TemporaryDirectory(prefix="koschei-affine-fuzz-") as directory:
        path = Path(directory, "main.ks")
        path.write_text(source, encoding="utf-8")
        out, err = io.StringIO(), io.StringIO()
        try:
            with redirect_stdout(out), redirect_stderr(err):
                status = ks_main(["--lang", "en", "check", str(path)])
        except SystemExit as exit_:
            status = exit_.code
        except Exception as error:  # noqa: BLE001 - a crash is a finding
            return "crash", repr(error)
        text = out.getvalue() + err.getvalue()
        if status == 0:
            return "ok", ""
        found = re.search(r"\bKS\d{4}\b", text)
        return (found.group(0), text[:300]) if found else ("crash", text[:300])


def main() -> int:
    if len(sys.argv) != 3:
        print(__doc__)
        return 2
    seed, count = int(sys.argv[1]), int(sys.argv[2])
    tally = {"safe_accepted": 0, "unsafe_rejected": 0, "conservative": 0, "skipped": 0}
    findings = []
    for index in range(count):
        rng = random.Random(seed * 1_000_003 + index)
        statements = Gen(rng).block(rng.randint(2, 4))
        source = program(statements)
        verdict = oracle(statements)
        if verdict is None:
            tally["skipped"] += 1
            continue
        result, detail = check(source)
        if result == "crash":
            findings.append(("crash", source, detail))
        elif result == "ok" and not verdict:
            findings.append(("unsound", source, "accepted, but a path uses a moved token"))
        elif result == "ok":
            tally["safe_accepted"] += 1
        elif not verdict:
            tally["unsafe_rejected"] += 1
        else:
            tally["conservative"] += 1
    print(f"affine_fuzz seed={seed} count={count} " + " ".join(f"{k}={v}" for k, v in tally.items()))
    order = {"unsound": 0, "crash": 1}
    findings.sort(key=lambda finding: order[finding[0]])
    kinds = {kind: sum(1 for f in findings if f[0] == kind) for kind in order}
    if findings:
        print(" ".join(f"{k}={v}" for k, v in kinds.items()))
    for kind, source, detail in findings[:3]:
        print(f"\n=== {kind}: {detail}\n{source}")
    if findings:
        print(f"\n{len(findings)} finding(s)")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
