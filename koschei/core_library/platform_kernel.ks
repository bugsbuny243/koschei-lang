// Koschei Core Library: platform_kernel
// Pure bounded frame ledger preflight. No hardware/CR3/UEFI access.
fn frame_in_pool(base: Int, pages: Int, frame: Int) -> Bool {
    if base < 1048576 || base >= 1073741824 ||
       base % 4096 != 0 || pages < 1 || pages > 512 ||
       pages > (1073741824 - base) / 4096 ||
       frame < base || frame >= 1073741824 ||
       frame % 4096 != 0 {
        return false
    }
    return frame - base < pages * 4096
}
fn claimed_frame(base: Int, pages: Int, claimed: List<Int>, frame: Int) -> Bool {
    if !frame_in_pool(base, pages, frame) ||
       claimed.length() > pages || !claimed.contains(frame) {
        return false
    }
    let mut seen: List<Int> = []
    for current in claimed {
        if !frame_in_pool(base, pages, current) || seen.contains(current) {
            return false
        }
        seen = seen.push(current)
    }
    return true
}
fn disjoint(first: Int, first_pages: Int, second: Int, second_pages: Int) -> Bool {
    if !frame_in_pool(first, first_pages, first) ||
       !frame_in_pool(second, second_pages, second) {
        return false
    }
    let first_end = first + first_pages * 4096
    let second_end = second + second_pages * 4096
    return first_end <= second || second_end <= first
}
