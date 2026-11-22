"""Byte-level fuzz of package archives, locks, manifests and index JSON.

Usage: python3 tools/fuzz/package_bytes_fuzz.py SEED COUNT
Only PackageError or ModuleError may come out.
"""
import json, random, sys, tempfile, io, tarfile, traceback, shutil
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from koschei.packages_v1 import PackageError, load_lock, load_project_packages, parse_dependencies, sync
from koschei.registry_v1 import extract_archive, validate_index, build_archive
from koschei.modules import ModuleError

rng = random.Random(int(sys.argv[1]))
def flip(b: bytes) -> bytes:
    b = bytearray(b)
    for _ in range(rng.randint(1, 8)):
        op = rng.randrange(4)
        if not b: b = bytearray(b"x")
        i = rng.randrange(len(b))
        if op == 0: b[i] = rng.randrange(256)
        elif op == 1: del b[i:i + rng.randint(1, 20)]
        elif op == 2: b[i:i] = bytes(rng.randrange(256) for _ in range(rng.randint(1, 8)))
        else: b[i:i] = rng.choice([b'"', b"{", b"}", b"[", b"]", b",", b"null", b"-1", b"1e999", b"\\u0000", b"../", b"=", b"\n[dependencies]\n"])
    return bytes(b)

findings = []
base = Path(tempfile.mkdtemp())
pkg = base / "hexfmt"; (pkg / "src").mkdir(parents=True)
(pkg / "koschei.toml").write_text('[package]\nname = "hexfmt"\nversion = "1.2.0"\nentry = "src/lib.ks"\n')
(pkg / "src" / "lib.ks").write_text("fn one() -> Int {\n    return 1\n}\n")
archive = build_archive(pkg)
app = base / "app"; (app / "src").mkdir(parents=True)
manifest = b'[package]\nname = "app"\nversion = "0.1.0"\n\n[dependencies]\nhexfmt = { path = "../hexfmt" }\n'
(app / "koschei.toml").write_bytes(manifest)
(app / "src" / "main.ks").write_text("import hexfmt\n\nfn main() {\n    println(hexfmt.one())\n}\n")
sync(app)
lock = (app / "koschei.packages.lock.json").read_bytes()
index = json.dumps({"schema": "koschei.registry-index/v1", "name": "hexfmt", "versions": [{"version": "1.2.0", "digest": "a"*64, "archive_sha256": "b"*64, "surface": [], "dependencies": {}, "yanked": False, "published": "x"}]}).encode()

for n in range(int(sys.argv[2])):
    target = rng.randrange(4)
    try:
        if target == 0:
            with tempfile.TemporaryDirectory() as d: extract_archive(flip(archive), Path(d))
        elif target == 1:
            (app / "koschei.packages.lock.json").write_bytes(flip(lock)); load_lock(app)
        elif target == 2:
            (app / "koschei.toml").write_bytes(flip(manifest)); load_project_packages(app)
        else:
            try: payload = json.loads(flip(index))
            except ValueError: continue
            validate_index(payload, "hexfmt")
    except (PackageError, ModuleError):
        pass
    except Exception as e:
        findings.append((target, f"{type(e).__name__}: {e}", traceback.format_exc()[-600:]))
(app / "koschei.toml").write_bytes(manifest); (app / "koschei.packages.lock.json").write_bytes(lock)
uniq = {}
for t, m, tb in findings: uniq.setdefault((t, m.split(":")[0]), (m, tb))
print("findings", len(findings), "unique", len(uniq))
for k, (m, tb) in uniq.items(): print(k, m[:200]); print(tb)
shutil.rmtree(base)
sys.exit(1 if uniq else 0)
