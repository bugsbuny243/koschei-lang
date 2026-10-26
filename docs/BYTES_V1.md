# Koschei Bytes v1

Status: **type in every executor and in MIR-Go binaries; readiness gate G1.3**

`String` is always valid UTF-8 text. Binary data is a separate type, `Bytes`:
an immutable byte sequence with value semantics. The two never convert into
each other silently.

```ks
import secure

fn main() {
    let data = "héllo".to_bytes()
    println(data)                         // Bytes(68c3a96c6c6f)
    println(data.length())                // 6
    println(data.get(1) or -1)            // 195
    let head = data.slice(0, 2) or data
    println(head.to_text())               // KS3430: not UTF-8 (half of "é")
    let key = bytes_from_hex("00ff") or data
    println(secure.hash_bytes(key) or "?")
}
```

## Surface

| Expression | Type | Notes |
|---|---|---|
| `text.to_bytes()` | `Bytes` | UTF-8 encoding; never fails |
| `data.length()` | `Int` | bytes, not characters |
| `data.hex()` | `String` | lowercase |
| `data.to_text()` | `String or Error` | `KS3430` when not valid UTF-8 |
| `data.get(index)` | `Int or Error` | 0..255; `KS3460` out of range |
| `data.slice(start, end)` | `Bytes or Error` | `0 <= start <= end <= length`; `KS3460` otherwise |
| `a + b` | `Bytes` | `KS3502` over 16 MiB |
| `==`, `!=`, `<`, … | `Bool` | byte by byte |
| `bytes_from_hex(text)` | `Bytes or Error` | even length, `0-9a-fA-F` only; `KS3461` otherwise (no spaces) |
| `sha3_256_bytes(data)` | `String or Error` | kernel digest of the bytes; at most 1 MiB |
| `secure.hash_bytes(data)` | `Result<String, Error>` | `"sha3-256:" + hex`; equals `secure.hash(text)` for `text.to_bytes()` |

A value renders as `Bytes(hex)`. Mixing `Bytes` and `String` in `+` or `==`
is a check-time error.

## Where binary data comes from

| Source | Operation |
|---|---|
| standard input | `InputCaps.read_bytes()`: same budget and errors as `read_text`, no UTF-8 check |
| files | `DiskCaps.read_bytes(path)` / `DiskReadCaps.read_bytes(path)`: same scope and symlink rules as `read` (`ks run` only; native disk waits for G2) |
| randomness | `RandomCaps.bytes(count)`: 1..1024 bytes, charged against the token's budget |

Network bodies as `Bytes` are not in v1; they arrive with the server and
broker gates (G4, G2).

## Native

MIR-Go represents a `Bytes` value as an immutable Go string, so equality and
ordering are byte comparisons exactly as in Python. Every operation above
except `DiskCaps.read_bytes` compiles, and the binary prints the same bytes
and the same Error values (`tests/test_bytes_v1.py`).
