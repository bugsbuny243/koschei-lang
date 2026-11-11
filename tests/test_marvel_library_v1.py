"""Marvel universe Core Library modules against their Python guardians.

``captain_marvel``, ``hela``, ``strange`` and ``wanda`` are written in Koschei.
Each test generates seeded cases, asks the Python guardian for the decision,
and embeds the case in a Koschei program run through ``ks run``. Decisions,
reasons and error causes must agree. Digests are checked against an
independent recomputation of the documented ``secure.digest`` encoding, since
the Koschei layout deliberately differs from the Python one.
"""
from __future__ import annotations

from contextlib import redirect_stderr, redirect_stdout
import hashlib
import io
from pathlib import Path
import random
import tempfile
import unittest

from koschei.captain_marvel_blast_radius_v1 import (
    BlastRadiusError,
    evaluate_propagation_v1,
    issue_blast_radius_budget_v1,
)
from koschei.cli_entry import main as cli_main
from koschei.hela_authority_death_v1 import (
    AuthorityDeathError,
    authority_remains_dead_v1,
    bury_authority_v1,
)
from koschei.strange_future_paths_v1 import (
    FuturePathError,
    FutureStepV1,
    simulate_future_path_v1,
)
from koschei.wanda_reality_integrity_v1 import (
    ZERO,
    RealityIntegrityError,
    commit_reality_v1,
    detect_reality_fork_v1,
    detects_rollback_v1,
    extends_reality_v1,
)

ZERO_DIGEST = "sha3-256:" + "0" * 64


def secure_digest(context: str, parts: list[str]) -> str:
    """Independent model of `secure.digest` (lengths in characters)."""

    encoded = f"koschei.secure.digest/v1\n{len(context)}:{context}"
    for part in parts:
        encoded += f"\n{len(part)}:{part}"
    return "sha3-256:" + hashlib.sha3_256(encoded.encode("utf-8")).hexdigest()


def secure_hash(value: str) -> str:
    return "sha3-256:" + hashlib.sha3_256(value.encode("utf-8")).hexdigest()


def ks(value: str) -> str:
    assert '"' not in value and "\\" not in value and "{" not in value
    return f'"{value}"'


def ks_list(values) -> str:
    return "[" + ", ".join(ks(item) for item in values) + "]"


def raw(digest: str) -> bytes:
    """The Python guardians' 32-byte form of a `secure` digest string."""

    return bytes.fromhex(digest.split(":", 1)[1])


class MarvelLibraryTests(unittest.TestCase):
    def run_program(self, source: str, *, max_steps: int | None = None) -> list[str]:
        temporary = tempfile.TemporaryDirectory(prefix="koschei-marvel-")
        self.addCleanup(temporary.cleanup)
        path = Path(temporary.name) / "main.ks"
        path.write_text(source, encoding="utf-8")
        stdout = io.StringIO()
        with redirect_stdout(stdout), redirect_stderr(io.StringIO()) as errors:
            budget = [] if max_steps is None else ["--max-steps", str(max_steps)]
            code = cli_main(["run", *budget, str(path)])
        self.assertEqual(code, 0, errors.getvalue())
        return stdout.getvalue().splitlines()

    def assert_lines(self, actual: list[str], expected: list[str]) -> None:
        self.assertEqual(len(actual), len(expected))
        for index, (got, want) in enumerate(zip(actual, expected)):
            self.assertEqual(got, want, f"case line {index}")

    # ---- captain_marvel ------------------------------------------------------

    def test_captain_marvel_matches_the_python_guardian(self) -> None:
        rng = random.Random(20261024)
        realities = ["", "A", "B", "C", "Δ", "earth-616"]
        program = [
            "import captain_marvel",
            "",
            "fn show_budget(result: Result<BlastRadiusBudget, Error>) -> String {",
            "    return match result {",
            '        Ok(b) => "budget {b.origin_reality} {b.allowed_destinations} {b.max_hops} {b.max_effects} {b.budget_digest}",',
            '        Err(e) => "error {e}",',
            "    }",
            "}",
            "",
            "fn show_verdict(result: Result<PropagationVerdict, Error>) -> String {",
            "    return match result {",
            '        Ok(v) => "verdict {v.allowed} {v.reason} {v.remaining_hops} {v.remaining_effects} {v.verdict_digest}",',
            '        Err(e) => "error {e}",',
            "    }",
            "}",
            "",
            "fn main() {",
        ]
        expected: list[str] = []
        for case in range(60):
            origin = rng.choice(realities)
            destinations = [rng.choice(realities[1:]) for _ in range(rng.randint(0, 4))]
            if case % 11 == 0:
                destinations.append("")
            max_hops = rng.randint(-1, 3)
            max_effects = rng.randint(-1, 3)
            probes = [
                (rng.choice(realities[1:]), rng.randint(-1, 4), rng.randint(-1, 4))
                for _ in range(rng.randint(1, 4))
            ]
            program.append(
                f"    let r{case} = captain_marvel.issue_budget({ks(origin)}, "
                f"{ks_list(destinations)}, {max_hops}, {max_effects})"
            )
            program.append(f"    println(show_budget(r{case}))")
            try:
                budget = issue_blast_radius_budget_v1(
                    origin_reality=origin,
                    allowed_destinations=frozenset(destinations),
                    max_hops=max_hops,
                    max_effects=max_effects,
                )
            except BlastRadiusError as error:
                expected.append(f"error captain_marvel.issue_budget: {error}")
                continue
            canonical = sorted(set(destinations))
            budget_digest = secure_digest(
                "koschei.marvel.captain-marvel.budget/v1",
                [origin, str(max_hops), str(max_effects), *canonical],
            )
            expected.append(
                f"budget {origin} {ks_list(canonical)} {max_hops} {max_effects} {budget_digest}"
            )
            # Only budgets the guardian issued are evaluated. A Koschei budget
            # that failed instead ends `main` here, so the output comes up short.
            program.append(f"    let b{case} = r{case} or return")
            for destination, hops, effects in probes:
                program.append(
                    f"    println(show_verdict(captain_marvel.evaluate(b{case}, "
                    f"{ks(destination)}, {hops}, {effects})))"
                )
                try:
                    verdict = evaluate_propagation_v1(
                        budget, destination=destination, hops_used=hops, effects_used=effects
                    )
                except BlastRadiusError as error:
                    expected.append(f"error captain_marvel.evaluate: {error}")
                    continue
                digest = secure_digest(
                    "koschei.marvel.captain-marvel.verdict/v1",
                    [
                        budget_digest,
                        destination,
                        str(hops),
                        str(effects),
                        verdict.reason,
                        "1" if verdict.allowed else "0",
                    ],
                )
                expected.append(
                    f"verdict {'true' if verdict.allowed else 'false'} {verdict.reason} "
                    f"{verdict.remaining_hops} {verdict.remaining_effects} {digest}"
                )
        program.append("}")
        self.assert_lines(self.run_program("\n".join(program) + "\n"), expected)

    def test_captain_marvel_rejects_edited_or_hand_built_budgets(self) -> None:
        source = """
import captain_marvel

fn show(result: Result<PropagationVerdict, Error>) -> String {
    return match result {
        Ok(v) => "allowed={v.allowed} {v.reason}",
        Err(e) => "{e}",
    }
}

fn main() {
    let budget = captain_marvel.issue_budget("A", ["C", "B"], 2, 2) or return
    println(show(captain_marvel.evaluate(budget, "B", 0, 0)))
    let mut widened = budget
    widened.allowed_destinations = ["B", "C", "Z"]
    println(show(captain_marvel.evaluate(widened, "Z", 0, 0)))
    let mut raised = budget
    raised.max_hops = 99
    println(show(captain_marvel.evaluate(raised, "B", 50, 0)))
    let unsorted = BlastRadiusBudget { origin_reality: "A", allowed_destinations: ["C", "B"], max_hops: 2, max_effects: 2, budget_digest: budget.budget_digest }
    println(show(captain_marvel.evaluate(unsorted, "B", 0, 0)))
    println("{captain_marvel.is_canonical_budget(budget)} {captain_marvel.is_canonical_budget(widened)}")
    println(budget.allowed_destinations)
}
"""
        rejected = "captain_marvel.evaluate: canonical budget required"
        self.assertEqual(
            self.run_program(source),
            [
                "allowed=true within-blast-radius",
                rejected,
                rejected,
                rejected,
                "true false",
                '["B", "C"]',
            ],
        )

    # ---- hela ----------------------------------------------------------------

    def test_hela_matches_the_python_guardian(self) -> None:
        rng = random.Random(616)
        labels = ["principal-a", "principal-b", "reality", "cause"]
        authorities = ["", "network:egress", "process:spawn"]
        messages = {
            "principal_digest must be exactly 32 bytes": "principal_digest must be a sha3-256 digest",
            "reality_digest must be exactly 32 bytes": "reality_digest must be a sha3-256 digest",
            "cause_digest must be exactly 32 bytes": "cause_digest must be a sha3-256 digest",
            "previous_tombstone must be exactly 32 bytes": "previous_tombstone must be a sha3-256 digest",
            "invalid authority/death epoch": "invalid authority/death epoch",
        }

        def pick_digest() -> tuple[str, str | None]:
            """(Koschei expression, digest string or None for a malformed one)."""

            roll = rng.random()
            if roll < 0.1:
                return ks("junk"), None
            if roll < 0.2:
                return "secure.zero_digest()", ZERO_DIGEST
            label = rng.choice(labels)
            return f"(secure.hash({ks(label)}) or \"\")", secure_hash(label)

        program = [
            "import hela",
            "import secure",
            "",
            "fn show(result: Result<AuthorityTombstone, Error>) -> String {",
            "    return match result {",
            '        Ok(t) => "tombstone {t.authority_id} {t.death_epoch} {t.tombstone_digest}",',
            '        Err(e) => "error {e}",',
            "    }",
            "}",
            "",
            "fn main() {",
        ]
        expected: list[str] = []
        for case in range(50):
            fields = [pick_digest() for _ in range(4)]
            authority = rng.choice(authorities)
            epoch = rng.randint(-1, 4)
            (p_src, p), (r_src, r), (c_src, c), (prev_src, prev) = fields
            program.append(
                f"    let t{case} = hela.bury({p_src}, {ks(authority)}, {epoch}, "
                f"{r_src}, {c_src}, {prev_src})"
            )
            program.append(f"    println(show(t{case}))")
            to_bytes = lambda digest: b"junk" if digest is None else raw(digest)  # noqa: E731
            try:
                tombstone = bury_authority_v1(
                    principal_digest=to_bytes(p),
                    authority_id=authority,
                    death_epoch=epoch,
                    reality_digest=to_bytes(r),
                    cause_digest=to_bytes(c),
                    previous_tombstone=to_bytes(prev),
                )
            except AuthorityDeathError as error:
                expected.append(f"error hela.bury: {messages[str(error)]}")
                continue
            digest = secure_digest(
                "koschei.marvel.hela.tombstone/v1", [p, authority, str(epoch), r, c, prev]
            )
            expected.append(f"tombstone {authority} {epoch} {digest}")
            program.append(f"    let b{case} = t{case} or return")
            for _ in range(4):
                q_src, q = pick_digest()
                q_authority = rng.choice(authorities)
                q_epoch = rng.randint(-1, 6)
                arguments = f"b{case}, {q_src}, {ks(q_authority)}, {q_epoch}"
                program.append(
                    f'    println("dead {{hela.remains_dead({arguments})}} '
                    f'{{hela.is_resurrection_attempt({arguments})}}")'
                )
                dead = authority_remains_dead_v1(
                    tombstone,
                    principal_digest=to_bytes(q),
                    authority_id=q_authority,
                    candidate_epoch=q_epoch,
                )
                flag = "true" if dead else "false"
                expected.append(f"dead {flag} {flag}")
        program.append("}")
        self.assert_lines(self.run_program("\n".join(program) + "\n"), expected)

    def test_hela_treats_an_edited_tombstone_as_dead(self) -> None:
        source = """
import hela
import secure

fn main() {
    let p = secure.hash("principal") or return
    let r = secure.hash("reality") or return
    let c = secure.hash("cause") or return
    let tombstone = hela.bury(p, "network:egress", 8, r, c, secure.zero_digest()) or return
    println("{hela.remains_dead(tombstone, p, "network:egress", 50)} {hela.remains_dead(tombstone, p, "network:egress", 7)}")
    let mut postponed = tombstone
    postponed.death_epoch = 100
    println("{hela.is_canonical(tombstone)} {hela.is_canonical(postponed)} {hela.remains_dead(postponed, p, "network:egress", 50)}")
    let other = secure.hash("someone-else") or return
    println(hela.remains_dead(tombstone, other, "network:egress", 50))
}
"""
        self.assertEqual(
            self.run_program(source), ["true false", "true false true", "false"]
        )

    # ---- strange -------------------------------------------------------------

    def test_strange_matches_the_python_guardian(self) -> None:
        rng = random.Random(1602)
        effects = ["", "read", "write", "net"]
        targets = ["", "disk", "socket"]
        names = ["disk", "net", "env"]
        program = [
            "import strange",
            "",
            "fn show(result: Result<FutureVerdict, Error>) -> String {",
            "    return match result {",
            '        Ok(v) => "{v.safe} {v.first_violation} {v.reason} {v.path_digest}",',
            '        Err(e) => "error {e}",',
            "    }",
            "}",
            "",
            "fn main() {",
        ]
        expected: list[str] = []
        for case in range(80):
            authority = [n for n in names if rng.random() < 0.6]
            steps: list[FutureStepV1] = []
            for _ in range(rng.randint(0, 5)):
                before = list(authority) if rng.random() < 0.8 else [n for n in names if rng.random() < 0.5]
                after = [n for n in before if rng.random() < 0.7]
                if rng.random() < 0.15:
                    after.append(rng.choice(names))
                if rng.random() < 0.3:
                    before = before + before[:1]
                steps.append(
                    FutureStepV1(
                        effect=rng.choice(effects[1:]) if rng.random() < 0.9 else "",
                        target=rng.choice(targets[1:]) if rng.random() < 0.9 else "",
                        authority_before=tuple(before),
                        authority_after=tuple(after),
                    )
                )
                authority = after
            max_steps = rng.randint(0, 5)
            forbidden = [e for e in effects[1:] if rng.random() < 0.2]
            rendered = ", ".join(
                "FutureStep { "
                f"effect: {ks(s.effect)}, target: {ks(s.target)}, "
                f"authority_before: {ks_list(s.authority_before)}, "
                f"authority_after: {ks_list(s.authority_after)}"
                " }"
                for s in steps
            )
            program.append(f"    let steps{case}: List<FutureStep> = [{rendered}]")
            program.append(
                f"    println(show(strange.simulate(steps{case}, {max_steps}, {ks_list(forbidden)})))"
            )
            python_steps = tuple(
                FutureStepV1(
                    s.effect, s.target, frozenset(s.authority_before), frozenset(s.authority_after)
                )
                for s in steps
            )
            try:
                verdict = simulate_future_path_v1(
                    python_steps, max_steps=max_steps, forbidden_effects=frozenset(forbidden)
                )
            except FuturePathError as error:
                expected.append(f"error strange.simulate: {error}")
                continue
            last = len(steps) - 1 if verdict.first_violation is None else verdict.first_violation
            parts: list[str] = []
            for index, step in enumerate(steps[: last + 1]):
                if index == verdict.first_violation and verdict.reason == "implicit effect/target":
                    break
                before = sorted(set(step.authority_before))
                after = sorted(set(step.authority_after))
                parts += [str(index), step.effect, step.target, str(len(before)), *before]
                parts += [str(len(after)), *after]
            digest = secure_digest("koschei.marvel.strange.path/v1", parts)
            violation = "None" if verdict.first_violation is None else f"Some({verdict.first_violation})"
            expected.append(
                f"{'true' if verdict.safe else 'false'} {violation} {verdict.reason} {digest}"
            )
        program.append("}")
        self.assert_lines(self.run_program("\n".join(program) + "\n"), expected)

    # ---- wanda ---------------------------------------------------------------

    def test_wanda_matches_the_python_guardian(self) -> None:
        rng = random.Random(838)
        realities = ["", "earth-616", "earth-838"]
        labels = ["state-0", "state-1", "authority"]
        messages = {
            "invalid reality identity/epoch": "invalid reality identity/epoch",
            "state_digest must be exactly 32 bytes": "state_digest must be a sha3-256 digest",
            "authority_digest must be exactly 32 bytes": "authority_digest must be a sha3-256 digest",
            "previous_commitment must be exactly 32 bytes": "previous_commitment must be a sha3-256 digest",
        }
        program = [
            "import secure",
            "import wanda",
            "",
            "fn main() {",
        ]
        expected: list[str] = []
        python_commitments: list[object] = []
        koschei_names: list[str] = []
        for case in range(24):
            reality = rng.choice(realities[1:]) if rng.random() < 0.95 else ""
            epoch = rng.randint(0, 3) if rng.random() < 0.95 else -1
            state_label = rng.choice(labels)
            authority_label = rng.choice(labels)
            state_src = f"(secure.hash({ks(state_label)}) or \"\")"
            authority_src = f"(secure.hash({ks(authority_label)}) or \"\")"
            state, authority = raw(secure_hash(state_label)), raw(secure_hash(authority_label))
            if rng.random() < 0.08:
                state_src, state = ks("junk"), b"junk"
            roll = rng.random()
            if python_commitments and roll < 0.6:
                parent = rng.randrange(len(python_commitments))
                previous_src = f"c{koschei_names[parent]}.commitment_digest"
                previous = python_commitments[parent].commitment_digest
                # Mostly a real next epoch of the parent, sometimes a skip or
                # another reality.
                if rng.random() < 0.7:
                    epoch = python_commitments[parent].epoch + 1
                if rng.random() < 0.8:
                    reality = python_commitments[parent].reality_id
            elif roll < 0.95:
                previous_src, previous = "secure.zero_digest()", ZERO
            else:
                previous_src, previous = ks("junk"), b"junk"
            try:
                commitment = commit_reality_v1(
                    reality_id=reality,
                    epoch=epoch,
                    state_digest=state,
                    authority_digest=authority,
                    previous_commitment=previous,
                )
            except RealityIntegrityError as error:
                program.append(
                    f"    let e{case} = wanda.commit({ks(reality)}, {epoch}, {state_src}, "
                    f"{authority_src}, {previous_src})"
                )
                program.append(
                    f'    let m{case} = match e{case} {{\n        Ok(_) => "accepted",\n'
                    f'        Err(error) => "{{error}}",\n    }}'
                )
                program.append(f"    println(m{case})")
                expected.append(f"wanda.commit: {messages[str(error)]}")
                continue
            program.append(
                f"    let c{case} = wanda.commit({ks(reality)}, {epoch}, {state_src}, "
                f"{authority_src}, {previous_src}) or return"
            )
            python_commitments.append(commitment)
            koschei_names.append(str(case))
        pairs = [
            (left, right)
            for left in range(len(python_commitments))
            for right in range(len(python_commitments))
        ]
        for left, right in rng.sample(pairs, min(len(pairs), 160)):
                a, b = python_commitments[left], python_commitments[right]
                ka, kb = f"c{koschei_names[left]}", f"c{koschei_names[right]}"
                program.append(
                    f'    println("{{wanda.extends({ka}, {kb})}} {{wanda.detects_fork({ka}, {kb})}} '
                    f'{{wanda.detects_rollback({ka}, {kb})}}")'
                )
                flags = (
                    extends_reality_v1(a, b),
                    detect_reality_fork_v1(a, b),
                    detects_rollback_v1(a, b),
                )
                expected.append(" ".join("true" if flag else "false" for flag in flags))
        program.append("}")
        self.assertGreater(len(python_commitments), 10)
        self.assertIn("true false false", expected)
        # Every check re-derives both commitments (fail closed on edits), so
        # the matrix needs more than the default `ks run` step budget.
        output = self.run_program("\n".join(program) + "\n", max_steps=10_000_000)
        self.assert_lines(output, expected)

    def test_wanda_fails_closed_on_edited_commitments(self) -> None:
        source = """
import secure
import wanda

fn main() {
    let state = secure.hash("state") or return
    let authority = secure.hash("authority") or return
    let genesis = wanda.commit("earth-616", 0, state, authority, secure.zero_digest()) or return
    let next = wanda.commit("earth-616", 1, state, authority, genesis.commitment_digest) or return
    println("{wanda.extends(genesis, next)} {wanda.detects_fork(genesis, next)} {wanda.detects_rollback(next, genesis)}")
    let mut rewritten = next
    rewritten.state_digest = authority
    println("{wanda.is_canonical(rewritten)} {wanda.extends(genesis, rewritten)} {wanda.detects_fork(next, rewritten)} {wanda.detects_rollback(genesis, rewritten)}")
    println(genesis.commitment_digest)
}
"""
        genesis = secure_digest(
            "koschei.marvel.wanda.commitment/v1",
            ["earth-616", "0", secure_hash("state"), secure_hash("authority"), ZERO_DIGEST],
        )
        self.assertEqual(
            self.run_program(source),
            ["true false true", "false false true true", genesis],
        )


if __name__ == "__main__":
    unittest.main()
