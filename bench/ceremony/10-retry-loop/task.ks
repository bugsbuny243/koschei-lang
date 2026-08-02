fn main() {
    let mut attempt = 0
    let mut success = false
    while attempt < 3 {
        attempt = attempt + 1
        if attempt == 2 { success = true break }
        println("retry {attempt}")
    }
    println("success: {success}")
}
