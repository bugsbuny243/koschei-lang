"""Black-box acceptance tests against a running VM worker (run as root on the VM).

    sudo /opt/koschei-worker/venv/bin/python acceptance.py https://localhost:8443

Talks to the worker over real TLS with the real token; nothing is mocked.
Prints one JSON line per check and exits non-zero on any failure.
"""
import concurrent.futures
import http.client
import json
import ssl
import sys
import time
from pathlib import Path
from urllib.parse import urlsplit

from koschei import playground_remote as remote
from koschei import untrusted

URL = sys.argv[1]
ETC = Path("/etc/koschei-worker")
TOKEN = (ETC / "worker-token").read_text().strip()
CA = str(ETC / "ca-cert.pem")
client = remote.RemoteEvaluator(URL, TOKEN, ca_file=CA)
failures = []


def report(name, ok, detail=""):
    print(json.dumps({"check": name, "ok": bool(ok), "detail": detail}), flush=True)
    if not ok:
        failures.append(name)


def raw(method, path, headers, body=None):
    url = urlsplit(URL)
    context = ssl.create_default_context(cafile=CA)
    connection = http.client.HTTPSConnection(url.hostname, url.port, timeout=300, context=context)
    connection.request(method, path, body=body, headers=headers)
    response = connection.getresponse()
    data = response.read()
    connection.close()
    return response.status, data


client.require_ready()
report("health_authenticated", True)

allowed = client.evaluate('fn main() {\n    println("playground-ok")\n}\n', "run", "en")
report("allowed_program_caps_and_run", allowed["stage"] == "run" and allowed["ran"]
       and allowed["run"]["exit_code"] == 0 and allowed["run"]["stdout"].strip() == "playground-ok",
       allowed.get("run", {}).get("stderr", "")[:200])

for domain, source in (
    ("disk", 'fn main(caps: SystemCaps) {\n    let d = caps.disk.allow_read_only("/etc")\n    println(d.read("/etc/passwd"))\n}\n'),
    ("net", 'fn main(caps: SystemCaps) {\n    let n = caps.net.allow("https://example.com")\n    println(n.get("https://example.com/"))\n}\n'),
):
    blocked = client.evaluate(source, "run", "en")
    report(f"forbidden_{domain}_rejected_before_run", blocked["stage"] == "policy" and blocked["ran"] is False
           and domain in untrusted.requested_domains(blocked["manifest"]))

big = client.evaluate('fn main() {\n    let mut i = 0\n    while i < 20000 {\n        println("0123456789012345678901234567890123456789")\n        i = i + 1\n    }\n}\n', "run", "en")
out = big["run"]["stdout"]
report("output_limit", len(out.encode()) <= untrusted.MAX_OUTPUT_BYTES + 64 and out.endswith("output truncated"),
       f"{len(out.encode())} bytes")

loop = client.evaluate('fn main() {\n    let mut i = 0\n    while true {\n        i = i + 1\n    }\n}\n', "run", "en")
report("runaway_program_stopped", loop["ran"] and (loop["run"]["timed_out"] or loop["run"]["exit_code"] != 0),
       (loop["run"]["stderr"] or "")[:160])

for name, headers in (
    ("missing_token", {}),
    ("wrong_token", {"Authorization": "Bearer " + "0" * 64}),
):
    status, _ = raw("GET", "/health", headers)
    report(f"{name}_refused", status == 401, status)
status, _ = raw("POST", "/api/evaluate", {"Authorization": "Bearer " + TOKEN, "Content-Type": "application/json"},
                b'{"source": 7}')
report("malformed_request_refused", status == 400, status)
try:
    remote.RemoteEvaluator(URL, "0" * 64, ca_file=CA).require_ready()
    report("client_wrong_token_fails_closed", False)
except untrusted.SandboxUnavailable:
    report("client_wrong_token_fails_closed", True)

# Capacity: more simultaneous runs than the worker's slots get a clean 503.
busy_source = 'fn main() {\n    let mut i = 0\n    while i < 150000 {\n        i = i + 1\n    }\n    println(i)\n}\n'
body = json.dumps({"source": busy_source, "action": "run"}).encode()
headers = {"Authorization": "Bearer " + TOKEN, "Content-Type": "application/json"}
with concurrent.futures.ThreadPoolExecutor(5) as pool:
    statuses = sorted(f.result()[0] for f in [pool.submit(raw, "POST", "/api/evaluate", headers, body) for _ in range(5)])
report("capacity_full_is_503", statuses.count(200) >= 1 and statuses.count(503) >= 1
       and set(statuses) <= {200, 503}, statuses)

print(json.dumps({"result": "FAIL" if failures else "PASS", "failures": failures}))
sys.exit(1 if failures else 0)
