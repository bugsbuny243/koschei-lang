// The attacker's next try: ask for the capabilities in the signature. The
// application never passes them, so the call does not compile either, and
// passing them would be a visible change in main and in `ks caps`.
fn checked_index(length: Int, index: Int, disk: DiskCaps, net: NetCaps) -> Bool {
    return index >= 0 && index < length
}
