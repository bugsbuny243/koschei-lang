fn main() {
    let values = [-3, 2, 0, 5, -1]
    let mut negative: List<Int> = []
    let mut non_negative: List<Int> = []
    for value in values {
        if value < 0 { negative = negative.push(value) }
        else { non_negative = non_negative.push(value) }
    }
    println(negative)
    println(non_negative)
}
