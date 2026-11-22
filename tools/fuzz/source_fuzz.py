"""Mutation fuzzer for the front end.

Usage: python3 tools/fuzz/source_fuzz.py SEED COUNT [check|run]

Mutates the repository's own .ks programs (deleting, duplicating, swapping
lines; inserting and removing tokens). Every outcome of ks check/run on a mutated program must be every outcome of ks check/run on a mutated program must be
success or a KSxxxx diagnostic. Anything else (internal error, traceback,
hang) is a finding."""
import io, os, random, re, subprocess, sys, tempfile, json, multiprocessing as mp
from contextlib import redirect_stdout, redirect_stderr
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
TOKENS = ["{", "}", "(", ")", "[", "]", ",", ":", ".", "=", "==", "+", "-", "*", "/", "%", "<", ">",
          "&&", "||", "!", "or", "return", "let", "mut", "fn", "if", "else", "while", "for", "in", "match",
          "=>", "struct", "enum", "import", "0", "-1", "9223372036854775807", "\"\"", "\"{x}\"", "true",
          "caps", "Error(\"e\")", "Some(1)", "None", "x", "self", "List<Int>", "Map<String, Int>", "->", "_", "break", "continue", "\n", "'"]

def mutate(text, rng):
    lines = text.split("\n")
    for _ in range(rng.randint(1, 3)):
        op = rng.randrange(7)
        if not lines: lines = [""]
        i = rng.randrange(len(lines))
        if op == 0: lines.pop(i)
        elif op == 1: lines.insert(i, lines[rng.randrange(len(lines))])
        elif op == 2:
            j = rng.randrange(len(lines)); lines[i], lines[j] = lines[j], lines[i]
        elif op == 3 and lines[i]:
            k = rng.randrange(len(lines[i]) + 1); lines[i] = lines[i][:k] + rng.choice(TOKENS) + lines[i][k:]
        elif op == 4 and lines[i]:
            a = rng.randrange(len(lines[i])); b = min(len(lines[i]), a + rng.randint(1, 6)); lines[i] = lines[i][:a] + lines[i][b:]
        elif op == 5:
            lines = lines[: rng.randrange(len(lines) + 1)]
        else:
            # replace an identifier-ish word with a token
            words = list(re.finditer(r"[A-Za-z_][A-Za-z0-9_]*|\d+", lines[i]))
            if words:
                w = rng.choice(words); lines[i] = lines[i][: w.start()] + rng.choice(TOKENS) + lines[i][w.end():]
    return "\n".join(lines)

def run_case(args):
    source, command = args
    from koschei.cli_entry import main
    with tempfile.TemporaryDirectory() as d:
        p = Path(d) / "main.ks"; p.write_text(source)
        out, err = io.StringIO(), io.StringIO()
        try:
            with redirect_stdout(out), redirect_stderr(err):
                code = main([command, str(p)])
        except SystemExit as e:
            code = e.code
        except BaseException as e:
            import traceback
            return ("crash", f"{type(e).__name__}: {e}", traceback.format_exc()[-1500:])
    e = err.getvalue()
    if code not in (0, None) and not re.search(r"KS\d{4}", e) and "KOSCHEI RUNTIME" not in e:
        return ("internal", e.strip()[:600], "")
    if "Compiler error —" in e and not re.search(r"KS\d{4} \[", e):
        return ("internal", e.strip()[:600], "")
    return ("ok", "", "")

def main():
    seed = int(sys.argv[1]); count = int(sys.argv[2]); command = sys.argv[3] if len(sys.argv) > 3 else "check"
    files = [REPO / f for f in subprocess.run(["git", "-C", str(REPO), "ls-files", "*.ks"], capture_output=True, text=True).stdout.split()]
    files = [f for f in files if f.stat().st_size < 6000 and "import" not in f.read_text()]
    rng = random.Random(seed)
    cases = []
    for _ in range(count):
        f = rng.choice(files); cases.append((mutate(f.read_text(), rng), command, f.name))
    findings = {}
    ctx = mp.get_context("fork")
    with ctx.Pool(8, maxtasksperchild=50) as pool:
        handles = [(c, pool.apply_async(run_case, ((c[0], c[1]),))) for c in cases]
        for (src, cmd, name), h in handles:
            try:
                kind, msg, tb = h.get(timeout=20)
            except mp.TimeoutError:
                kind, msg, tb = "hang", "timeout 20s", ""
            if kind != "ok":
                key = (kind, re.sub(r"\d+", "N", msg.splitlines()[0] if msg else "")[:160])
                if key not in findings:
                    findings[key] = (name, src, msg, tb)
    print(f"cases={count} unique_findings={len(findings)}")
    out = Path(os.environ.get("FUZZ_OUT", ".")) / f"findings_{command}_{seed}.json"
    out.write_text(json.dumps([{"kind": k[0], "sig": k[1], "seed_file": v[0], "source": v[1], "msg": v[2], "tb": v[3]} for k, v in findings.items()], indent=1))
    for k in findings: print(k)
    sys.exit(1 if findings else 0)

if __name__ == "__main__":
    main()
