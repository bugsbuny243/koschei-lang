"""odin, sokovia and quicksilver: capability derivation, separation of
privilege and velocity limits in the Koschei Core Library.

Each module is checked against an independent Python model over every case
of a small domain (every pair of right subsets, every approval pattern of
four people, seeded spend histories), and the security invariant of each is
asserted on the Koschei answers themselves: an allowed grant holds the right
at every link and no link is revoked or expired; an approved action has
`threshold` distinct eligible approvers other than the requester for exactly
that action; an allowed spend keeps the window within its limit.
"""
from __future__ import annotations

from contextlib import redirect_stderr, redirect_stdout
from dataclasses import dataclass
import hashlib
import hmac
import io
from itertools import chain as iter_chain, combinations, product
import os
from pathlib import Path
import random
import shutil
import subprocess
import sys
import tempfile
import unittest

from koschei.cli_entry import main as cli_main

ROOT = Path(__file__).resolve().parent.parent
GO = shutil.which("go")
ZERO = "sha3-256:" + "0" * 64
INT_MAX = 2**63 - 1
RIGHTS = ("read", "trade", "withdraw")
# The chain check runs every case of this smaller universe; "admin" is asked
# for but never granted.
CHAIN_RIGHTS = ("read", "withdraw")


def secure_digest(context: str, parts: list[str]) -> str:
    """Independent model of `secure.digest` (lengths in characters)."""

    encoded = f"koschei.secure.digest/v1\n{len(context)}:{context}"
    for part in parts:
        encoded += f"\n{len(part)}:{part}"
    return "sha3-256:" + hashlib.sha3_256(encoded.encode("utf-8")).hexdigest()


def ks_list(values) -> str:
    return "[" + ", ".join(f'"{value}"' for value in values) + "]"


def subsets(items):
    return list(iter_chain.from_iterable(combinations(items, size) for size in range(len(items) + 1)))


def run_koschei(test: unittest.TestCase, source: str) -> list[str]:
    with tempfile.TemporaryDirectory(prefix="koschei-guardians-") as directory:
        path = Path(directory) / "main.ks"
        path.write_text(source, encoding="utf-8")
        stdout = io.StringIO()
        with redirect_stdout(stdout), redirect_stderr(io.StringIO()) as errors:
            code = cli_main(["run", "--max-steps", "100000000", str(path)])
        test.assertEqual(code, 0, errors.getvalue())
        return stdout.getvalue().splitlines()


# ---- odin ---------------------------------------------------------------------


@dataclass(frozen=True)
class Grant:
    parent: str
    holder: str
    rights: tuple[str, ...]
    not_after: int
    depth: int

    @property
    def digest(self) -> str:
        parts = [self.parent, self.holder, str(self.not_after), str(self.depth), str(len(self.rights)), *self.rights]
        return secure_digest("koschei.marvel.odin.grant/v1", parts)


def grant(parent: str, holder: str, rights, not_after: int, depth: int) -> Grant:
    return Grant(parent, holder, tuple(sorted(set(rights))), not_after, depth)


def odin_check(chain: list[Grant], right: str, epoch: int, revoked: set[str]):
    if not chain:
        return (False, "empty chain", None)
    previous = None
    holds = False
    for index, link in enumerate(chain):
        if previous is None:
            if link.depth != 0 or link.parent != ZERO:
                return (False, "chain does not start at a root", index)
        else:
            if link.parent != previous.digest or link.depth != previous.depth + 1:
                return (False, "broken chain", index)
            if not set(link.rights) <= set(previous.rights):
                return (False, "widened rights", index)
            if link.not_after > previous.not_after:
                return (False, "outlives its parent", index)
        if link.digest in revoked:
            return (False, "revoked", index)
        if epoch > link.not_after:
            return (False, "expired", index)
        holds = right in link.rights
        previous = link
    if not holds:
        return (False, "right not granted", len(chain) - 1)
    return (True, "allowed", None)


def render(verdict) -> str:
    allowed, reason, link = verdict
    rendered = "None" if link is None else f"Some({link})"
    return f"{str(allowed).lower()} {reason} {rendered}"


ODIN_CASE = '''import odin
import secure

fn case(r0: List<String>, r1: List<String>, na1: Int, right: String, epoch: Int, revoke: Int) -> String {
    let root = odin.issue(secure.zero_digest(), "root", r0, 50, 0) or return "issue failed"
    let child = odin.issue(root.grant_digest, "child", r1, na1, 1) or return "issue failed"
    let mut revoked: List<String> = []
    if revoke == 1 {
        revoked = [root.grant_digest]
    }
    if revoke == 2 {
        revoked = [child.grant_digest]
    }
    let v = odin.check([root, child], right, epoch, revoked)
    return "{v.allowed} {v.reason} {v.failed_link}"
}

fn derived(r0: List<String>, r1: List<String>, na1: Int) -> String {
    let root = odin.root("root", r0, 50) or return "root failed"
    let child = odin.derive(root, "child", r1, na1) or return "refused"
    return "derived {child.depth} {child.rights}"
}
'''


class OdinTests(unittest.TestCase):
    def test_every_two_link_chain_decides_like_the_model_and_never_widens(self) -> None:
        cases = list(
            product(subsets(CHAIN_RIGHTS), subsets(CHAIN_RIGHTS), (40, 60), ("read", "withdraw", "admin"), (10, 45, 55), (0, 1, 2))
        )
        lines: list[str] = []
        for start in range(0, len(cases), 200):
            calls = "\n".join(
                f'    println(case({ks_list(r0)}, {ks_list(r1)}, {na1}, "{right}", {epoch}, {revoke}))'
                for r0, r1, na1, right, epoch, revoke in cases[start : start + 200]
            )
            lines += run_koschei(self, ODIN_CASE + "\nfn main() {\n" + calls + "\n}\n")
        self.assertEqual(len(lines), len(cases))
        allowed_cases = 0
        for line, (r0, r1, na1, right, epoch, revoke) in zip(lines, cases):
            root = grant(ZERO, "root", r0, 50, 0)
            child = grant(root.digest, "child", r1, na1, 1)
            revoked = {None: set(), 1: {root.digest}, 2: {child.digest}}.get(revoke, set())
            expected = odin_check([root, child], right, epoch, revoked)
            with self.subTest(case=(r0, r1, na1, right, epoch, revoke)):
                self.assertEqual(line, render(expected))
            if line.startswith("true"):
                allowed_cases += 1
                # The invariant, on Koschei's own answer.
                self.assertIn(right, r0)
                self.assertIn(right, r1)
                self.assertTrue(set(r1) <= set(r0))
                self.assertLessEqual(epoch, min(50, na1))
                self.assertEqual(revoke, 0)
        self.assertGreater(allowed_cases, 0)

    def test_derive_refuses_every_widening_and_every_longer_life(self) -> None:
        cases = list(product(subsets(RIGHTS), subsets(RIGHTS), (49, 50, 51)))
        calls = "\n".join(
            f"    println(derived({ks_list(r0)}, {ks_list(r1)}, {na1}))" for r0, r1, na1 in cases
        )
        lines = run_koschei(self, ODIN_CASE + "\nfn main() {\n" + calls + "\n}\n")
        for line, (r0, r1, na1) in zip(lines, cases):
            with self.subTest(case=(r0, r1, na1)):
                if set(r1) <= set(r0) and na1 <= 50:
                    self.assertEqual(line, f"derived 1 {ks_list(sorted(set(r1))).replace('\"', chr(34))}")
                else:
                    self.assertEqual(line, "refused")

    def test_revoking_an_ancestor_kills_the_subtree_and_depth_is_bounded(self) -> None:
        source = '''import odin

fn main() {
    let mut chain: List<Grant> = []
    let root = odin.root("root", ["read"], 100) or return
    chain = chain.push(root)
    let mut last = root
    let mut depth = 0
    while depth < 16 {
        let next = odin.derive(last, "h{depth}", ["read"], 100) or return
        chain = chain.push(next)
        last = next
        depth = depth + 1
    }
    println(odin.derive(last, "too-deep", ["read"], 100))
    let fine = odin.check(chain, "read", 1, [])
    println("{fine.allowed} {fine.reason}")
    let mut index = 0
    for link in chain {
        let v = odin.check(chain, "read", 1, [link.grant_digest])
        println("{index} {v.allowed} {v.reason} {v.failed_link}")
        index = index + 1
    }
}
'''
        lines = run_koschei(self, source)
        self.assertEqual(lines[0], "Err(odin.derive: derivation is too deep)")
        self.assertEqual(lines[1], "true allowed")
        for index, line in enumerate(lines[2:]):
            self.assertEqual(line, f"{index} false revoked Some({index})")

    def test_a_hand_built_or_edited_grant_is_refused(self) -> None:
        source = '''import odin
import secure

fn main() {
    let root = odin.root("root", ["read", "trade"], 50) or return
    let child = odin.derive(root, "bot", ["read"], 40) or return
    let edited = Grant { parent: child.parent, holder: child.holder, rights: ["read", "trade", "withdraw"], not_after: 40, depth: 1, grant_digest: child.grant_digest }
    let v1 = odin.check([root, edited], "withdraw", 1, [])
    println("{v1.allowed} {v1.reason} {v1.failed_link}")
    let widened = odin.issue(root.grant_digest, "bot", ["read", "withdraw"], 40, 1) or return
    let v2 = odin.check([root, widened], "withdraw", 1, [])
    println("{v2.allowed} {v2.reason} {v2.failed_link}")
    let longer = odin.issue(root.grant_digest, "bot", ["read"], 90, 1) or return
    let v3 = odin.check([root, longer], "read", 1, [])
    println("{v3.allowed} {v3.reason} {v3.failed_link}")
    let orphan = odin.issue(secure.zero_digest(), "bot", ["read"], 40, 1) or return
    let v4 = odin.check([root, orphan], "read", 1, [])
    println("{v4.allowed} {v4.reason} {v4.failed_link}")
    println(odin.derive(edited, "x", ["read"], 10))
}
'''
        self.assertEqual(
            run_koschei(self, source),
            [
                "false grant is not canonical Some(1)",
                "false widened rights Some(1)",
                "false outlives its parent Some(1)",
                "false broken chain Some(1)",
                "Err(odin.derive: canonical parent required)",
            ],
        )

    def test_seals_bind_every_link_to_the_key(self) -> None:
        key = "k" * 32
        source = f'''import odin

fn main() {{
    let key = "{key}".to_bytes()
    let root = odin.root("root", ["read"], 50) or return
    let child = odin.derive(root, "bot", ["read"], 40) or return
    let seals = [odin.seal(root, key), odin.seal(child, key)]
    println(seals.get(1) or "")
    let ok = odin.check_sealed([root, child], seals, key, "read", 1, [])
    println("{{ok.allowed}} {{ok.reason}}")
    let swapped = [seals.get(1) or "", seals.get(0) or ""]
    let bad = odin.check_sealed([root, child], swapped, key, "read", 1, [])
    println("{{bad.allowed}} {{bad.reason}} {{bad.failed_link}}")
    let other = odin.check_sealed([root, child], seals, "other".to_bytes(), "read", 1, [])
    println("{{other.allowed}} {{other.reason}} {{other.failed_link}}")
    let short = odin.check_sealed([root, child], [seals.get(0) or ""], key, "read", 1, [])
    println("{{short.allowed}} {{short.reason}}")
}}
'''
        lines = run_koschei(self, source)
        root = grant(ZERO, "root", ["read"], 50, 0)
        child = grant(root.digest, "bot", ["read"], 40, 1)
        self.assertEqual(lines[0], hmac.new(key.encode(), child.digest.encode(), hashlib.sha256).hexdigest())
        self.assertEqual(
            lines[1:],
            ["true allowed", "false seal mismatch Some(0)", "false seal mismatch Some(0)", "false one seal per link required"],
        )


# ---- sokovia ------------------------------------------------------------------

ELIGIBLE = ("a", "b", "c")


def sokovia_decide(action: str, requester: str, eligible, threshold: int, approvals):
    approvers = set(eligible)
    possible = len(approvers) - (1 if requester in approvers else 0)
    if threshold < 1 or threshold > possible:
        return "Err(sokovia.decide: threshold must be between 1 and the eligible approvers other than the requester)"
    counted = sorted({who for target, who in approvals if target == action and who != requester and who in approvers})
    rendered = ks_list(counted)
    if len(counted) >= threshold:
        return f"true approved {rendered}"
    return f"false needs {threshold} distinct approvals, has {len(counted)} {rendered}"


SOKOVIA_CASE = '''import sokovia

fn case(requester: String, threshold: Int, approvals: List<Approval>, action: String) -> String {
    let verdict = sokovia.decide(action, requester, ["a", "b", "c"], threshold, approvals) or return "Err(sokovia.decide: threshold must be between 1 and the eligible approvers other than the requester)"
    return "{verdict.approved} {verdict.reason} {verdict.counted}"
}
'''


class SokoviaTests(unittest.TestCase):
    def test_every_approval_pattern_decides_like_the_model(self) -> None:
        action = secure_digest("koschei.marvel.sokovia.action/v1", ["withdraw", "BTC", "500", "cold"])
        other = secure_digest("koschei.marvel.sokovia.action/v1", ["withdraw", "BTC", "500", "attacker"])
        people = ("a", "b", "c", "m")  # m is not eligible
        rng = random.Random(3490)
        cases = []
        for pattern in product((None, "this", "other"), repeat=len(people)):
            approvals = [(action if choice == "this" else other, who) for who, choice in zip(people, pattern) if choice]
            if approvals and rng.random() < 0.3:
                approvals.append(rng.choice(approvals))  # a repeated approval
            for requester in ("a", "x"):
                for threshold in range(0, 5):
                    cases.append((requester, threshold, approvals))
        lines = []
        header = SOKOVIA_CASE + f'\nfn main() {{\n    let action = "{action}"\n    let other = "{other}"\n'
        # Run time grows faster than the size of one function, so the cases go
        # into several modest programs.
        for start in range(0, len(cases), 200):
            chunk = cases[start : start + 200]
            body = "\n".join(
                "    println(case(\"{}\", {}, [{}], action))".format(
                    requester,
                    threshold,
                    ", ".join(
                        "Approval {{ action: {}, approver: \"{}\" }}".format("action" if target == action else "other", who)
                        for target, who in approvals
                    ),
                )
                for requester, threshold, approvals in chunk
            )
            lines += run_koschei(self, header + body + "\n}\n")
        self.assertEqual(len(lines), len(cases))
        approved = 0
        for line, (requester, threshold, approvals) in zip(lines, cases):
            with self.subTest(case=(requester, threshold, approvals)):
                self.assertEqual(line, sokovia_decide(action, requester, ELIGIBLE, threshold, approvals))
            if line.startswith("true"):
                approved += 1
                voters = {who for target, who in approvals if target == action and who in ELIGIBLE and who != requester}
                self.assertGreaterEqual(len(voters), threshold)
        self.assertGreater(approved, 0)

    def test_the_action_digest_names_every_field(self) -> None:
        source = '''import sokovia

fn main() {
    println(sokovia.action("withdraw", ["BTC", "500", "cold"]))
    println(sokovia.action("withdraw", ["BTC", "5", "00cold"]))
    println(sokovia.action("", ["BTC"]))
}
'''
        lines = run_koschei(self, source)
        self.assertEqual(lines[0], 'Ok("{}")'.format(secure_digest("koschei.marvel.sokovia.action/v1", ["withdraw", "BTC", "500", "cold"])))
        self.assertNotEqual(lines[0], lines[1])
        self.assertEqual(lines[2], "Err(sokovia.action: action kind must be explicit)")

    def test_an_unnamed_approver_never_counts(self) -> None:
        source = f'''import sokovia

fn main() {{
    let action = "{ZERO}"
    let votes = [Approval {{ action: action, approver: "" }}, Approval {{ action: action, approver: "b" }}]
    println(sokovia.decide(action, "a", ["a", "", "b"], 2, votes))
    println(sokovia.decide("not-a-digest", "a", ["a", "b"], 1, votes))
    println(sokovia.decide(action, "", ["a", "b"], 1, votes))
}}
'''
        self.assertEqual(
            run_koschei(self, source),
            [
                "Err(sokovia.decide: every eligible approver must be named)",
                "Err(sokovia.decide: action must be a sha3-256 digest)",
                "Err(sokovia.decide: requester must be explicit)",
            ],
        )


# ---- quicksilver ---------------------------------------------------------------


def quicksilver_check(history, now, window, limit, amount):
    if now < 0 or window < 1 or limit < 0 or amount < 0:
        return "Err(quicksilver.check: now must be non-negative, window positive, limit and amount non-negative)"
    for epoch, spent_amount in history:
        if spent_amount < 0:
            return "Err(quicksilver.check: a spend cannot be negative)"
        if epoch < 0 or epoch > now:
            return "Err(quicksilver.check: history holds a spend outside 0..now)"
    spent = sum(value for epoch, value in history if now - epoch < window)
    if spent > limit:
        return f"false window already over its limit {limit} 0"
    remaining = limit - spent
    if amount > remaining:
        return f"false would exceed the window limit {spent} {remaining}"
    return f"true within the window limit {spent} {remaining}"


QUICKSILVER_CASE = '''import quicksilver

fn case(history: List<Spend>, now: Int, window: Int, limit: Int, amount: Int) -> String {
    let v = quicksilver.check(history, now, window, limit, amount) or return "error"
    return "{v.allowed} {v.reason} {v.spent_in_window} {v.remaining}"
}

fn failed(history: List<Spend>, now: Int, window: Int, limit: Int, amount: Int) -> String {
    let checked = quicksilver.check(history, now, window, limit, amount)
    return match checked {
        Ok(v) => "{v.allowed} {v.reason} {v.spent_in_window} {v.remaining}",
        Err(e) => "Err({e})",
    }
}
'''


class QuicksilverTests(unittest.TestCase):
    def test_seeded_histories_decide_like_the_model_and_never_overspend(self) -> None:
        rng = random.Random(1193)
        cases = []
        for _ in range(500):
            now = rng.choice((0, 1, 7, 20, rng.randint(0, 50)))
            history = []
            for _ in range(rng.randint(0, 6)):
                epoch = rng.randint(-2 if rng.random() < 0.05 else 0, now + (3 if rng.random() < 0.05 else 0))
                amount = rng.choice((0, 1, 5, rng.randint(0, 40), INT_MAX, -1 if rng.random() < 0.03 else 2))
                history.append((epoch, amount))
            window = rng.choice((0, 1, 3, 10, INT_MAX))
            limit = rng.choice((0, 10, 30, rng.randint(0, 60), INT_MAX, -1 if rng.random() < 0.03 else 50))
            amount = rng.choice((0, 1, 7, rng.randint(0, 40), INT_MAX))
            cases.append((history, now, window, limit, amount))
        body = "\n".join(
            "    println(failed([{}], {}, {}, {}, {}))".format(
                ", ".join(f"Spend {{ epoch: {epoch}, amount: {value} }}" for epoch, value in history),
                now,
                window,
                limit,
                amount,
            )
            for history, now, window, limit, amount in cases
        )
        rows = body.split("\n")
        lines: list[str] = []
        for start in range(0, len(rows), 200):
            lines += run_koschei(self, QUICKSILVER_CASE + "\nfn main() {\n" + "\n".join(rows[start : start + 200]) + "\n}\n")
        self.assertEqual(len(lines), len(cases))
        allowed = 0
        for line, (history, now, window, limit, amount) in zip(lines, cases):
            with self.subTest(case=(history, now, window, limit, amount)):
                self.assertEqual(line, quicksilver_check(history, now, window, limit, amount))
            if line.startswith("true"):
                allowed += 1
                in_window = sum(value for epoch, value in history if now - epoch < window)
                self.assertLessEqual(in_window + amount, limit)
        self.assertGreater(allowed, 0)


# ---- native ---------------------------------------------------------------------


class GuardianNativeTests(unittest.TestCase):
    @unittest.skipUnless(GO, "Go is not installed")
    def test_binaries_decide_like_ks_run(self) -> None:
        source = '''import odin
import sokovia
import quicksilver

fn main() {
    let root = odin.root("exchange", ["read", "trade", "withdraw"], 100) or return
    let bot = odin.derive(root, "bot", ["read", "trade"], 50) or return
    let viewer = odin.derive(bot, "viewer", ["read"], 40) or return
    let key = "server-key-material-0123456789ab".to_bytes()
    let seals = [odin.seal(root, key), odin.seal(bot, key), odin.seal(viewer, key)]
    let a = odin.check_sealed([root, bot, viewer], seals, key, "read", 10, [])
    let b = odin.check([root, bot, viewer], "read", 10, [bot.grant_digest])
    println("{a.allowed} {a.reason} {b.allowed} {b.reason} {b.failed_link}")
    let action = sokovia.action("withdraw", ["BTC", "500", "cold"]) or return
    let votes = [Approval { action: action, approver: "b" }, Approval { action: action, approver: "b" }, Approval { action: action, approver: "c" }]
    let q = sokovia.decide(action, "a", ["a", "b", "c", "d"], 2, votes) or return
    println("{q.approved} {q.reason} {q.counted}")
    let v = quicksilver.check([Spend { epoch: 9, amount: 9223372036854775807 }, Spend { epoch: 9, amount: 1 }], 10, 5, 9223372036854775807, 1) or return
    println("{v.allowed} {v.reason} {v.spent_in_window} {v.remaining}")
}
'''
        with tempfile.TemporaryDirectory(prefix="koschei-guardians-native-") as directory:
            Path(directory, "main.ks").write_text(source, encoding="utf-8")
            environment = dict(os.environ, PYTHONPATH=str(ROOT))
            build = subprocess.run(
                [sys.executable, "-m", "koschei", "build", "main.ks", "-o", "app"],
                cwd=directory, env=environment, capture_output=True, timeout=300, check=False,
            )
            self.assertEqual(build.returncode, 0, build.stderr.decode())
            native = subprocess.run([str(Path(directory) / "app")], capture_output=True, timeout=60, check=False)
            ran = subprocess.run(
                [sys.executable, "-m", "koschei", "run", "main.ks"],
                cwd=directory, env=environment, capture_output=True, timeout=300, check=False,
            )
        self.assertEqual((native.returncode, native.stderr.decode()), (0, ""))
        self.assertEqual(native.stdout.decode(), ran.stdout.decode())
        self.assertEqual(
            native.stdout.decode().splitlines(),
            [
                "true allowed false revoked Some(1)",
                'true approved ["b", "c"]',
                "false window already over its limit 9223372036854775807 0",
            ],
        )


if __name__ == "__main__":
    unittest.main()
