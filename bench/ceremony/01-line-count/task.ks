fn main(caps: SystemCaps) {
    let disk = caps.disk.allow_read_only("bench/ceremony/fixtures")
    let text = disk.read("bench/ceremony/fixtures/lines.txt") or return
    println(text.split("\n").length())
}
