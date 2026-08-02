fn main() {
    let groups: List<List<Int>> = [[1, 2], [3], [4, 5]]
    let mut flat: List<Int> = []
    let mut index = 0
    while index < groups.length() {
        let group: List<Int> = groups.get(index) or []
        for value in group {
            flat = flat.push(value)
        }
        index = index + 1
    }
    println(flat)
}
