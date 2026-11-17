"""Smoke test for a running Koschei Forms image (or binary).

Usage: forms_docker_smoke_v1.py BASE_URL BROKER_PID PASSWORD

Drives the product over HTTP, then reads /proc for the worker process (the
broker's only child) and checks it is confined. The time a request waits
behind three idle connections is measured and printed; above 2 s it is
reported as a GitHub Actions warning, not a failure (see the workflow).
Exit status 1 on any failed check.
"""
from __future__ import annotations

import http.client
import socket
import sys
import time
import urllib.parse
from pathlib import Path


def main() -> int:
    base, broker_pid, password = sys.argv[1], int(sys.argv[2]), sys.argv[3]
    url = urllib.parse.urlsplit(base)
    host, port = url.hostname or "127.0.0.1", url.port or 80
    failures: list[str] = []

    def request(method, path, body=None, cookie=None, timeout=30):
        connection = http.client.HTTPConnection(host, port, timeout=timeout)
        headers = {"Host": "forms.example"}
        if body is not None:
            headers["Content-Type"] = "application/x-www-form-urlencoded"
            body = urllib.parse.urlencode(body)
        if cookie:
            headers["Cookie"] = cookie
        connection.request(method, path, body=body, headers=headers)
        response = connection.getresponse()
        result = (response.status, dict(response.getheaders()), response.read().decode("utf-8"))
        connection.close()
        return result

    def check(name, condition, detail=""):
        print(("PASS " if condition else "FAIL ") + name + (f"  {detail}" if detail else ""))
        if not condition:
            failures.append(name)

    for _ in range(300):
        try:
            request("GET", "/")
            break
        except OSError:
            time.sleep(0.1)

    status, _, body = request("GET", "/")
    check("home page", status == 200 and "Koschei Forms" in body, str(status))
    status, _, _ = request("POST", "/admin/login", {"password": "wrong"})
    check("wrong password refused", status == 401, str(status))
    status, headers, _ = request("POST", "/admin/login", {"password": password})
    cookie = headers.get("Set-Cookie", "").split(";")[0]
    check("sign in", status == 303 and cookie.startswith("kf_session="), str(status))
    status, _, _ = request("POST", "/admin/forms", {"slug": "contact", "redirect_url": ""}, cookie)
    check("create form (data directory writable)", status == 303, str(status))
    sent = {"email": "a+b@example.com", "name": "Ayşe Öz", "message": "<b>hi</b>"}
    status, _, body = request("POST", "/f/contact", sent)
    check("submit", status == 200 and "Thank you" in body, str(status))
    status, _, body = request("GET", "/admin/f/contact", cookie=cookie)
    check("submission listed and escaped", "Ayşe Öz" in body and "&lt;b&gt;hi&lt;/b&gt;" in body)
    status, headers, body = request("GET", "/admin/f/contact/csv", cookie=cookie)
    check("csv export", status == 200 and '"a+b@example.com"' in body, str(status))

    children_file = Path(f"/proc/{broker_pid}/task/{broker_pid}/children")
    children = children_file.read_text().split() if children_file.exists() else []
    check("broker has one worker", len(children) == 1, str(children))
    if children:
        status_text = Path(f"/proc/{children[0]}/status").read_text()
        fields = dict(line.split(":\t", 1) for line in status_text.splitlines() if ":\t" in line)
        check("worker under seccomp filter", fields.get("Seccomp", "").strip() == "2", fields.get("Seccomp", "?"))
        check("worker no_new_privs", fields.get("NoNewPrivs", "").strip() == "1", fields.get("NoNewPrivs", "?"))
        uid = fields.get("Uid", "").split()
        check("worker not root", bool(uid) and uid[0] != "0", " ".join(uid))

    idle = [socket.create_connection((host, port), timeout=60) for _ in range(3)]
    try:
        started = time.monotonic()
        status, _, _ = request("GET", "/", timeout=90)
        waited = time.monotonic() - started
    finally:
        for client in idle:
            client.close()
    print(f"IDLE_CONNECTION_WAIT seconds={waited:.2f} status={status}")
    if waited > 2.0:
        print(
            f"::warning title=Forms image serves one connection at a time::A request waited {waited:.1f} s "
            "behind 3 idle connections. The image installs a koschei-lang release without concurrent "
            "request reading (#404); release it and raise the pin in products/forms/Dockerfile."
        )

    print(f"SUMMARY failures={len(failures)}")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
