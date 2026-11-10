# Koschei MCP server

`ks-mcp` lets an AI agent run code on your machine without giving it your machine.

The agent writes a Koschei program instead of a shell command or a Python script. Before anything runs, the compiler reports exactly what the program asks for: which directories, which network origins, which environment variables. You decide in advance what is allowed. A program that asks for anything else is rejected, and none of its code executes.

## Install

```sh
pip install koschei-lang      # gives you ks and ks-mcp; needs Python 3.12+
```

Or skip the install and let `uvx` fetch it: `uvx koschei-lang` is the same program as `ks-mcp`.

## Start it

```sh
ks-mcp                                         # programs may only compute
ks-mcp --allow-read /srv/reports               # plus: read files under /srv/reports
ks-mcp --allow-write /tmp/agent-out \
       --allow-net https://api.example.com     # plus: write under one directory, reach one origin
```

| Option | Programs may |
|---|---|
| (none) | compute, read the clock, draw random numbers |
| `--allow-read PATH` | read files under `PATH` |
| `--allow-write PATH` | read and write files under `PATH` |
| `--allow-net ORIGIN` | send requests to exactly that origin |
| `--allow-env NAME` | read that environment variable |
| `--allow DOMAIN` | use a whole domain (`disk`, `net`, `env`, `input`, ...) with no scope limit |

All options repeat. The policy is fixed by the command line. The agent cannot change it.

## Connect an agent

Any MCP client that starts a stdio server works. A typical entry (use `"command": "ks-mcp"` without the first argument if you installed with pip):

```json
{
  "mcpServers": {
    "koschei": {
      "command": "uvx",
      "args": ["koschei-lang", "--allow-read", "/srv/reports"]
    }
  }
}
```

## Tools

| Tool | What it does |
|---|---|
| `koschei_guide` | Returns a short language reference. Agents read it once, then write Koschei. |
| `koschei_check` | Compiles a program and reports its capability manifest and whether the policy allows it. Nothing runs. |
| `koschei_run` | Checks the program the same way, then runs it if the policy allows it. Returns the manifest and the output. |

A blocked program gets a result like this:

```text
BLOCKED before running. The program asks for authority this server does not allow:
- Disk read of /etc (line 2) is outside the allowed paths
Nothing was executed. Allowed: disk read under /data; clock; random.

Capability manifest:
- Disk: /etc (read-only), line 2; uses read
```

## How the policy is enforced

1. **Before running.** The compiler builds the capability manifest from the source. The server compares every grant with the policy. A scope that is computed at run time cannot be checked, so under a scoped policy it is rejected.
2. **While running.** The Koschei runtime holds each token to its scope. A token for `/data` cannot read `/etc`, cannot leave through `..`, and does not follow a symbolic link that points outside.
3. **Around the process.** Each run is a child process in an empty temporary directory with a minimal environment, CPU, memory and file-size limits, a 10 second timeout and a step budget.

## Limits to know

- Unix-like systems only (the process limits use `resource`).
- Programs are limited to 16 KB of source and 16 KB of output.
- `--allow DOMAIN` gives the whole domain. Prefer the scoped options.
- The process limits are a backstop, not a container. For hostile code at scale, also run the server inside a container or VM.
- Koschei has a small standard library. It suits scripts that compute, read and write files, and call HTTP APIs.
