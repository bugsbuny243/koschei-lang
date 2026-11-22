"""Differential fuzz: mutated programs that pass `ks check` must give the same
stdout and exit status under `ks run` and as a native `ks build` binary
(or be refused by `ks build` with KS40xx).

Usage: python3 tools/fuzz/native_diff_fuzz.py SEED TARGET   (needs Go)
"""
import random, subprocess, sys, tempfile, json, re, os
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent)); import source_fuzz as fuzz
from concurrent.futures import ThreadPoolExecutor
REPO = fuzz.REPO
files = [REPO / f for f in subprocess.run(["git","-C",str(REPO),"ls-files","*.ks"],capture_output=True,text=True).stdout.split()]
files = [f for f in files if f.stat().st_size < 6000 and "import" not in f.read_text() and "caps" not in f.read_text()]
rng = random.Random(int(sys.argv[1])); target = int(sys.argv[2])
def sh(cmd, cwd, timeout=60):
    try:
        r = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, timeout=timeout)
        return r.returncode, r.stdout, r.stderr
    except subprocess.TimeoutExpired:
        return "timeout", "", ""
def one(src):
    with tempfile.TemporaryDirectory() as d:
        p = Path(d) / "main.ks"; p.write_text(src)
        c = sh(["ks", "check", "main.ks"], d)
        if c[0] != 0: return None
        r = sh(["ks", "run", "main.ks"], d, 30)
        b = sh(["ks", "build", "main.ks", "--output", "bin"], d, 120)
        if b[0] != 0:
            if re.search(r"KS4004|KS40", b[2]): return ("refused", None)
            return ("build_failed", src, r, b)
        n = sh(["./bin"], d, 30)
        same = (r[0] == n[0] and r[1] == n[1]) or (r[0] != 0 and n[0] != 0 and r[1] == n[1])
        return ("same" if same else "diff", src, r, n)
srcs = []
while len(srcs) < target * 4:
    srcs.append(fuzz.mutate(rng.choice(files).read_text(), rng))
res = []
with ThreadPoolExecutor(6) as ex:
    for out in ex.map(one, srcs):
        if out: res.append(out)
from collections import Counter
print(Counter(o[0] for o in res))
bad = [o for o in res if o[0] in ("diff", "build_failed")]
Path(os.environ.get("FUZZ_OUT", ".")) / f"diff_{sys.argv[1]}.json".write_text(json.dumps([{"kind": o[0], "src": o[1], "run": o[2], "native": o[3]} for o in bad], indent=1))
for o in bad[:4]:
    print("----", o[0]); print(o[1][:600]); print("RUN", o[2]); print("NATIVE", o[3])
sys.exit(1 if bad else 0)
