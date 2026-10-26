fn main() {
    let mut parts: List<String> = []
    let mut i = 0
    while i < 3000 {
        parts = parts.push("item{i}")
        i = i + 1
    }
    let joined = ",".join(parts) or ""
    let back = joined.split(",") or parts
    println("{joined.length()} {back.length()}")
}
