"""Morag and Xandar: admission by support window and by known advisories.

Both modules are written in Koschei. Seeded random cases are decided by an
independent Python model of the documented rules and embedded in a Koschei
program; `ks run` must print the same decisions, reasons and digests, and the
MIR-Go binary must print the same bytes.
"""
from __future__ import annotations

from contextlib import redirect_stderr, redirect_stdout
import hashlib
import io
from pathlib import Path
import random
import shutil
import subprocess
import tempfile
import unittest

from koschei.cli_entry import main as cli_main

GO = shutil.which("go")
HEX = set("0123456789abcdef")


def secure_hash(value: str) -> str:
    return "sha3-256:" + hashlib.sha3_256(value.encode("utf-8")).hexdigest()


def secure_digest(context: str, parts: list[str]) -> str:
    encoded = f"koschei.secure.digest/v1\n{len(context)}:{context}"
    for part in parts:
        encoded += f"\n{len(part)}:{part}"
    return "sha3-256:" + hashlib.sha3_256(encoded.encode("utf-8")).hexdigest()


def is_digest(value: str) -> bool:
    pieces = value.split(":")
    return (
        len(pieces) == 2
        and pieces[0] == "sha3-256"
        and len(pieces[1]) == 64
        and set(pieces[1]) <= HEX
    )


def ks(value: str) -> str:
    assert '"' not in value and "\\" not in value and "{" not in value
    return f'"{value}"'


def ks_list(values) -> str:
    return "[" + ", ".join(ks(item) for item in values) + "]"


def flag(value: bool) -> str:
    return "true" if value else "false"


# ---- independent models of the documented rules ----------------------------


def xandar_feed_digest(advisories: list[tuple[str, list[str]]]) -> str:
    parts = [str(len(advisories))]
    for advisory_id in sorted({item[0] for item in advisories}):
        for candidate, affected in advisories:
            if candidate == advisory_id:
                canonical = sorted(set(affected))
                parts += [advisory_id, str(len(canonical)), *canonical]
    return secure_digest("koschei.marvel.xandar.feed/v1", parts)


def xandar_check(identity: str, advisories: list[tuple[str, list[str]]]):
    feed = xandar_feed_digest(advisories)
    matched: list[str] = []
    if not is_digest(identity):
        admitted, reason = False, "identity-is-not-a-digest"
    elif (
        any(not advisory_id or not affected for advisory_id, affected in advisories)
        or any(not is_digest(item) for _, affected in advisories for item in affected)
        or len({item[0] for item in advisories}) != len(advisories)
    ):
        admitted, reason = False, "advisory-feed-is-malformed"
    else:
        matched = sorted({advisory_id for advisory_id, affected in advisories if identity in affected})
        admitted = not matched
        reason = "no-known-advisory" if admitted else "known-vulnerable"
    digest = secure_digest(
        "koschei.marvel.xandar.verdict/v1",
        [identity, feed, reason, "1" if admitted else "0", *matched],
    )
    return admitted, reason, matched, feed, digest


def morag_check(identity, today, windows, backports):
    def verdict(admitted, reason, maintainer="", until=-1):
        digest = secure_digest(
            "koschei.marvel.morag.verdict/v1",
            [identity, str(today), reason, "1" if admitted else "0", maintainer, str(until)],
        )
        return admitted, reason, maintainer, until, digest

    if not is_digest(identity):
        return verdict(False, "identity-is-not-a-digest")
    found = []
    for window in windows:
        if window[0] == identity and window[1] and window[2] >= 0 and window not in found:
            found.append(window)
    if not found:
        return verdict(False, "support-unknown")
    if len(found) > 1:
        return verdict(False, "conflicting-support-windows")
    _, maintainer, until = found[0]
    if today <= until:
        return verdict(True, "within-support", maintainer, until)
    best_maintainer, best_until = "", -1
    for candidate, name, last in backports:
        if candidate == identity and name and today <= last:
            if last > best_until or (last == best_until and name < best_maintainer):
                best_maintainer, best_until = name, last
    if best_until >= 0:
        return verdict(True, "maintainer-backport", best_maintainer, best_until)
    return verdict(False, "support-expired", maintainer, until)


class MoragXandarTests(unittest.TestCase):
    def write(self, source: str) -> Path:
        temporary = tempfile.TemporaryDirectory(prefix="koschei-morag-xandar-")
        self.addCleanup(temporary.cleanup)
        path = Path(temporary.name) / "main.ks"
        path.write_text(source, encoding="utf-8")
        return path

    def ks_run(self, path: Path) -> str:
        stdout = io.StringIO()
        with redirect_stdout(stdout), redirect_stderr(io.StringIO()) as errors:
            code = cli_main(["run", str(path)])
        self.assertEqual(code, 0, errors.getvalue())
        return stdout.getvalue()

    def assert_native_agrees(self, path: Path, expected: str) -> None:
        if GO is None:
            return
        binary = path.parent / "app"
        with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()) as errors:
            self.assertEqual(cli_main(["build", str(path), "-o", str(binary)]), 0, errors.getvalue())
        completed = subprocess.run([str(binary)], capture_output=True, timeout=120, check=False)
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertEqual(completed.stdout.decode("utf-8"), expected)

    def test_xandar_matches_the_model(self) -> None:
        rng = random.Random(109618)
        artifacts = [secure_hash(f"artifact-{index}") for index in range(5)]
        labels = ["php-8.1.2", "8.5.12", ""]
        ids = ["CVE-2026-109618", "CVE-2026-109619", "GHSA-w8hw", "GHSA-6wmf", ""]
        lines = ["import xandar", "", "fn main() {"]
        expected: list[str] = []
        for case in range(50):
            feed = []
            for _ in range(rng.randint(0, 4)):
                affected = [rng.choice(artifacts) for _ in range(rng.randint(0, 3))]
                if rng.random() < 0.08:
                    affected.append(rng.choice(labels[:2]))
                feed.append((rng.choice(ids) if rng.random() < 0.9 else ids[0], affected))
            identity = rng.choice(artifacts) if rng.random() < 0.85 else rng.choice(labels)
            rendered = ", ".join(
                f"SecurityAdvisory {{ id: {ks(advisory_id)}, affected: {ks_list(affected)} }}"
                for advisory_id, affected in feed
            )
            lines.append(f"    let feed{case}: List<SecurityAdvisory> = [{rendered}]")
            lines.append(f"    let v{case} = xandar.check({ks(identity)}, feed{case}) or return")
            lines.append(
                f'    println("{{v{case}.admitted}} {{v{case}.reason}} {{v{case}.advisories}} '
                f'{{v{case}.feed_digest}} {{v{case}.verdict_digest}}")'
            )
            admitted, reason, matched, feed_digest, digest = xandar_check(identity, feed)
            expected.append(f"{flag(admitted)} {reason} {ks_list(matched)} {feed_digest} {digest}")
        lines.append("}")
        path = self.write("\n".join(lines) + "\n")
        output = self.ks_run(path)
        self.assertEqual(output.splitlines(), expected)
        reasons = {line.split()[1] for line in expected}
        self.assertEqual(
            reasons,
            {"no-known-advisory", "known-vulnerable", "identity-is-not-a-digest", "advisory-feed-is-malformed"},
        )
        self.assert_native_agrees(path, output)

    def test_xandar_feed_digest_ignores_order(self) -> None:
        a, b = secure_hash("a"), secure_hash("b")
        source = (
            "import xandar\n\nfn main() {\n"
            f'    let one = [SecurityAdvisory {{ id: "X", affected: [{ks(a)}, {ks(b)}] }}, SecurityAdvisory {{ id: "Y", affected: [{ks(b)}] }}]\n'
            f'    let two = [SecurityAdvisory {{ id: "Y", affected: [{ks(b)}, {ks(b)}] }}, SecurityAdvisory {{ id: "X", affected: [{ks(b)}, {ks(a)}] }}]\n'
            '    let first = xandar.feed_digest(one) or "?"\n'
            '    let second = xandar.feed_digest(two) or "?"\n'
            '    println("{first == second}")\n}\n'
        )
        self.assertEqual(self.ks_run(self.write(source)), "true\n")

    def test_morag_matches_the_model(self) -> None:
        rng = random.Random(20251231)
        artifacts = [secure_hash(f"build-{index}") for index in range(4)]
        maintainers = ["php.net", "ondrej", "debian", ""]
        lines = ["import morag", "", "fn main() {"]
        expected: list[str] = []
        for case in range(60):
            today = rng.randint(20000, 20100)
            # Mostly one window per artifact around today, sometimes a repeat
            # (harmless) or a second, different window (a conflict).
            windows = []
            for artifact in artifacts:
                if rng.random() < 0.7:
                    windows.append((artifact, rng.choice(maintainers), today + rng.randint(-60, 60)))
            if windows and rng.random() < 0.2:
                windows.append(windows[0])
            if windows and rng.random() < 0.15:
                first = windows[0]
                windows.append((first[0], first[1], first[2] + 1))
            backports = [
                (rng.choice(artifacts), rng.choice(maintainers), today + rng.randint(-30, 90))
                for _ in range(rng.randint(0, 3))
            ]
            identity = rng.choice(artifacts) if rng.random() < 0.9 else "8.1.2"
            window_items = ", ".join(
                f"SupportWindow {{ identity: {ks(a)}, maintainer: {ks(m)}, until_day: {d} }}"
                for a, m, d in windows
            )
            backport_items = ", ".join(
                f"MaintainerBackport {{ identity: {ks(a)}, maintainer: {ks(m)}, until_day: {d} }}"
                for a, m, d in backports
            )
            lines.append(f"    let windows{case}: List<SupportWindow> = [{window_items}]")
            lines.append(f"    let backports{case}: List<MaintainerBackport> = [{backport_items}]")
            lines.append(
                f"    let v{case} = morag.check({ks(identity)}, {today}, windows{case}, backports{case}) or return"
            )
            lines.append(
                f'    println("{{v{case}.admitted}} {{v{case}.reason}} [{{v{case}.maintainer}}] '
                f'{{v{case}.until_day}} {{v{case}.verdict_digest}}")'
            )
            admitted, reason, maintainer, until, digest = morag_check(identity, today, windows, backports)
            expected.append(f"{flag(admitted)} {reason} [{maintainer}] {until} {digest}")
        lines.append("}")
        path = self.write("\n".join(lines) + "\n")
        output = self.ks_run(path)
        self.assertEqual(output.splitlines(), expected)
        reasons = {line.split()[1] for line in expected}
        self.assertTrue(
            {
                "within-support",
                "maintainer-backport",
                "support-expired",
                "support-unknown",
                "conflicting-support-windows",
            }
            <= reasons,
            reasons,
        )
        self.assert_native_agrees(path, output)

    def test_morag_rejects_a_day_before_the_epoch(self) -> None:
        source = (
            "import morag\n\nfn main() {\n"
            "    let none: List<SupportWindow> = []\n"
            "    let nobody: List<MaintainerBackport> = []\n"
            '    let refused = morag.check("x", -1, none, nobody)\n'
            '    println(match refused {\n        Ok(v) => v.reason,\n        Err(e) => "{e}",\n    })\n}\n'
        )
        self.assertEqual(
            self.ks_run(self.write(source)),
            "morag.check: today must be a day counted from 1970-01-01\n",
        )


if __name__ == "__main__":
    unittest.main()
