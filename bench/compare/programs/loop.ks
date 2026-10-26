fn main() {
    let mut total = 0
    let mut i = 0
    while i < 300000 {
        total = total + i * i % 7
        i = i + 1
    }
    println(total)
}
