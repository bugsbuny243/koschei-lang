# Koschei Program Input v1

Status: **capability in every executor and in MIR-Go binaries; readiness gate G1.2**

A Koschei program reads its command-line arguments and its standard input only
through a narrowed capability. A function without that capability cannot see
either, so a library that was never handed `InputCaps` cannot read what the
user typed.

```ks
fn main(caps: SystemCaps) {
    let input = caps.input.allow(65536)
    let args = input.args() or return
    let text = input.read_text() or return
    let lines = text.split("\n") or return
    println("{args.length()} arguments, {lines.length()} lines")
}
```

```sh
printf 'one\ntwo\n' | ks run count.ks first second
ks build count.ks -o count && printf 'one\ntwo\n' | ./count first second
```

Both print the same bytes.

## Surface

| Expression | Type | Effect |
|---|---|---|
| `caps.input` | `InputRoot` | none (a root cannot read) |
| `caps.input.allow(max_bytes)` | `InputCaps` | `authority.derive` |
| `input.args()` | `List<String> or Error` | `input.read` |
| `input.read_text()` | `String or Error` | `input.read` |

`max_bytes` must be a static `Int` literal from 1 to 16,777,216 (the `String`
value budget): `KS2430` when it is not a literal, `KS2431` when it is out of
range. `ks caps` shows the bound:

```
PROGRAM GİRDİSİ:
  - argümanlar + standart girdi | stdin_bytes=65536  (satır 2)
  kullanılan işlemler: args, read_text
```

The power domain is `data`. `input.read` is an effect, so a `pure fn` cannot
read input (`KS3940`).

## `args()`

The arguments after the program path, in order. `ks run app.ks a b` and
`./app a b` both give `["a", "b"]`. For `ks run`, everything after the first
`--` belongs to the program, so `ks run app.ks -- --max-steps` hands the
program `"--max-steps"` instead of setting the interpreter budget.

An argument that is not valid UTF-8 is not silently repaired: `args()` returns
the Error value `KS3430: N. program argümanı geçerli UTF-8 metin değil.` for
the first such argument (counting from 1).

## `read_text()`

Reads standard input to its end and returns it as text.

| Input | Result |
|---|---|
| at most `max_bytes` bytes of UTF-8 | the text |
| more than `max_bytes` bytes | `KS3431: Standart girdi bütçesi aşıldı: en fazla N bayt okunabilir.` |
| bytes that are not UTF-8 | `KS3430: Standart girdi geçerli UTF-8 metin değil.` |
| the operating system fails the read | `KS3432: Standart girdi okunamadı.` |
| a closed standard input | `""` |

At most `max_bytes + 1` bytes are read per call, so the budget also bounds
memory. Bytes that were read are not given back: after an over-budget result
the next call continues after them, and after the end of the input every call
returns `""`. A UTF-8 byte order mark is kept as `U+FEFF`.

A closed standard input reads as empty in every executor: the Go runtime
reopens a closed standard descriptor on `/dev/null` at start, and the Python
executors do the same.

## Why native binaries may carry it

Disk, network and environment authority stay closed in native binaries
(`KS4004`) until the native capability broker exists (readiness gate G2).
Program input is different in kind: argv and stdin are data the invoker
already chose to hand the process, and reading them reaches no resource the
invoker did not provide. MIR-Go therefore admits `main(caps: SystemCaps)` when
the program uses only `caps.input`; any other domain still fails closed with a
reason that names G2.

The input runtime is emitted only into binaries that use it. It reads
`os.Args` and `os.Stdin` and links no file, network, environment or process
API (`tests/test_program_input_v1.py` checks the symbol table). The legacy
AST-Go backend behind `ks emit-go` has no input runtime and refuses such
programs with `KS4001`.

## Capability values are opaque

Working on this gate showed that printing an authority token printed the host
object, memory address included (`<koschei.interpreter.EnvCaps object at
0x7f…>`): a host detail in program output that changed on every run. Every
capability now renders as its type only, in every executor:

```ks
println(caps)                      // <SystemCaps>
println("{caps.input.allow(8)}")   // <InputCaps>
```

The scope a token was narrowed to is not printed. Comparing tokens with `==`
or `!=` is refused (`KS2407`): it asked the host whether two tokens were the
same object, which Koschei does not define and executors answered differently.
The rule covers structs that carry a token at any depth.

## Not in v1

- Reading one line at a time (interactive prompts). Line-oriented tools read
  the whole input and split it.
- Binary input. Bytes arrive with the `Bytes` type (readiness gate G1.3).
- Environment variables in native binaries (G2).

## Evidence

`tests/test_program_input_v1.py`:

- checker rules (`KS2430`, `KS2431`, `KS2402`, `KS2403`, `KS2404`, `KS1301`,
  `KS2401`, `KS2407`, `KS3940`) and the `ks caps` manifest;
- every outcome above as a value, through `ks run`;
- the checked-AST interpreter, the canonical MIR executor and `ks run` print
  the same output for the same arguments and input;
- arguments do not leak from one run into the next;
- the MIR-Go binary prints the same bytes as `ks run` for valid, over-budget,
  invalid UTF-8, encoded-surrogate, byte-order-mark, non-UTF-8 argument and
  closed-input cases, a 1 MiB input at and over its budget, and a read the
  kernel fails (`EISDIR`);
- other domains, capability-typed struct fields and other `main` signatures
  still fail closed natively with `KS4004`;
- the input binary links no resource-access symbols.
