# Koschei Lang

A capability-secure programming language: an imported package cannot touch
your disk, network or environment unless you hand it a token. `ks run` checks
a program completely before it runs, and `ks build` compiles the same program
to a native binary that prints the same bytes.

Free for personal use; commercial use needs a license (see `LICENSING.md`).

## Install

You need Python 3.12 or newer. Go 1.24 or newer is optional; `ks build`
needs it.

```sh
./install.sh
```

The installer creates a virtual environment in `~/.koschei` and links `ks`
into `~/.local/bin`. Set `KOSCHEI_HOME` or `KOSCHEI_BIN` to choose other
places.

## First steps

```sh
ks run examples/hello.ks
printf 'the cat saw the dog\n' | ks run examples/apps/wordfreq/main.ks
ks caps examples/apps/release_gate/main.ks     # what this program may touch
ks check examples/supply_chain/main.ks         # rejected: a dependency reaches for a secret
ks build examples/apps/keygen/main.ks -o keygen && ./keygen 2
```

Two ready-made security tools, each limited to reading the directory you
give it, with no network access (`ks caps` shows it):

```sh
ks build examples/apps/secretscan/main.ks -o secretscan
./secretscan path/to/repo        # leaked keys and tokens; exit 1 on a finding
ks build examples/apps/integrity/main.ks -o integrity
./integrity snapshot site > manifest.txt
./integrity verify site < manifest.txt   # CHANGED / MISSING / NEW; exit 1 on a difference
```

## Documentation

- `docs/guide/LANGUAGE_GUIDE.en.md`: the language guide (Turkish:
  `LANGUAGE_GUIDE.tr.md`); every example in it is tested.
- `docs/reference/CORE_LIBRARY.md`: the Core Library.
- `docs/reference/ERROR_CODES.md`: every error code and how to fix it;
  `ks explain <code>` prints the same text.

## License

Koschei Lang License 1.0: `LICENSE` (Turkish: `LICENSE.tr.md`). Prices and
the difference between personal and commercial use: `LICENSING.md`.

Türkçe: `README.tr.md`
