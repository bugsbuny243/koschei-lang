# The same compromised dependency, in Rust and in Koschei

In August 2026 three crates.io packages (`arrayref` 0.3.10, `internment` 0.8.7,
`append-only-vec` 0.1.9) were made to depend on a typosquat whose build script
downloaded and started a backdoor. Building any project that depended on them
was enough. This demo repeats the mechanism, harmlessly: the "key" is a fake
file in `fixture/`, and "exfiltration" writes `exfiltrated.txt` locally.

```sh
./run.sh
```

| Step | Rust | Koschei |
|---|---|---|
| Building the project | `build.rs` of the dependency runs on your machine | No build hooks, macros or compile-time code: nothing of a package runs while compiling |
| Helper reads a secret and ships it | Compiles and runs: any library may call `std::fs` / `std::net` | Does not compile (`KS1101`): there is no global file or network API |
| Helper asks for the capabilities in its signature | — | Does not compile (`KS1301`): `main` never passed them; passing them would be visible in `main` and in `ks caps` |
| Honest helper | — | `ks caps`: no side-effect capability, pure computation |

What this does **not** claim: Koschei cannot help once an attacker already
controls the machine (a stolen laptop, stolen keys), and the Go toolchain used
by `ks build` is part of the trusted base. There is no package registry yet;
imports are local files.
