fn main() {
    let left = ["alpha", "beta", "gamma"]
    let right = ["alpha", "BETA", "gamma"]
    let mut index = 0
    while index < left.length() && index < right.length() {
        let a = left.get(index) or ""
        let b = right.get(index) or ""
        if a != b { println("difference at {index}") break }
        index = index + 1
    }
}
