fn main() {
    let left = ["alpha", "beta", "gamma"]
    let right = ["alpha", "BETA", "gamma"]
    match left.first_difference(right) {
        Some(index) => println("difference at {index}"),
        None => {},
    }
}
