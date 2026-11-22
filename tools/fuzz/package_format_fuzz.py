"""Structure-aware fuzz of koschei.packages.lock.json and registry index JSON.

Usage: python3 tools/fuzz/package_format_fuzz.py SEED COUNT
Only PackageError may come out; any other exception is a finding.
"""
import json, random, sys, tempfile, traceback, copy
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from koschei.packages_v1 import PackageError, load_lock
from koschei.registry_v1 import validate_index
rng = random.Random(int(sys.argv[1]))
VALUES = [None, True, 0, -1, 1.5, "", "x", "a"*64, [], [[]], [{}], {}, {"a": []}, ["disk"], ["nope"], [1], {"x": 1}]
def paths(o, p=()):
    yield p
    if isinstance(o, dict):
        for k, v in o.items(): yield from paths(v, p + (k,))
    elif isinstance(o, list):
        for i, v in enumerate(o): yield from paths(v, p + (i,))
def setp(o, p, v):
    if not p: return v
    cur = o
    for k in p[:-1]: cur = cur[k]
    cur[p[-1]] = v
    return o
lock = {"schema": "koschei.packages-lock/v1", "packages": {"hexfmt": {"version": "1.2.0", "entry": "src/lib.ks", "source": {"path": "../hexfmt"}, "digest": "a"*64, "surface": [], "dependencies": []}}}
index = {"schema": "koschei.registry-index/v1", "name": "hexfmt", "versions": [{"version": "1.2.0", "digest": "a"*64, "archive_sha256": "b"*64, "surface": [], "dependencies": {}, "yanked": False, "published": "x"}]}
uniq = {}
d = Path(tempfile.mkdtemp())
for n in range(int(sys.argv[2])):
    which = rng.randrange(2)
    doc = copy.deepcopy(lock if which == 0 else index)
    for _ in range(rng.randint(1, 3)):
        ps = list(paths(doc)); doc = setp(doc, rng.choice(ps), copy.deepcopy(rng.choice(VALUES)))
    try:
        if which == 0:
            (d / "koschei.packages.lock.json").write_text(json.dumps(doc)); load_lock(d)
        else:
            validate_index(doc, "hexfmt")
    except PackageError:
        pass
    except Exception as e:
        uniq.setdefault((which, type(e).__name__, str(e)[:80]), (json.dumps(doc)[:300], traceback.format_exc()[-500:]))
print("unique", len(uniq))
for k, (doc, tb) in list(uniq.items())[:8]: print(k); print(doc); print(tb)
sys.exit(1 if uniq else 0)
