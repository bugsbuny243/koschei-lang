// keygen: issue API keys and the fingerprints a server stores instead.
//
//   ks run main.ks 3
//   ks build main.ks -o keygen && ./keygen 3
//
// Each key is 32 bytes from the operating system's secure random source,
// shown once as hex. The fingerprint is a domain-separated SHA3-256 digest of
// the key: store the fingerprint, hand out the key, and a leaked fingerprint
// list reveals no key. At most 16 keys per run; the random token is budgeted
// for exactly that.

import secure

fn count_from(args: List<String>) -> Int or Error {
    let raw = args.get(0) or return 1
    let count = raw.to_int() or return Error("COUNT must be a number: {raw}")
    if count < 1 || count > 16 {
        return Error("COUNT must be between 1 and 16: {count}")
    }
    return count
}

fn issue(random: RandomCaps, count: Int) -> Int or Error {
    let mut issued = 0
    while issued < count {
        let key = random.hex(32) or return Error("random budget exhausted")
        let fingerprint = secure.digest("koschei.example.keygen/v1", [key]) or return Error("key could not be digested")
        println("key={key} fingerprint={fingerprint}")
        issued = issued + 1
    }
    return issued
}

fn main(caps: SystemCaps) {
    let input = caps.input.allow(1)
    let none: List<String> = []
    let args = input.args() or none
    let count = count_from(args) or 0
    if count == 0 {
        println("keygen: usage: keygen [COUNT 1..16]")
    } else {
        let issued = issue(caps.random.allow(512), count) or 0
        println("{issued} keys issued")
    }
}
