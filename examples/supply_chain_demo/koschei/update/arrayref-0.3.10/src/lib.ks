// The compromised release. Reading the key needs the capabilities in the
// signature, so the update widens the package's surface to disk and net.
fn checked_index(length: Int, index: Int, disk: DiskCaps, net: NetCaps) -> Bool {
    return index >= 0 && index < length
}
