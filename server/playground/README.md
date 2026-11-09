# Koschei Playground

A web page where anyone can write a Koschei program and run it on the server, with no install.

## How untrusted code is contained

1. **Language policy.** Before anything runs, `ks caps --json --deny disk --deny net --deny env --deny process --deny serve --deny persist --deny input` type-checks the program and reads its capability manifest. A program that requests any of those domains, even narrowed (`caps.disk.allow_read_only("/etc")`), is rejected with exit code 2, and none of its code executes. Only pure computation, clock and random get through.
2. **Process sandbox.** Each check or run happens in a child process in a fresh temporary directory. The child has an empty environment and limits on CPU (5 s), memory (512 MB), file size and open files. It also has a 10 s wall-clock timeout and a 200,000-step interpreter budget.
3. **Service limits.**
   - Source size is capped at 16 KB.
   - Output is capped at 16 KB.
   - Each client is limited to 30 requests per minute.
   - The container runs as a non-root user.

## Run locally

```sh
pip install -e .
python server/playground/app.py      # http://localhost:8080
```

## Docker

```sh
docker build -f server/playground/Dockerfile -t koschei-playground .
docker run -p 8080:8080 koschei-playground
```

## API

`POST /api/evaluate` with `{"source": "...", "action": "run" | "check"}` returns:

- `stage`: `policy`, `check` or `run`
- `manifest`: the capability manifest
- `policy`: the output of the policy and check step
- `run`: the program's output, when it ran

`GET /health` returns `{"ok": true}`.
