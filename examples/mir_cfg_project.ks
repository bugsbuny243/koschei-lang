fn classify(limit: Int) -> String {
    let mut count = 0
    while count < limit {
        count = count + 1
    }
    if count > 2 {
        return "large"
    }
    return "small"
}

fn main() {
    println(classify(4))
}
