"""TEST ONLY: frontend <-> worker connectivity and network isolation, end to end.

    sudo python3 connectivity.py /path/to/koschei-lang

Run as root on a VM where install.sh has installed the worker with
NAMES including worker.koschei.test and LISTEN 0.0.0.0:8443.

The real frontend (server/playground/app.py, remote mode) runs in its own
network namespace behind a veth pair, so it reaches the worker from a
non-loopback address exactly as a remote Railway frontend would. Nothing is
mocked. Ingress changes use `systemctl set-property --runtime` on the socket
unit (live cgroup BPF update, no worker restart); they are removed at the end.

Prints one JSON line per check and exits non-zero on any failure.
"""
import json
import os
import shutil
import socket
import ssl
import subprocess
import sys
import tempfile
import time
import urllib.request
from pathlib import Path

REPO = Path(sys.argv[1]).resolve()
NS = "kfront"
HOST_IP, FRONT_IP = "10.77.0.1", "10.77.0.2"
NAME = "worker.koschei.test"
ETC = Path("/etc/koschei-worker")
PYTHON = "/opt/koschei-worker/venv/bin/python"
SERVICE_CGROUP = Path("/sys/fs/cgroup/system.slice/koschei-worker.service")
TOKEN = (ETC / "worker-token").read_text().strip()
CA_PEM = (ETC / "ca-cert.pem").read_text()
RUNTIME_CONTROL = Path("/run/systemd/system.control/koschei-worker.socket.d")
failures = []
frontends = []


def report(name, ok, detail=""):
    print(json.dumps({"check": name, "ok": bool(ok), "detail": detail}), flush=True)
    if not ok:
        failures.append(name)


def run(*args, check=True, **kw):
    return subprocess.run(args, check=check, text=True, capture_output=True, **kw)


def in_ns(*args, **kw):
    return run("ip", "netns", "exec", NS, *args, **kw)


def setup_namespace():
    run("ip", "netns", "del", NS, check=False)
    run("ip", "link", "del", "kf-host", check=False)
    run("ip", "netns", "add", NS)
    run("ip", "link", "add", "kf-host", "type", "veth", "peer", "name", "kf-front")
    run("ip", "link", "set", "kf-front", "netns", NS)
    run("ip", "addr", "add", HOST_IP + "/24", "dev", "kf-host")
    run("ip", "link", "set", "kf-host", "up")
    in_ns("ip", "addr", "add", FRONT_IP + "/24", "dev", "kf-front")
    in_ns("ip", "link", "set", "kf-front", "up")
    in_ns("ip", "link", "set", "lo", "up")
    # `ip netns exec` bind-mounts this over /etc/hosts inside the namespace.
    hosts = Path("/etc/netns") / NS
    hosts.mkdir(parents=True, exist_ok=True)
    (hosts / "hosts").write_text(f"127.0.0.1 localhost\n{HOST_IP} {NAME}\n")


def set_ingress(value):
    run("systemctl", "set-property", "--runtime", "koschei-worker.socket",
        "IPAddressAllow=", "IPAddressAllow=" + value)


def start_frontend(port, **worker_env):
    env = {"PATH": "/usr/bin:/bin", "KOSCHEI_PLAYGROUND_MODE": "remote", "PORT": str(port),
           "KOSCHEI_SITE_DIR": str(REPO / "commercial" / "lang-site")}
    env.update(worker_env)
    process = subprocess.Popen(
        ["ip", "netns", "exec", NS, PYTHON, "app.py"], cwd=REPO / "server" / "playground",
        env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    frontends.append(process)
    for _ in range(120):
        if http(port, "GET", "/health")[0] == 200:
            return process
        if process.poll() is not None:
            raise RuntimeError(f"frontend :{port} exited: {process.stdout.read()[-500:]}")
        time.sleep(0.5)
    raise RuntimeError(f"frontend :{port} did not start")


def http(port, method, path, body=None, timeout=60):
    """A request to a frontend inside the namespace (curl-free, via python)."""
    code = (
        "import json,sys,time,urllib.request,urllib.error\n"
        "req=urllib.request.Request('http://127.0.0.1:%d%s',method=%r,data=%r,"
        "headers={'Content-Type':'application/json'})\n"
        "t=time.monotonic()\n"
        "try:\n r=urllib.request.urlopen(req,timeout=%d);s=r.status;b=r.read()\n"
        "except urllib.error.HTTPError as e:\n s=e.code;b=e.read()\n"
        "except OSError:\n s=0;b=b''\n"
        "print(json.dumps([s,b.decode('utf-8','replace')[:2000],round(time.monotonic()-t,2)]))\n"
    ) % (port, path, method, body, timeout)
    out = in_ns("/usr/bin/python3", "-c", code, check=False, env={"PATH": "/usr/bin:/bin"},
                timeout=timeout + 30).stdout
    try:
        return json.loads(out)
    except ValueError:
        return [0, out[-300:], 0]


PROGRAM = json.dumps({"source": 'fn main() {\n    println("playground-ok")\n}\n',
                      "action": "run", "lang": "en"}).encode()


def evaluate(port, timeout=200):
    status, body, seconds = http(port, "POST", "/api/evaluate", PROGRAM, timeout)
    try:
        data = json.loads(body)
    except ValueError:
        data = {}
    return status, data, seconds


def ran_ok(data):
    return (data.get("ran") is True and data.get("run", {}).get("exit_code") == 0
            and data["run"].get("stdout", "").strip() == "playground-ok")


def wait_for(predicate, seconds, step=5):
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        result = predicate()
        if result:
            return result
        time.sleep(step)
    return predicate()


def raw_tls(host, cafile=None, server_name=NAME, timeout=8):
    """TCP + TLS from the frontend namespace; returns OK or the error class."""
    code = (
        "import socket,ssl,sys\n"
        "ctx=ssl.create_default_context(%s)\n"
        "try:\n"
        " s=socket.create_connection((%r,8443),timeout=%d)\n"
        " ctx.wrap_socket(s,server_hostname=%r).close();print('TLS_OK')\n"
        "except Exception as e:\n print('FAILED',type(e).__name__)\n"
    ) % ("cafile=%r" % cafile if cafile else "", host, timeout, server_name)
    return in_ns("/usr/bin/python3", "-c", code, check=False, timeout=timeout + 30).stdout.strip()


def from_service_cgroup(host, port):
    """connect() from a process placed in the worker service's cgroup."""
    code = (
        "import os,socket,sys\n"
        "open(%r,'w').write(str(os.getpid()))\n"
        "try:\n socket.create_connection((%r,%d),timeout=5).close();print('CONNECTED')\n"
        "except OSError as e:\n print('BLOCKED',type(e).__name__)\n"
    ) % (str(SERVICE_CGROUP / "cgroup.procs"), host, port)
    return run("/usr/bin/python3", "-c", code, check=False).stdout.strip()


def worker_active():
    return run("systemctl", "is-active", "koschei-worker.service", check=False).stdout.strip() == "active"


def main():
    setup_namespace()
    good = {"KOSCHEI_WORKER_URL": f"https://{NAME}:8443", "KOSCHEI_WORKER_TOKEN": TOKEN,
            "KOSCHEI_WORKER_CA_PEM": CA_PEM}

    # 1. Ingress limited to the frontend's address: the authorized frontend works.
    set_ingress(FRONT_IP + "/32")
    start_frontend(8080, **good)
    status, data, _ = wait_for(lambda: (lambda r: r if r[0] == 200 else None)(evaluate(8080)), 120) or evaluate(8080)
    report("authorized_frontend_runs_program", status == 200 and ran_ok(data), [status, data.get("run")])
    report("tls_with_pinned_ca", raw_tls(HOST_IP, cafile=str(ETC / "ca-cert.pem")) == "TLS_OK")

    # 2. Wrong token: the worker refuses; the frontend site stays up, 503 only.
    start_frontend(8081, **dict(good, KOSCHEI_WORKER_TOKEN="0" * 64))
    status, data, _ = evaluate(8081)
    report("wrong_token_frontend_503", status == 503, [status, data.get("error")])
    report("wrong_token_frontend_site_up", http(8081, "GET", "/")[0] == 200)

    # 3. Untrusted certificates: a foreign CA, public CAs only, wrong hostname.
    foreign = tempfile.mkdtemp(prefix="foreign-ca-")
    run("openssl", "req", "-x509", "-newkey", "ec", "-pkeyopt", "ec_paramgen_curve:P-256", "-nodes",
        "-days", "1", "-subj", "/CN=Foreign CA", "-keyout", foreign + "/k.pem", "-out", foreign + "/c.pem")
    foreign_pem = Path(foreign, "c.pem").read_text()
    for port, name, env in (
        (8082, "foreign_ca", dict(good, KOSCHEI_WORKER_CA_PEM=foreign_pem)),
        (8083, "system_cas_only", {k: v for k, v in good.items() if k != "KOSCHEI_WORKER_CA_PEM"}),
        (8084, "hostname_mismatch", dict(good, KOSCHEI_WORKER_URL=f"https://{HOST_IP}:8443")),
    ):
        start_frontend(port, **env)
        status, data, _ = evaluate(port)
        report(f"untrusted_tls_{name}_503", status == 503, [status, data.get("error")])
    os.chmod(foreign, 0o755)
    os.chmod(foreign + "/c.pem", 0o644)
    report("raw_tls_foreign_ca_rejected",
           raw_tls(HOST_IP, cafile=foreign + "/c.pem") == "FAILED SSLCertVerificationError")
    report("raw_tls_wrong_name_rejected",
           raw_tls(HOST_IP, cafile=str(ETC / "ca-cert.pem"), server_name="evil.example")
           == "FAILED SSLCertVerificationError")
    shutil.rmtree(foreign)

    # 4. Ingress from an address that is not allowed is dropped (cgroup BPF).
    set_ingress("10.77.0.99/32")
    report("ingress_not_allowed_dropped", raw_tls(HOST_IP, cafile=str(ETC / "ca-cert.pem"), timeout=5)
           in ("FAILED TimeoutError", "FAILED timeout"))
    status, _, seconds = evaluate(8080)
    report("ingress_not_allowed_frontend_503", status == 503 and seconds < 40, [status, seconds])

    # 5. Ingress "any" (Railway without static IPs): the frontend works, and the
    #    worker service still cannot open a single outbound connection.
    set_ingress("any")
    status, data, _ = evaluate(8080)
    report("ingress_any_authorized_frontend_runs", status == 200 and ran_ok(data), status)
    gateway = run("sh", "-c", "ip -4 route show default | awk '{print $3; exit}'").stdout.strip()
    reachable = run("/usr/bin/python3", "-c",
                    f"import socket;socket.create_connection(('{FRONT_IP}',8080),timeout=5).close();print('CONNECTED')",
                    check=False).stdout.strip()
    report("control_frontend_reachable_outside_worker_cgroup", reachable == "CONNECTED", reachable)
    for label, host, port in (
        ("public_ipv4", "1.1.1.1", 443),
        ("frontend_private_net", FRONT_IP, 8080),
        ("default_gateway", gateway or "10.0.2.2", 53),
        ("cloud_metadata", "169.254.169.254", 80),
        ("rfc1918", "192.168.0.1", 80),
    ):
        result = from_service_cgroup(host, port)
        report(f"ingress_any_worker_egress_{label}_blocked", result.startswith("BLOCKED"), result)
    allow = run("systemctl", "show", "-p", "IPAddressAllow", "--value", "koschei-worker.service").stdout.split()
    report("worker_service_allowlist_loopback_only", sorted(allow) == ["127.0.0.0/8", "::1/128"], allow)

    # 6. Submitted programs: no network in any configuration (preflight result).
    journal = run("journalctl", "-u", "koschei-worker", "-o", "cat", "--no-pager", "-n", "200").stdout
    passed = [json.loads(l) for l in journal.splitlines() if l.startswith('{"checks"')]
    checks = passed[-1]["checks"] if passed else []
    report("user_code_network_isolated_by_preflight",
           {"child_no_network", "child_loopback_network", "child_no_inherited_fds"} <= set(checks), checks)

    # 7. Worker down: the site stays up, evaluation fails fast and controlled.
    run("systemctl", "stop", "koschei-worker.socket", "koschei-worker.service")
    status, data, seconds = evaluate(8080)
    report("worker_stopped_evaluate_503", status == 503 and seconds < 30, [status, data.get("error"), seconds])
    status, _, seconds = http(8080, "GET", "/")
    report("worker_stopped_site_up", status == 200 and seconds < 2, [status, seconds])
    start_frontend(8085, **good)  # a frontend that boots while the worker is down
    report("frontend_boots_while_worker_down", http(8085, "GET", "/")[0] == 200
           and evaluate(8085)[0] == 503)
    run("systemctl", "start", "koschei-worker.socket", "koschei-worker.service", timeout=2400)
    report("worker_restarted", worker_active())
    status, data, _ = wait_for(lambda: (lambda r: r if r[0] == 200 else None)(evaluate(8080)), 300) or evaluate(8080)
    report("evaluation_recovers_after_restart", status == 200 and ran_ok(data), status)
    status, data, _ = wait_for(lambda: (lambda r: r if r[0] == 200 else None)(evaluate(8085)), 120, step=10) or evaluate(8085)
    report("late_frontend_enabled_by_watcher", status == 200 and ran_ok(data), status)


def cleanup():
    for process in frontends:
        process.terminate()
    for process in frontends:
        try:
            process.wait(10)
        except subprocess.TimeoutExpired:
            process.kill()
    shutil.rmtree(RUNTIME_CONTROL, ignore_errors=True)
    run("systemctl", "daemon-reload", check=False)
    run("ip", "netns", "del", NS, check=False)
    run("ip", "link", "del", "kf-host", check=False)
    shutil.rmtree(Path("/etc/netns") / NS, ignore_errors=True)


try:
    main()
except Exception as error:  # report, never hide, a harness failure
    report("harness", False, f"{type(error).__name__}: {error}")
finally:
    cleanup()
print(json.dumps({"result": "FAIL" if failures else "PASS", "failures": failures}))
sys.exit(1 if failures else 0)
