# Example applications

Five complete command-line programs. Each one runs under `ks run` and
compiles with `ks build` to a native binary that prints the same bytes;
`tests/test_example_apps_v1.py` checks both.

| App | Shows | Authority (`ks caps`) |
|---|---|---|
| [`wordfreq`](wordfreq/main.ks) | reading standard input, arguments, the `text` library, errors as values | program input (1 MiB) |
| [`release_gate`](release_gate/main.ks) | structs, parsing, the `xandar` and `morag` admission libraries, the clock | program input (1 MiB), clock (1 s) |
| [`keygen`](keygen/main.ks) | secure randomness under a byte budget, `secure.digest` fingerprints | program input, random (512 bytes) |
| [`secretscan`](secretscan/main.ks) | walking a directory, `Bytes`, matching credential formats; exit status 1 on a finding | program input, disk (read-only) |
| [`integrity`](integrity/main.ks) | SHA3-256 manifests, maps, chunked digests of large files; exit status 1 on a difference | program input, disk (read-only) |

```sh
printf 'the cat saw the dog\nthe end\n' | ks run examples/apps/wordfreq/main.ks
ks build examples/apps/release_gate/main.ks -o release_gate
./release_gate 20800 < statements.txt
ks run examples/apps/keygen/main.ks 3
ks build examples/apps/secretscan/main.ks -o secretscan && ./secretscan .
ks build examples/apps/integrity/main.ks -o integrity
./integrity snapshot site > manifest.txt && ./integrity verify site < manifest.txt
```

`wordfreq`, `release_gate` and `keygen` cannot touch the disk, the network or
the environment. `secretscan` and `integrity` may only read the directory they
are given: their manifests list read-only disk access and no network, so what
they read cannot leave the machine, and the checker refuses any code that
tries. Both fail with exit status 1 when they find something, so a CI step can
gate on them, and neither lets a file it could not check pass as a clean one.
