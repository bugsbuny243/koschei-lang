fn countdown(value: Int) -> Int {
    if value == 0 {
        return 0
    }
    return countdown(value - 1)
}

fn main() {
    let mut value = 3
    while value > 0 {
        value = value - 1
    }
    println("resource contract ready")
}
