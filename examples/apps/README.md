# Example applications

Three complete command-line programs. Each one runs under `ks run` and
compiles with `ks build` to a native binary that prints the same bytes;
`tests/test_example_apps_v1.py` checks both.

| App | Shows | Authority (`ks caps`) |
|---|---|---|
| [`wordfreq`](wordfreq/main.ks) | reading standard input, arguments, the `text` library, errors as values | program input (1 MiB) |
| [`release_gate`](release_gate/main.ks) | structs, parsing, the `xandar` and `morag` admission libraries, the clock | program input (1 MiB), clock (1 s) |
| [`keygen`](keygen/main.ks) | secure randomness under a byte budget, `secure.digest` fingerprints | program input, random (512 bytes) |

```sh
printf 'the cat saw the dog\nthe end\n' | ks run examples/apps/wordfreq/main.ks
ks build examples/apps/release_gate/main.ks -o release_gate
./release_gate 20800 < statements.txt
ks run examples/apps/keygen/main.ks 3
```

None of the three can touch the disk, the network or the environment: their
manifests list no such grant, and the checker refuses any code that tries.
