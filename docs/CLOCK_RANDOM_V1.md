# Koschei Clock and Random v1

Status: **capabilities in every executor and in MIR-Go binaries; readiness gate G3**

Time and randomness are authority in Koschei: a function that was not handed
a clock cannot read the time, and one that was not handed a random token
cannot draw randomness.

```ks
fn main(caps: SystemCaps) {
    let clock = caps.clock.allow(1000)
    let today = clock.now_ms() / 86400000
    let random = caps.random.allow(64)
    let session = random.hex(16) or return
    let die = random.below(6) or return
    println("day {today}, session {session}, die {die + 1}")
}
```

## Clock

| Expression | Type | Meaning |
|---|---|---|
| `caps.clock.allow(resolution_ms)` | `ClockCaps` | static Int literal, 1..86,400,000 (`KS2440`/`KS2441`) |
| `clock.now_ms()` | `Int` | wall clock, milliseconds since 1970-01-01 UTC |
| `clock.monotonic_ms()` | `Int` | milliseconds since an arbitrary start; never decreases |

Both readings are rounded down to the resolution. A coarse clock is weaker
authority: code holding `caps.clock.allow(1000)` cannot time anything finer
than a second, which also limits timing side channels. `now_ms() / 86400000`
is the day number `morag.check` expects.

## Random

| Expression | Type | Meaning |
|---|---|---|
| `caps.random.allow(max_bytes)` | `RandomCaps` | static Int literal, 1..1,048,576 (`KS2450`/`KS2451`) |
| `random.hex(count)` | `String or Error` | `count` fresh bytes (1..1024) as lowercase hex |
| `random.below(bound)` | `Int or Error` | uniform Int in `0..bound-1`; costs 8 bytes |

`max_bytes` is the most randomness the token may ever produce; the budget is
shared by every holder of the token. Over the budget is the Error value
`KS3450`, an argument out of range is `KS3451`; neither draws or charges
anything.

Randomness comes only from the operating system's cryptographically secure
source: Python `secrets` under `ks run`, Go `crypto/rand` in binaries. Koschei
implements no generator of its own (`crypto_agility_v1`). If the source fails,
the program stops with `KS5002` instead of producing a weak value.

Reading time and randomness are effects (`clock.read`, `random.read`, power
domain `data`): a `pure fn` cannot do either (`KS3940`). `ks caps` shows the
resolution and the budget.

## Native binaries

Neither domain reaches a resource, so MIR-Go compiles them, like program input
(`PROGRAM_INPUT_V1.md`). Each runtime is emitted only into binaries that use
it: a clock-only binary does not link `crypto/rand`.

## Not in v1

- Deadlines and sleeping (`deadline` stays planned in the stdlib catalog).
- Random bytes as a `Bytes` value (readiness gate G1.3).
- A deterministic test clock or seeded randomness: tests check shapes and
  bounds, not values.

## Evidence

`tests/test_clock_random_v1.py`: checker rules, the effect contract and the
manifest; rounding, monotonicity, budget exhaustion and every Error value with
identical transcripts from `ks run` and the binary; wall-clock bounds, value
ranges and hex shape in both; per-domain runtime emission.
