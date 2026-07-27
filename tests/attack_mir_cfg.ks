fn main() {
    let secret = disk.read("/etc/shadow") or "blocked"
    println(secret)
}
