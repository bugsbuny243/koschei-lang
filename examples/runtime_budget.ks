fn descend(value: Int) -> Int {
    if value == 0 {
        return 0
    }
    return descend(value - 1)
}

fn main() {
    let mut value = 4
    while value > 0 {
        value = value - 1
    }
    println(descend(4))
    println("runtime budget ready")
}
