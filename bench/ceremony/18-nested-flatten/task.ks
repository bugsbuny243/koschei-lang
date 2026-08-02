fn main() {
    let groups: List<List<Int>> = [[1, 2], [3], [4, 5]]
    let mut flat: List<Int> = []
    for group in groups {
        for value in group {
            flat = flat.push(value)
        }
    }
    println(flat)
}
